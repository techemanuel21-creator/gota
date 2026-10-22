"""The Gota window: first-run setup, chats, voice, calls (as a pop-up), agent confirmations, knowledge base, tray icon."""
import webbrowser
import json, os, re, threading, time, tkinter as tk, uuid, winsound
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

from . import routines as routines_mod, memory as memory_mod, agent as agent_mod, cloud as cloud_mod, brain as brain_mod, chrome, imagegen, kb, llm, projects as projects_mod, server as server_mod, skills as skills_mod, store, tools, voice, vscode as vscode_mod
from . import widgets as widgets_mod
from .overlay import CatOverlay
from .widgets import (ACCENT, BG, BORDER, COLORS, FONT, GREEN, GREEN_HOVER, HOVER, MUTED, PRIMARY, PRIMARY_HOVER, RED, SURFACE, SURFACE2, TEXT,
                      CatView, ChatInput, PillEntry, RoundButton, Toggle, bubble, lerp, rounded, sprites)

HOTKEY_DEFAULT = "ctrl+alt+g"
CALL_HOTKEY_DEFAULT = "ctrl+alt+l"


class Dialog(tk.Toplevel):
    """A small borderless, rounded window in the app's style."""

    def __init__(self, app, title, width, height):
        super().__init__(app)
        self.app = app
        self.overrideredirect(True)
        self.configure(bg=chrome.Chrome.BORDER)
        self.attributes("-topmost", True)
        app.update_idletasks()
        x = app.winfo_x() + (app.winfo_width() - width) // 2
        y = app.winfo_y() + max(30, (app.winfo_height() - height) // 3)
        ax, ay, aw, ah = chrome.work_area(app)   # stay on the monitor of the main window (coordinates can be negative)
        x = min(max(ax, x), ax + aw - width)
        y = min(max(ay, y), ay + ah - height)
        self.geometry(f"{width}x{height}+{x}+{y}")
        shell = tk.Frame(self, bg=SURFACE)
        shell.pack(fill="both", expand=True, padx=1, pady=1)
        bar = tk.Frame(shell, bg=COLORS["bar"], height=38)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text=title, bg=COLORS["bar"], fg=MUTED, font=("Segoe UI", 10)).pack(side="left", padx=16)
        x_btn = tk.Label(bar, text="✕", bg=COLORS["bar"], fg=TEXT, width=5, cursor="hand2")
        x_btn.pack(side="right", fill="y")
        x_btn.bind("<Enter>", lambda e: x_btn.configure(bg=RED))
        x_btn.bind("<Leave>", lambda e: x_btn.configure(bg=COLORS["bar"]))
        x_btn.bind("<Button-1>", lambda e: self.destroy())
        bar.bind("<ButtonPress-1>", lambda e: setattr(self, "_o", (e.x_root - self.winfo_x(), e.y_root - self.winfo_y())))
        bar.bind("<B1-Motion>", lambda e: self.geometry(f"+{e.x_root - self._o[0]}+{e.y_root - self._o[1]}"))
        self.body = tk.Frame(shell, bg=SURFACE)
        self.body.pack(fill="both", expand=True, padx=18, pady=14)
        self.after(30, lambda: chrome.round_corners(self, chrome.Chrome.BORDER))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gota Local Assistant")
        self.bind_class("Text", "<Button-3>", self._edit_menu, add="+")    # right click anywhere you type: Cortar, Copiar, Colar, Selecionar tudo
        self.bind_class("Entry", "<Button-3>", self._edit_menu, add="+")
        try:   # the Gota cat as the window / taskbar icon (the packaged exe carries the same icon)
            self._icon = ImageTk.PhotoImage(Image.open(sprites().dir / "logo.png").convert("RGBA").resize((64, 64), Image.NEAREST))
            self.iconphoto(True, self._icon)
        except Exception:
            pass
        ax, ay, aw, ah = chrome.work_area()
        w, h = min(1100, aw - 60), min(740, ah - 40)
        self.geometry(f"{w}x{h}+{ax + (aw - w) // 2}+{ay + (ah - h) // 2}")
        self.minsize(min(820, aw - 20), min(520, ah - 20))
        self.profile, self.settings, self.chats = store.Profile(), store.Settings(), store.Chats()
        kb.install_seed()
        self.images = imagegen.ImageGen()
        self.gemma = None
        self.speaker = None
        self.listener = voice.Listener()
        self.listener.preferred = self.settings.get("mic_name") or ""
        self.pending_image = None
        self.busy = False
        self.dictating = False
        self.typing = False   # a typed message is being answered
        self.turn = 0         # raised on every new voice turn and on cancel: work started under an older value is dropped
        self.call = None
        self.voice_question = None
        self.wake_stop = threading.Event()
        self.tray = None
        self.hotkey = None
        self.call_hotkey = None
        self.project = None   # the folder of the coding project the open chat belongs to (None for a normal chat)
        self.vscode_server = server_mod.LocalServer(lambda: self.gemma)
        self.render_width = 0
        self.brain = brain_mod.Brain(self.profile, self.settings, lambda: self.gemma, self.images, self._status, self._notify)
        self.brain.confirm = self.confirm_sync
        self.brain.confirm_message = self.confirm_message_sync
        self.brain.followup = self.followup
        self.brain.agent.approve_plan = self.approve_plan_sync          # "plan mode": the plan is shown and approved before the agent acts
        self.brain.agent.on_plan_progress = lambda plan, done: self.ui(self._plan_card, plan, done)
        self.brain.hide_window = self.hide_for_capture
        self.chrome = chrome.Chrome(self, "Gota Local Assistant", sprites().frame("logo", 20, COLORS["bar"]), COLORS)
        self.overlay = CatOverlay(self)
        self.protocol("WM_DELETE_WINDOW", self.to_tray)
        self.after(50, lambda: (chrome.round_corners(self, chrome.Chrome.BORDER), chrome.show_in_taskbar(self)))
        self.show_boot()

    # ------------------------------------------------------------------ helpers
    @property
    def body(self):
        return self.chrome.body

    def ui(self, fn, *a):
        try:
            self.after(0, lambda: fn(*a))
        except Exception:
            pass

    def clear(self):
        for w in self.body.winfo_children():
            w.destroy()

    def _status(self, text):
        self.ui(self._set_status, text)

    PHASE_TEXT = {"thinking": "Pensando…", "working": "Executando no computador…", "searching": "Pesquisando…", "drawing": "Pintando a imagem…"}

    def set_activity(self, text):
        """The status line above the message box ("● Pensando… · 12 s") with a Stop button; None hides it."""
        bar = getattr(self, "activity", None)
        if bar is None or not bar.winfo_exists():
            return
        if text:
            self._act_label = text[:60]
            if not getattr(self, "_act_since", None):
                self._act_since = time.time()
                self.after(1000, self._act_tick)
            self._act_paint()
            if not bar.winfo_ismapped():
                bar.pack(fill="x", padx=32, pady=(0, 6), before=self.entry.master)
        else:
            self._act_since = None
            bar.pack_forget()

    def _act_paint(self):
        if getattr(self, "_act_since", None) and self.activity_text.winfo_exists():
            self.activity_text.configure(text=f"●  {self._act_label}  ·  {int(time.time() - self._act_since)} s")

    def _act_tick(self):
        if getattr(self, "_act_since", None):
            self._act_paint()
            self.after(1000, self._act_tick)

    # ---- the answer appearing while it is written (typed chat)
    def _live_update(self, my, text):
        """Called from the worker thread with the answer so far; the window is refreshed at most ~8 times a second."""
        self._live_text = text
        if getattr(self, "_live_pending", False):
            return
        self._live_pending = True
        self.ui(lambda: self.after(120, lambda: self._live_flush(my)))

    def _live_flush(self, my):
        self._live_pending = False
        if my != self.turn or not self.typing or not self._live_text.strip():
            return
        row = getattr(self, "_live_row", None)
        if row is None or not row.winfo_exists():
            row = self._live_row = tk.Frame(self.msgs, bg=BG)
            row.pack(fill="x", padx=44, pady=6)
            tk.Label(row, image=sprites().frame("logo", 30, BG), bg=BG, bd=0).pack(side="left", anchor="n", padx=(0, 10), pady=(4, 0))
            card = tk.Frame(row, bg=SURFACE, highlightbackground=widgets_mod.CARD_BORDER, highlightthickness=1, bd=0)
            card.pack(side="left")
            self._live_label = tk.Label(card, text="", bg=SURFACE, fg=TEXT, font=FONT, justify="left", anchor="w", wraplength=self.maxw(True) - 40, padx=14, pady=10)
            self._live_label.pack(side="left")
            thinking = getattr(self, "thinking", None)
            if thinking is not None and thinking.winfo_exists():
                thinking.pack_forget()   # the text itself now shows that he is answering
        self._live_label.configure(text=self._live_text)
        self.to_bottom((0,))

    def _live_clear(self):
        row = getattr(self, "_live_row", None)
        if row is not None and row.winfo_exists():
            row.destroy()
        self._live_row = None

    def cancel_current(self):
        """Stops the current voice turn or typed answer: silences him, stops listening, interrupts the model and drops what was pending."""
        self.turn += 1
        self.brain.on_partial = None
        self._live_clear()
        self.listener.cancel.set()
        try:
            self.get_speaker().stop()
        except Exception:
            pass
        self.brain.cancel()
        was_busy = self.busy or self.typing
        self.busy = self.typing = False
        self.voice_question = None
        self.set_activity(None)
        self.after(300, self.warm_chat)
        thinking = getattr(self, "thinking", None)
        if thinking is not None and thinking.winfo_exists():
            thinking.destroy()
        if self.overlay.visible:
            self.overlay.set("Cancelado." if was_busy else "…", "anim_cat_idle")
            self.overlay.hide_later(900)

    def _set_status(self, text):
        if self.busy or self.typing:
            self.set_activity(text)
        if getattr(self, "status_label", None) and self.status_label.winfo_exists():
            self.status_label.configure(text=text[:60])
        if self.overlay.visible and self.voice_question:
            self.overlay.set(f"“{self.voice_question}”\n\n{text}")

    def hide_for_capture(self, hide):
        """Makes Gota's own windows invisible while the screen is photographed, then visible again."""
        def apply():
            for w in (self, self.overlay.win, getattr(getattr(self.call, "ov", None), "win", None)):
                try:
                    if w is not None and w.winfo_exists():
                        w.attributes("-alpha", 0.0 if hide else 1.0)
                except Exception:
                    pass
        done = threading.Event()
        self.ui(lambda: (apply(), done.set()))
        done.wait(2)

    def confirm_sync(self, text, danger=False):
        """Called from a worker thread: shows a permission window and waits for the answer."""
        result, done = {"ok": False}, threading.Event()

        def show():
            d = Dialog(self, "Permissão", 560, 330 if len(text) < 300 else 430)
            tk.Label(d.body, text="⚠  Preciso da sua permissão" if danger else "Preciso da sua permissão", bg=SURFACE, fg=RED if danger else PRIMARY_HOVER,
                     font=("Segoe UI", 14, "bold")).pack(anchor="w")
            box = tk.Text(d.body, bg=SURFACE2, fg=TEXT, relief="flat", font=("Consolas", 10), wrap="word", height=8, padx=12, pady=10, bd=0)
            box.insert("1.0", text)
            box.configure(state="disabled")
            box.pack(fill="both", expand=True, pady=12)
            row = tk.Frame(d.body, bg=SURFACE)
            row.pack(fill="x")

            def answer(ok):
                result["ok"] = ok
                d.destroy()
                done.set()
            RoundButton(row, "Negar", lambda: answer(False), parent_bg=SURFACE).pack(side="right", padx=(10, 0))
            RoundButton(row, "Permitir", lambda: answer(True), bg=RED if danger else PRIMARY, hover="#F0686C" if danger else PRIMARY_HOVER, parent_bg=SURFACE).pack(side="right")
            d.protocol("WM_DELETE_WINDOW", lambda: answer(False))
            d.lift()
            self.bell()
        self.ui(show)
        done.wait(180)
        return result["ok"]

    def _edit_menu(self, e):
        w = e.widget
        if getattr(w, "_has_menu", False) or str(w.cget("state")) == "disabled":   # read-only chat text has its own copy menu
            return
        w.focus_set()
        menu = tk.Menu(w, tearoff=0, bg=SURFACE2, fg=TEXT, activebackground=PRIMARY, activeforeground=TEXT, bd=0, font=("Segoe UI", 10))
        has_sel = False
        try:
            has_sel = bool(w.selection_present()) if isinstance(w, tk.Entry) else bool(w.tag_ranges("sel"))
        except tk.TclError:
            pass
        menu.add_command(label="Cortar", command=lambda: w.event_generate("<<Cut>>"), state="normal" if has_sel else "disabled")
        menu.add_command(label="Copiar", command=lambda: w.event_generate("<<Copy>>"), state="normal" if has_sel else "disabled")
        menu.add_command(label="Colar", command=lambda: w.event_generate("<<Paste>>"))
        menu.add_separator()
        menu.add_command(label="Selecionar tudo", command=lambda: (w.select_range(0, "end") if isinstance(w, tk.Entry) else w.tag_add("sel", "1.0", "end-1c")))
        menu.tk_popup(e.x_root, e.y_root)
        return "break"

    def followup(self, chat_id, text):
        """A message from Gota that arrives on its own after the answer (for example the model's check of an instant script)."""
        def show():
            self.chats.append(chat_id, "gota", text)
            if self.settings.get("current_chat") == chat_id and hasattr(self, "msgs") and self.msgs.winfo_exists():
                self.add_message("gota", text)
        self.ui(show)

    def approve_plan_sync(self, goal, plan):
        """Called from the agent's worker thread: shows the plan and waits for Executar / Cancelar."""
        result, done = {"ok": False}, threading.Event()

        def show():
            d = Dialog(self, "Plano", 580, 200 + 30 * len(plan))
            tk.Label(d.body, text="Este é o meu plano", bg=SURFACE, fg=PRIMARY_HOVER, font=("Segoe UI", 14, "bold")).pack(anchor="w")
            tk.Label(d.body, text=goal[:160], bg=SURFACE, fg=MUTED, font=("Segoe UI", 10), wraplength=520, justify="left").pack(anchor="w", pady=(2, 8))
            for i, step in enumerate(plan, 1):
                tk.Label(d.body, text=f"{i}.  {step}", bg=SURFACE, fg=TEXT, font=FONT, wraplength=520, justify="left", anchor="w").pack(anchor="w", pady=2)
            row = tk.Frame(d.body, bg=SURFACE)
            row.pack(fill="x", side="bottom", pady=(14, 0))

            def answer(ok):
                result["ok"] = ok
                d.destroy()
                done.set()
            RoundButton(row, "Cancelar", lambda: answer(False), parent_bg=SURFACE).pack(side="right", padx=(10, 0))
            RoundButton(row, "Executar o plano", lambda: answer(True), bg=PRIMARY, hover=PRIMARY_HOVER, parent_bg=SURFACE).pack(side="right")
            d.protocol("WM_DELETE_WINDOW", lambda: answer(False))
            d.lift()
            self.bell()
        self.ui(show)
        done.wait(300)
        return result["ok"]

    def _plan_card(self, plan, done_count):
        """A live to-do list under the conversation: the plan's steps with ☑ for the ones already done."""
        try:
            card = getattr(self, "_plan_frame", None)
            if card is None or not card.winfo_exists() or getattr(self, "_plan_steps", None) != plan:
                self._plan_clear()
                self._plan_steps = list(plan)
                row = tk.Frame(self.msgs, bg=BG)
                row.pack(fill="x", padx=32, pady=(0, 6))
                card = tk.Frame(row, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1, bd=0)
                card.pack(side="left", fill="x", expand=True)
                tk.Label(card, text="Plano em andamento", bg=SURFACE, fg=MUTED, font=("Segoe UI", 9, "bold"), anchor="w", padx=14, pady=6).pack(fill="x")
                self._plan_frame, self._plan_row, self._plan_labels = card, row, []
                for step in plan:
                    lab = tk.Label(card, text="", bg=SURFACE, fg=MUTED, font=("Segoe UI", 10), anchor="w", justify="left", padx=14, wraplength=self.maxw(True) - 40)
                    lab.pack(fill="x", pady=1)
                    self._plan_labels.append(lab)
                tk.Frame(card, bg=SURFACE, height=6).pack()
            for i, lab in enumerate(self._plan_labels):
                done = i < done_count
                lab.configure(text=f"{'☑' if done else '☐'}  {i + 1}. {plan[i]}", fg=GREEN if done else (TEXT if i == done_count else MUTED))
            self.to_bottom((0, 80))
        except Exception:
            pass

    def _plan_clear(self):
        row = getattr(self, "_plan_row", None)
        if row is not None:
            try:
                row.destroy()
            except Exception:
                pass
        self._plan_row = self._plan_frame = None
        self._plan_steps, self._plan_labels = None, []

    def confirm_message_sync(self, found, requested, message, extra=""):
        """WhatsApp: shows who it goes to and the text, which can be edited before sending. Returns (ok, edited text)."""
        result, done = {"ok": False, "text": None}, threading.Event()

        def show():
            d = Dialog(self, "Enviar no WhatsApp", 600, 440)
            tk.Label(d.body, text=f"Enviar para  {found}", bg=SURFACE, fg=TEXT, font=("Segoe UI", 14, "bold")).pack(anchor="w")
            sub = ("Você pediu “" + requested + "”. " if found.strip().lower() != requested.strip().lower() else "") + (f"Vai junto: {extra}." if extra else "")
            if sub:
                tk.Label(d.body, text=sub, bg=SURFACE, fg=MUTED, font=("Segoe UI", 10), wraplength=540, justify="left").pack(anchor="w", pady=(2, 0))
            tk.Label(d.body, text=("Mensagem (você pode editar):" if message or not extra else "Quer mandar uma mensagem junto com o print? Escreva abaixo, ou deixe em branco para enviar só a imagem:"),
                     wraplength=540, justify="left", bg=SURFACE, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(12, 4))
            box = tk.Text(d.body, bg=SURFACE2, fg=TEXT, insertbackground=TEXT, relief="flat", font=("Segoe UI", 11), wrap="word", height=7, padx=12, pady=10, bd=0)
            box.insert("1.0", message)
            box.pack(fill="both", expand=True)
            box.focus_set()
            row = tk.Frame(d.body, bg=SURFACE)
            row.pack(fill="x", pady=(14, 0))

            def answer(ok):
                result["ok"], result["text"] = ok, box.get("1.0", "end").strip() if ok else None
                d.destroy()
                done.set()
            RoundButton(row, "Cancelar", lambda: answer(False), parent_bg=SURFACE).pack(side="right", padx=(10, 0))
            RoundButton(row, "Enviar", lambda: answer(True), bg=PRIMARY, hover=PRIMARY_HOVER, parent_bg=SURFACE).pack(side="right")
            d.protocol("WM_DELETE_WINDOW", lambda: answer(False))
            d.lift()
            self.bell()
        self.ui(show)
        done.wait(300)
        return result["ok"], result["text"]

    # ------------------------------------------------------------------ boot: name → model → chat
    def show_boot(self):
        self.clear()
        if not self.profile.is_set:
            return self.show_name()
        if not self.settings.get("cloud_asked"):
            return self.show_cloud_setup()
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

    def card(self, title, text):
        outer = tk.Frame(self.body, bg=BG)
        outer.pack(expand=True)
        box = tk.Frame(outer, bg=SURFACE, padx=44, pady=34)
        box.pack()
        CatView(box, size=120, bg=SURFACE).pack()
        tk.Label(box, text=title, bg=SURFACE, fg=TEXT, font=("Segoe UI", 19, "bold")).pack(pady=(10, 4))
        tk.Label(box, text=text, bg=SURFACE, fg=MUTED, font=FONT, wraplength=440, justify="center").pack()
        return box

    def show_name(self):
        box = self.card("Prazer, eu sou o Gota", "Seu mordomo pessoal. Como devo chamá-lo?")
        pill = PillEntry(box, lambda: go(), parent_bg=SURFACE, fill=SURFACE2, hint="Seu nome")
        pill.pack(fill="x", pady=(20, 10))
        pill.focus()
        treat = tk.StringVar(value="senhor")
        row = tk.Frame(box, bg=SURFACE)
        row.pack()
        for label, val in (("Senhor", "senhor"), ("Senhora", "senhora"), ("Só o nome", "")):
            tk.Radiobutton(row, text=label, value=val, variable=treat, bg=SURFACE, fg=TEXT, selectcolor=SURFACE2, activebackground=SURFACE,
                           activeforeground=TEXT, font=FONT, bd=0, highlightthickness=0).pack(side="left", padx=8)

        def go():
            if not pill.get():
                return
            self.profile.set_name(pill.get(), treat.get())
            self.show_boot()
        RoundButton(box, "Continuar", go, bg=PRIMARY, hover=PRIMARY_HOVER, parent_bg=SURFACE, height=42, width=180).pack(pady=(20, 0))

    def show_cloud_setup(self):
        """First use: the OpenRouter key for the online brain (optional: without it Gota answers with the on-device model only)."""
        box = self.card("Inteligência na nuvem", "Online, o Gota fica bem mais rápido e esperto usando um modelo gratuito do OpenRouter (Nemotron Ultra, da NVIDIA). "
                                                 "Sem internet, ou sem chave, ele usa o Gemma que roda aqui no computador.")
        tk.Label(box, text="Cole a sua chave de API do OpenRouter (começa com sk-or-). Crie uma de graça em openrouter.ai/keys.", bg=SURFACE, fg=MUTED,
                 font=("Segoe UI", 10), wraplength=440, justify="center").pack(pady=(14, 0))
        pill = PillEntry(box, lambda: save(), parent_bg=SURFACE, fill=SURFACE2, hint="sk-or-v1-...")
        pill.pack(fill="x", pady=(12, 6))
        pill.focus()
        note = tk.Label(box, text="Atenção: com a nuvem ligada, o que você escreve e os prints de tela que pedir para analisar são enviados ao OpenRouter e ao provedor do modelo. "
                                  "Offline, tudo fica só neste computador. A chave fica guardada criptografada para o seu usuário do Windows.",
                        bg=SURFACE, fg=MUTED, font=("Segoe UI", 9), wraplength=440, justify="left")
        note.pack(pady=(4, 8))
        status = tk.Label(box, text="", bg=SURFACE, fg=ACCENT, font=("Segoe UI", 10), wraplength=440)
        status.pack()

        def finish():
            self.settings.set("cloud_asked", True)
            self.show_boot()

        def save():
            key = pill.get().strip()
            if not key:
                return
            status.configure(text="Testando a chave...")

            def work():
                err = cloud_mod.OpenRouter(key, self.settings.get("cloud_model") or cloud_mod.DEFAULT_MODEL).check()

                def done():
                    if err:
                        status.configure(text=f"Não funcionou: {err}", fg=RED)
                    else:
                        cloud_mod.save_key(key)
                        self.settings.set("use_cloud", True)
                        finish()
                self.ui(done)
            threading.Thread(target=work, daemon=True).start()
        row = tk.Frame(box, bg=SURFACE)
        row.pack(pady=(10, 0))
        RoundButton(row, "Salvar e continuar", save, bg=PRIMARY, hover=PRIMARY_HOVER, parent_bg=SURFACE, height=42, width=190).pack(side="left", padx=6)
        RoundButton(row, "Usar só offline", lambda: (self.settings.set("use_cloud", False), finish()), parent_bg=SURFACE, height=42, width=150).pack(side="left", padx=6)

    def mic_dialog(self):
        """Choose the microphone (a headset, say) or leave it automatic, and test that it hears."""
        d = Dialog(self, "Voz e microfone", 560, 520)
        tk.Label(d.body, text="Automático segue o microfone padrão do Windows e troca sozinho se ele ficar mudo (por exemplo ao colocar o fone). "
                              "Se o Gota não te ouvir, escolha aqui o microfone do fone e teste.", bg=SURFACE, fg=MUTED, wraplength=510, justify="left", font=("Segoe UI", 10)).pack(anchor="w")
        choice = tk.StringVar(value=self.settings.get("mic_name") or "")
        box = tk.Frame(d.body, bg=SURFACE)
        box.pack(fill="x", pady=(10, 0))
        status = tk.Label(d.body, text="", bg=SURFACE, fg=ACCENT, font=("Segoe UI", 10), wraplength=510, justify="left")

        def pick():
            self.settings.set("mic_name", choice.get())
            self.listener.preferred = choice.get()
            self.listener.skip.clear()

        def refresh():
            for w in box.winfo_children():
                w.destroy()
            options = [("Automático (padrão do Windows)", "")] + [(n, n) for _i, n in voice.input_devices()]
            for label, val in options:
                tk.Radiobutton(box, text=label, value=val, variable=choice, command=pick, bg=SURFACE, fg=TEXT, selectcolor=SURFACE2, activebackground=SURFACE,
                               activeforeground=TEXT, font=FONT, bd=0, highlightthickness=0, anchor="w").pack(fill="x", pady=3)

        def test():
            status.configure(text="Fale agora por 3 segundos…", fg=ACCENT)

            def work():
                import queue as _q, numpy as np
                q = _q.Queue()
                lis = self.listener
                peak, err = 0, ""
                try:
                    with lis._stream(q):
                        end = time.time() + 3
                        while time.time() < end:
                            try:
                                peak = max(peak, int(np.abs(np.frombuffer(q.get(timeout=0.3), dtype=np.int16)).max(initial=0)))
                            except _q.Empty:
                                pass
                except Exception as e:
                    err = str(e)
                name = lis.device_name

                def done():
                    if err:
                        status.configure(text=f"Não consegui abrir o microfone: {err}", fg=RED)
                    elif peak < 60:
                        status.configure(text=f"“{name}”: quase nenhum som (nível {peak}). Escolha outro microfone ou confira o volume do Windows.", fg=RED)
                    else:
                        status.configure(text=f"“{name}”: te ouvi bem (nível {peak}).", fg=GREEN)
                self.ui(done)
            threading.Thread(target=work, daemon=True).start()
        refresh()
        en = tk.Frame(d.body, bg=SURFACE)
        en.pack(fill="x", pady=(14, 0))
        tk.Label(en, text="Ler frases em inglês com pronúncia de inglês (mesma voz)", bg=SURFACE, fg=TEXT, font=FONT).pack(side="left")

        def set_english(v):
            self.settings.set("english_speech", bool(v))
            if self.speaker is not None:
                self.speaker.english = bool(v)
        Toggle(en, self.settings.get("english_speech") is not False, set_english).pack(side="right")
        row = tk.Frame(d.body, bg=SURFACE)
        row.pack(fill="x", pady=(12, 0))
        RoundButton(row, "Testar", test, bg=PRIMARY, hover=PRIMARY_HOVER, parent_bg=SURFACE).pack(side="left")
        RoundButton(row, "Atualizar lista", refresh, parent_bg=SURFACE).pack(side="left", padx=8)
        status.pack(anchor="w", pady=(10, 0))

    def memory_dialog(self):
        """What Gota remembers about the user across conversations, the routines that run by themselves, and the agent's switches."""
        d = Dialog(self, "Memória e rotinas", 640, 700)
        mem, routines = self.brain.memory, self.brain.routines

        def section(title, hint):
            tk.Label(d.body, text=title, bg=SURFACE, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(6, 0))
            tk.Label(d.body, text=hint, bg=SURFACE, fg=MUTED, font=("Segoe UI", 9), wraplength=580, justify="left").pack(anchor="w", pady=(0, 4))

        def listbox(height):
            lb = tk.Listbox(d.body, bg=SURFACE2, fg=TEXT, selectbackground=PRIMARY, relief="flat", font=("Segoe UI", 10), activestyle="none", bd=0, highlightthickness=0, height=height)
            lb.pack(fill="x")
            return lb

        # ---- memory
        section("Memória", "O que o Gota aprendeu sobre você e como você gosta das coisas. Ele guarda sozinho o que você conta; aqui você corrige ou apaga.")
        mlb = listbox(8)
        shown = []

        def refresh_mem():
            mlb.delete(0, "end")
            shown[:] = sorted(mem.items(), key=lambda i: (memory_mod.TYPES.index(i["type"]), -i["updated"]))
            for it in shown:
                mlb.insert("end", f"  [{memory_mod.LABELS[it['type']]}]  {it['text'][:70]}")

        def add_mem():
            text = simpledialog.askstring("Memória", "O que devo lembrar?", parent=d)
            if text:
                mem.add(memory_mod.Memory.guess(text) if hasattr(memory_mod.Memory, "guess") else "user", text)
                refresh_mem()

        def edit_mem():
            sel = mlb.curselection()
            if sel:
                it = shown[sel[0]]
                text = simpledialog.askstring("Memória", "Corrija:", initialvalue=it["text"], parent=d)
                if text:
                    mem.update(it["id"], text)
                    refresh_mem()

        def del_mem():
            sel = mlb.curselection()
            if sel:
                mem.delete(shown[sel[0]]["id"])
                refresh_mem()
        row = tk.Frame(d.body, bg=SURFACE)
        row.pack(fill="x", pady=(6, 0))
        RoundButton(row, "Adicionar", add_mem, parent_bg=SURFACE, height=30).pack(side="left")
        RoundButton(row, "Editar", edit_mem, parent_bg=SURFACE, height=30).pack(side="left", padx=6)
        RoundButton(row, "Apagar", del_mem, bg=RED, hover="#F0686C", parent_bg=SURFACE, height=30).pack(side="right")
        refresh_mem()

        # ---- routines
        section("Rotinas", "Tarefas que o Gota faz sozinho em um horário, só com consultas (nada é alterado), e avisa o resultado. Ex.: conferir os backups toda manhã.")
        rlb = listbox(5)
        rshown = []

        def refresh_routines():
            rlb.delete(0, "end")
            rshown[:] = routines.items() if routines else []
            for r in rshown:
                rlb.insert("end", f"  #{r['id']}  {r['name'][:30]}  ·  {r['repeat']} às {r['when']}")

        def add_routine():
            if not routines:
                return
            goal = simpledialog.askstring("Rotina", "O que o Gota deve fazer?", parent=d)
            when = goal and simpledialog.askstring("Rotina", "Que horas? (HH:MM)", initialvalue="08:00", parent=d)
            if goal and when and re.match(r"^\d{1,2}:\d{2}$", when):
                repeat = simpledialog.askstring("Rotina", "Repetir: daily, weekdays, weekly ou hourly", initialvalue="daily", parent=d) or "daily"
                routines.add(goal[:40], goal, when, repeat.strip().lower())
                refresh_routines()

        def run_now():
            sel = rlb.curselection()
            if sel and routines:
                routines.fire(rshown[sel[0]])
                self.toast("Rotina", "Rodando agora…")

        def del_routine():
            sel = rlb.curselection()
            if sel and routines:
                routines.delete(rshown[sel[0]]["id"])
                refresh_routines()
        row = tk.Frame(d.body, bg=SURFACE)
        row.pack(fill="x", pady=(6, 0))
        RoundButton(row, "Nova rotina", add_routine, parent_bg=SURFACE, height=30).pack(side="left")
        RoundButton(row, "Rodar agora", run_now, parent_bg=SURFACE, height=30).pack(side="left", padx=6)
        RoundButton(row, "Apagar", del_routine, bg=RED, hover="#F0686C", parent_bg=SURFACE, height=30).pack(side="right")
        refresh_routines()

        # ---- agent switches
        section("Agente", "Como o Gota trabalha nas tarefas de vários passos.")
        for key, label, default in (("plan_approval", "Mostrar o plano e pedir aprovação antes de agir", True), ("agent_verify", "Conferir a resposta final com o que as ferramentas mostraram", True)):
            r = tk.Frame(d.body, bg=SURFACE)
            r.pack(fill="x", pady=2)
            tk.Label(r, text=label, bg=SURFACE, fg=TEXT, font=("Segoe UI", 10)).pack(side="left")
            Toggle(r, self.settings.get(key) is not False if default else bool(self.settings.get(key)), lambda v, k=key: self.settings.set(k, bool(v))).pack(side="right")
        r = tk.Frame(d.body, bg=SURFACE)
        r.pack(fill="x", pady=(6, 0))
        tk.Label(r, text="Tópico ntfy para avisos no celular (opcional):", bg=SURFACE, fg=TEXT, font=("Segoe UI", 10)).pack(side="left")
        topic = tk.Entry(r, bg=SURFACE2, fg=TEXT, insertbackground=TEXT, relief="flat", font=FONT, width=18)
        topic.insert(0, self.settings.get("ntfy_topic") or "")
        topic.pack(side="right", ipady=4)
        topic.bind("<FocusOut>", lambda e: self.settings.set("ntfy_topic", topic.get().strip()))

    def cloud_dialog(self):
        """Settings for the online brain: key, on/off, and a test."""
        d = Dialog(self, "Nuvem (OpenRouter)", 560, 430)
        tk.Label(d.body, text="Online o Gota usa o modelo da nuvem; offline, ou se ela falhar, usa o Gemma deste computador.", bg=SURFACE, fg=MUTED,
                 wraplength=510, justify="left", font=("Segoe UI", 10)).pack(anchor="w")
        on = tk.Frame(d.body, bg=SURFACE)
        on.pack(fill="x", pady=(12, 4))
        tk.Label(on, text="Usar a nuvem quando estiver online", bg=SURFACE, fg=TEXT, font=FONT).pack(side="left")
        Toggle(on, self.settings.get("use_cloud") is not False, lambda v: self.settings.set("use_cloud", bool(v))).pack(side="right")
        tk.Label(d.body, text="Chave de API do OpenRouter (deixe em branco para manter a atual):", bg=SURFACE, fg=MUTED, wraplength=510, justify="left",
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(10, 4))
        pill = PillEntry(d.body, lambda: save(), parent_bg=SURFACE, fill=SURFACE2, hint="sk-or-v1-... (" + ("já há uma chave guardada" if cloud_mod.load_key() else "sem chave") + ")")
        pill.pack(fill="x")
        tk.Label(d.body, text="Modelo:", bg=SURFACE, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(10, 4))
        model = PillEntry(d.body, lambda: None, parent_bg=SURFACE, fill=SURFACE2, hint=self.settings.get("cloud_model") or cloud_mod.DEFAULT_MODEL)
        model.pack(fill="x")
        status = tk.Label(d.body, text="", bg=SURFACE, fg=ACCENT, font=("Segoe UI", 10), wraplength=510, justify="left")
        status.pack(anchor="w", pady=(10, 0))

        def save(test_only=False):
            key = pill.get().strip() or cloud_mod.load_key()
            mid = model.get().strip() or self.settings.get("cloud_model") or cloud_mod.DEFAULT_MODEL
            if not key:
                status.configure(text="Cole uma chave primeiro.", fg=RED)
                return
            status.configure(text="Testando...", fg=ACCENT)

            def work():
                err = cloud_mod.OpenRouter(key, mid).check()

                def done():
                    if err:
                        status.configure(text=f"Não funcionou: {err}", fg=RED)
                    else:
                        cloud_mod.save_key(key)
                        self.settings.set("cloud_model", "" if mid == cloud_mod.DEFAULT_MODEL else mid)
                        self.settings.set("use_cloud", True)
                        self.settings.set("cloud_asked", True)
                        status.configure(text="Funcionando e salvo. A nuvem será usada quando houver internet.", fg=GREEN)
                self.ui(done)
            threading.Thread(target=work, daemon=True).start()

        def remove():
            cloud_mod.clear_key()
            status.configure(text="Chave removida: o Gota usa só o Gemma local.", fg=ACCENT)
        row = tk.Frame(d.body, bg=SURFACE)
        row.pack(fill="x", pady=(14, 0))
        RoundButton(row, "Testar e salvar", save, bg=PRIMARY, hover=PRIMARY_HOVER, parent_bg=SURFACE).pack(side="left")
        RoundButton(row, "Remover chave", remove, parent_bg=SURFACE).pack(side="left", padx=8)

    def show_download(self):
        box = self.card("Preparando o Gota", f"Baixando a inteligência do Gota (~{llm.MODEL_MB / 1000:.1f} GB, uma vez só). Depois disso ela roda no próprio computador, mesmo sem internet.")
        bar = tk.Canvas(box, width=440, height=10, bg=SURFACE, highlightthickness=0)
        bar.pack(pady=(20, 6))
        rounded(bar, 0, 0, 440, 10, 5, fill=SURFACE2, outline="")
        label = tk.Label(box, text="Começando...", bg=SURFACE, fg=MUTED, font=("Segoe UI", 10))
        label.pack()
        state = {"fill": None}

        def progress(pct, done, total):
            def draw():
                if state["fill"]:
                    bar.delete(state["fill"])
                state["fill"] = rounded(bar, 0, 0, max(10, 4.4 * pct), 10, 5, fill=ACCENT, outline="")
                label.configure(text=f"Baixando... {done} MB de {total} MB")
            self.ui(draw)

        def work():
            try:
                llm.download_model(llm.MODEL_FILE, progress)
                self.ui(self.show_boot)
            except Exception as e:
                self.ui(lambda: label.configure(text=f"Não consegui baixar: {e}. Verifique a internet."))
                self.ui(lambda: RoundButton(box, "Tentar de novo", self.show_boot, parent_bg=SURFACE).pack(pady=8))
        threading.Thread(target=work, daemon=True).start()

        def pick():
            f = filedialog.askopenfilename(title="Escolha o arquivo do modelo (.litertlm)", filetypes=[("Modelo", "*.litertlm")], parent=self)
            if f:
                self.settings.set("model_path", f)
                self.show_boot()
        tk.Button(box, text="Já tenho o arquivo do modelo…", command=pick, bg=SURFACE, fg=MUTED, relief="flat", bd=0, cursor="hand2", activebackground=SURFACE).pack(pady=(14, 0))

    def show_loading(self, path):
        self.card("Acordando o Gota", "Carregando a inteligência… leva alguns segundos.")

        def work():
            try:
                self.gemma = cloud_mod.Hybrid(llm.Gemma(path), self.settings)   # online: OpenRouter; offline (or on failure): Gemma
                threading.Thread(target=self.get_speaker, daemon=True).start()   # load the voice now (it takes a few seconds)
                self.brain.toast = self.toast
                self.brain.routines = routines_mod.Routines(self.settings, lambda goal, done: self.brain.agent.run_background(goal, done, unattended=True), self.toast)
                self.ui(self.show_boot)
            except Exception as e:
                self.ui(lambda: messagebox.showerror("Gota", f"Não consegui carregar o modelo:\n{e}", parent=self))
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------ the chat screen
    def show_chat(self):
        self.clear()
        self.sidebar = tk.Frame(self.body, bg=SURFACE, width=236)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        main = tk.Frame(self.body, bg=BG)
        main.pack(side="left", fill="both", expand=True)

        head = tk.Frame(main, bg=BG)
        head.pack(fill="x", padx=32, pady=(16, 6))
        self.title_label = tk.Label(head, text="", bg=BG, fg=TEXT, font=("Segoe UI", 12, "bold"), anchor="w")
        self.title_label.pack(side="left")
        self.title_label.configure(cursor="hand2")
        self.title_label.bind("<Double-Button-1>", lambda e: (lambda cid: cid != store.VOICE_CHAT and self.rename_chat(cid, self.title_label.cget("text").replace("🎙  ", "")))(self.settings.get("current_chat")))
        self.sub_label = tk.Label(head, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9), anchor="w")
        self.sub_label.pack(side="left", padx=(12, 0))
        self.main_frame = main
        self.right = None   # the right-hand panels (tasks, files) are built on demand
        RoundButton(head, "📞  Ligar", self.start_call, bg=SURFACE2, hover=HOVER, height=32, font=("Segoe UI", 10)).pack(side="right")

        RoundButton(head, "🎙  Chamar", self.summon, bg=SURFACE2, hover=HOVER, height=32, font=("Segoe UI", 10)).pack(side="right", padx=(0, 8))

        wrap = tk.Frame(main, bg=BG)
        wrap.pack(fill="both", expand=True)
        self.scroll = tk.Canvas(wrap, bg=BG, highlightthickness=0, bd=0)
        sb = tk.Scrollbar(wrap, command=self.scroll.yview, bg=BG, troughcolor=BG, bd=0, relief="flat", width=10)
        self.scroll.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.scroll.pack(fill="both", expand=True)
        self.msgs = tk.Frame(self.scroll, bg=BG)
        self.win_id = self.scroll.create_window((0, 0), window=self.msgs, anchor="nw")
        self._stick = True   # follow the end of the chat while it grows, until the user scrolls up
        self.msgs.bind("<Configure>", self._msgs_changed)
        self.scroll.bind("<Configure>", self._on_resize)
        self.bind_all("<MouseWheel>", self._wheel)

        self.attach_row = tk.Frame(main, bg=BG)
        self.attach_row.pack(fill="x", padx=32)
        self.activity = tk.Frame(main, bg=BG)   # a status line above the message box, only while Gota is doing something
        self.activity_text = tk.Label(self.activity, text="", bg=BG, fg=MUTED, font=("Segoe UI", 10), anchor="w")
        self.activity_text.pack(side="left")
        RoundButton(self.activity, "■  Parar", self.cancel_current, bg=SURFACE2, hover=HOVER, height=28, font=("Segoe UI", 9)).pack(side="left", padx=(12, 0))
        bar = tk.Frame(main, bg=BG)
        bar.pack(fill="x", padx=32, pady=(0, 6))
        self.entry = ChatInput(bar, self.send, left=[("attach", "＋", self.attach)], right=[("mic", "🎤", self.toggle_dictation), ("send", "➤", self.send, True)])
        self.entry.pack(fill="x")
        self.mic = self.entry.buttons["mic"]
        tk.Label(main, text="Online usa a nuvem (OpenRouter); offline roda neste computador (Gemma 4). Confira respostas importantes.", bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(pady=(0, 10))

        cur = self.settings.get("current_chat")
        if not cur or not self.chats.get(cur):
            normal = [c for c in self.chats.list() if c["id"] != store.VOICE_CHAT]
            cur = normal[0]["id"] if normal else self.chats.create()["id"]
            self.settings.set("current_chat", cur)
        self.build_sidebar()
        self.open_chat(cur)
        self.entry.focus()
        self.setup_background()
        if not self.settings.get("tutorial"):
            self.after(600, self.tutorial)

    def _msgs_changed(self, _e=None):
        self.scroll.configure(scrollregion=self.scroll.bbox("all"))
        if self._stick:
            self.scroll.yview_moveto(1.0)

    def to_bottom(self, delays=(0, 60, 250, 700)):
        """Scrolls to the newest message. Done several times because the layout settles a moment after a message is added."""
        self._stick = True

        def go():
            try:
                if not self.scroll.winfo_exists():
                    return
                self.update_idletasks()
                self.scroll.configure(scrollregion=self.scroll.bbox("all"))
                self.scroll.yview_moveto(1.0)
            except Exception:
                pass
        for d in delays:
            self.after(d, go)

    def _on_resize(self, e):
        self.scroll.itemconfigure(self.win_id, width=e.width)
        if not self.render_width:
            self.render_width = e.width
        elif abs(e.width - self.render_width) > 90:
            self.render_width = e.width
            if getattr(self, "_rerender", None):
                self.after_cancel(self._rerender)
            self._rerender = self.after(350, lambda: self.open_chat(self.settings.get("current_chat")))

    def _wheel(self, ev):
        """Scrolls the chat when the pointer is anywhere over it, including over message text and code boxes."""
        w = self.winfo_containing(ev.x_root, ev.y_root)
        while w is not None:
            if w is self.scroll:
                self.scroll.yview_scroll(int(-ev.delta / 120) * 2, "units")
                self._stick = self.scroll.yview()[1] >= 0.98   # scrolled up to read: stop following; back at the end: follow again
                return
            w = w.master

    def maxw(self, plain=False):
        width = self.scroll.winfo_width() or 700
        return int(max(320, min(760, width * 0.86 - 40))) if plain else int(max(320, min(620, width * 0.7)))

    def build_sidebar(self):
        for w in self.sidebar.winfo_children():
            w.destroy()
        top = tk.Frame(self.sidebar, bg=SURFACE)
        top.pack(fill="x", padx=18, pady=(12, 4))
        tk.Label(top, image=sprites().frame("logo", 30, SURFACE), bg=SURFACE, bd=0).pack(side="left")
        tk.Label(top, text="Gota", bg=SURFACE, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(side="left", padx=10)
        # no list of chats or projects here: four big buttons open them (and create new ones)
        for text, cmd, hot in (("＋   Nova conversa", self.new_chat, True), ("＋   Novo projeto", self.create_project_dialog, True),
                               ("☰   Selecionar conversa", self.chats_dialog, False), ("📁   Selecionar projeto", self.projects_dialog, False)):
            row = tk.Label(self.sidebar, text=text, bg=SURFACE, fg=PRIMARY if hot else TEXT, anchor="w", font=("Segoe UI", 10, "bold" if hot else "normal"), padx=12, pady=5, cursor="hand2")
            row.pack(fill="x", padx=10, pady=0)
            row.bind("<Enter>", lambda e, w=row: w.configure(bg=SURFACE2))
            row.bind("<Leave>", lambda e, w=row: w.configure(bg=SURFACE))
            row.bind("<Button-1>", lambda e, c=cmd: c())
        tk.Frame(self.sidebar, bg=BORDER, height=1).pack(fill="x", padx=18, pady=(6, 4))
        foot = tk.Frame(self.sidebar, bg=SURFACE)
        foot.pack(side="bottom", fill="x", padx=14, pady=(4, 8))
        sw = tk.Frame(foot, bg=SURFACE)
        sw.pack(fill="x", padx=8, pady=(0, 6))
        tk.Label(sw, text='Escutar "Hey Gota"', bg=SURFACE, fg=TEXT, font=("Segoe UI", 10)).pack(side="left")
        Toggle(sw, self.settings.get("hey_gota"), self.toggle_hey).pack(side="right")
        self.dl_label = tk.Label(foot, text="", bg=SURFACE, fg=ACCENT, font=("Segoe UI", 1), anchor="w", pady=0)   # grows only while something downloads
        self.dl_label.pack(fill="x", padx=8)
        groups = (("Conexões", (("🔗  Conexões (WhatsApp e Outlook)", self.connections_dialog), ("☁  Nuvem (OpenRouter)", self.cloud_dialog), ("🔌  Integrações", self.integrations_dialog))),
                  ("Conhecimento", (("📚  Base de conhecimento", self.kb_dialog), ("🧩  Habilidades", self.skills_dialog), ("⏱  Tarefas em segundo plano", self.background_dialog), ("🧠  Memória e rotinas", self.memory_dialog))),
                  ("Preferências", (("🏷   Apelidos de programas", self.aliases_dialog), ("🖥  Telas (apelidos)", self.screens_dialog), ("🎤  Voz e microfone", self.mic_dialog),
                                    ("🎩  Meu nome e tratamento", self.edit_name), ("❓  Como me chamar", self.tutorial))),
                  ("Avançado", (("📜  Registro de ações", self.audit_dialog),)))
        for label, links in groups:   # a small muted label above each group, no boxes: just spacing
            tk.Label(foot, text=label.upper(), bg=SURFACE, fg="#5D6492", font=("Segoe UI", 7, "bold"), anchor="w", padx=10).pack(fill="x", pady=(5, 0))
            for text, cmd in links:
                self._link(foot, text, cmd, fg=MUTED, pad=1)
        self._poll_download()

    def _link(self, parent, text, cmd, fg=TEXT, pad=5):
        row = tk.Label(parent, text=text, bg=SURFACE, fg=fg, anchor="w", font=("Segoe UI", 9), padx=10, pady=pad, cursor="hand2")
        row.pack(fill="x")
        row.bind("<Enter>", lambda e: row.configure(bg=SURFACE2, fg=TEXT))
        row.bind("<Leave>", lambda e: row.configure(bg=SURFACE, fg=fg))
        row.bind("<Button-1>", lambda e: cmd())

    def _chat_row(self, parent, c, selected):
        title = ("🎙  " if c["id"] == store.VOICE_CHAT else "📁  " if c.get("project") else "") + c["title"]
        row = tk.Label(parent, text=title[:30], anchor="w", bg=SURFACE2 if selected else SURFACE, fg=TEXT, font=("Segoe UI", 10), padx=12, pady=8, cursor="hand2")
        row.pack(fill="x", pady=1)
        if not selected:
            row.bind("<Enter>", lambda e: row.configure(bg=lerp(SURFACE, SURFACE2, 0.6)))
            row.bind("<Leave>", lambda e: row.configure(bg=SURFACE))
        row.bind("<Button-1>", lambda e, cid=c["id"]: self.open_chat(cid))
        row.bind("<Button-3>", lambda e, cid=c["id"], t=c["title"]: self.chat_menu(e, cid, t))

    def _poll_download(self):
        if not getattr(self, "dl_label", None) or not self.dl_label.winfo_exists():
            return
        note = getattr(self.gemma, "notice", None)
        if note:   # the cloud model was retired by its provider: say so once
            self.gemma.notice = None
            self.toast("Modelo da nuvem trocado", note)
        msg = f"🎨 Baixando o pintor… {self.images.percent}%" if self.images.downloading else "🎙 Baixando o modelo de voz…" if self.listener.whisper_downloading else ""
        self.dl_label.configure(text=msg, font=("Segoe UI", 9 if msg else 1))
        self.after(2000, self._poll_download)

    def chat_menu(self, event, cid, title):
        m = tk.Menu(self, tearoff=0, bg=SURFACE2, fg=TEXT, activebackground=PRIMARY, bd=0)
        if cid != store.VOICE_CHAT:
            m.add_command(label="Renomear…", command=lambda: self.rename_chat(cid, title))
        m.add_command(label="Apagar conversa", command=lambda: self.delete_chat(cid, title))
        m.tk_popup(event.x_root, event.y_root)

    # ------------------------------------------------------------------ right-hand panels: background tasks and (in projects) files
    SKIP_TREE = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".idea", ".gradle", ".kotlin", "target", ".next", ".cache"}

    def _build_right(self):
        panel = tk.Frame(self.body, bg=BG, width=300)
        panel.pack_propagate(False)
        # --- tasks card
        self.tasks_card = tk.Frame(panel, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        head = tk.Frame(self.tasks_card, bg=SURFACE)
        head.pack(fill="x", padx=14, pady=(10, 4))
        tk.Label(head, text="Tarefas em segundo plano", bg=SURFACE, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(side="left")
        clear = tk.Label(head, text="🗑", bg=SURFACE, fg=MUTED, cursor="hand2", font=("Segoe UI", 10))
        clear.pack(side="right")
        clear.bind("<Button-1>", lambda e: self._tasks_clear())
        self.tasks_box = tk.Frame(self.tasks_card, bg=SURFACE)
        self.tasks_box.pack(fill="x", padx=14, pady=(0, 10))
        self._tasks_sig, self._tasks_open, self._done_open = None, None, False
        # --- files card
        self.files_card = tk.Frame(panel, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        fh = tk.Frame(self.files_card, bg=SURFACE)
        fh.pack(fill="x", padx=14, pady=(10, 6))
        tk.Label(fh, text="Arquivos", bg=SURFACE, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(side="left")
        reload_btn = tk.Label(fh, text="⟳", bg=SURFACE, fg=MUTED, cursor="hand2", font=("Segoe UI", 12))
        reload_btn.pack(side="right")
        reload_btn.bind("<Button-1>", lambda e: self.files_refresh(reset=True))
        vs = tk.Label(fh, text="Abrir no VS Code", bg=SURFACE2, fg=TEXT, cursor="hand2", font=("Segoe UI", 9), padx=8, pady=3)
        vs.pack(side="right", padx=(0, 10))
        vs.bind("<Button-1>", lambda e: self.open_in_vscode())
        self.files_filter = tk.StringVar()
        fe = tk.Entry(self.files_card, textvariable=self.files_filter, bg=SURFACE2, fg=TEXT, insertbackground=TEXT, relief="flat", font=("Segoe UI", 10))
        fe.pack(fill="x", padx=14, ipady=5, pady=(0, 8))
        self.files_filter.trace_add("write", lambda *_: self.files_refresh())
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Gota.Treeview", background=SURFACE2, fieldbackground=SURFACE2, foreground=TEXT, borderwidth=0, rowheight=24, font=("Segoe UI", 10), bordercolor=SURFACE2, lightcolor=SURFACE2, darkcolor=SURFACE2)
        style.layout("Gota.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])   # no focus ring around the list
        style.map("Gota.Treeview", background=[("selected", PRIMARY)], foreground=[("selected", "#FFFFFF")])
        wrap = tk.Frame(self.files_card, bg=SURFACE)
        wrap.pack(fill="both", expand=True, padx=(14, 6), pady=(0, 12))
        self.tree = ttk.Treeview(wrap, show="tree", style="Gota.Treeview", selectmode="browse")
        sb = tk.Scrollbar(wrap, command=self.tree.yview, bg=SURFACE2, troughcolor=SURFACE, bd=0, width=10, activebackground=HOVER, highlightthickness=0)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewOpen>>", self._tree_open)
        self.tree.bind("<Double-Button-1>", self._tree_activate)
        self.tree.bind("<Return>", self._tree_activate)
        self.right = panel
        self.after(1500, self._right_tick)
        return panel

    def _right_tick(self):
        if self.right is None or not self.right.winfo_exists():
            return
        self._update_right()
        self.after(1500, self._right_tick)

    def _running_items(self):
        """What is running now: background tasks, plus the foreground work of the moment."""
        items = [(f"#{t['id']}  {t['goal'][:22]}", int(time.time() - t["started"]), t) for t in self.brain.agent.bg if t["status"] == "rodando"]
        if getattr(self, "_act_since", None) and self.activity.winfo_exists() and self.activity.winfo_ismapped():
            items.insert(0, (getattr(self, "_act_label", "Trabalhando…")[:38], int(time.time() - self._act_since), None))
        return items

    def _update_right(self):
        if not hasattr(self, "main_frame"):
            return
        if self.right is None or not self.right.winfo_exists():
            self._build_right()
        tasks = self.brain.agent.bg
        running = self._running_items()
        show_tasks = bool(tasks) or (bool(running) and bool(self.project))
        show_files = bool(self.project)
        if not (show_tasks or show_files):
            self.right.pack_forget()
            return
        if not self.right.winfo_ismapped():
            self.right.pack(side="right", fill="y", padx=(0, 12), pady=12, before=self.main_frame)
        for card, on, kw in ((self.tasks_card, show_tasks, dict(fill="x", pady=(0, 10))), (self.files_card, show_files, dict(fill="both", expand=True))):
            if on and not card.winfo_ismapped():
                card.pack(**kw)
            elif not on and card.winfo_ismapped():
                card.pack_forget()
        # repaint the task list only when something changed
        sig = (tuple((t["id"], t["status"]) for t in tasks), tuple((i[0], i[1] // 5) for i in running), self._done_open, self._tasks_open)
        if show_tasks and sig != self._tasks_sig:
            self._tasks_sig = sig
            self._tasks_paint(running)

    def _tasks_paint(self, running):
        for w in self.tasks_box.winfo_children():
            w.destroy()
        tasks = self.brain.agent.bg
        if running:
            tk.Label(self.tasks_box, text="Em execução", bg=SURFACE, fg=MUTED, font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=(2, 2))
            for label, secs, t in running:
                row = tk.Label(self.tasks_box, text=f"●  {label}      {secs} s", bg=SURFACE, fg=TEXT, font=("Segoe UI", 10), anchor="w", cursor="hand2" if t else "arrow")
                row.pack(fill="x", pady=1)
                if t:
                    row.bind("<Button-1>", lambda e, t=t: self._task_toggle(t))
        done = [t for t in tasks if t["status"] != "rodando"]
        if done:
            head = tk.Label(self.tasks_box, text=f"Concluído {len(done)}  {'▾' if self._done_open else '▸'}", bg=SURFACE, fg=MUTED, font=("Segoe UI", 9), anchor="w", cursor="hand2")
            head.pack(fill="x", pady=(8, 2))
            head.bind("<Button-1>", lambda e: (setattr(self, "_done_open", not self._done_open), setattr(self, "_tasks_sig", None)))
            if self._done_open:
                for t in done[-12:]:
                    mark = "✓" if t["status"] == "concluída" else "✕"
                    row = tk.Label(self.tasks_box, text=f"{mark}  #{t['id']}  {t['goal'][:36]}", bg=SURFACE, fg=TEXT, font=("Segoe UI", 10), anchor="w", cursor="hand2")
                    row.pack(fill="x", pady=1)
                    row.bind("<Button-1>", lambda e, t=t: self._task_toggle(t))
        if self._tasks_open is not None:
            t = self._tasks_open
            tk.Label(self.tasks_box, text=(t["result"] or "Ainda em andamento…")[:500], bg=SURFACE2, fg=TEXT, font=("Segoe UI", 9), anchor="w", justify="left", wraplength=250, padx=8, pady=6).pack(fill="x", pady=(6, 0))
            if t["status"] == "rodando":
                RoundButton(self.tasks_box, "■  Parar", lambda t=t: t.__setitem__("stop", True), bg=SURFACE2, hover=HOVER, height=26, font=("Segoe UI", 9), parent_bg=SURFACE).pack(anchor="e", pady=(6, 0))
        if not running and not done:
            tk.Label(self.tasks_box, text="Nenhuma tarefa. Peça, por exemplo, “faça uma varredura nos logs em segundo plano e me avise”.", bg=SURFACE, fg=MUTED, font=("Segoe UI", 9), anchor="w", justify="left", wraplength=250).pack(fill="x")

    def _task_toggle(self, t):
        self._tasks_open = None if self._tasks_open is t else t
        self._tasks_sig = None

    def _tasks_clear(self):
        self.brain.agent.bg[:] = [t for t in self.brain.agent.bg if t["status"] == "rodando"]
        self._tasks_open, self._tasks_sig = None, None

    # ---- files of the open project
    def files_refresh(self, reset=False):
        if self.right is None or not self.right.winfo_exists() or not self.project:
            return
        query = self.files_filter.get().strip().lower()
        if query and len(query) >= 2:   # a flat list of matches
            self.tree.delete(*self.tree.get_children())
            n = 0
            for root, dirs, files in os.walk(self.project):
                dirs[:] = [d for d in dirs if d not in self.SKIP_TREE and not d.startswith(".")]
                for f in files:
                    if query in f.lower():
                        full = os.path.join(root, f)
                        self.tree.insert("", "end", text="📄 " + os.path.relpath(full, self.project), values=(full,))
                        n += 1
                        if n >= 80:
                            return
            return
        if reset or not self.tree.get_children() or getattr(self, "_tree_root", None) != self.project:
            self._tree_root = self.project
            self.tree.delete(*self.tree.get_children())
            self._tree_fill("", self.project)
        else:   # keep what is expanded; just re-read the open folders
            for iid in list(self._open_dirs()):
                self._tree_fill(iid, self.tree.set(iid, "path") if False else self.tree.item(iid, "values")[0], refresh=True)

    def _open_dirs(self, parent=""):
        for iid in self.tree.get_children(parent):
            if self.tree.item(iid, "open"):
                yield iid
                yield from self._open_dirs(iid)

    def _tree_fill(self, parent, folder, refresh=False):
        try:
            entries = sorted(os.scandir(folder), key=lambda e: (not e.is_dir(), e.name.lower()))
        except OSError:
            return
        if refresh:
            self.tree.delete(*self.tree.get_children(parent))
        for e in entries[:400]:
            if e.is_dir():
                if e.name in self.SKIP_TREE or e.name.startswith("."):
                    continue
                iid = self.tree.insert(parent, "end", text="📁 " + e.name, values=(e.path,), open=False)
                self.tree.insert(iid, "end", text="…", values=("",))   # a placeholder so the folder can be expanded
            else:
                self.tree.insert(parent, "end", text="📄 " + e.name, values=(e.path,))

    def _tree_open(self, _=None):
        iid = self.tree.focus()
        kids = self.tree.get_children(iid)
        if len(kids) == 1 and self.tree.item(kids[0], "values")[0] == "":
            self.tree.delete(kids[0])
            self._tree_fill(iid, self.tree.item(iid, "values")[0])

    def _tree_activate(self, _=None):
        iid = self.tree.focus()
        path = self.tree.item(iid, "values")[0] if iid else ""
        if path and os.path.isfile(path):
            try:
                if vscode_mod.find_code():
                    vscode_mod.open_path(path)
                else:
                    os.startfile(path)
            except Exception:
                pass

    # ------------------------------------------------------------------ coding projects
    def open_project(self, path):
        proj = projects_mod.register(self.settings, path)
        key = str(Path(path).resolve()).lower()
        chat = next((c for c in self.chats.list() if c.get("project") and str(Path(c["project"]).resolve()).lower() == key), None)
        if chat is None:
            chat = self.chats.create(proj["name"], project=proj["path"])
        self.open_chat(chat["id"])
        return chat

    def projects_dialog(self):
        d = Dialog(self, "Projetos", 600, 520)
        tk.Label(d.body, text="Abra um projeto de programação: o Gota trabalha dentro da pasta dele, em etapas (lê, planeja, escreve, testa e corrige).", bg=SURFACE, fg=MUTED,
                 font=("Segoe UI", 10), wraplength=550, justify="left").pack(anchor="w", pady=(0, 8))
        lb = tk.Listbox(d.body, bg=SURFACE2, fg=TEXT, selectbackground=PRIMARY, relief="flat", font=FONT, activestyle="none", bd=0, highlightthickness=0)
        lb.pack(fill="both", expand=True)
        shown = []

        def refresh():
            lb.delete(0, "end")
            shown.clear()
            for p in projects_mod.recent(self.settings):
                shown.append(p)
                lb.insert("end", f"  📁 {p['name']}      {p['path']}")
            if not shown:
                lb.insert("end", "  (nenhum projeto ainda: crie um ou importe uma pasta)")
        refresh()

        def current():
            sel = lb.curselection()
            return shown[sel[0]] if sel and sel[0] < len(shown) else None

        def open_it(_=None):
            p = current()
            if p:
                d.destroy()
                self.open_project(p["path"])

        def forget():
            p = current()
            if p:
                projects_mod.forget(self.settings, p["path"])
                refresh()
        lb.bind("<Double-Button-1>", open_it)
        row = tk.Frame(d.body, bg=SURFACE)
        row.pack(fill="x", pady=(12, 0))
        RoundButton(row, "＋  Criar projeto", lambda: (d.destroy(), self.create_project_dialog()), bg=PRIMARY, hover=PRIMARY_HOVER, parent_bg=SURFACE, height=36).pack(side="left")
        RoundButton(row, "Abrir", open_it, parent_bg=SURFACE, height=36).pack(side="left", padx=8)
        RoundButton(row, "Tirar da lista", forget, bg=SURFACE, hover=HOVER, parent_bg=SURFACE, height=36).pack(side="left")
        small = tk.Frame(d.body, bg=SURFACE)
        small.pack(fill="x", pady=(8, 0))
        tk.Label(small, text="Já tem um projeto feito por você ou por outra IA?", bg=SURFACE, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        RoundButton(small, "⤓ Importar existente", lambda: (d.destroy(), self.import_project()), bg=SURFACE2, hover=HOVER, fg=MUTED, parent_bg=SURFACE, height=26, font=("Segoe UI", 9)).pack(side="right")

    def create_project_dialog(self):
        d = Dialog(self, "Criar projeto", 580, 500)
        tk.Label(d.body, text="Nome do projeto", bg=SURFACE, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w")
        name = tk.Entry(d.body, bg=SURFACE2, fg=TEXT, insertbackground=TEXT, relief="flat", font=FONT)
        name.pack(fill="x", ipady=7, pady=(2, 10))
        tk.Label(d.body, text="Criar dentro da pasta", bg=SURFACE, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w")
        where_row = tk.Frame(d.body, bg=SURFACE)
        where_row.pack(fill="x", pady=(2, 10))
        default_parent = Path.home() / "Documents" / "Projetos Gota"
        where = tk.Entry(where_row, bg=SURFACE2, fg=TEXT, insertbackground=TEXT, relief="flat", font=FONT)
        where.insert(0, str(default_parent))
        where.pack(side="left", fill="x", expand=True, ipady=7)

        def choose():
            f = filedialog.askdirectory(title="Pasta onde o projeto será criado", parent=d, initialdir=str(Path(where.get()).parent if Path(where.get()).parent.exists() else Path.home()))
            if f:
                where.delete(0, "end")
                where.insert(0, f)
        RoundButton(where_row, "Escolher…", choose, parent_bg=SURFACE, height=34).pack(side="left", padx=(8, 0))
        tk.Label(d.body, text="O que você quer construir? (opcional)", bg=SURFACE, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w")
        desc = tk.Text(d.body, bg=SURFACE2, fg=TEXT, insertbackground=TEXT, relief="flat", font=FONT, height=6, wrap="word", padx=10, pady=8, bd=0)
        desc.pack(fill="both", expand=True, pady=(2, 8))
        start = tk.BooleanVar(value=True)
        tk.Checkbutton(d.body, text="Pedir ao Gota para começar agora", variable=start, bg=SURFACE, fg=TEXT, selectcolor=SURFACE2, activebackground=SURFACE, activeforeground=TEXT).pack(anchor="w")

        def make():
            n, text = name.get().strip(), desc.get("1.0", "end").strip()
            if not n:
                messagebox.showinfo("Gota", "Dê um nome ao projeto.", parent=d)
                return
            try:
                folder = projects_mod.create(where.get().strip() or default_parent, n, text)
            except Exception as e:
                messagebox.showerror("Gota", str(e), parent=d)
                return
            d.destroy()
            self.open_project(folder)
            if start.get() and text:
                self.entry.set(f"Vamos começar. {text}")
                self.after(300, self.send)
        RoundButton(d.body, "Criar projeto", make, bg=PRIMARY, hover=PRIMARY_HOVER, parent_bg=SURFACE, height=38).pack(anchor="e", pady=(8, 0))
        name.focus_set()

    def import_project(self):
        """Opens a project that already exists (made by you or by another AI/tool): registers the folder and shows its structure."""
        f = filedialog.askdirectory(title="Escolha a pasta do projeto que já existe", parent=self)
        if not f:
            return
        chat = self.open_project(f)
        name = Path(f).name

        def work():
            try:
                tree = self.brain.agent.t_repo_map(f, 2)
            except Exception as e:
                tree = f"(não consegui mapear: {e})"
            self.chats.append(chat["id"], "gota", f"Importei o projeto **{name}**. Este é o mapa que vi:\n```\n{tree}\n```\nDiga o que quer fazer nele (corrigir, acrescentar uma função, criar testes, entender o código…) e eu trabalho em etapas, pedindo permissão uma vez para editar essa pasta.")
            self.ui(lambda: self.open_chat(chat["id"]) if self.settings.get("current_chat") == chat["id"] else None)
        threading.Thread(target=work, daemon=True).start()

    def open_in_vscode(self):
        if not self.project:
            return
        if vscode_mod.find_code() is None:
            return self.install_vscode(then=lambda: self.open_in_vscode())
        try:
            vscode_mod.open_path(self.project)
        except Exception as e:
            messagebox.showerror("Gota", f"Não consegui abrir o VS Code: {e}", parent=self)

    def install_vscode(self, then=None):
        """VS Code is missing: asks permission, downloads Microsoft's official installer and installs it for this user."""
        try:
            _, size = vscode_mod.installer_info()
        except Exception:
            size = 0
        if not messagebox.askyesno("Instalar o VS Code", "O VS Code ainda não está instalado neste computador.\n\nBaixar e instalar agora?\n\n"
                                   f"Origem: Microsoft (update.code.visualstudio.com), cerca de {size // (1024 * 1024) or 230} MB.\nInstalação só para o seu usuário, sem precisar de administrador.", parent=self):
            return

        def progress(pct):
            self.ui(lambda: self.dl_label.winfo_exists() and self.dl_label.configure(text=f"💻 Instalando o VS Code… {pct}%"))

        def work():
            try:
                found = vscode_mod.install_vscode(progress)
            except Exception as e:
                found, err = None, str(e)
            else:
                err = ""

            def done():
                if self.dl_label.winfo_exists():
                    self.dl_label.configure(text="")
                if found:
                    messagebox.showinfo("Gota", "VS Code instalado.", parent=self)
                    then and then()
                else:
                    messagebox.showerror("Gota", "Não consegui instalar o VS Code." + (f"\n{err}" if err else ""), parent=self)
            self.ui(done)
        threading.Thread(target=work, daemon=True).start()

    def vscode_integration(self, on):
        """Turns on/off the local server for the Gota extension (and installs the extension when turning on)."""
        self.settings.set("vscode_server", bool(on))
        if on:
            port = self.vscode_server.start()
            try:
                vscode_mod.install()
            except Exception:
                pass
            return port
        self.vscode_server.stop()
        return None

    def rename_chat(self, cid, title, parent=None):
        new = simpledialog.askstring("Renomear conversa", "Novo nome da conversa:", initialvalue=title, parent=parent or self)
        if new and new.strip():
            self.chats.set_title(cid, new.strip()[:80])
            if self.settings.get("current_chat") == cid:
                self.title_label.configure(text=new.strip()[:80])
            self.build_sidebar()
            return True
        return False

    def chats_dialog(self):
        """A searchable list of every conversation: open, rename or delete one."""
        d = Dialog(self, "Conversas", 600, 560)
        tk.Label(d.body, text="Escolha uma conversa para abrir. Duplo clique abre.", bg=SURFACE, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 8))
        q = tk.StringVar()
        entry = tk.Entry(d.body, textvariable=q, bg=SURFACE2, fg=TEXT, insertbackground=TEXT, relief="flat", font=FONT)
        entry.pack(fill="x", ipady=7, pady=(0, 8))
        lb = tk.Listbox(d.body, bg=SURFACE2, fg=TEXT, selectbackground=PRIMARY, relief="flat", font=FONT, activestyle="none", bd=0, highlightthickness=0)
        lb.pack(fill="both", expand=True)
        shown = []

        def refresh(*_):
            lb.delete(0, "end")
            shown.clear()
            found = {h["id"]: h["snippet"] for h in self.chats.search(q.get())} if q.get().strip() else {}
            for c in self.chats.list():
                if c.get("project"):   # coding chats live under Projects only
                    continue
                if not q.get().strip() or tools.norm(q.get()) in tools.norm(c["title"]) or c["id"] in found:   # title or any message
                    shown.append(c)
                    when = datetime.fromtimestamp(c["updated"]).strftime("%d/%m %H:%M")
                    lb.insert("end", f"  {c['title'][:36]}   ·  {when}" + (f"   —  {found[c['id']][:46]}" if c["id"] in found else f"   ·  {len(c['messages'])} msg"))
        q.trace_add("write", refresh)
        refresh()

        def current():
            sel = lb.curselection()
            return shown[sel[0]] if sel else None

        def open_it(_=None):
            c = current()
            if c:
                d.destroy()
                self.open_chat(c["id"])

        def rename():
            c = current()
            if c and c["id"] != store.VOICE_CHAT and self.rename_chat(c["id"], c["title"], parent=d):
                refresh()

        def delete():
            c = current()
            if c and messagebox.askyesno("Apagar conversa", f"Apagar \"{c['title']}\"?", parent=d):
                self.chats.delete(c["id"])
                if self.settings.get("current_chat") == c["id"]:
                    self.new_chat()
                self.build_sidebar()
                refresh()
        lb.bind("<Double-Button-1>", open_it)
        row = tk.Frame(d.body, bg=SURFACE)
        row.pack(fill="x", pady=(12, 0))
        RoundButton(row, "Abrir", open_it, bg=PRIMARY, hover=PRIMARY_HOVER, parent_bg=SURFACE, height=34).pack(side="left")
        RoundButton(row, "Renomear", rename, parent_bg=SURFACE, height=34).pack(side="left", padx=8)
        RoundButton(row, "Apagar", delete, bg=RED, hover="#F0686C", parent_bg=SURFACE, height=34).pack(side="right")
        entry.focus_set()

    def delete_chat(self, cid, title):
        if messagebox.askyesno("Apagar conversa", f"Apagar \"{title}\"?", parent=self):
            self.chats.delete(cid)
            if self.settings.get("current_chat") == cid:
                self.settings.set("current_chat", "")
                self.show_chat()
            else:
                self.build_sidebar()

    def new_chat(self):
        self.open_chat(self.chats.create()["id"])

    def open_chat(self, cid):
        self.settings.set("current_chat", cid)
        self.clear_attachment()
        chat = self.chats.get(cid) or self.chats.create()
        self.title_label.configure(text=("🎙  " if cid == store.VOICE_CHAT else "") + chat["title"])
        self.project = chat.get("project") if chat.get("project") and Path(chat["project"]).exists() else None
        self._project_ui()
        self.sub_label.configure(text=f"{len(chat['messages'])} mensagens" if chat["messages"] else "conversa nova")
        for w in self.msgs.winfo_children():
            w.destroy()
        if not chat["messages"]:
            now = datetime.now()
            salute = "Bom dia" if 5 <= now.hour < 12 else "Boa tarde" if now.hour < 18 else "Boa noite"
            serve = {"senhora": "servi-la", "": "ajudar"}.get(self.profile.treatment, "servi-lo")
            self.add_message("gota", f"{salute}, {self.profile.address()}. Em que posso {serve}?")
        for m in chat["messages"]:
            self.add_message(m["role"], m["text"], m.get("image"), m.get("steps"))
        self.build_sidebar()
        self.to_bottom()
        self.after(400, lambda: self.warm_chat(cid))

    def _project_ui(self):
        """The open chat is (or is not) a coding chat: change the hint of the message box and show/hide the Files panel."""
        if not hasattr(self, "entry"):
            return
        self.entry.hint = "Diga ao Gota o que desenvolver neste projeto…" if self.project else "Escreva para o Gota…"
        self.entry._hint(True)
        self._update_right()
        self.files_refresh(reset=True)

    def add_message(self, role, text, image=None, steps=None):
        mine = role == "user"
        if image and Path(image).exists():
            try:
                img = Image.open(image)
                img.thumbnail((380, 380))
                photo = ImageTk.PhotoImage(img)
                row = tk.Frame(self.msgs, bg=BG)
                lab = tk.Label(row, image=photo, bg=BG, bd=0, cursor="hand2")
                lab.image = photo
                lab.pack(side="right" if mine else "left")
                lab.bind("<Button-1>", lambda e, p=image: os.startfile(p))
                row.pack(fill="x", padx=44, pady=6)
            except Exception:
                pass
        if text.strip():
            row = tk.Frame(self.msgs, bg=BG)
            row.pack(fill="x", padx=44, pady=6)
            if not mine:   # the assistant's avatar beside its answer
                tk.Label(row, image=sprites().frame("logo", 30, BG), bg=BG, bd=0).pack(side="left", anchor="n", padx=(0, 10), pady=(4, 0))
            bubble(row, text, mine, self.maxw(plain=not mine)).pack(side="right" if mine else "left")
        if steps and not mine:
            self._steps_card(steps)
        self.to_bottom()

    FILE_TOOLS = ("file", "dir", "move", "rename", "report", "archive", "convert", "notebook", "search_files", "regex", "repo_map", "edit", "write", "read")
    COMMAND_TOOLS = ("command", "git", "tests", "bash", "powershell", "run_", "schedule", "monitor", "process", "disk", "system", "env", "sql")
    WEB_TOOLS = ("web_", "http", "browser", "kb_learn", "github", "mcp")

    @classmethod
    def _step_symbol(cls, line):
        """📄 for files, ❯ for commands, 🌐 for the web, • for the rest (by the name of the tool the agent used)."""
        name = line.split(" ", 1)[0].lower()
        if any(k in name for k in cls.WEB_TOOLS):
            return "🌐"
        if any(k in name for k in cls.COMMAND_TOOLS):
            return "❯"
        if any(k in name for k in cls.FILE_TOOLS):
            return "📄"
        return "•"

    def _steps_card(self, steps):
        """A collapsible card listing what the agent did ("Executou 3 ações"), like Claude's tool cards."""
        row = tk.Frame(self.msgs, bg=BG)
        row.pack(fill="x", padx=32, pady=(0, 6))
        card = tk.Frame(row, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1, bd=0)
        card.pack(side="left", fill="x", expand=True)
        head = tk.Label(card, text=f"⚙  Executou {len(steps)} ação{'ões' if len(steps) != 1 else ''}   ▸", bg=SURFACE, fg=MUTED, font=("Segoe UI", 10), anchor="w", padx=14, pady=8, cursor="hand2")
        head.pack(fill="x")
        body = tk.Frame(card, bg=SURFACE)
        for line in steps:
            tk.Label(body, text=f"{self._step_symbol(line)}  {line}", bg=SURFACE, fg=MUTED, font=("Consolas", 9), anchor="w", justify="left", padx=14,
                     wraplength=self.maxw(True) - 40).pack(fill="x", pady=1)

        def toggle(_=None):
            if body.winfo_ismapped():
                body.pack_forget()
                head.configure(text=head.cget("text").replace("▾", "▸"))
            else:
                body.pack(fill="x", pady=(0, 10))
                head.configure(text=head.cget("text").replace("▸", "▾"))
        head.bind("<Button-1>", toggle)

    # ------------------------------------------------------------------ sending
    def send(self):
        text, image = self.entry.get(), self.pending_image
        if not text and not image:
            return
        if self.dictating:
            self.toggle_dictation()
        self.entry.clear()
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
        row = tk.Frame(self.msgs, bg=BG)
        row.pack(fill="x", padx=44, pady=6)
        pill = tk.Canvas(row, bg=BG, highlightthickness=0, bd=0, width=340, height=54)
        rounded(pill, 0, 0, 340, 54, 18, fill=SURFACE2, outline="")
        self.thinking_cat = CatView(pill, size=40, bg=SURFACE2)
        self.thinking_cat.play("anim_cat_read")
        pill.create_window(30, 27, window=self.thinking_cat)
        self.status_label = tk.Label(pill, text="Pensando...", bg=SURFACE2, fg=MUTED, font=("Segoe UI", 10), anchor="w", width=34)
        pill.create_window(58, 27, window=self.status_label, anchor="w")
        pill.pack(side="left")
        self.thinking = row
        self.to_bottom()
        self.typing = True
        my = self.turn
        proj = self.project
        self.set_activity("Pensando…")

        def phase(p):
            self.ui(lambda: (self.thinking_cat.winfo_exists() and self.thinking_cat.play("anim_cat_paint" if p == "drawing" else "anim_cat_read"), my == self.turn and self.set_activity(self.PHASE_TEXT.get(p, "Pensando…"))))

        def work():
            self.brain.on_partial = lambda t: my == self.turn and self._live_update(my, t)
            self.brain.agent.last_steps = []
            try:
                reply, img = self.brain.run(text, history, cid, image, on_phase=phase, project=proj)
            except Exception as e:
                reply, img = f"Perdão, {self.profile.sir()}, tive um problema: {e}", None
            finally:
                self.brain.on_partial = None
            if my != self.turn:   # cancelled while it was working
                return
            steps = list(self.brain.agent.last_steps)
            self.chats.append(cid, "gota", reply, img, steps=steps)

            def done():
                self.typing = False
                self.set_activity(None)
                self._live_clear()
                self._plan_clear()
                self.files_refresh()
                if self.thinking.winfo_exists():
                    self.thinking.destroy()
                if self.settings.get("current_chat") == cid:
                    self.add_message("gota", reply, img, steps)
                    self.build_sidebar()
                chat = self.chats.get(cid)
                if chat and chat["title"] == "Nova conversa" and sum(1 for m in chat["messages"] if m["role"] == "user") == 1:
                    threading.Thread(target=self.auto_title, args=(cid, text, reply), daemon=True).start()
            self.ui(done)
        threading.Thread(target=work, daemon=True).start()

    def auto_title(self, cid, question, reply):
        """Names a new chat from its first message, like Gemini or ChatGPT do: a short title written by the model."""
        title = ""
        try:
            if self.gemma is not None:
                raw = self.gemma.one_shot(
                    "Você cria títulos curtos para conversas, como o ChatGPT e o Gemini. Responda SOMENTE com o título: de 2 a 5 palavras, em português do Brasil, "
                    "sem aspas, sem ponto final e sem emojis, resumindo o assunto da conversa (não copie a pergunta palavra por palavra).",
                    f"Primeira mensagem do usuário: {question[:400]}\nResposta do assistente: {reply[:300]}")
                data = brain_mod.Brain.extract_json(raw)
                raw = str((data or {}).get("text") or raw)
                title = raw.strip().splitlines()[0].strip().strip("\"'“”‘’*#. ") if raw.strip() else ""
        except Exception:
            pass
        if not title or len(title) > 60:
            title = question.strip().splitlines()[0][:40] if question.strip() else "Conversa"
        title = title[:1].upper() + title[1:]
        self.chats.set_title(cid, title)

        def refresh():
            if self.settings.get("current_chat") == cid:
                self.title_label.configure(text=title)
            self.build_sidebar()
        self.ui(refresh)

    def attach(self):
        f = filedialog.askopenfilename(title="Anexar imagem", filetypes=[("Imagens", "*.png *.jpg *.jpeg *.webp *.bmp")], parent=self)
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
        lab.pack(side="left", pady=(0, 4))
        tk.Button(self.attach_row, text="✕ remover imagem", command=self.clear_attachment, bg=BG, fg=MUTED, relief="flat", bd=0, cursor="hand2", activebackground=BG).pack(side="left", padx=8)

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
            self.speaker.english = self.settings.get("english_speech") is not False
            self.speaker.on_state = lambda on: self.ui(widgets_mod.set_speaking, on)   # the cat's mouth moves only while the voice is playing
        return self.speaker

    def toggle_dictation(self):
        if self.dictating:
            self.dictating = False
            self.listener.cancel.set()
            self.mic.set(bg=SURFACE2, hover=HOVER)
            return
        self.dictating = True
        self.mic.set(bg=RED, hover="#F0686C")
        base = self.entry.get()

        def work():
            text = base
            try:
                while self.dictating:
                    heard = self.listener.listen(lambda p: self.ui(lambda: self.entry.set((text + " " + p).strip())), silence=1.0, timeout=60)
                    if heard:
                        text = (text + " " + heard).strip()
                        self.ui(lambda t=text: self.entry.set(t))
            except Exception as e:
                self.ui(lambda: messagebox.showerror("Microfone", f"Não consegui usar o microfone:\n{e}", parent=self))
            self.ui(lambda: (setattr(self, "dictating", False), self.mic.set(bg=SURFACE2, hover=HOVER)))
        threading.Thread(target=work, daemon=True).start()

    def summon(self):
        """Calls Gota: the cat slides up over whatever is on screen, listens, answers aloud, slides down."""
        if self.call is not None:  # never on top of a call
            return
        if self.busy:              # pressing the shortcut again cancels the previous one
            return self.cancel_current()
        if self.gemma is None:
            return
        self.busy = True
        self.turn += 1
        self.voice_question = None
        self.set_activity("Ouvindo…")
        self.overlay.show(f"Pois não, {self.profile.sir()}?", "anim_cat_listen")
        threading.Thread(target=lambda: winsound.Beep(880, 90), daemon=True).start()
        threading.Thread(target=self._voice_turn, daemon=True).start()

    def _voice_turn(self):
        sp = self.get_speaker()
        my = self.turn

        def level(pk):
            if not self.voice_question:
                bars = min(8, pk // 600)
                self.ui(lambda: self.overlay.set(f"Ouvindo… 🎙 {'▮' * bars}{'▯' * (8 - bars)}"))
        try:
            heard = self.listener.listen(lambda p: self.ui(lambda: self.overlay.set(f"“{p}”")), silence=0.9, timeout=8, on_level=level)
        except Exception as e:
            self.ui(lambda: self.overlay.set(f"Perdão, não consegui usar o microfone: {e}", "anim_cat_idle"))
            self.ui(self.overlay.hide_later, 4000)
            self.busy = False
            return
        if my != self.turn:
            return
        if not heard:
            why = self.listener.explain_silence()
            self.ui(lambda: self.overlay.set(f"Perdão, não ouvi. {why}", "anim_cat_idle"))
            self.ui(self.overlay.hide_later, 7000)
            self.busy = False
            return
        text = brain_mod.strip_wake_word(heard)
        self.voice_question = text
        history = [("user" if m["role"] == "user" else "model", m["text"]) for m in self.chats.voice()["messages"]]
        self.chats.append(store.VOICE_CHAT, "user", text)
        self.ui(lambda: self.overlay.set(f"“{text}”", "anim_cat_read"))

        def phase(p):
            if p == "searching":
                sp.speak(f"Um momento, {self.profile.sir()}. Vou pesquisar.")
            self.ui(lambda: self.overlay.cat.play("anim_cat_paint" if p == "drawing" else "anim_cat_read") if self.overlay.visible else None)
            self.ui(lambda: my == self.turn and self.set_activity(self.PHASE_TEXT.get(p, "Pensando…")))
        self.ui(lambda: self.set_activity("Pensando…"))
        feeder, last = voice.SentenceFeeder(sp), {"t": 0.0}

        def partial(t):
            if my != self.turn:
                return
            feeder.feed(t)
            if time.time() - last["t"] > 0.15:
                last["t"] = time.time()
                self.ui(lambda: self.overlay.set(t, "anim_cat_talk") if my == self.turn else None)
        self.brain.on_partial = partial
        try:
            reply, img = self.brain.run(text, history, store.VOICE_CHAT, spoken=True, on_phase=phase)
        finally:
            self.brain.on_partial = None
        if my != self.turn:
            return
        self.chats.append(store.VOICE_CHAT, "gota", reply, img)
        self.voice_question = None

        def done():
            if my != self.turn:
                return
            self.ui(lambda: self.set_activity(None))
            self.ui(lambda: self.overlay.cat.play("anim_cat_idle") if self.overlay.visible else None)
            self.ui(self.overlay.hide_later, 700)
            self.busy = False
            if self.settings.get("current_chat") == store.VOICE_CHAT:
                self.ui(lambda: self.open_chat(store.VOICE_CHAT))
        self.ui(lambda: (self.overlay.set(reply, "anim_cat_talk"), self.set_activity("Falando…")))
        feeder.finish(reply, done)

    def start_call(self):
        if self.call is not None or self.gemma is None or self.busy:
            return
        self.wake_stop.set()  # the "Hey Gota" listener must not share the microphone (or the screen) with the call
        if self.overlay.visible:
            self.overlay.hide()
        self.call = CallPopup(self)

    def toggle_call(self):
        """Ctrl+Alt+L: starts a call, or hangs up the one in progress."""
        if self.call is not None:
            self.call.hang_up()
        else:
            self.start_call()

    # ------------------------------------------------------------------ hotkey, "Hey Gota", tray, downloads
    def warm_chat(self, cid=None):
        """Pre-reads the model's instructions and the chat in the background: the first message after opening, switching or calling is not slow."""
        if self.gemma is None:
            return
        cid = cid or self.settings.get("current_chat")
        chat = self.chats.get(cid) if cid else None
        history = [("user" if m["role"] == "user" else "model", m["text"]) for m in (chat["messages"] if chat else [])]
        self.brain.warm(cid or "warm", history)

    def setup_background(self):
        self.after(1500, self.warm_chat)
        if self.settings.get("vscode_server"):
            try:
                self.vscode_server.start()
            except Exception:
                pass
        self.after(30000, lambda: self.warm_chat(store.VOICE_CHAT))   # so the first Ctrl+Alt+G is quick too
        if self.hotkey is None:
            try:
                self.hotkey = voice.Hotkey(self.settings.get("hotkey") or HOTKEY_DEFAULT, lambda: self.ui(self.summon))
                if not self.hotkey.registered:
                    messagebox.showwarning("Gota", "Outro programa já usa o atalho Ctrl+Alt+G. Use o botão \"Chamar\" ou o \"Hey Gota\".", parent=self)
            except Exception:
                pass
        if self.call_hotkey is None:
            try:
                self.call_hotkey = voice.Hotkey(self.settings.get("call_hotkey") or CALL_HOTKEY_DEFAULT, lambda: self.ui(self.toggle_call))
                if not self.call_hotkey.registered:
                    messagebox.showwarning("Gota", "Outro programa já usa o atalho Ctrl+Alt+L. Use o botão \"Ligar\" da janela.", parent=self)
            except Exception:
                pass
        if self.tray is None:
            self.make_tray()
        if self.settings.get("hey_gota"):
            self.start_wake()
        # the painter is fetched in the background so it is already here when the first picture is asked for
        threading.Thread(target=lambda: tools.is_online() and self.images.start_download(), daemon=True).start()
        threading.Thread(target=lambda: tools.is_online() and self.listener.download_whisper(), daemon=True).start()

    def toggle_hey(self, value):
        self.settings.set("hey_gota", value)
        if value:
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
                                pystray.MenuItem("Ligar agora", lambda: self.ui(self.toggle_call)),
                                pystray.MenuItem("Sair", lambda: self.ui(self.quit_app)))
            self.tray = pystray.Icon("Gota", img, "Gota — Ctrl+Alt+G chama, Ctrl+Alt+L liga", menu)
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
            self.call_hotkey and self.call_hotkey.stop()
            self.vscode_server.stop()
            self.tray and self.tray.stop()
        except Exception:
            pass
        os._exit(0)

    def toast(self, title, text):
        """A Windows notification (from the tray icon); when there is no tray icon, Gota's own bubble."""
        def show():
            try:
                if self.tray:
                    self.tray.notify(text[:250], title)
                    return
            except Exception:
                pass
            self.overlay.show(f"{title}: {text[:160]}", "anim_cat_talk")
            self.overlay.hide_later(6000)
        self.ui(show)

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
            sir = self.profile.sir().capitalize()
            msg = f"{sir}, atenção: {label}." if "%" in label else f"{sir}, é a hora: {label}."
            self.overlay.show(msg, "anim_cat_talk")
            self.get_speaker().speak(msg)
            self.overlay.hide_later(8000)
        self.ui(show)

    # ------------------------------------------------------------------ dialogs
    def edit_name(self):
        name = simpledialog.askstring("Gota", "Como devo chamá-lo?", initialvalue=self.profile.name, parent=self)
        if name and name.strip():
            t = messagebox.askyesno("Tratamento", "Chamar de \"senhor\"?\n\nSim = senhor   Não = senhora", parent=self)
            self.profile.set_name(name, "senhor" if t else "senhora")
            self.build_sidebar()

    def _list_dialog(self, title, hint, height=560):
        d = Dialog(self, title, 560, height)
        tk.Label(d.body, text=hint, bg=SURFACE, fg=MUTED, wraplength=500, justify="left", font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 8))
        return d

    def screens_dialog(self):
        """Lists the screens as Windows numbers them and lets him name each one by clicking it ("notebook", "monitor grande")."""
        d = self._list_dialog("Telas", "Clique em Identificar: aparece um aviso em cada tela. Clique no aviso da tela que quiser e escolha um apelido "
                                       "(ex.: notebook, monitor grande). Depois é só dizer \"olha o notebook\" ou \"manda um print do monitor grande\".", 520)
        box = tk.Frame(d.body, bg=SURFACE)
        box.pack(fill="both", expand=True)
        overlays = []

        def names():
            return dict(self.settings.get("screen_names") or {})

        def rename(m):
            cur = names().get(m["key"], "")
            nick = simpledialog.askstring("Apelido da tela", f"Apelido para a tela {m['n']} ({m['rect'][2] - m['rect'][0]}x{m['rect'][3] - m['rect'][1]}). Vazio remove:", initialvalue=cur, parent=d)
            if nick is None:
                return
            all_names = names()
            if nick.strip():
                all_names[m["key"]] = nick.strip()
            else:
                all_names.pop(m["key"], None)
            self.settings.set("screen_names", all_names)
            refresh()

        def close_overlays():
            for o in overlays:
                try:
                    o.destroy()
                except Exception:
                    pass
            overlays.clear()

        def refresh():
            for w in box.winfo_children():
                w.destroy()
            nick = names()
            for m in tools.monitors():
                row = tk.Frame(box, bg=SURFACE2)
                row.pack(fill="x", pady=4)
                w, h = m["rect"][2] - m["rect"][0], m["rect"][3] - m["rect"][1]
                tk.Label(row, text=nick.get(m["key"]) or f"Tela {m['n']}", bg=SURFACE2, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(side="left", padx=12, pady=10)
                tk.Label(row, text=(f"tela {m['n']}  ·  " if nick.get(m["key"]) else "sem apelido  ·  ") + f"{m['where']}  ·  {w}x{h}", bg=SURFACE2, fg=MUTED, font=("Segoe UI", 10)).pack(side="left", padx=4)
                RoundButton(row, "Apelido", lambda m=m: rename(m), parent_bg=SURFACE2).pack(side="right", padx=8, pady=6)

        def identify():
            close_overlays()
            for m in tools.monitors():
                l, t, r, b = m["rect"]
                o = tk.Toplevel(self)
                overlays.append(o)
                o.overrideredirect(True)
                o.attributes("-topmost", True)
                o.attributes("-alpha", 0.88)
                o.configure(bg=BG, cursor="hand2")
                o.geometry(f"{r - l}x{b - t}+{l}+{t}")
                tk.Label(o, text=names().get(m["key"]) or str(m["n"]), bg=BG, fg=TEXT, font=("Segoe UI", 110, "bold")).pack(expand=True, pady=(0, 0))
                tk.Label(o, text="Clique aqui para dar um apelido a esta tela   (Esc cancela)", bg=BG, fg=MUTED, font=("Segoe UI", 20)).pack(pady=(0, 120))

                def pick(_e=None, m=m):
                    close_overlays()
                    rename(m)
                for w in (o, *o.winfo_children()):
                    w.bind("<Button-1>", pick)
                o.bind("<Escape>", lambda _e: close_overlays())
                o.focus_force()
        refresh()
        row = tk.Frame(d.body, bg=SURFACE)
        row.pack(fill="x", pady=(10, 0))
        RoundButton(row, "Identificar telas", identify, bg=PRIMARY, hover=PRIMARY_HOVER, parent_bg=SURFACE).pack(side="left")
        d.bind("<Destroy>", lambda e: close_overlays() if e.widget is d else None)

    def aliases_dialog(self):
        d = self._list_dialog("Apelidos de programas", 'Dê apelidos aos seus programas. Ex.: "whats 2" abre o WhatsApp que você escolher. Dê dois cliques num programa.')
        q = tk.StringVar()
        tk.Entry(d.body, textvariable=q, bg=SURFACE2, fg=TEXT, insertbackground=TEXT, relief="flat", font=FONT).pack(fill="x", ipady=7, pady=(0, 8))
        lb = tk.Listbox(d.body, bg=SURFACE2, fg=TEXT, selectbackground=PRIMARY, relief="flat", font=FONT, activestyle="none", bd=0, highlightthickness=0)
        lb.pack(fill="both", expand=True)
        aliases, shown = self.settings.get("aliases"), []

        def refresh(*_):
            lb.delete(0, "end")
            shown.clear()
            for name, _t in tools.installed_apps():
                if tools.norm(q.get()) in tools.norm(name):
                    nick = next((k for k, v in aliases.items() if v == name), "")
                    shown.append(name)
                    lb.insert("end", f"  {name}" + (f"     🏷 {nick}" if nick else ""))
        q.trace_add("write", refresh)
        refresh()

        def edit(_=None):
            sel = lb.curselection()
            if not sel:
                return
            name = shown[sel[0]]
            old = next((k for k, v in aliases.items() if v == name), "")
            nick = simpledialog.askstring("Apelido", f"Apelido para {name} (vazio remove):", initialvalue=old, parent=d)
            if nick is None:
                return
            aliases.pop(old, None)
            if nick.strip():
                aliases[nick.strip().lower()] = name
            self.settings.set("aliases", aliases)
            refresh()
        lb.bind("<Double-Button-1>", edit)

    def kb_dialog(self):
        d = self._list_dialog("Base de conhecimento", "Tudo o que eu sei de TI e o que aprendi pela internet. Quando não sei algo, eu pesquiso, guardo aqui e respondo a partir disso. Duplo clique abre a nota.", 600)
        lb = tk.Listbox(d.body, bg=SURFACE2, fg=TEXT, selectbackground=PRIMARY, relief="flat", font=FONT, activestyle="none", bd=0, highlightthickness=0)
        lb.pack(fill="both", expand=True)

        def refresh():
            lb.delete(0, "end")
            for n in kb.listing():
                lb.insert("end", "  " + n)
        refresh()
        lb.bind("<Double-Button-1>", lambda e: lb.curselection() and os.startfile(kb.KB_DIR / (lb.get(lb.curselection()[0]).strip() + ".md")))
        row = tk.Frame(d.body, bg=SURFACE)
        row.pack(fill="x", pady=(12, 0))

        def learn():
            topic = simpledialog.askstring("Aprender", "Sobre o que devo pesquisar e aprender?", parent=d)
            if topic:
                def work():
                    saved = self.brain.learn_topic(topic, self._status)
                    self.ui(lambda: (messagebox.showinfo("Gota", f"Guardei {len(saved)} nota(s)." if saved else "Não consegui material (sem internet?).", parent=self), refresh()))
                threading.Thread(target=work, daemon=True).start()

        def add_note():
            title = simpledialog.askstring("Nova nota", "Título:", parent=d)
            text = title and simpledialog.askstring("Nova nota", "Conteúdo:", parent=d)
            if title and text:
                kb.add(title, text)
                refresh()
        def download_docs():
            if not messagebox.askyesno("Baixar documentações", "Baixar da internet as documentações de TI (Veeam, VMware, Hyper-V, Nutanix, Windows, Linux, redes, segurança, linguagens, "
                                       "contêineres, nuvem...) e guardar neste computador?\n\nPode levar cerca de 15 minutos e continua em segundo plano; quem já foi baixado é pulado.", parent=d):
                return

            def work():
                from . import docpack
                _, n = docpack.run(self._status)
                self.ui(lambda: (self._status(""), refresh()))
            threading.Thread(target=work, daemon=True).start()
        RoundButton(row, "Pesquisar e aprender…", learn, bg=PRIMARY, hover=PRIMARY_HOVER, parent_bg=SURFACE).pack(side="left")
        RoundButton(row, "Baixar documentações", download_docs, parent_bg=SURFACE).pack(side="left", padx=(8, 0))
        RoundButton(row, "Anotar", add_note, parent_bg=SURFACE).pack(side="left", padx=8)
        RoundButton(row, "Abrir pasta", lambda: os.startfile(kb.KB_DIR), parent_bg=SURFACE).pack(side="right")

    def connections_dialog(self):
        """Connect WhatsApp (scan a QR code once) and Outlook (sign in with the Microsoft account) inside Gota."""
        d = Dialog(self, "Conexões", 600, 720)
        tk.Label(d.body, text="Conecte uma vez e depois é só pedir: “manda um print da tela 2 pro João no WhatsApp”, “qual a minha agenda de hoje no Outlook?”. "
                              "Tudo fica só neste computador.", bg=SURFACE, fg=MUTED, wraplength=550, justify="left", font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 10))
        wa, ol = self.brain.whatsapp, self.brain.outlook

        def card(title):
            box = tk.Frame(d.body, bg=SURFACE2)
            box.pack(fill="x", pady=6)
            head = tk.Frame(box, bg=SURFACE2)
            head.pack(fill="x", padx=16, pady=(12, 0))
            tk.Label(head, text=title, bg=SURFACE2, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(side="left")
            state = tk.Label(head, text="", bg=SURFACE2, font=("Segoe UI", 10, "bold"))
            state.pack(side="right")
            info = tk.Label(box, text="", bg=SURFACE2, fg=MUTED, wraplength=520, justify="left", font=("Segoe UI", 10), anchor="w")
            info.pack(fill="x", padx=16, pady=(4, 0))
            row = tk.Frame(box, bg=SURFACE2)
            row.pack(fill="x", padx=16, pady=(10, 14))
            return state, info, row

        # ---------------------------------------------------------------- WhatsApp
        wa_state, wa_info, wa_row = card("💬  WhatsApp")
        wa_busy = {"on": False}

        def wa_refresh(msg=None):
            if not wa_state.winfo_exists():
                return
            on = wa.connected()
            wa_state.configure(text="● Conectado" if on else "○ Não conectado", fg=GREEN if on else MUTED)
            wa_info.configure(text=msg or ("Posso enviar mensagens e prints da tela aos seus contatos, sempre perguntando antes de enviar." if on else
                                           "Abro o WhatsApp Web numa janela do Microsoft Edge. No celular: WhatsApp > Aparelhos conectados > Conectar um aparelho, e escaneie o QR code."))
            for w in wa_row.winfo_children():
                w.destroy()
            if on:
                RoundButton(wa_row, "Desconectar", wa_disconnect, bg=SURFACE, hover=HOVER, parent_bg=SURFACE2, height=34).pack(side="left")
            else:
                RoundButton(wa_row, "Conectar WhatsApp", wa_connect, bg=GREEN, hover=GREEN_HOVER, fg="#06251A", parent_bg=SURFACE2, height=34).pack(side="left")

        def wa_connect():
            if wa_busy["on"]:
                return
            wa_busy["on"] = True
            wa_refresh("Abrindo o WhatsApp Web… aguarde o QR code e escaneie com o celular (tenho 4 minutos).")

            def work():
                try:
                    ok = wa.connect(lambda m: self.ui(lambda: wa_refresh(m)))
                    msg = None if ok else "Não deu tempo de conectar. Tente de novo e escaneie o QR code logo que aparecer."
                except Exception as e:
                    msg = f"Não consegui abrir o WhatsApp Web: {str(e)[:200]}"
                wa_busy["on"] = False
                self.ui(lambda: wa_refresh(msg))
            threading.Thread(target=work, daemon=True).start()

        def wa_disconnect():
            if messagebox.askyesno("WhatsApp", "Desconectar o WhatsApp do Gota? A sessão guardada neste computador será apagada.", parent=d):
                wa.disconnect()
                wa_refresh()
        wa_refresh()

        # ---------------------------------------------------------------- Outlook
        ol_state, ol_info, ol_row = card("📧  Outlook (e-mails e agenda)")
        ol_busy = {"on": False}

        def ol_refresh(msg=None):
            if not ol_state.winfo_exists():
                return
            on = ol.connected()
            ol_state.configure(text="● Conectado" if on else "○ Não conectado", fg=GREEN if on else MUTED)
            ol_info.configure(text=msg or (f"Conta: {ol.who()}. Leio sua agenda e seus e-mails (somente leitura): nada é enviado, apagado ou alterado." if on else
                                           "Entre com a sua conta Microsoft (trabalho, escola ou pessoal). A página de login da Microsoft abre no navegador e você digita um código curto."))
            for w in ol_row.winfo_children():
                w.destroy()
            if on:
                RoundButton(ol_row, "Sair da conta", ol_disconnect, bg=SURFACE, hover=HOVER, parent_bg=SURFACE2, height=34).pack(side="left")
            else:
                RoundButton(ol_row, "Entrar com a conta Microsoft", ol_connect, bg=PRIMARY, hover=PRIMARY_HOVER, parent_bg=SURFACE2, height=34).pack(side="left")
                RoundButton(ol_row, "Avançado", ol_advanced, bg=SURFACE, hover=HOVER, parent_bg=SURFACE2, height=34).pack(side="left", padx=8)

        def ol_connect():
            if ol_busy["on"]:
                return
            ol_busy["on"] = True

            def work():
                try:
                    flow = ol.begin_login()
                except Exception as e:
                    ol_busy["on"] = False
                    return self.ui(lambda: ol_refresh(f"Não consegui iniciar o login: {str(e)[:200]}"))
                code = flow["user_code"]

                def show():
                    ol_info.configure(text=f"1) A página da Microsoft vai abrir.  2) Digite este código:  {code}  (já copiei para a área de transferência).  3) Entre com a sua conta e aceite.", fg=TEXT)
                    for w in ol_row.winfo_children():
                        w.destroy()
                    RoundButton(ol_row, "Abrir a página de novo", lambda: webbrowser.open(flow["verification_uri"]), bg=SURFACE, hover=HOVER, parent_bg=SURFACE2, height=34).pack(side="left")
                    self.clipboard_clear()
                    self.clipboard_append(code)
                    webbrowser.open(flow["verification_uri"])
                self.ui(show)
                try:
                    who = ol.finish_login(flow)
                    msg = f"Conectado como {who}." if who else None
                except Exception as e:
                    msg = f"Login não concluído: {str(e)[:200]}"
                ol_busy["on"] = False
                self.ui(lambda: (ol_info.configure(fg=MUTED), ol_refresh(msg)))
            threading.Thread(target=work, daemon=True).start()

        def ol_disconnect():
            if messagebox.askyesno("Outlook", "Sair da conta Microsoft no Gota?", parent=d):
                ol.disconnect()
                ol_refresh()

        def ol_advanced():
            cid = simpledialog.askstring("Avançado", "ID de aplicativo (client ID) do Azure/Entra para o login. Deixe vazio para usar o padrão da Microsoft.\n"
                                         "Use só se a TI da sua empresa exigir um aplicativo próprio.", initialvalue=self.settings.get("outlook_client_id") or "", parent=d)
            if cid is not None:
                self.settings.set("outlook_client_id", cid.strip())
                ol._app = None   # rebuilt with the new id on the next login
        ol_refresh()

        # ---------------------------------------------------------------- VS Code
        vs_state, vs_info, vs_row = card("💻  VS Code (programar com o Gota)")

        def vs_refresh(msg=None):
            if not vs_state.winfo_exists():
                return
            on = self.vscode_server.running
            have = vscode_mod.find_code() is not None
            vs_state.configure(text=("● Ligado" if on else "○ Desligado"), fg=GREEN if on else MUTED)
            vs_info.configure(text=msg or (f"Servidor local na porta {self.vscode_server.port} (só este computador, com senha). A extensão do Gota está no VS Code: reabra o VS Code e use o menu Gota (botão direito) ou Ctrl+Alt+K." if on else
                                          ("Liga o servidor local e instala a extensão do Gota no VS Code (explicar, corrigir, refatorar, testar e gerar código)." if have else
                                           "O VS Code não está instalado. O Gota pode baixar e instalar para você (com a sua permissão).")))
            for w in vs_row.winfo_children():
                w.destroy()
            if not have:
                RoundButton(vs_row, "Instalar o VS Code", lambda: self.install_vscode(then=vs_refresh), bg=PRIMARY, hover=PRIMARY_HOVER, parent_bg=SURFACE2, height=34).pack(side="left")
            if on:
                RoundButton(vs_row, "Desligar", lambda: (self.vscode_integration(False), vs_refresh()), bg=SURFACE, hover=HOVER, parent_bg=SURFACE2, height=34).pack(side="left", padx=(0 if have else 8, 0))
            else:
                RoundButton(vs_row, "Ligar integração", lambda: (self.vscode_integration(True), vs_refresh()), bg=GREEN, hover=GREEN_HOVER, fg="#06251A", parent_bg=SURFACE2, height=34).pack(side="left", padx=(0 if have else 8, 0))
        vs_refresh()

        tk.Label(d.body, text="O WhatsApp usa o WhatsApp Web (não oficial): se o WhatsApp mudar o site, esse recurso pode precisar de atualização. "
                              "O Outlook usa a API oficial da Microsoft.", bg=SURFACE, fg=MUTED, wraplength=550, justify="left", font=("Segoe UI", 9)).pack(anchor="w", pady=(8, 0))

    def skills_dialog(self):
        d = self._list_dialog("Habilidades", "Procedimentos passo a passo que eu sigo quando o seu pedido combina com eles (ex.: job do Veeam com falha, conta do AD bloqueada). "
                                              "Dê dois cliques para ler ou editar. Você pode criar as suas: elas valem mais que as que já vêm comigo.", 560)
        lb = tk.Listbox(d.body, bg=SURFACE2, fg=TEXT, selectbackground=PRIMARY, relief="flat", font=FONT, activestyle="none", bd=0, highlightthickness=0)
        lb.pack(fill="both", expand=True)
        shown = []

        def refresh():
            lb.delete(0, "end")
            shown.clear()
            for sk in skills_mod.load_all():
                shown.append(sk)
                lb.insert("end", f"  {sk['name']}   ·   {'sua' if sk['source'] == 'sua' else 'embutida'}")
        refresh()
        lb.bind("<Double-Button-1>", lambda e: lb.curselection() and os.startfile(shown[lb.curselection()[0]]["path"]))
        row = tk.Frame(d.body, bg=SURFACE)
        row.pack(fill="x", pady=(12, 0))

        def new_skill():
            name = simpledialog.askstring("Nova habilidade", "Nome da habilidade (ex.: backup-do-sql-falhou):", parent=d)
            if name and name.strip():
                os.startfile(skills_mod.create(name.strip()))
                messagebox.showinfo("Gota", "Abri o modelo no seu editor. Preencha a descrição, as palavras-chave e os passos, salve e feche; depois a habilidade aparece aqui.", parent=d)
                d.after(500, refresh)
        RoundButton(row, "Nova habilidade", new_skill, bg=PRIMARY, hover=PRIMARY_HOVER, parent_bg=SURFACE).pack(side="left")
        RoundButton(row, "Atualizar", refresh, parent_bg=SURFACE).pack(side="left", padx=8)
        RoundButton(row, "Abrir pasta das minhas", lambda: (skills_mod.USER_DIR.mkdir(parents=True, exist_ok=True), os.startfile(skills_mod.USER_DIR)), parent_bg=SURFACE).pack(side="right")

    def background_dialog(self):
        d = self._list_dialog("Tarefas em segundo plano", "Peça, por exemplo, “faz uma varredura nos logs em segundo plano e me avisa”. Eu continuo conversando e aviso quando terminar.", 520)
        lb = tk.Listbox(d.body, bg=SURFACE2, fg=TEXT, selectbackground=PRIMARY, relief="flat", font=FONT, activestyle="none", bd=0, highlightthickness=0)
        lb.pack(fill="both", expand=True)
        out = tk.Label(d.body, text="", bg=SURFACE, fg=MUTED, wraplength=500, justify="left", font=("Segoe UI", 10), anchor="w")
        out.pack(fill="x", pady=(8, 0))
        tasks = self.brain.agent.bg

        def refresh():
            if not lb.winfo_exists():
                return
            sel = lb.curselection()
            lb.delete(0, "end")
            for t in tasks:
                lb.insert("end", f"  #{t['id']}  {t['status']:<10}  {t['goal'][:48]}")
            if not tasks:
                lb.insert("end", "  (nenhuma tarefa ainda)")
            if sel:
                lb.selection_set(sel[0])
            d.after(1500, refresh)

        def show(_=None):
            sel = lb.curselection()
            if sel and sel[0] < len(tasks):
                t = tasks[sel[0]]
                out.configure(text=(t["result"] or "Ainda em andamento…")[:600])

        def stop():
            sel = lb.curselection()
            if sel and sel[0] < len(tasks) and tasks[sel[0]]["status"] == "rodando":
                tasks[sel[0]]["stop"] = True
        lb.bind("<<ListboxSelect>>", show)
        RoundButton(d.body, "Parar a selecionada", stop, bg=RED, hover="#F0686C", parent_bg=SURFACE, height=34).pack(anchor="e", pady=(10, 0))
        refresh()

    def integrations_dialog(self):
        d = self._list_dialog("Integrações", "Para eu enviar alertas por chat. Cole o endereço do webhook (Slack ou Discord) ou o token e o chat do Telegram. Ficam só neste computador.", 470)
        cfg = self.settings.get("integrations") or {}
        fields = {}
        for key, label in (("slack", "Webhook do Slack"), ("discord", "Webhook do Discord"), ("telegram_token", "Token do bot do Telegram"), ("telegram_chat", "ID do chat do Telegram")):
            tk.Label(d.body, text=label, bg=SURFACE, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 0))
            e = tk.Entry(d.body, bg=SURFACE2, fg=TEXT, insertbackground=TEXT, relief="flat", font=FONT, show="•" if "token" in key else "")
            e.insert(0, cfg.get(key, ""))
            e.pack(fill="x", ipady=7)
            fields[key] = e

        def save():
            self.settings.set("integrations", {k: v.get().strip() for k, v in fields.items() if v.get().strip()})
            d.destroy()
        row = tk.Frame(d.body, bg=SURFACE)
        row.pack(fill="x", pady=(16, 0))
        RoundButton(row, "Servidores MCP…", lambda: self.mcp_dialog(d), parent_bg=SURFACE).pack(side="left")
        RoundButton(row, "Salvar", save, bg=PRIMARY, hover=PRIMARY_HOVER, parent_bg=SURFACE).pack(side="right")

    def mcp_dialog(self, parent=None):
        """Plug in third-party tool servers (MCP): a JSON list the user edits, e.g. a database or Slack server."""
        d = Dialog(self, "Servidores MCP", 640, 520)
        tk.Label(d.body, text="Servidores de ferramentas de terceiros (MCP) que o agente pode usar. Uma lista em JSON: nome, comando, argumentos e variáveis. "
                              "Ex.: [{\"name\":\"arquivos\",\"command\":\"npx\",\"args\":[\"-y\",\"@modelcontextprotocol/server-filesystem\",\"C:/dados\"]}]. "
                              "Cada uso que altera algo pede a sua permissão.", bg=SURFACE, fg=MUTED, wraplength=590, justify="left", font=("Segoe UI", 10)).pack(anchor="w")
        box = tk.Text(d.body, bg=SURFACE2, fg=TEXT, insertbackground=TEXT, relief="flat", font=("Consolas", 10), wrap="word", bd=0, padx=10, pady=8, height=14)
        box.pack(fill="both", expand=True, pady=10)
        box.insert("1.0", json.dumps(self.settings.get("mcp_servers") or [], ensure_ascii=False, indent=2))
        status = tk.Label(d.body, text="", bg=SURFACE, fg=MUTED, font=("Segoe UI", 10), wraplength=590, justify="left")
        status.pack(anchor="w")

        def save(test=False):
            try:
                cfg = json.loads(box.get("1.0", "end").strip() or "[]")
                assert isinstance(cfg, list) and all(isinstance(c, dict) and c.get("name") and c.get("command") for c in cfg)
            except Exception:
                status.configure(text="JSON inválido: precisa ser uma lista de objetos com name e command.", fg=RED)
                return
            self.settings.set("mcp_servers", cfg)
            self.brain.agent.close_mcp()
            if not test:
                status.configure(text="Salvo.", fg=GREEN)
                return
            status.configure(text="Testando…", fg=MUTED)

            def work():
                lines = []
                for c in cfg:
                    try:
                        cli = self.brain.agent._mcp().client(c["name"])
                        lines.append(f"✓ {c['name']}: {len(cli.tools)} ferramenta(s)")
                    except Exception as e:
                        lines.append(f"✗ {c['name']}: {str(e)[:120]}")
                self.ui(lambda: status.configure(text="\n".join(lines) or "Nenhum servidor.", fg=MUTED))
            threading.Thread(target=work, daemon=True).start()
        row = tk.Frame(d.body, bg=SURFACE)
        row.pack(fill="x", pady=(10, 0))
        RoundButton(row, "Salvar e testar", lambda: save(True), bg=PRIMARY, hover=PRIMARY_HOVER, parent_bg=SURFACE).pack(side="left")
        RoundButton(row, "Salvar", save, parent_bg=SURFACE).pack(side="left", padx=8)

    def audit_dialog(self):
        d = self._list_dialog("Registro de ações", "Cada ferramenta que usei e cada permissão que você deu ou negou, da mais recente para a mais antiga.", 600)
        box = tk.Text(d.body, bg=SURFACE2, fg=TEXT, relief="flat", font=("Consolas", 9), wrap="word", bd=0, padx=10, pady=8)
        sb = tk.Scrollbar(d.body, command=box.yview)
        box.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        box.pack(fill="both", expand=True)
        try:
            lines = agent_mod.AUDIT.read_text("utf-8").splitlines()[-200:]
        except Exception:
            lines = []
        for l in reversed(lines):
            try:
                r = json.loads(l)
                what = (r.get("tool", "") + " " + r.get("args", "")) if r["kind"] == "tool" else r.get("goal", r.get("text", ""))
                box.insert("end", f"{r['t'][5:16].replace('T', ' ')}  {r['kind']:<8} {what}\n")
            except Exception:
                pass
        if not lines:
            box.insert("end", "Nada registrado ainda.")
        box.configure(state="disabled")

    def tutorial(self):
        self.settings.set("tutorial", True)
        d = Dialog(self, "Como me chamar", 540, 540)
        CatView(d.body, size=130, bg=SURFACE).pack()
        tk.Label(d.body, text="Me chame de qualquer programa", bg=SURFACE, fg=TEXT, font=("Segoe UI", 16, "bold")).pack(pady=(6, 6))
        k = tk.Frame(d.body, bg=SURFACE)
        k.pack(pady=6)
        for i, key in enumerate(("Ctrl", "Alt", "G")):
            if i:
                tk.Label(k, text="+", bg=SURFACE, fg=MUTED, font=("Segoe UI", 14)).pack(side="left", padx=4)
            tk.Label(k, text=key, bg=SURFACE2, fg=TEXT, font=("Segoe UI", 14, "bold"), padx=14, pady=6).pack(side="left")
        tk.Label(d.body, text="O gatinho sobe na tela, ouve sua pergunta, responde em voz alta e desce.\n\nPeça \"o que tem na minha tela?\" para eu olhar o que você está vendo, "
                              "ou ligue 📞 (ou aperte Ctrl+Alt+L, que também desliga): a ligação abre um pop-up em que você conversa comigo e eu posso analisar a tela.\n\nFico também ao lado do relógio.",
                 bg=SURFACE, fg=MUTED, font=FONT, wraplength=470, justify="center").pack(pady=10)
        RoundButton(d.body, "Entendi", d.destroy, bg=PRIMARY, hover=PRIMARY_HOVER, parent_bg=SURFACE, width=160).pack()


class CallPopup:
    """A phone call with Gota as a small pop-up, like when he is listening: the cat on the phone, a speech bubble and three tiny buttons."""

    def __init__(self, app):
        self.app = app
        self.sir = app.profile.sir()
        self.chat_id = app.chats.create("📞 Ligação · " + datetime.now().strftime("%d/%m %H:%M"))["id"]
        self.ended = self.muted = False
        self.silent = 0
        self.speaker = app.get_speaker()
        self.ov = CatOverlay(app, maxw=250, font=("Segoe UI", 10), size=130, click_hides=False,
                             buttons=[("screen", "👁", self.look_screen), ("mute", "🎙", self.toggle_mute), ("hang", "✕", self.hang_up)])
        self.carry = None   # a correction spoken instead of yes/no: handled as the next thing he hears
        self._prev_confirm = app.brain.confirm_message
        app.brain.confirm_message = self.voice_confirm
        self.ov.show("Chamando…", "anim_phone_idle")
        self.ov.buttons["hang"].set(bg=RED, hover="#F0686C")
        app.warm_chat(self.chat_id)   # while it rings, the model reads its instructions
        winsound.Beep(440, 400)
        app.after(1300, self.answer)
        threading.Thread(target=app.listener.preload, daemon=True).start()

    def ui(self, fn):
        try:
            self.app.after(0, fn)
        except Exception:
            pass

    def show(self, text, mood=None):
        """Shows `text` in the bubble (and optionally changes the cat's animation) from any thread."""
        self.ui(lambda: self.ov.set(text, mood) if not self.ended else None)

    def answer(self):
        if self.ended:
            return
        hello = f"Alô, {self.app.profile.address()}. Às suas ordens."
        self.app.chats.append(self.chat_id, "gota", hello)
        self.say(hello, then=self.loop)

    def say(self, text, then=None):
        self.show(text[:400], "anim_phone_talk")
        self.speaker.speak(text, lambda: then and then())

    def loop(self):
        if not self.ended:
            threading.Thread(target=self._turn, daemon=True).start()

    def voice_confirm(self, found, requested, message, extra=""):
        """In a call the permission is asked out loud: he reads the message and waits for yes or no."""
        text = f"Vou enviar para {found}: {message}" + (f", com {extra}" if extra else "") + ". Posso enviar?"
        spoken = threading.Event()
        self.show(text[:400], "anim_phone_talk")
        self.speaker.speak(text, spoken.set)
        spoken.wait(90)
        self.show("Diga sim para enviar…", "anim_phone_listen")
        try:
            heard = self.app.listener.listen(lambda p: self.show(f"“{p}”"), silence=1.0, timeout=9)
        except Exception:
            return False, None
        words = set(tools.norm(heard).split())
        yes = bool(words & {"sim", "pode", "manda", "mande", "envia", "envie", "confirmo", "confirmado", "claro", "isso", "ok", "vai", "positivo", "certo"})
        no = bool(words & {"nao", "cancela", "cancele", "para", "espera", "calma", "errado"})
        if yes and not no:
            return True, None
        if heard and not no:   # he did not say yes or no: he is correcting the text; take it as the next instruction
            self.carry = heard
        return False, None

    def _turn(self):
        while not self.ended and self.muted:
            time.sleep(0.3)
        if self.ended:
            return
        self.show("…", "anim_phone_listen")
        try:
            if self.carry:
                heard, self.carry = self.carry, None
            else:
                heard = self.app.listener.listen(lambda p: self.show(f"“{p}”"), silence=1.3, timeout=10)
        except Exception:
            return self.say(f"Perdão, {self.sir}, estou com dificuldade para ouvir. Vou desligar.", lambda: self.ui(self.hang_up))
        if self.ended:
            return
        if not heard:
            self.silent += 1
            self.show(self.app.listener.explain_silence() if self.silent >= 2 else "…")
            if self.silent >= 6:
                return self.say(f"Vou desligar, então, {self.sir}. Quando precisar, é só me ligar.", lambda: self.ui(self.hang_up))
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
            return self.say(bye, lambda: self.ui(self.hang_up))
        self.reply_to(text)

    def reply_to(self, text, forced_screen=False):
        self.show(f"“{text[:200]}”", "anim_phone_think")
        history = [("user" if m["role"] == "user" else "model", m["text"]) for m in self.app.chats.get(self.chat_id)["messages"][:-1]]

        def phase(p):
            if p == "searching":
                self.speaker.speak(f"Um momento, {self.sir}. Vou pesquisar.")
            elif p == "drawing":
                self.show("Pintando…", "anim_cat_paint")
        self.app.brain.on_status = lambda s: self.show(s)
        feeder, last = voice.SentenceFeeder(self.speaker), {"t": 0.0}

        def partial(t):
            if self.ended:
                return
            feeder.feed(t)
            if time.time() - last["t"] > 0.15:
                last["t"] = time.time()
                self.show(t[-400:], "anim_phone_talk")
        self.app.brain.on_partial = partial
        try:
            if forced_screen:
                self.app.brain.history = history
                reply = self.app.brain.look_at_screen(text, spoken=True, history=history)
            else:
                reply = self.app.brain.run(text, history, self.chat_id, spoken=True, on_phase=phase)[0]
        except Exception as e:
            reply = f"Perdão, {self.sir}, tive um problema: {e}"
        finally:
            self.app.brain.on_partial = None
        self.app.brain.on_status = self.app._status
        self.app.chats.append(self.chat_id, "gota", reply)
        if not self.ended:
            self.show(reply[:400], "anim_phone_talk")
            feeder.finish(reply, self.loop)

    def look_screen(self):
        """The 'Tela' button: Gota looks at what is on screen right now and says what he sees."""
        if self.ended:
            return
        self.app.listener.cancel.set()
        self.speaker.stop()
        self.app.chats.append(self.chat_id, "user", "[pediu para olhar a tela]")
        question = "Olhe a tela e me diga, de forma objetiva, o que está acontecendo e se há algum erro, alerta ou algo importante."
        threading.Thread(target=lambda: self.reply_to(question, forced_screen=True), daemon=True).start()

    def toggle_mute(self):
        self.muted = not self.muted
        self.ov.buttons["mute"].set(text="🔇" if self.muted else "🎙", bg=ACCENT if self.muted else SURFACE2, hover=ACCENT if self.muted else HOVER)
        if self.muted:
            self.show("Microfone mudo.")
        if self.muted:
            self.app.listener.cancel.set()

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
        if not chat or sum(1 for m in chat["messages"] if m["role"] == "user") == 0:
            self.app.chats.delete(self.chat_id)
        else:
            self.app.settings.set("current_chat", self.chat_id)
            threading.Thread(target=self._remember, args=(chat,), daemon=True).start()
        self.app.call = None
        self.app.brain.confirm_message = self._prev_confirm
        self.ov.hide()
        if self.app.settings.get("hey_gota"):
            self.app.start_wake()
        if getattr(self.app, "msgs", None) and self.app.msgs.winfo_exists():
            self.app.open_chat(self.app.settings.get("current_chat"))

    def _remember(self, chat):
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
