"""Routines: things Gota does by itself at a time of day (check the backups every morning, summarise the logs on Mondays...).
They run the agent unattended and READ-ONLY: anything that would change the computer is refused, because nobody is there to approve it."""
import threading, time
from datetime import datetime

REPEATS = ("daily", "weekdays", "weekly", "hourly")


class Routines:
    def __init__(self, settings, run, notify):
        self.settings, self.run, self.notify = settings, run, notify   # run(goal, on_done): starts an unattended background task
        self._stop = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def items(self):
        return list(self.settings.get("routines") or [])

    def _save(self, items):
        self.settings.set("routines", items)

    def add(self, name, goal, when="08:00", repeat="daily"):
        items = self.items()
        r = {"id": max([i["id"] for i in items] + [0]) + 1, "name": name, "goal": goal, "when": when, "repeat": repeat if repeat in REPEATS else "daily", "last": 0}
        self._save(items + [r])
        return r

    def delete(self, rid):
        self._save([i for i in self.items() if i["id"] != rid])

    @staticmethod
    def due(r, now):
        """True when the routine's time has come today (or this hour) and it has not run since."""
        hh, mm = (int(x) for x in r["when"].split(":"))
        last = datetime.fromtimestamp(r["last"]) if r.get("last") else None
        if r["repeat"] == "hourly":
            return now.minute >= mm and (last is None or (now - last).total_seconds() > 3300)
        if r["repeat"] == "weekdays" and now.weekday() >= 5:
            return False
        if r["repeat"] == "weekly" and last is not None and (now - last).days < 6:
            return False
        scheduled = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        return now >= scheduled and (last is None or last < scheduled) and (now - scheduled).total_seconds() < 6 * 3600   # not a day-old miss

    def _loop(self):
        while not self._stop.wait(30):
            try:
                now = datetime.now()
                for r in self.items():
                    if self.due(r, now):
                        self._mark(r["id"])
                        self.fire(r)
            except Exception:
                pass

    def _mark(self, rid):
        items = self.items()
        for i in items:
            if i["id"] == rid:
                i["last"] = time.time()
        self._save(items)

    def fire(self, r):
        def done(task):
            self.notify(f"Rotina: {r['name']}", str(task.get("result", ""))[:300])
        self.run(r["goal"], done)

    def stop(self):
        self._stop.set()