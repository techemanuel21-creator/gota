"""The Gota window: first-run setup, chats, voice, calls, nicknames for programs, tray icon."""
import os, shutil, threading, time, tkinter as tk, uuid, winsound
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

from PIL import Image, ImageTk

from . import brain as brain_mod, imagegen, llm, store, tools, voice
from .overlay import CatOverlay
from .widgets import (ACCENT, BG, FONT, GREEN, KEY, MUTED, PRIMARY, RED, SURFACE, SURFACE2, TEXT, CatView, bubble, button, sprites)

HOTKEY_DEFAULT = "ctrl+alt+g"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gota Local Assistant")
        self.geometry("1020x720")
        self.minsize(760, 520)
        self.configure(bg=BG)
        try:
            self.iconphoto(True, sprites().frame("logo", 64))
        except Exception:
            pass
        self.profile, self.settings, self.chats = store.Profile(), store.Settings(), store.Chats()
        self.images = imagegen.ImageGen()
        self.gemma = None
        self.speaker = None
        self.listener = voice.Listener()
        self.overlay = CatOverlay(self)
        self.busy = False          # a voice conversation is running
        self.dictating = False
        self.pending_image = None
        self.call = None
        self.wake_stop = threading.Event()
        self.brain = brain_mod.Brain(self.profile, self.settings, lambda: self.gemma, self.images, self._status, self._notify)
        self.tray = None
        self.hotkey = None
        self.protocol("WM_DELETE_WINDOW", self.to_tray)
        self.ui_queue = []
        self.show_boot()

    # ------------------------------------------------------------------ small helpers
    def ui(self, fn, *a):
        """Run something on the window's thread from any thread."""
        try:
            self.after(0, lambda: fn(*a))
        except Exception:
            pass

    def clear(self):
        for w in self.winfo_children():
            if w is not self.overlay.win:
                w.destroy()

    def _status(self, text):
        self.ui(self._set_status, text)

    def _set_status(self, text):
        if getattr(self, "status_label", None) and self.status_label.winfo_exists():
            self.status_label.configure(text=text)
        if self.overlay.visible and getattr(self, "voice_question", None):
            self.overlay.set(f"“{self.voice_question}”\n\n{text}")

    # ------------------------------------------------------------------ boot: name → model → chat
    def show_boot(self):
        self.clear()
        if not self.profile.is_set:
            return self.show_name()
        path = self.model_path()
        if path is None:
            return self.show_download()
        if self.gemma is None:
            return self.show_loading(path)
        self.show_chat()

    def model_path(self):
        for cand in (self.settings.get("model_path"), str(llm.MODEL_FILE)):
            if cand and Path(cand).exists() and Path(cand).stat().st_size > 2_000_000_000:
                return Path(cand)
        return None

    def card(self, icon, title, text):
        outer = tk.Frame(self, bg=BG)
        outer.pack(expand=True)
        box = tk.Frame(outer, bg=SURFACE, padx=40, pady=30)
        box.pack()
        cat = CatView(box, size=120, bg=SURFACE)
        cat.pack()
        tk.Label(box, text=title, bg=SURFACE, fg=TEXT, font=("Segoe UI", 18, "bold")).pack(pady=(10, 4))
        tk.Label(box, text=text, bg=SURFACE, fg=MUTED, font=FONT, wraplength=420, justify="center").pack()
        return box

    def show_name(self):
        box = self.card("🎩", "Prazer, eu sou o Gota", "Seu mordomo pessoal. Como devo chamá-lo?")
        name = tk.Entry(box, bg=SURFACE2, fg=TEXT, insertbackground=TEXT, relief="flat", font=("Segoe UI", 13), justify="center")
        name.pack(fill="x", pady=(18, 8), ipady=8)
        name.focus_set()
        treat = tk.StringVar(value="senhor")
        row = tk.Frame(box, bg=SURFACE)
        row.pack()
        for label, val in (("Senhor", "senhor"), ("Senhora", "senhora"), ("Só o nome", "")):
            tk.Radiobutton(row, text=label, value=val, variable=treat, bg=SURFACE, fg=TEXT, selectcolor=SURFACE2,
                           activebackground=SURFACE, activeforeground=TEXT, font=FONT).pack(side="left", padx=6)

        def go(_=None):
            if not name.get().strip():
                return
            self.profile.set_name(name.get(), treat.get())
            self.show_boot()
        button(box, "Continuar", go).pack(pady=(16, 0))
        name.bind("<Return>", go)

    def show_download(self):
        box = self.card("🧠", "Preparando o Gota",
                        f"Baixando a inteligência do Gota (~{llm.MODEL_MB / 1000:.1f} GB, uma vez só). Depois disso ela roda no próprio computador, mesmo sem internet.")
        bar = tk.Canvas(box, width=420, height=10, bg=SURFACE2, highlightthickness=0)
        bar.pack(pady=(18, 4))
        fill = bar.create_rectangle(0, 0, 0, 10, fill=ACCENT, width=0)
        label = tk.Label(box, text="Começando...", bg=SURFACE, fg=MUTED, font=("Segoe UI", 10))
        label.pack()

        def progress(pct, done, total):
            self.ui(lambda: (bar.coords(fill, 0, 0, 4.2 * pct, 10), label.configure(text=f"Baixando... {done} MB de {total} MB")))

        def work():
            try:
                llm.download_model(llm.MODEL_FILE, progress)
                self.ui(self.show_boot)
            except Exception as e:
                self.ui(lambda: label.configure(text=f"Não consegui baixar: {e}. Verifique a internet e tente de novo."))
                self.ui(lambda: button(box, "Tentar de novo", self.show_boot).pack(pady=8))
        threading.Thread(target=work, daemon=True).start()

        def pick():
            f = filedialog.askopenfilename(title="Escolha o arquivo do modelo (.litertlm)", filetypes=[("Modelo", "*.litertlm")])
            if f:
                self.settings.set("model_path", f)
                self.show_boot()
        tk.Button(box, text="Já tenho o arquivo do modelo…", command=pick, bg=SURFACE, fg=MUTED, relief="flat", bd=0, cursor="hand2").pack(pady=(12, 0))

    def show_loading(self, path):
        self.card("🧠", "Acordando o Gota", "Carregando a inteligência… leva alguns segundos.")

        def work():
            try:
                self.gemma = llm.Gemma(path)
                self.ui(self.show_boot)
            except Exception as e:
                self.ui(lambda: messagebox.showerror("Gota", f"Não consegui carregar o modelo:\n{e}"))
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------ the chat screen
    def show_chat(self):
        self.clear()
        self.sidebar = tk.Frame(self, bg=SURFACE, width=250)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        main = tk.Frame(self, bg=BG)
        main.pack(side="left", fill="both", expand=True)

        head = tk.Frame(main, bg=BG)
        head.pack(fill="x", padx=16, pady=(14, 6))
        CatView(head, size=44, bg=BG).pack(side="left")
        titles = tk.Frame(head, bg=BG)
        titles.pack(side="left", padx=10)
        tk.Label(titles, text="Gota", bg=BG, fg=TEXT, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        self.title_label = tk.Label(titles, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.title_label.pack(anchor="w")
        button(head, "📞  Ligar", self.start_call, bg=GREEN).pack(side="right")
        button(head, "🎙  Chamar", self.summon, bg=SURFACE2).pack(side="right", padx=8)

        self.scroll = tk.Canvas(main, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(main, command=self.scroll.yview)
        self.scroll.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.scroll.pack(fill="both", expand=True, padx=(16, 0))
        self.msgs = tk.Frame(self.scroll, bg=BG)
        win = self.scroll.create_window((0, 0), window=self.msgs, anchor="nw")
        self.msgs.bind("<Configure>", lambda e: self.scroll.configure(scrollregion=self.scroll.bbox("all")))
        self.scroll.bind("<Configure>", lambda e: self.scroll.itemconfigure(win, width=e.width))
        self.bind_all("<MouseWheel>", lambda e: self.scroll.yview_scroll(int(-e.delta / 120), "units"))

        self.attach_row = tk.Frame(main, bg=BG)
        self.attach_row.pack(fill="x", padx=16)
        bar = tk.Frame(main, bg=BG)
        bar.pack(fill="x", padx=16, pady=(6, 14))
        tk.Button(bar, text="📎", command=self.attach, bg=BG, fg=TEXT, relief="flat", bd=0, font=("Segoe UI", 14), cursor="hand2").pack(side="left")
        self.entry = tk.Text(bar, height=1, bg=SURFACE2, fg=TEXT, insertbackground=TEXT, relief="flat", font=("Segoe UI", 12), wrap="word", padx=12, pady=9)
        self.entry.pack(side="left", fill="x", expand=True, padx=6)
        self.entry.bind("<Return>", lambda e: (self.send(), "break")[1])
        self.entry.bind("<Shift-Return>", lambda e: None)
        self.entry.bind("<KeyRelease>", lambda e: self.entry.configure(height=min(5, int(self.entry.index("end-1c").split(".")[0]))))
        self.mic = tk.Button(bar, text="🎤", command=self.toggle_dictation, bg=SURFACE2, fg=TEXT, relief="flat", bd=0, font=("Segoe UI", 13), width=3, cursor="hand2")
        self.mic.pack(side="left")
        button(bar, "➤", self.send, font=("Segoe UI", 13)).pack(side="left", padx=(6, 0))
        self.entry.focus_set()

        self.build_sidebar()
        cur = self.settings.get("current_chat")
        if not cur or not self.chats.get(cur):
            normal = [c for c in self.chats.list() if c["id"] != store.VOICE_CHAT]
            cur = normal[0]["id"] if normal else self.chats.create()["id"]
            self.settings.set("current_chat", cur)
        self.open_chat(cur)
        self.setup_background()
        if not self.settings.get("tutorial"):
            self.after(600, self.tutorial)

    def build_sidebar(self):
        for w in self.sidebar.winfo_children():
            w.destroy()
        tk.Label(self.sidebar, text="Conversas", bg=SURFACE, fg=TEXT, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=16, pady=(16, 6))
        button(self.sidebar, "+ Nova conversa", self.new_chat).pack(fill="x", padx=14, pady=(0, 8))
        box = tk.Frame(self.sidebar, bg=SURFACE)
        box.pack(fill="both", expand=True, padx=8)
        cur = self.settings.get("current_chat")
        for c in (self.chats.list() or [self.chats.voice()]):
            title = ("🎙 " if c["id"] == store.VOICE_CHAT else "") + c["title"]
            row = tk.Label(box, text=title, anchor="w", bg=SURFACE2 if c["id"] == cur else SURFACE, fg=TEXT, font=("Segoe UI", 10), padx=10, pady=7, cursor="hand2")
            row.pack(fill="x", pady=1)
            row.bind("<Button-1>", lambda e, cid=c["id"]: self.open_chat(cid))
            row.bind("<Button-3>", lambda e, cid=c["id"], t=c["title"]: self.chat_menu(e, cid, t))
        foot = tk.Frame(self.sidebar, bg=SURFACE)
        foot.pack(fill="x", padx=14, pady=10)
        self.hey_var = tk.BooleanVar(value=bool(self.settings.get("hey_gota")))
        tk.Checkbutton(foot, text='Escutar "Hey Gota"\n(microfone sempre ligado)', variable=self.hey_var, command=self.toggle_hey, bg=SURFACE, fg=TEXT,
                       selectcolor=SURFACE2, activebackground=SURFACE, activeforeground=TEXT, justify="left", font=("Segoe UI", 9)).pack(anchor="w")
        for text, cmd in (("🏷  Apelidos de programas", self.aliases_dialog), ("🎩  Meu nome e tratamento", self.edit_name), ("❓  Como me chamar", self.tutorial)):
            tk.Button(foot, text=text, command=cmd, bg=SURFACE, fg=TEXT, relief="flat", bd=0, anchor="w", font=("Segoe UI", 10), cursor="hand2").pack(fill="x", pady=2)

    def chat_menu(self, event, cid, title):
        m = tk.Menu(self, tearoff=0)
        m.add_command(label="Apagar conversa", command=lambda: self.delete_chat(cid, title))
        m.tk_popup(event.x_root, event.y_root)

    def delete_chat(self, cid, title):
        if messagebox.askyesno("Apagar conversa", f"Apagar \"{title}\"?"):
            self.chats.delete(cid)
            if self.settings.get("current_chat") == cid:
                self.settings.set("current_chat", "")
                self.show_chat()
            else:
                self.build_sidebar()

    def new_chat(self):
        c = self.chats.create()
        self.open_chat(c["id"])

    def open_chat(self, cid):
        self.settings.set("current_chat", cid)
        self.clear_attachment()
        chat = self.chats.get(cid) or self.chats.create()
        self.title_label.configure(text=("🎙 " if cid == store.VOICE_CHAT else "") + chat["title"])
        for w in self.msgs.winfo_children():
            w.destroy()
        if not chat["messages"]:
            now = datetime.now()
            salute = "Bom dia" if 5 <= now.hour < 12 else "Boa tarde" if now.hour < 18 else "Boa noite"
            serve = {"senhora": "servi-la", "": "ajudar"}.get(self.profile.treatment, "servi-lo")
            self.add_message("gota", f"{salute}, {self.profile.address()}. Em que posso {serve}?")
        for m in chat["messages"]:
            self.add_message(m["role"], m["text"], m.get("image"))
        self.build_sidebar()

    def add_message(self, role, text, image=None):
        mine = role == "user"
        if image and Path(image).exists():
            try:
                img = Image.open(image)
                img.thumbnail((360, 360))
                photo = ImageTk.PhotoImage(img)
                row = tk.Frame(self.msgs, bg=BG)
                lab = tk.Label(row, image=photo, bg=SURFACE2, bd=0, cursor="hand2")
                lab.image = photo
                lab.pack(side="right" if mine else "left")
                lab.bind("<Button-1>", lambda e, p=image: os.startfile(p))
                row.pack(fill="x", pady=4, padx=(0, 12))
            except Exception:
                pass
        if text.strip():
            holder, _ = bubble(self.msgs, text, mine, width=max(300, min(560, self.winfo_width() - 420)))
            holder.pack(fill="x", pady=4, padx=(0, 12))
        self.after(50, lambda: self.scroll.yview_moveto(1.0))

    # ------------------------------------------------------------------ sending
    def send(self):
        text = self.entry.get("1.0", "end").strip()
        image = self.pending_image
        if not text and not image:
            return
        if self.dictating:
            self.toggle_dictation()
        self.entry.delete("1.0", "end")
        self.entry.configure(height=1)
        self.clear_attachment(delete=False)
        cid = self.settings.get("current_chat")
        history = [("user" if m["role"] == "user" else "model", m["text"]) for m in self.chats.get(cid)["messages"]]
        self.chats.append(cid, "user", text, image)
        if not history:
            for w in self.msgs.winfo_children():
                w.destroy()
        self.add_message("user", text, image)
        self.title_label.configure(text=self.chats.get(cid)["title"])
        self.build_sidebar()
        self.thinking = tk.Frame(self.msgs, bg=SURFACE2)
        self.thinking_cat = CatView(self.thinking, size=44, bg=SURFACE2)
        self.thinking_cat.pack(side="left", padx=6, pady=4)
        self.thinking_cat.play("anim_cat_read")
        self.status_label = tk.Label(self.thinking, text="Pensando...", bg=SURFACE2, fg=MUTED, font=("Segoe UI", 10))
        self.status_label.pack(side="left", padx=(0, 12))
        self.thinking.pack(anchor="w", pady=4)
        self.after(50, lambda: self.scroll.yview_moveto(1.0))

        def phase(p):
            self.ui(lambda: self.thinking_cat.winfo_exists() and self.thinking_cat.play("anim_cat_paint" if p == "drawing" else "anim_cat_read"))

        def work():
            reply, img = self.brain.run(text, history, cid, image, on_phase=phase)
            self.chats.append(cid, "gota", reply, img)

            def done():
                if self.thinking.winfo_exists():
                    self.thinking.destroy()
                if self.settings.get("current_chat") == cid:
                    self.add_message("gota", reply, img)
            self.ui(done)
        threading.Thread(target=work, daemon=True).start()

    def attach(self):
        f = filedialog.askopenfilename(title="Anexar imagem", filetypes=[("Imagens", "*.png *.jpg *.jpeg *.webp *.bmp")])
        if not f:
            return
        folder = store.ROOT / "attachments"
        folder.mkdir(exist_ok=True)
        img = Image.open(f).convert("RGB")
        img.thumbnail((1024, 1024))
        dest = folder / f"{uuid.uuid4().hex}.jpg"
        img.save(dest, quality=85)
        self.clear_attachment()
        self.pending_image = str(dest)
        thumb = img.copy()
        thumb.thumbnail((56, 56))
        photo = ImageTk.PhotoImage(thumb)
        lab = tk.Label(self.attach_row, image=photo, bg=BG)
        lab.image = photo
        lab.pack(side="left")
        tk.Button(self.attach_row, text="✕ remover imagem", command=self.clear_attachment, bg=BG, fg=MUTED, relief="flat", bd=0, cursor="hand2").pack(side="left", padx=8)

    def clear_attachment(self, delete=True):
        if delete and self.pending_image:
            Path(self.pending_image).unlink(missing_ok=True)
        self.pending_image = None
        if getattr(self, "attach_row", None) and self.attach_row.winfo_exists():
            for w in self.attach_row.winfo_children():
                w.destroy()

    # ------------------------------------------------------------------ voice pieces
    def get_speaker(self):
        if self.speaker is None:
            self.speaker = voice.Speaker()
        return self.speaker

    def toggle_dictation(self):
        if self.dictating:
            self.dictating = False
            self.listener.cancel.set()
            self.mic.configure(bg=SURFACE2)
            return
        self.dictating = True
        self.mic.configure(bg=RED)
        base = self.entry.get("1.0", "end").strip()

        def work():
            text = base
            try:
                while self.dictating:
                    heard = self.listener.listen(lambda p: self.ui(lambda: self._dictate(text, p)), silence=1.0, timeout=60)
                    if heard:
                        text = (text + " " + heard).strip()
                        self.ui(lambda t=text: self._dictate(t, ""))
            except Exception as e:
                self.ui(lambda: messagebox.showerror("Microfone", f"Não consegui usar o microfone:\n{e}"))
            self.ui(lambda: (setattr(self, "dictating", False), self.mic.configure(bg=SURFACE2)))
        threading.Thread(target=work, daemon=True).start()

    def _dictate(self, base, partial):
        self.entry.delete("1.0", "end")
        self.entry.insert("1.0", (base + " " + partial).strip())

    def summon(self):
        """Calls Gota: the cat slides up over whatever is on screen, listens, answers aloud, slides down."""
        if self.busy or self.gemma is None:
            return
        self.busy = True
        self.voice_question = None
        self.overlay.show(f"Pois não, {self.profile.sir()}?", "anim_cat_listen")
        try:
            winsound.Beep(880, 120)
        except Exception:
            pass
        threading.Thread(target=self._voice_turn, daemon=True).start()

    def _voice_turn(self):
        sp = self.get_speaker()
        try:
            heard = self.listener.listen(lambda p: self.ui(lambda: self.overlay.set(f"“{p}”")), silence=1.3, timeout=8)
        except Exception as e:
            self.ui(lambda: self.overlay.set(f"Perdão, não consegui usar o microfone: {e}", "anim_cat_idle"))
            self.ui(self.overlay.hide_later, 4000)
            self.busy = False
            return
        if not heard:
            self.ui(lambda: self.overlay.set("Perdão, não ouvi. É só me chamar de novo.", "anim_cat_idle"))
            self.ui(self.overlay.hide_later, 1800)
            self.busy = False
            return
        text = brain_mod.strip_wake_word(heard)
        self.voice_question = text
        vchat = self.chats.voice()
        history = [("user" if m["role"] == "user" else "model", m["text"]) for m in vchat["messages"]]
        self.chats.append(store.VOICE_CHAT, "user", text)
        self.ui(lambda: self.overlay.set(f"“{text}”", "anim_cat_read"))

        def phase(p):
            if p == "searching":
                sp.speak(f"Um momento, {self.profile.sir()}. Vou pesquisar.")
            self.ui(lambda: self.overlay.cat.play("anim_cat_paint" if p == "drawing" else "anim_cat_read") if self.overlay.visible else None)
        reply, img = self.brain.run(text, history, store.VOICE_CHAT, spoken=True, on_phase=phase)
        self.chats.append(store.VOICE_CHAT, "gota", reply, img)
        self.voice_question = None

        def done():
            self.ui(lambda: self.overlay.cat.play("anim_cat_idle") if self.overlay.visible else None)
            self.ui(self.overlay.hide_later, 700)
            self.busy = False
            if self.settings.get("current_chat") == store.VOICE_CHAT:
                self.ui(lambda: self.open_chat(store.VOICE_CHAT))
        self.ui(lambda: self.overlay.set(reply, "anim_cat_talk"))
        sp.speak(reply, done)

    # ------------------------------------------------------------------ calls
    def start_call(self):
        if self.call is not None or self.gemma is None:
            return
        self.call = CallWindow(self)

    # ------------------------------------------------------------------ hotkey, "Hey Gota", tray
    def setup_background(self):
        if self.hotkey is None:
            try:
                self.hotkey = voice.Hotkey(self.settings.get("hotkey") or HOTKEY_DEFAULT, lambda: self.ui(self.summon))
                if not self.hotkey.registered:
                    messagebox.showwarning("Gota", "Outro programa já usa o atalho Ctrl+Alt+G. Use o botão \"Chamar\" ou o \"Hey Gota\".")
            except Exception:
                pass
        if self.tray is None:
            self.make_tray()
        if self.settings.get("hey_gota"):
            self.start_wake()

    def toggle_hey(self):
        self.settings.set("hey_gota", self.hey_var.get())
        if self.hey_var.get():
            self.start_wake()
        else:
            self.wake_stop.set()

    def start_wake(self):
        self.wake_stop = threading.Event()
        stop = self.wake_stop

        def loop():
            try:
                self.listener.preload()
                while not stop.is_set():
                    if self.busy or self.call or self.dictating:
                        time.sleep(0.5)
                        continue
                    if self.listener.wait_for_wake_word(stop):
                        self.ui(self.summon)
                        time.sleep(1.0)
            except Exception:
                pass
        threading.Thread(target=loop, daemon=True).start()

    def make_tray(self):
        try:
            import pystray
            img = Image.open(sprites().dir / "logo.png").convert("RGBA").resize((64, 64), Image.NEAREST)
            menu = pystray.Menu(pystray.MenuItem("Abrir o Gota", lambda: self.ui(self.show_window), default=True),
                                pystray.MenuItem("Chamar agora", lambda: self.ui(self.summon)),
                                pystray.MenuItem("Sair", lambda: self.ui(self.quit_app)))
            self.tray = pystray.Icon("Gota", img, "Gota — Ctrl+Alt+G para chamar", menu)
            self.tray.run_detached()
        except Exception:
            self.tray = False

    def to_tray(self):
        if self.tray:
            self.withdraw()
        else:
            self.quit_app()

    def show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def quit_app(self):
        self.wake_stop.set()
        try:
            self.hotkey and self.hotkey.stop()
            self.tray and self.tray.stop()
        except Exception:
            pass
        os._exit(0)

    # ------------------------------------------------------------------ timers / alarms
    def _notify(self, label):
        def show():
            if label.startswith("__clipboard__:"):
                self.clipboard_clear()
                self.clipboard_append(label.split(":", 1)[1])
                return
            try:
                winsound.Beep(1000, 300)
                winsound.Beep(1300, 300)
            except Exception:
                pass
            self.overlay.show(f"{self.profile.sir().capitalize()}, é a hora: {label}.", "anim_cat_talk")
            self.get_speaker().speak(f"{self.profile.sir().capitalize()}, é a hora: {label}.")
            self.overlay.hide_later(8000)
        self.ui(show)

    # ------------------------------------------------------------------ dialogs
    def edit_name(self):
        name = simpledialog.askstring("Gota", "Como devo chamá-lo?", initialvalue=self.profile.name, parent=self)
        if name and name.strip():
            t = messagebox.askyesno("Tratamento", "Chamar de \"senhor\"?\n\nSim = senhor   Não = senhora")
            self.profile.set_name(name, "senhor" if t else "senhora")
            self.build_sidebar()

    def aliases_dialog(self):
        win = tk.Toplevel(self)
        win.title("Apelidos de programas")
        win.configure(bg=BG)
        win.geometry("520x560")
        tk.Label(win, text='Dê apelidos aos seus programas. Ex.: "whats 2" abre o WhatsApp que você escolher.', bg=BG, fg=MUTED, wraplength=480).pack(pady=8)
        q = tk.StringVar()
        tk.Entry(win, textvariable=q, bg=SURFACE2, fg=TEXT, insertbackground=TEXT, relief="flat", font=FONT).pack(fill="x", padx=14, ipady=6)
        listbox = tk.Listbox(win, bg=SURFACE, fg=TEXT, selectbackground=PRIMARY, relief="flat", font=FONT, activestyle="none")
        listbox.pack(fill="both", expand=True, padx=14, pady=10)
        aliases = self.settings.get("aliases")
        shown = []

        def refresh(*_):
            listbox.delete(0, "end")
            shown.clear()
            for name, _t in tools.installed_apps():
                if tools.norm(q.get()) in tools.norm(name):
                    nick = next((k for k, v in aliases.items() if v == name), "")
                    shown.append(name)
                    listbox.insert("end", f"{name}" + (f"   🏷 {nick}" if nick else ""))
        q.trace_add("write", refresh)
        refresh()

        def edit(_=None):
            sel = listbox.curselection()
            if not sel:
                return
            name = shown[sel[0]]
            old = next((k for k, v in aliases.items() if v == name), "")
            nick = simpledialog.askstring("Apelido", f"Apelido para {name} (vazio remove):", initialvalue=old, parent=win)
            if nick is None:
                return
            aliases.pop(old, None)
            if nick.strip():
                aliases[nick.strip().lower()] = name
            self.settings.set("aliases", aliases)
            refresh()
        listbox.bind("<Double-Button-1>", edit)
        button(win, "Dar apelido ao selecionado", edit).pack(pady=(0, 12))

    def tutorial(self):
        self.settings.set("tutorial", True)
        win = tk.Toplevel(self)
        win.title("Como me chamar")
        win.configure(bg=SURFACE)
        win.geometry("520x470")
        win.transient(self)
        CatView(win, size=130, bg=SURFACE).pack(pady=(18, 0))
        tk.Label(win, text="Me chame de qualquer programa", bg=SURFACE, fg=TEXT, font=("Segoe UI", 16, "bold")).pack(pady=(8, 4))
        k = tk.Frame(win, bg=SURFACE)
        k.pack(pady=6)
        for i, key in enumerate(("Ctrl", "Alt", "G")):
            if i:
                tk.Label(k, text="+", bg=SURFACE, fg=MUTED, font=("Segoe UI", 14)).pack(side="left", padx=4)
            tk.Label(k, text=key, bg=SURFACE2, fg=TEXT, font=("Segoe UI", 14, "bold"), padx=14, pady=6).pack(side="left")
        tk.Label(win, text="O gatinho sobe na tela, ouve sua pergunta, responde em voz alta e desce.\n\n"
                           "Ele também fica ao lado do relógio (ícone perto da hora): clique com o botão direito para chamar ou sair. "
                           'Se preferir, ative "Hey Gota" no menu da esquerda.', bg=SURFACE, fg=MUTED, font=FONT, wraplength=440, justify="center").pack(pady=10)
        button(win, "Entendi", win.destroy).pack()


class CallWindow(tk.Toplevel):
    """A phone call with Gota: he answers, listens, thinks, speaks, listens again — until you hang up."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Ligação com o Gota")
        self.configure(bg="#141833")
        self.geometry("420x640")
        self.resizable(False, False)
        self.chat_id = app.chats.create("📞 Ligação · " + datetime.now().strftime("%d/%m %H:%M"))["id"]
        self.sir = app.profile.sir()
        self.ended = False
        self.muted = False
        self.silent = 0
        self.speaker = app.get_speaker()
        tk.Label(self, text="Gota", bg=self["bg"], fg=TEXT, font=("Segoe UI", 24, "bold")).pack(pady=(26, 0))
        self.status = tk.Label(self, text="Chamando…", bg=self["bg"], fg=MUTED, font=("Segoe UI", 12))
        self.status.pack()
        self.cat = CatView(self, size=240, bg=self["bg"])
        self.cat.pack(pady=18)
        self.cat.play("anim_phone_idle")
        self.caption = tk.Label(self, text="", bg=self["bg"], fg=TEXT, font=("Segoe UI", 13), wraplength=370, height=6, justify="center")
        self.caption.pack()
        row = tk.Frame(self, bg=self["bg"])
        row.pack(side="bottom", pady=30)
        self.mute_btn = tk.Button(row, text="🎙  Mudo", command=self.toggle_mute, bg=SURFACE2, fg=TEXT, relief="flat", font=FONT, padx=18, pady=12, cursor="hand2")
        self.mute_btn.pack(side="left", padx=14)
        tk.Button(row, text="📞  Desligar", command=self.hang_up, bg=RED, fg=TEXT, relief="flat", font=FONT, padx=18, pady=12, cursor="hand2").pack(side="left", padx=14)
        self.protocol("WM_DELETE_WINDOW", self.hang_up)
        self.started = None
        winsound.Beep(440, 400)
        self.after(1300, self.answer)
        threading.Thread(target=self.app.listener.preload, daemon=True).start()

    def answer(self):
        if self.ended:
            return
        self.started = time.time()
        self.tick()
        hello = f"Alô, {self.app.profile.address()}. Às suas ordens."
        self.app.chats.append(self.chat_id, "gota", hello)
        self.say(hello, then=self.loop)

    def tick(self):
        if self.ended:
            return
        s = int(time.time() - self.started)
        self.status.configure(text=f"{s // 60:02d}:{s % 60:02d}" + (" · mudo" if self.muted else ""))
        self.after(1000, self.tick)

    def say(self, text, then=None):
        self.ui(lambda: (self.caption.configure(text=text, fg=TEXT), self.cat.play("anim_phone_talk")))
        self.speaker.speak(text, lambda: then and then())

    def ui(self, fn):
        try:
            self.after(0, fn)
        except Exception:
            pass

    def loop(self):
        """One listening turn; schedules itself again after each answer (runs in a worker thread)."""
        if self.ended:
            return
        threading.Thread(target=self._turn, daemon=True).start()

    def _turn(self):
        while not self.ended and self.muted:
            time.sleep(0.3)
        if self.ended:
            return
        self.ui(lambda: self.cat.play("anim_phone_listen"))
        try:
            heard = self.app.listener.listen(lambda p: self.ui(lambda: self.caption.configure(text=f"“{p}”", fg=ACCENT)), silence=1.3, timeout=10)
        except Exception as e:
            self.say(f"Perdão, {self.sir}, estou com dificuldade para ouvir. Vou desligar.", self.hang_up_threadsafe)
            return
        if self.ended:
            return
        if not heard:
            self.silent += 1
            if self.silent >= 6:
                return self.say(f"Vou desligar, então, {self.sir}. Quando precisar, é só me ligar.", self.hang_up_threadsafe)
            if self.silent == 3:
                return self.say(f"Ainda está aí, {self.sir}?", self.loop)
            return self.loop()
        self.silent = 0
        text = brain_mod.strip_wake_word(heard)
        n = tools.norm(text)
        self.app.chats.append(self.chat_id, "user", text)
        if len(n) < 40 and any(g in n for g in ("tchau", "ate logo", "ate mais", "pode desligar", "desliga", "encerra", "tenho que ir")):
            bye = f"Até logo, {self.sir}. Foi um prazer."
            self.app.chats.append(self.chat_id, "gota", bye)
            return self.say(bye, self.hang_up_threadsafe)
        self.ui(lambda: (self.caption.configure(text=f"“{text}”", fg=ACCENT), self.cat.play("anim_phone_think")))
        history = [("user" if m["role"] == "user" else "model", m["text"]) for m in self.app.chats.get(self.chat_id)["messages"][:-1]]

        def phase(p):
            if p == "searching":
                self.speaker.speak(f"Um momento, {self.sir}. Vou pesquisar.")
            elif p == "drawing":
                self.ui(lambda: self.cat.play("anim_cat_paint"))
        reply, img = self.app.brain.run(text, history, self.chat_id, spoken=True, on_phase=phase)
        self.app.chats.append(self.chat_id, "gota", reply, img)
        if not self.ended:
            self.say(reply, self.loop)

    def toggle_mute(self):
        self.muted = not self.muted
        self.mute_btn.configure(text="🎙  Mudo ligado" if self.muted else "🎙  Mudo", bg=ACCENT if self.muted else SURFACE2, fg=BG if self.muted else TEXT)
        if self.muted:
            self.app.listener.cancel.set()

    def hang_up_threadsafe(self):
        self.ui(self.hang_up)

    def hang_up(self):
        if self.ended:
            return
        self.ended = True
        self.app.listener.cancel.set()
        self.speaker.stop()
        try:
            winsound.Beep(330, 250)
        except Exception:
            pass
        chat = self.app.chats.get(self.chat_id)
        if not chat or not any(m["role"] == "user" for m in chat["messages"]):
            self.app.chats.delete(self.chat_id)
        else:
            self.app.settings.set("current_chat", self.chat_id)
            threading.Thread(target=self._remember, args=(chat,), daemon=True).start()
        self.app.call = None
        self.destroy()
        if getattr(self.app, "msgs", None):
            self.app.show_chat()

    def _remember(self, chat):
        """One sentence about the call, so Gota remembers it later."""
        if self.app.gemma is None:
            return
        transcript = "\n".join(("Dono: " if m["role"] == "user" else "Gota: ") + m["text"][:300] for m in chat["messages"])[-3500:]
        date = datetime.now().strftime("%d/%m")
        try:
            raw = self.app.gemma.one_shot(
                "Você resume ligações entre o Gota (um mordomo) e o dono dele. Em português do Brasil, escreva UMA frase curta (até 30 palavras) "
                f"com os assuntos e fatos importantes da ligação, para o Gota lembrar depois. Comece com \"Em {date}\". Responda só com a frase, sem JSON.", transcript)
            data = brain_mod.Brain.extract_json(raw)
            self.app.profile.add_call_note(((data or {}).get("text") or raw).strip().strip('"'))
        except Exception:
            pass
