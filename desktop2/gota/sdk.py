"""Gota as a library and as a command line: the same brain and agent as the window, without the window.

    from gota.sdk import Gota
    g = Gota()                       # cloud when a key is set and there is internet, the on-device model otherwise
    print(g.ask("o que é RAID 5?"))
    print(g.agent("liste os 5 maiores arquivos de C:/Logs"))

    python main.py --cli "pergunta"      one answer          python main.py --cli      interactive
"""
import sys
from . import brain as brain_mod, cloud, store


class _LazyLocal:
    """The on-device model, loaded only if it is actually needed (offline, or the cloud failed): loading takes seconds and 2.5 GB of memory."""

    def __init__(self, path=None):
        self.path, self._m = path, None

    def _model(self):
        if self._m is None:
            from . import llm
            self._m = llm.Gemma(self.path or llm.MODEL_FILE)
        return self._m

    def __getattr__(self, name):
        return getattr(self._model(), name)

    def warm(self, *a):   # never warm up in the background here
        pass

    def cancel(self):
        if self._m is not None:
            self._m.cancel()


class Gota:
    def __init__(self, model_path=None, confirm=None, name="você"):
        self.profile, self.settings = store.Profile(), store.Settings()
        if not self.profile.is_set:
            self.profile.set_name(name, "")
        self.llm = cloud.Hybrid(_LazyLocal(model_path), self.settings)
        self.brain = brain_mod.Brain(self.profile, self.settings, lambda: self.llm, images=None)
        self.brain.confirm = confirm or self._ask_terminal
        self.history = []
        self.chat_id = "sdk"

    @staticmethod
    def _ask_terminal(text, danger=False):
        print(("\n⚠ " if danger else "\n") + text)
        return input("Permitir? [s/N] ").strip().lower() in ("s", "sim", "y", "yes")

    def ask(self, text, stream=None):
        """One question, with the conversation so far remembered between calls. Returns the answer text."""
        self.brain.on_partial = stream
        try:
            reply, _image = self.brain.run(text, self.history, self.chat_id)
        finally:
            self.brain.on_partial = None
        self.history += [("user", text), ("model", reply)]
        return reply

    def agent(self, goal):
        """A task with tools (files, terminal, web, browser, ...). Anything that changes the computer asks first."""
        return self.brain.agent.run(goal)


def main(argv):
    g = Gota()
    if argv:
        print(g.ask(" ".join(argv)))
        return 0
    print("Gota (linha de comando). Linha vazia ou 'sair' termina.")
    while True:
        try:
            q = input("\nvocê> ").strip()
        except (EOFError, KeyboardInterrupt):
            return 0
        if not q or q.lower() in ("sair", "exit", "quit"):
            return 0
        print("gota> " + g.ask(q))