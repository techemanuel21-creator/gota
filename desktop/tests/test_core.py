"""Core checks. Run: python -m unittest discover -s tests  (from the desktop folder)."""
import json, os, sys, tempfile, unittest
from pathlib import Path

os.environ["GOTA_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gota import brain, store, tools
from gota.imagegen import ClipTokenizer, suffix_for, PHOTO, ART, PAINTING

CLIP = Path(__file__).resolve().parents[1] / "models" / "imagegen"   # the CLIP vocabulary that ships with the painter
REF = os.environ.get("GOTA_TOKENS")  # official tokenizer ids, made by tools in the project history


class Fake:
    def __init__(self, settings=None):
        self.p = store.Profile(); self.p.set_name("emanuel", "senhor")
        self.s = store.Settings()
        self.b = brain.Brain(self.p, self.s, lambda: None, images=None)


class Quick(unittest.TestCase):
    def setUp(self): self.f = Fake()

    def ask(self, text):
        return self.f.b.run(text, [], "c")[0]

    def test_greetings_use_the_name(self):
        self.assertEqual(self.ask("bom dia"), "Bom dia, senhor Emanuel. Em que posso servi-lo?")
        self.assertIn("senhor Emanuel", self.ask("oi"))
        self.assertIn("Disponha", self.ask("obrigado"))

    def test_wake_word_is_dropped(self):
        self.assertEqual(brain.strip_wake_word("Ei Gota, que horas são"), "Que horas são")
        self.assertEqual(brain.strip_wake_word("pegou tô o fim da escala"), "pegou tô o fim da escala")

    def test_time_and_date_answer_only_what_was_asked(self):
        self.assertRegex(self.ask("que horas são"), r"^São \d\d:\d\d, senhor\.$")
        self.assertTrue(self.ask("que dia é hoje").startswith("Hoje é "))
        self.assertIsNone(self.f.b.time_or_date("que horas abre o mercado"))

    def test_remember_and_name(self):
        self.assertIn("Anotado", self.ask("lembre que eu gosto de café sem açúcar"))
        self.assertIn("Gosta" if False else "café sem açúcar", " ".join(self.f.p.d["facts"]))
        self.ask("me chame de Carlos")
        self.assertEqual(self.f.p.name, "Carlos")

    def test_fresh_info_goes_to_search(self):
        n = brain.norm
        self.assertTrue(brain.Brain.needs_fresh(n("o fim da escala 6x1 já foi aprovado?")))
        self.assertTrue(brain.Brain.needs_fresh(n("quando vai começar a valer a nova lei")))
        self.assertFalse(brain.Brain.needs_fresh(n("qual a capital da Austrália")))

    def test_search_query_numbers(self):
        self.assertEqual(brain.search_query("o fim da escala seis por um já foi aprovado?"), "o fim da escala 6x1 já foi aprovado")

    def test_retry(self):
        for t in ("outra", "de novo", "gera outra imagem", "faz outra", "refaz"):
            self.assertTrue(brain.is_retry(t), t)
        for t in ("outra coisa", "nova conversa", "abre o whatsapp de novo por favor"):
            self.assertFalse(brain.is_retry(t), t)

    def test_json_repair(self):
        self.assertEqual(brain.Brain.extract_json('```json\n{"action":"reply","text":"oi"}\n```')["text"], "oi")
        self.assertEqual(brain.Brain.extract_json('{"action":"reply","text":"oi')["text"], "oi")
        self.assertIsNone(brain.Brain.extract_json("sem json"))

    def test_phone_only_actions_are_explained(self):
        text = self.f.b.act({"action": "call", "number": "123"}, "ligue", "ligue", None, False)[0]
        self.assertIn("celular", text)


class Tokenizer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = ClipTokenizer((CLIP / "vocab.json").read_text("utf-8"), (CLIP / "merges.txt").read_text("utf-8"))

    def test_known_ids(self):
        self.assertEqual(self.t.encode("A photo of a cat")[:8], [49406, 320, 1125, 539, 320, 2368, 49407, 49407])

    def test_suffix_survives_long_text(self):
        ids = self.t.encode(" ".join(["cat"] * 200), PHOTO)
        tail = self.t.tokens(PHOTO)
        end = ids.index(49407)
        self.assertEqual(len(ids), 77)
        self.assertEqual(ids[end - len(tail):end], tail)

    @unittest.skipUnless(REF and Path(REF).exists(), "needs GOTA_TOKENS")
    def test_matches_official_tokenizer(self):
        for prompt, ids in json.loads(Path(REF).read_text("utf-8")).items():
            self.assertEqual(self.t.encode(prompt), ids, prompt)

    def test_style_words(self):
        self.assertEqual(suffix_for("a cartoon cat"), ART)
        self.assertEqual(suffix_for("an oil painting of a harbour"), PAINTING)
        self.assertEqual(suffix_for("a gray cat on a roof"), PHOTO)


class Tools(unittest.TestCase):
    def test_nicknames_come_first(self):
        tools._apps_cache.update(t=1e12, list=[("WhatsApp", "a"), ("WhatsApp Beta", "b"), ("Bloco de Notas", "c")])
        self.assertEqual(tools.find_app("whats 2", {"whats 2": "WhatsApp Beta"})[1], "b")
        self.assertEqual(tools.find_app("zap", {})[0], "WhatsApp")
        self.assertEqual(tools.find_app("bloco de notas", {})[1], "c")
        self.assertIsNone(tools.find_app("programa que nao existe", {}))

    def test_search_dates_sort_newest_first(self):
        old = tools._dated("2 de set. de 2026 · antigo")
        new = tools._dated("4 horas atrás · novo")
        self.assertLess(new[1], old[1])
        self.assertTrue(new[0].endswith("novo"))


class Chats(unittest.TestCase):
    def test_store(self):
        c = store.Chats(); chat = c.create()
        c.append(chat["id"], "user", "olá mundo")
        got = c.get(chat["id"])
        self.assertEqual(got["title"], "Nova conversa")   # the title is written by the model after the first answer, not copied from the message
        c.set_title(chat["id"], "Saudação")
        self.assertEqual(c.get(chat["id"])["title"], "Saudação")
        self.assertEqual(c.voice()["id"], "voice")
        self.assertEqual(c.list()[0]["id"], "voice")


class Streaming(unittest.TestCase):
    def test_partial_reply_text(self):
        from gota.brain import reply_text_so_far as r
        self.assertEqual(r('{"action":"reply","text":"Bom dia, sen'), "Bom dia, sen")
        self.assertEqual(r('{"action":"reply","text":"a\\nb \\"c\\" d","remember":"x"}'), 'a\nb "c" d')
        self.assertIsNone(r('{"action":"ask_expert","query":"abc'))
        self.assertEqual(r('{"action":"reply","te'), "")
        self.assertEqual(r('```json\n{"action":"reply","text":"Oi'), "Oi")
        self.assertEqual(r("texto puro"), "texto puro")
        self.assertEqual(r('{"thought":"ok","action":"final","args":{"text":"Pronto, sen'), "Pronto, sen")   # the agent's closing answer
        self.assertIsNone(r('{"thought":"ver","action":"list_dir","args":{"path":"C:'))

    def test_sentence_feeder(self):
        from gota.voice import SentenceFeeder, speakable

        class Fake:
            def __init__(self): self.said, self.stopped = [], 0
            def speak(self, t, done=None):
                self.said.append(t)
                done and done()
            def after(self, done): done()
            def stop(self): self.stopped += 1
        sp = Fake(); f = SentenceFeeder(sp)
        f.feed("Primeira frase. Segunda em andam")
        self.assertEqual(sp.said, ["Primeira frase."])
        f.feed("Primeira frase. Segunda em andamento. Terce")
        self.assertEqual(sp.said, ["Primeira frase.", "Segunda em andamento."])
        called = []
        f.finish("Primeira frase. Segunda em andamento. Terceira.", lambda: called.append(1))
        self.assertEqual(sp.said[-1], "Terceira.")
        self.assertEqual(called, [1])
        self.assertEqual(sp.stopped, 0)
        # a final text that differs from what was streamed starts over
        sp2 = Fake(); f2 = SentenceFeeder(sp2)
        f2.feed("Uma coisa. Outra ")
        f2.finish("Resposta completamente diferente.", None)
        self.assertEqual(sp2.stopped, 1)
        self.assertEqual(sp2.said[-1], "Resposta completamente diferente.")
        # code blocks are never read aloud, not even half written
        self.assertIn("(o comando está no chat)", speakable("Use isto:\n```powershell\nGet-Service\n```\nPronto."))
        self.assertNotIn("Get-Service", speakable("Use isto:\n```powershell\nGet-Service\n```\nPronto."))
        self.assertNotIn("ls -la", speakable("Use:\n```bash\nls -la"))

class QuickMath(unittest.TestCase):
    def test_instant_answers(self):
        from gota import quick
        cases = [("quanto é 12 vezes 8", "12 vezes 8 = 96"), ("quanto é 15% de 200", "15% de 200 é 30"), ("quanto é 7,5 mais 2,25", "7,5 mais 2,25 = 9,75"),
                 ("calcule 2 elevado a 10", "2 elevado a 10 = 1.024"), ("quanto é 12*(3+4)", "12*(3+4) = 84"), ("quanto é a raiz quadrada de 144", "A raiz quadrada de 144 é 12"),
                 ("converta 5 km em milhas", "5 km equivalem a 3,106856 milhas"), ("quanto é 100 f em c", "100°F equivalem a 37,78°C"),
                 ("converte 3 horas em minutos", "3 horas equivalem a 180 minutos"), ("2+2", "2+2 = 4")]
        for text, want in cases:
            self.assertEqual(quick.answer(text), want, text)

    def test_not_a_calculation(self):
        from gota import quick
        for text in ("quanto está o dólar hoje", "quanto custa um servidor", "quanto é 5 dividido por 0", "me conta uma piada", "quanto é 2 elevado a 100000", "quanto é 10 mais"):
            self.assertIsNone(quick.answer(text), text)


class Skills(unittest.TestCase):
    def test_bundled_skills_are_valid_and_found(self):
        from gota import skills
        found = skills.load_all()
        self.assertGreaterEqual(len(found), 8)
        for s in found:
            self.assertEqual(skills.validate(s), [], s["name"])
        top = skills.search("o job de backup do veeam falhou com erro de vss", 1)
        self.assertEqual(top[0][1]["name"], "veeam-falha-de-job")
        self.assertEqual(skills.search("qual a capital da França", 1), [])


class LocalServer(unittest.TestCase):
    def test_security_and_format(self):
        import json, urllib.request, urllib.error
        from gota import server

        class FakeModel:
            def complete(self, messages, on_delta=None):
                self.seen = messages
                text = "Olá, mundo."
                if on_delta:
                    for i in range(1, len(text) + 1):
                        on_delta(text[:i])
                return text
        model = FakeModel()
        srv = server.LocalServer(lambda: model, port=11600)
        port = srv.start()
        try:
            cfg = server.read_config()
            self.assertEqual(cfg["port"], port)
            base = f"http://127.0.0.1:{port}"
            body = json.dumps({"messages": [{"role": "system", "content": "s"}, {"role": "user", "content": [{"type": "text", "text": "oi"}]}]}).encode()

            def call(path, data=None, token=True, extra=None):
                h = {"Content-Type": "application/json"}
                if token:
                    h["Authorization"] = "Bearer " + cfg["token"]
                h.update(extra or {})
                try:
                    with urllib.request.urlopen(urllib.request.Request(base + path, data=data, headers=h), timeout=10) as r:
                        return r.status, r.read().decode("utf-8")
                except urllib.error.HTTPError as e:
                    return e.code, e.read().decode("utf-8")
            self.assertEqual(call("/health", token=False)[0], 401)                              # no token: refused
            self.assertEqual(call("/health", extra={"Origin": "https://evil.example"})[0], 403)  # a web page: refused
            self.assertEqual(call("/health")[0], 200)
            code, text = call("/v1/chat/completions", body)
            self.assertEqual(code, 200)
            self.assertEqual(json.loads(text)["choices"][0]["message"]["content"], "Olá, mundo.")
            self.assertEqual(model.seen[-1]["content"], "oi")                                    # list-of-parts content is flattened
            code, text = call("/v1/chat/completions", json.dumps({"stream": True, "messages": [{"role": "user", "content": "oi"}]}).encode())
            pieces = [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: {")]
            self.assertEqual("".join(p["choices"][0]["delta"].get("content", "") for p in pieces), "Olá, mundo.")
            self.assertIn("[DONE]", text)
            self.assertEqual(call("/v1/chat/completions", json.dumps({"messages": [{"role": "assistant", "content": "x"}]}).encode())[0], 400)
        finally:
            srv.stop()
        self.assertFalse(server.CONFIG.exists())

    def test_long_input_is_shortened(self):
        from gota import server
        msgs = [{"role": "system", "content": "regras"}, {"role": "user", "content": "x" * 50000}]
        short = server._shorten(msgs)
        self.assertEqual(short[0]["role"], "system")
        self.assertLessEqual(sum(len(m["content"]) for m in short), server.MAX_CHARS + 200)


class AgentCode(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from gota import brain
        self.b = brain.Brain(store.Profile(), store.Settings(), lambda: None, images=None)
        self.a = self.b.agent
        self.a.ask = lambda text, danger=False, path=None: True
        self.dir = Path(tempfile.mkdtemp())

    def test_code_comes_from_blocks_not_from_json(self):
        raw = '{"action":"write_file","args":{"path":"a.py"}}\n```python\nprint("oi")\n```'
        d = self.b.extract_json(raw)
        args = self.a._attach_code(d["action"], d["args"], raw)
        self.assertEqual(args["content"], 'print("oi")')

    def test_broken_json_is_salvaged_and_aliases_are_understood(self):
        raw = '{"action":"edit_file","args":{"path":"x.py","antes":"a","depois":"b"}}'
        d = self.b.extract_json(raw)
        args = self.a._attach_code(d["action"], d["args"], raw)
        self.assertEqual((args["old"], args["new"]), ("a", "b"))
        self.assertEqual(self.a._salvage('{"action":"write_file","args":{"path":"c.py","content":"x = "quebrado"}}')["args"]["path"], "c.py")

    def test_edit_ignores_blank_line_differences_and_reports_ambiguity(self):
        f = self.dir / "calc.py"
        f.write_text("def soma(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n", "utf-8")
        old = "def soma(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n"   # the model used one blank line instead of two
        self.assertTrue(self.a.t_edit_file(str(f), old, old + "\ndef mul(a, b):\n    return a * b\n").startswith("Editado"))
        self.assertIn("def mul", f.read_text("utf-8"))
        self.assertIn("aparece", self.a.t_edit_file(str(f), "return", "x"))
        self.assertIn("mais parecido", self.a.t_edit_file(str(f), "def soma(a, b):\n    return a * 99\n", "x"))

    def test_rewriting_keeps_a_backup_and_counts_lines(self):
        f = self.dir / "t.py"
        f.write_text("1\n2\n3\n4\n5\n6\n7\n8\n", "utf-8")
        msg = self.a.t_write_file(str(f), "1\n2\n")
        self.assertIn("reescrito", msg)
        self.assertIn("ATENÇÃO", msg)   # most lines disappeared
        self.assertIn("backups", msg)

    def test_project_grant_covers_only_the_project_folder(self):
        asked = []
        self.a.confirm = lambda text, danger: (asked.append(text), True)[1]
        self.a.ask = type(self.a).ask.__get__(self.a)   # the real permission logic
        self.a._tl.project, self.a._tl.granted = self.dir, None
        self.assertTrue(self.a.ask("gravar", False, path=self.dir / "a.py"))
        self.assertTrue(self.a.ask("gravar", False, path=self.dir / "b.py"))
        self.assertEqual(len(asked), 1)   # one grant for the whole session
        self.assertTrue(self.a.ask("gravar fora", False, path=self.dir.parent / "fora.py"))
        self.assertEqual(len(asked), 2)   # outside the folder it asks again
        self.a._tl.project = None


class KbLearn(unittest.TestCase):
    def test_keywords_drop_generic_words(self):
        from gota import kb
        self.assertEqual(kb.keywords("biblioteca Python rich para tabelas no terminal"), ["python", "rich", "tabelas", "terminal"])

    def test_relevance_rejects_pages_about_something_else(self):
        from gota import kb
        kws = kb.keywords("biblioteca Python rich tabelas terminal")
        self.assertGreaterEqual(kb.relevance("The rich library for Python prints tables in the terminal tabelas", kws), 0.6)
        self.assertLess(kb.relevance("A Biblioteca Mário de Andrade fica em São Paulo e empresta livros", kws), 0.6)

    def test_page_text_keeps_code_blocks_with_line_breaks(self):
        from gota import kb
        html = "<h2>Uso</h2><p>Para criar uma tabela use a classe Table do modulo rich.table assim:</p><pre><code>from rich.table import Table\ntable = Table()\nprint(table)</code></pre>"
        text = kb._page_text(html)
        self.assertIn("```\nfrom rich.table import Table\ntable = Table()\nprint(table)\n```", text)
        self.assertIn("## Uso", text)


if __name__ == "__main__":
    unittest.main()
