"""Outlook inside Gota: you sign in once with your Microsoft account (work, school or personal) and Gota reads your calendar and mail
through Microsoft's own Graph API. Read-only (Mail.Read, Calendars.Read). The login token is kept encrypted for your Windows user."""
import ctypes, json, subprocess, urllib.parse, urllib.request
from ctypes import wintypes
from datetime import datetime, timedelta, timezone
from .store import ROOT

# Microsoft's public "Graph Command Line Tools" client: no app registration needed. Can be replaced in Settings ("outlook_client_id").
DEFAULT_CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
AUTHORITY = "https://login.microsoftonline.com/common"
SCOPES = ["Mail.Read", "Calendars.Read"]
GRAPH = "https://graph.microsoft.com/v1.0"
CACHE_FILE = ROOT / "outlook.cache"


class NotConnected(Exception):
    pass


# ---------------------------------------------------------------------- DPAPI: the token file only opens for this Windows user
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _crypt(data: bytes, protect: bool) -> bytes:
    src = _Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
    out = _Blob()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    if not fn(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("DPAPI")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _local_tz_name():
    try:
        return subprocess.run(["tzutil", "/g"], capture_output=True, text=True, timeout=5, creationflags=0x08000000).stdout.strip() or "UTC"
    except Exception:
        return "UTC"


class Outlook:
    def __init__(self, settings=None):
        self.settings = settings
        self._app = None
        self._cache = None

    # ------------------------------------------------------------------ login
    def _client(self):
        import msal
        if self._app is None:
            self._cache = msal.SerializableTokenCache()
            try:
                self._cache.deserialize(_crypt(CACHE_FILE.read_bytes(), False).decode("utf-8"))
            except Exception:
                pass
            cid = (self.settings.get("outlook_client_id") if self.settings else "") or DEFAULT_CLIENT_ID
            self._app = msal.PublicClientApplication(cid, authority=AUTHORITY, token_cache=self._cache)
        return self._app

    def _save(self):
        if self._cache is not None and self._cache.has_state_changed:
            ROOT.mkdir(parents=True, exist_ok=True)
            CACHE_FILE.write_bytes(_crypt(self._cache.serialize().encode("utf-8"), True))

    def account(self):
        accounts = self._client().get_accounts()
        return accounts[0] if accounts else None

    def connected(self):
        try:
            return self.account() is not None
        except Exception:
            return False

    def who(self):
        a = self.account()
        return (a or {}).get("username", "")

    def begin_login(self):
        """Starts the device sign-in. Returns the flow: show flow['user_code'] and open flow['verification_uri'] for the user."""
        flow = self._client().initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(flow.get("error_description") or "não consegui iniciar o login")
        return flow

    def finish_login(self, flow):
        """Blocks until the user finishes signing in on the Microsoft page (or the code expires). Returns the account's e-mail."""
        result = self._client().acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise RuntimeError(result.get("error_description") or "login não concluído")
        self._save()
        return self.who()

    def disconnect(self):
        self._app = self._cache = None
        try:
            CACHE_FILE.unlink()
        except OSError:
            pass

    def _token(self):
        app = self._client()
        acc = self.account()
        if acc is None:
            raise NotConnected()
        res = app.acquire_token_silent(SCOPES, account=acc)
        if not res or "access_token" not in res:
            raise NotConnected()
        self._save()
        return res["access_token"]

    # ------------------------------------------------------------------ Graph
    def _get(self, path, params=None, prefer_tz=True):
        url = GRAPH + path + ("?" + urllib.parse.urlencode(params, safe="$,/") if params else "")
        headers = {"Authorization": "Bearer " + self._token()}
        if prefer_tz:
            headers["Prefer"] = f'outlook.timezone="{_local_tz_name()}"'
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))

    def agenda(self, days=1, start=None):
        """Events from `start` (default: today 00:00 local) for `days` days: [{title, start, end, where, all_day, online}]."""
        start = start or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=max(1, int(days)))
        data = self._get("/me/calendarView", {"startDateTime": start.strftime("%Y-%m-%dT%H:%M:%S"), "endDateTime": end.strftime("%Y-%m-%dT%H:%M:%S"),
                                              "$orderby": "start/dateTime", "$top": "50", "$select": "subject,start,end,location,isAllDay,isOnlineMeeting,organizer,isCancelled"})
        out = []
        for e in data.get("value", []):
            if e.get("isCancelled"):
                continue
            out.append({"title": e.get("subject") or "(sem título)", "start": e["start"]["dateTime"][:16].replace("T", " "), "end": e["end"]["dateTime"][:16].replace("T", " "),
                        "where": (e.get("location") or {}).get("displayName", ""), "all_day": bool(e.get("isAllDay")), "online": bool(e.get("isOnlineMeeting")),
                        "organizer": ((e.get("organizer") or {}).get("emailAddress") or {}).get("name", "")})
        return out

    def emails(self, top=25, unread_only=False, days=14):
        """Recent inbox mail, newest first, each marked with `answered` (you already replied in that conversation)."""
        since = (datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))).strftime("%Y-%m-%dT%H:%M:%SZ")
        flt = f"receivedDateTime ge {since}" + (" and isRead eq false" if unread_only else "")
        data = self._get("/me/mailFolders/inbox/messages", {"$top": str(min(50, int(top))), "$orderby": "receivedDateTime desc", "$filter": flt,
                                                            "$select": "subject,from,receivedDateTime,isRead,importance,flag,bodyPreview,hasAttachments,conversationId"}, prefer_tz=False)
        replied = {}
        try:
            sent = self._get("/me/mailFolders/sentitems/messages", {"$top": "50", "$orderby": "sentDateTime desc", "$select": "conversationId,sentDateTime"}, prefer_tz=False)
            for m in sent.get("value", []):
                replied[m.get("conversationId")] = max(replied.get(m.get("conversationId"), ""), m.get("sentDateTime", ""))
        except Exception:
            pass
        out = []
        for m in data.get("value", []):
            sender = ((m.get("from") or {}).get("emailAddress") or {})
            got = m.get("receivedDateTime", "")
            out.append({"from": f"{sender.get('name', '')} <{sender.get('address', '')}>".strip(), "subject": m.get("subject") or "(sem assunto)", "received": got[:16].replace("T", " "),
                        "unread": not m.get("isRead"), "importance": m.get("importance", "normal"), "flagged": (m.get("flag") or {}).get("flagStatus") == "flagged",
                        "attachments": bool(m.get("hasAttachments")), "preview": " ".join((m.get("bodyPreview") or "").split())[:240],
                        "answered": replied.get(m.get("conversationId"), "") > got})
        return out
