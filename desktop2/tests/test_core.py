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


class TestScreensAndNames(unittest.TestCase):
    def test_parse_screen(self):
        from gota import tools
        self.assertEqual(tools.parse_screen("O que está acontecendo na minha primeira hotel?"), 1)   # speech slip for "tela"
        self.assertEqual(tools.parse_screen("analisa a segunda tela"), 2)
        self.assertEqual(tools.parse_screen("olha o monitor dois"), 2)
        self.assertEqual(tools.parse_screen("as duas telas"), "all")
        self.assertEqual(tools.parse_screen("e na outra tela?"), "other")
        self.assertIsNone(tools.parse_screen("o que tem na minha tela"))
        self.assertIsNone(tools.parse_screen("qual a segunda coisa do menu"))

    def test_name_variants(self):
        from gota import whatsapp
        v = whatsapp.name_variants("Emmanuel SP", ["emanuel"])
        self.assertEqual(v[0], "Emmanuel SP")
        self.assertIn("Emanuel SP", v[:3])
        self.assertLessEqual(len(v), 8)

class TestCloud(unittest.TestCase):
    def test_clean_removes_reasoning(self):
        from gota import cloud
        self.assertEqual(cloud.clean("<think>pensando</think>Olá"), "Olá")
        self.assertEqual(cloud.clean("Resposta <think>ainda pensando"), "Resposta ")
        self.assertEqual(cloud.clean("Oi"), "Oi")

    def test_hybrid_falls_back_to_local(self):
        from gota import cloud

        class Local:
            def chat(self, *a, **k): return "local"
            def cancel(self): pass

        class Settings:
            def get(self, k): return None

        class Broken:
            def chat(self, *a, **k): raise cloud.CloudError("fora do ar")
            def cancel(self): pass
        h = cloud.Hybrid(Local(), Settings())
        h._client = lambda: Broken()
        self.assertEqual(h.chat("k", "s", [], "oi"), "local")
        self.assertEqual(h.using, "local")
        self.assertIn("fora do ar", h.last_error)
        self.assertGreater(h.down_until, 0)

class TestVoiceLanguages(unittest.TestCase):
    def test_split_languages(self):
        from gota import voice
        parts = voice.split_languages("Senhor, a tela diz: Job has been terminated Error: Job aborted due to server termination. Isso significa que o serviço parou.")
        langs = [l for l, _ in parts]
        self.assertIn("en", langs)
        en = " ".join(s for l, s in parts if l == "en")
        self.assertIn("Job has been terminated", en)
        self.assertNotIn("serviço", en)

    def test_portuguese_stays_portuguese(self):
        from gota import voice
        self.assertEqual([l for l, _ in voice.split_languages("O backup do servidor Veeam falhou na tela dois.")], ["pt"])

class TestSpokenForm(unittest.TestCase):
    def test_job_names_are_spelled_out(self):
        from gota import voice
        self.assertEqual(voice.spoken_form("JOB_BACKUP_TAPE_NOD01_B"), "job, backup, tape, nod zero um, bê")
        self.assertEqual(voice.spoken_form("o servidor falhou"), "o servidor falhou")

    def test_ui_labels_are_english(self):
        from gota import voice
        langs = dict((s.strip(), l) for l, s in voice.split_languages("O resultado é Last Result Failed."))
        self.assertEqual(langs.get("Last Result Failed."), "en")

class TestEnglishVoice(unittest.TestCase):
    def test_match_voice_moves_pitch(self):
        import numpy as np
        from gota import voice
        sr = 22050
        t = np.arange(sr * 1) / sr
        x = 0.4 * np.sin(2 * np.pi * 90 * t) * (1 + 0.3 * np.sin(2 * np.pi * 3 * t))   # a low buzz around 90 Hz
        y = voice.match_voice(x, sr)
        self.assertGreater(len(y), sr // 2)
        import parselmouth
        pitch = parselmouth.Sound(y, sampling_frequency=sr).to_pitch(pitch_floor=60, pitch_ceiling=400)
        f0 = parselmouth.praat.call(pitch, "Get quantile", 0, 0, 0.5, "Hertz")
        self.assertGreater(f0, 130)

class TestCatMouth(unittest.TestCase):
    def test_mouth_follows_the_voice(self):
        import tkinter as tk
        from gota import widgets
        root = tk.Tk()
        root.withdraw()
        try:
            cat = widgets.CatView(root, size=32)
            cat.play("anim_cat_talk")
            self.assertEqual(cat.name, "anim_cat_idle")     # not speaking: mouth closed, only blinking
            widgets.set_speaking(True)
            self.assertEqual(cat.name, "anim_cat_talk")
            widgets.set_speaking(False)
            self.assertEqual(cat.name, "anim_cat_idle")
            phone = widgets.CatView(root, size=32)
            phone.play("anim_phone_talk")
            self.assertEqual(phone.name, "anim_phone_idle")
        finally:
            widgets.set_speaking(False)
            root.destroy()

class TestCiscoSkill(unittest.TestCase):
    def test_switch_request_finds_the_cisco_skill(self):
        from gota import skills
        goal = ("configurar um switch gigabit cisco com as seguintes portas e vlans, resetar essas portas para config de fabrica antes de configurar\n"
                "Trunk: 39 e 40; Lan dos FWs\nVlan acess 1 e voice vlan 13: 13 a 27; PC/Ramal")
        self.assertEqual(skills.search(goal, 1)[0][1]["name"], "cisco-configurar-portas-e-vlans")

class TestMarkdownAndSteps(unittest.TestCase):
    def test_markdown_lines_are_tagged(self):
        import tkinter as tk
        from gota import widgets
        root = tk.Tk()
        root.withdraw()
        try:
            box = widgets._prose(root, "# Título\n- um **item**\n1. primeiro\ntexto `código`", ("Segoe UI", 11), widgets.BG, 400, root)
            tags = {name for name in box.tag_names() if box.tag_ranges(name)}
            self.assertTrue({"h1", "li0", "b", "m"} <= tags)
            self.assertIn("•", box.get("1.0", "end"))
            self.assertNotIn("# ", box.get("1.0", "end"))
        finally:
            root.destroy()

    def test_step_symbols(self):
        from gota.app import App
        self.assertEqual(App._step_symbol("read_file C:/x.py"), "📄")
        self.assertEqual(App._step_symbol("run_command pytest"), "❯")
        self.assertEqual(App._step_symbol("web_search veeam"), "🌐")
        self.assertEqual(App._step_symbol("kb_search raid"), "•")

class AgentParallel(unittest.TestCase):
    """Several tools in one step run at the same time; sub-agents run side by side; the plan can be refused."""

    class Script:
        def __init__(self, replies, plan=None):
            self.replies, self.plan = list(replies), plan
        def chat(self, key, system, history, user_text, image=None, think=False, on_delta=None):
            return self.replies.pop(0)
        def one_shot(self, system, user_text, image=None, on_delta=None):
            if "dividem tarefas" in system or "divide tarefas" in system:
                return json.dumps({"steps": self.plan or []})
            return '{"ok":true}'

    def make(self, replies, plan=None):
        from gota import brain
        llm = self.Script(replies, plan)
        b = brain.Brain(store.Profile(), store.Settings(), lambda: llm, images=None)
        b.agent.ask = lambda text, danger=False, path=None: True
        return b, b.agent

    def test_parallel_reads_finish_together(self):
        import time
        b, a = self.make(['{"thought":"x","actions":[{"action":"slow_a","args":{}},{"action":"slow_b","args":{}}]}', '{"action":"final","args":{"text":"feito"}}'])
        a.t_slow_a = lambda: (time.sleep(0.6), "A")[1]
        a.t_slow_b = lambda: (time.sleep(0.6), "B")[1]
        from gota import agent
        agent.PARALLEL_SAFE.update({"slow_a", "slow_b"})
        try:
            t0 = time.time()
            out = a._loop("faça duas leituras ao mesmo tempo agora", verify=False)
            took = time.time() - t0
        finally:
            agent.PARALLEL_SAFE.difference_update({"slow_a", "slow_b"})
        self.assertEqual(out, "feito")
        self.assertLess(took, 1.1)   # one after the other would take 1.2 s

    def test_delegate_runs_several_sub_agents(self):
        b, a = self.make(['{"action":"final","args":{"text":"achado 1"}}', '{"action":"final","args":{"text":"achado 2"}}'])
        out = a.t_delegate(tasks=[{"role": "explorar", "task": "olhe a"}, {"role": "revisar", "task": "olhe b"}])
        self.assertIn("sub-agente de explorar", out)
        self.assertIn("sub-agente de revisar", out)
        self.assertIn("achado 1", out)
        self.assertIn("achado 2", out)

    def test_refused_plan_stops_before_acting(self):
        b, a = self.make(['{"action":"final","args":{"text":"não deveria chegar aqui"}}'], plan=["Listar arquivos", "Ler o log", "Resumir o erro"])
        a.approve_plan = lambda goal, plan: False
        out = a._loop("investigue o erro do servidor olhando os logs e depois os arquivos de configuração", verify=False)
        self.assertIn("não executei nada", out)

class MemoryAndChats(unittest.TestCase):
    def test_capture_preferences_and_environment(self):
        from gota import memory
        m = memory.Memory(Path(tempfile.mkdtemp()) / "m.json")
        self.assertEqual([i["type"] for i in m.capture("Eu prefiro respostas curtas e sem emoji")], ["feedback"])
        self.assertEqual([i["type"] for i in m.capture("Nosso ambiente tem três servidores VMware e um backup Veeam")], ["project"])
        self.assertEqual(m.capture("Qual a capital da França?"), [])           # questions are not memories
        self.assertEqual(len(m.items()), 2)
        m.capture("eu prefiro respostas curtas, sem emoji nenhum")               # almost the same: updated, not duplicated
        self.assertEqual(len(m.items()), 2)
        self.assertIn("respostas curtas", m.block("qualquer coisa"))
        m.delete(m.items()[0]["id"])
        self.assertEqual(len(m.items()), 1)

    def test_search_old_chats(self):
        chats = store.Chats()
        c = chats.create("Veeam fita")
        chats.append(c["id"], "user", "meu job JOB_TAPE_SEMANAL falhou ontem")
        chats.append(c["id"], "gota", "Verifique o drive de fita, senhor.")
        hits = chats.search("job tape semanal")
        self.assertTrue(any(h["id"] == c["id"] for h in hits))
        self.assertIn("JOB_TAPE", next(h for h in hits if h["id"] == c["id"])["snippet"])
        self.assertEqual(chats.search("palavra que nunca foi dita xyz"), [])


class ExtToolsTests(unittest.TestCase):
    def setUp(self):
        from gota import brain
        self.b = brain.Brain(store.Profile(), store.Settings(), lambda: None, images=None)
        self.a = self.b.agent
        self.a.ask = lambda text, danger=False, path=None: True
        self.dir = Path(tempfile.mkdtemp())

    def test_notebook_cells_are_edited_with_backup(self):
        nb = {"cells": [{"cell_type": "code", "metadata": {}, "source": ["print(1)"], "outputs": [], "execution_count": 1}], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
        f = self.dir / "a.ipynb"
        f.write_text(json.dumps(nb), "utf-8")
        self.assertIn("[0] code", self.a.t_notebook_edit(str(f), "read"))
        self.a.t_notebook_edit(str(f), "insert", 1, "# título", "markdown")
        self.a.t_notebook_edit(str(f), "replace", 0, "print(2)")
        cells = json.loads(f.read_text("utf-8"))["cells"]
        self.assertEqual("".join(cells[0]["source"]), "print(2)")
        self.assertEqual(cells[1]["cell_type"], "markdown")
        self.a.t_notebook_edit(str(f), "delete", 1)
        self.assertEqual(len(json.loads(f.read_text("utf-8"))["cells"]), 1)

    def test_chart_is_a_self_contained_page_with_dark_mode(self):
        import webbrowser
        webbrowser.open = lambda *a, **k: True
        out = self.a.t_make_chart(str(self.dir / "g.html"), "bar", "Vendas", ["jan", "fev"], [{"name": "x", "values": [3, 5]}])
        page = (self.dir / "g.html").read_text("utf-8")
        self.assertIn("prefers-color-scheme:dark", page)
        self.assertIn("<rect", page)
        self.assertIn("criado", out)

    def test_github_refuses_dangerous_commands(self):
        self.assertIn("proibida", self.a.t_github("repo delete algo/repo"))

    def test_large_document_is_read_in_parts(self):
        text = "\n".join(f"Linha {i}: o servidor SRV{i % 7} reiniciou às {i % 24}h" for i in range(2500))
        f = self.dir / "grande.txt"
        f.write_text(text, "utf-8")

        class Fast:
            def cloud_ready(self): return True
            def one_shot(self, system, user, image=None, on_delta=None):
                return "[parte] SRV3 reiniciou" if "PARTE" in user else "SRV3 reiniciou várias vezes (p.1)"
        self.b.llm = lambda: Fast()
        out = self.a.t_read_document(str(f), "quais servidores reiniciaram?")
        self.assertIn("SRV3", out)
        self.assertIn("DADOS EXTERNOS", out)   # content read from files is data, never instructions

    def test_worktree_isolates_risky_changes(self):
        import subprocess
        repo = self.dir / "proj"
        repo.mkdir()
        run = lambda *a: subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True)
        run("init", "-q"); run("config", "user.email", "t@t"); run("config", "user.name", "t")
        (repo / "a.txt").write_text("x")
        run("add", "."); run("commit", "-qm", "init")
        out = self.a.t_git_worktree("create", str(repo), "teste")
        self.assertTrue((self.dir / "proj-teste").is_dir(), out)
        self.assertIn("proj-teste", self.a.t_git_worktree("list", str(repo)))


class RoutinesTests(unittest.TestCase):
    def test_due_logic(self):
        from datetime import datetime
        from gota.routines import Routines
        r = {"id": 1, "name": "x", "goal": "g", "when": "08:00", "repeat": "daily", "last": 0}
        self.assertFalse(Routines.due(r, datetime(2026, 10, 21, 7, 59)))
        self.assertTrue(Routines.due(r, datetime(2026, 10, 21, 8, 5)))
        r["last"] = datetime(2026, 10, 21, 8, 1).timestamp()
        self.assertFalse(Routines.due(r, datetime(2026, 10, 21, 9, 0)))          # already ran today
        self.assertTrue(Routines.due(r, datetime(2026, 10, 22, 8, 1)))           # next day
        w = {"id": 2, "name": "x", "goal": "g", "when": "08:00", "repeat": "weekdays", "last": 0}
        self.assertFalse(Routines.due(w, datetime(2026, 10, 24, 9, 0)))          # Saturday

    def test_unattended_agent_refuses_changes(self):
        from gota import brain
        b = brain.Brain(store.Profile(), store.Settings(), lambda: None, images=None)
        b.confirm = lambda t, d: True
        b.agent._tl.unattended = True
        try:
            self.assertFalse(b.agent.ask("apagar tudo", True))
        finally:
            b.agent._tl.unattended = False

class BrowserTool(unittest.TestCase):
    """Drives Edge on a local page (skipped when Edge/Playwright are not there)."""

    def test_browser_reads_structure_clicks_and_protects(self):
        import functools, http.server, threading
        try:
            import playwright  # noqa: F401
        except ImportError:
            self.skipTest("playwright não instalado")
        d = Path(tempfile.mkdtemp())
        (d / "index.html").write_text("""<!doctype html><html><head><meta charset="utf-8"><title>Teste</title></head><body><h1>Oi</h1>
<input id="nome"><input id="senha" type="password"><button onclick="document.getElementById('r').innerText='Olá ' + document.getElementById('nome').value">Mostrar</button>
<button type="submit">Enviar pedido</button><p id="r"></p><script>console.error('falha de teste')</script></body></html>""", "utf-8")
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8771), functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(d)))
        srv.RequestHandlerClass.log_message = lambda *a, **k: None
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        from gota import brain
        b = brain.Brain(store.Profile(), store.Settings(), lambda: None, images=None)
        a, asked = b.agent, []
        a.ask = lambda text, danger=False, path=None: (asked.append(text), True)[1]
        try:
            self.assertIn("Teste", a.t_browser("open", url="http://127.0.0.1:8771/"))
            snap = a.t_browser("snapshot")
            self.assertIn("ref 1", snap)
            self.assertIn("DADOS EXTERNOS", snap)                    # page content is data, never orders
            a.t_browser("type", target="#nome", text="Emanuel")
            self.assertIn("SENHA", a.t_browser("type", target="#senha", text="x"))   # never types passwords
            a.t_browser("click", target="Mostrar")
            self.assertIn("Olá Emanuel", a.t_browser("text"))
            self.assertIn("falha de teste", a.t_browser("console"))
            a.t_browser("click", target="Enviar pedido")
            self.assertTrue(any("Enviar pedido" in x for x in asked))               # a risky click asks first
            self.a_resized = a.t_browser("resize", preset="mobile")
            self.assertIn("390", self.a_resized)
        finally:
            a.close_browser()
            srv.shutdown()

class McpTool(unittest.TestCase):
    def test_mcp_server_tools_and_permissions(self):
        from gota import brain
        fake = str(Path(__file__).parent / "fixtures" / "fake_mcp.py")
        s = store.Settings()
        s.set("mcp_servers", [{"name": "fake", "command": sys.executable, "args": [fake]}])
        b = brain.Brain(store.Profile(), s, lambda: None, images=None)
        a, asked = b.agent, []
        a.ask = lambda text, danger=False, path=None: (asked.append(text), True)[1]
        try:
            self.assertIn("fake", a.t_mcp("servers"))
            self.assertIn("eco", a.t_mcp("tools", "fake"))
            out = a.t_mcp("call", "fake", "eco", {"x": 1})
            self.assertIn('eco: {"x": 1}', out)
            self.assertIn("DADOS EXTERNOS", out)        # what a server returns is data, never orders
            self.assertEqual(asked, [])                  # read-only tool: no question
            a.t_mcp("call", "fake", "apagar", {"o": "tudo"})
            self.assertEqual(len(asked), 1)              # a tool that changes things asks first
            self.assertIn("ERRO", a.t_mcp("call", "fake", "naoexiste"))
        finally:
            a.close_mcp()
            s.set("mcp_servers", [])

class ExtractJsonFences(unittest.TestCase):
    def test_code_blocks_inside_text_are_kept(self):
        raw = '{"action":"reply","text":"Segue:\\n\\n```cisco\\nconfigure terminal\\n```\\nFim"}'
        self.assertEqual(brain.Brain.extract_json(raw)["text"], "Segue:\n\n```cisco\nconfigure terminal\n```\nFim")

    def test_a_fence_around_the_json_is_still_removed(self):
        self.assertEqual(brain.Brain.extract_json('```json\n{"action":"reply","text":"oi"}\n```')["text"], "oi")

    def test_half_written_answer_keeps_its_fence(self):
        d = brain.Brain.extract_json('{"action":"reply","text":"a\\n```ps\\nGet-X\\n```"')
        self.assertIn("```ps", d["text"])

class SyntaxHighlighting(unittest.TestCase):
    def test_cisco_config_tokens(self):
        from gota import widgets
        toks = list(widgets._ios_tokens("interface GigabitEthernet1/0/41\n description Link02\n switchport access vlan 900\n! nota"))
        kinds = {tag for tag, _ in toks if tag}
        self.assertTrue({"keyword", "iface", "number", "string", "comment"} <= kinds)
        self.assertIn(("string", "Link02"), toks)          # the free text after "description"

    def test_powershell_and_unknown_languages(self):
        import tkinter as tk
        from gota import widgets
        root = tk.Tk()
        root.withdraw()
        try:
            t = tk.Text(root)
            widgets.insert_highlighted(t, "powershell", "Get-Process | Select Name")
            self.assertTrue(t.tag_ranges("syn_builtin") or t.tag_ranges("syn_keyword"))
            t2 = tk.Text(root)
            widgets.insert_highlighted(t2, "linguagem-inexistente", "texto qualquer")
            self.assertEqual(t2.get("1.0", "end-1c"), "texto qualquer")      # falls back to plain text
        finally:
            root.destroy()

class NetconfFastPath(unittest.TestCase):
    REQUEST = ("crie um comando para eu\nconfigurar um switch gigabit cisco, resetar essas portas antes\n\nCom a VLAN 900 em mode acess (Não existe ainda) :\n41; Link02\n42; Link01FW01\n43; Link01FW02\n\n"
               "Trunk:\n39 e 40; Lan dos FWs\n28 a 37; Antenas\n\nVlan acess 1 e voice vlan 13:\n13 a 27; PC/Ramal\n\nVlan acess 1\n11 e 12; DVR\n3 a 10; Impressoras\n1 e 2; Servidor\n")

    def test_script_follows_the_request_exactly(self):
        from gota import netconf
        out = netconf.try_answer(self.REQUEST)
        self.assertIn("default interface range GigabitEthernet1/0/1-37", out)
        self.assertIn("default interface range GigabitEthernet1/0/39-43", out)       # port 38 is never touched
        self.assertNotRegex(out, r"default interface range [^\n]*38")
        self.assertIn("interface GigabitEthernet1/0/42\n description Link01FW01\n switchport mode access\n switchport access vlan 900", out)
        self.assertIn("interface range GigabitEthernet1/0/13-27\n description PC/Ramal\n switchport mode access\n switchport access vlan 1\n switchport voice vlan 13", out)
        self.assertIn("interface range GigabitEthernet1/0/28-37\n description Antenas\n switchport mode trunk\nexit", out)   # no invented allowed/native vlan
        self.assertNotIn("allowed", out.split("```")[1])
        self.assertTrue(out.split("```")[1].rstrip().endswith("write memory"))

    def test_unclear_requests_are_left_to_the_model(self):
        from gota import netconf
        self.assertIsNone(netconf.try_answer("o que é uma vlan?"))
        self.assertIsNone(netconf.try_answer("Trunk:\n5 e 6; A\nVlan acess 2\n6 a 8; B\n"))     # port 6 twice: ambiguous
        self.assertIsNone(netconf.try_answer("41; Link02\n42; Link01"))                          # no heading: which vlan/mode?

class ValidateBeforeAnswer(unittest.TestCase):
    FINAL = "Pois não.\n\n```cisco\nconfigure terminal\nend\n```\n- ok"

    def brain(self, cloud_reply=None, ready=True):
        from gota import brain

        class Cloud:
            def cloud_ready(self): return ready
            def cancel(self): pass
            def one_shot(self, system, user, image=None, on_delta=None):
                if cloud_reply is None:
                    raise RuntimeError("fora do ar")
                self.last_user = user
                return cloud_reply
        self.cloud = Cloud()
        b = brain.Brain(store.Profile(), store.Settings(), lambda: self.cloud, images=None)
        b.followup = lambda cid, text: self.fail("nothing about the checking may be shown separately")
        return b

    def test_the_user_only_sees_the_checked_final_script(self):
        b = self.brain(self.FINAL)
        reply, _ = b.run(NetconfFastPath.REQUEST, [], "t")
        self.assertEqual(reply, self.FINAL)                      # the model's corrected result, not the rule-built draft
        self.assertIn("RASCUNHO", self.cloud.last_user)           # the draft went through the check
        self.assertNotIn("erro", reply.lower())

    def test_without_a_cloud_model_a_complete_draft_is_still_delivered(self):
        b = self.brain(None, ready=False)
        reply, _ = b.run(NetconfFastPath.REQUEST, [], "t")
        self.assertIn("default interface range GigabitEthernet1/0/1-37", reply)

    def test_a_failed_check_keeps_the_complete_draft(self):
        reply, _ = self.brain(None).run(NetconfFastPath.REQUEST, [], "t")
        self.assertIn("```cisco", reply)

    def test_requirements_beyond_the_table_make_the_draft_partial(self):
        from gota import netconf
        extra = NetconfFastPath.REQUEST + "\n49 a 52 devem ficar desativadas\nTrunks permitindo somente as vlans 150, 200 e 201\n"
        self.assertFalse(netconf.analyze(extra)["complete"])
        self.assertTrue(netconf.analyze(NetconfFastPath.REQUEST)["complete"])

class WhatsappUnread(unittest.TestCase):
    def make(self, connected, chats=None, error=None):
        from gota import brain
        b = brain.Brain(store.Profile(), store.Settings(), lambda: None, images=None)
        b.whatsapp.connected = lambda: connected
        def unread(on_status=None):
            if error:
                raise error
            return chats
        b.whatsapp.unread = unread
        return b

    def test_unread_question_goes_straight_to_whatsapp_without_the_model(self):
        b = self.make(True, [{"title": "Maria", "count": 3}, {"title": "João", "count": 1}])
        reply, _ = b.run("quantas conversas não lidas eu tenho no whatsapp?", [], "t")
        self.assertIn("2 conversas não lidas", reply)
        self.assertIn("Maria (3)", reply)
        self.assertIn("4 mensagens", reply)

    def test_the_chip_number_is_the_reference_for_how_many_chats(self):
        b = self.make(True, {"total": 1, "chats": [{"title": "T2W | PLANTONISTA", "count": 2}], "via": "filtro"})
        reply, _ = b.run("quantas conversas não lidas eu tenho no whatsapp?", [], "t")
        self.assertEqual(reply, "O senhor tem 1 conversa não lida no WhatsApp (2 mensagens): T2W | PLANTONISTA (2).")

    def test_not_connected_and_empty(self):
        self.assertIn("não está conectado", self.make(False).run("tem mensagem nova no zap?", [], "t")[0])
        self.assertIn("Nenhuma conversa não lida", self.make(True, []).run("tenho mensagens não lidas no whatsapp?", [], "t")[0])

    def test_sending_is_not_mistaken_for_reading(self):
        from gota.brain import WA_UNREAD, norm
        self.assertIsNone(WA_UNREAD.search(norm("abre o whatsapp")))

    def test_unread_badges_are_found_in_the_chat_list(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright não instalado")
        from gota import whatsapp
        # mirrors a real list: the chip shows how many chats are unread, only one row has the green number, times contain ":", phone numbers are titles
        row = lambda title, time_, badge="", extra="": (f'<div role="listitem" style="display:flex;width:500px;height:60px;justify-content:space-between"><span title="{title}">{title}</span>'
                                                       f'<span style="display:flex;flex-direction:column"><span>{time_}</span>{badge}</span>{extra}</div>')
        html = ('<button aria-pressed="false">Tudo</button><button>Não lidas 1</button><div id="pane-side">'
                + row("Meu Numero", "17:40") + row("T2W | PLANTONISTA", "16:33", '<span style="width:20px;display:inline-block">2</span>')
                + row("+55 11 99630-9400", "14:37", extra='<span aria-label="Mensagem enviada">ok</span>') + row("Tech2Work", "15:26") + "</div>")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page()
            page.set_content(html)
            res = page.evaluate(whatsapp.WhatsApp._UNREAD_JS)
            browser.close()
        self.assertEqual(res["chip"], 1)
        counts = {r["title"]: r["count"] for r in res["rows"]}
        self.assertEqual(counts["T2W | PLANTONISTA"], 2)
        self.assertEqual(counts["+55 11 99630-9400"], 0)           # digits in a phone-number title are not a badge
        self.assertEqual(counts["Meu Numero"], 0)                   # "17:40" is a time, not a badge

class MassiveContext(unittest.TestCase):
    def setUp(self):
        from gota import brain
        self.b = brain.Brain(store.Profile(), store.Settings(), lambda: None, images=None)
        self.a = self.b.agent
        self.dir = Path(tempfile.mkdtemp())

    def test_big_document_is_read_in_one_call_with_the_cloud(self):
        f = self.dir / "contrato.txt"
        f.write_text("\n".join(f"Página {i // 40 + 1} linha {i}: cláusula {i % 90}" for i in range(6000)), "utf-8")

        class Cloud:
            calls = 0
            def cloud_ready(self): return True
            def one_shot(self, system, user, image=None, on_delta=None):
                Cloud.calls += 1
                return "achei na cláusula 44 [p.140]"
        self.b.llm = lambda: Cloud()
        out = self.a.t_read_document(str(f), "qual a cláusula?")
        self.assertEqual(Cloud.calls, 1)                      # not 20 partial reads and a merge
        self.assertIn("de uma vez", out)

    def test_project_is_gathered_key_files_first_and_junk_skipped(self):
        (self.dir / "README.md").write_text("# projeto")
        (self.dir / "src").mkdir()
        (self.dir / "src" / "a.py").write_text("print(1)")
        (self.dir / "node_modules").mkdir()
        (self.dir / "node_modules" / "x.js").write_text("lixo")
        (self.dir / "foto.png").write_bytes(b"\x89PNG")
        files = self.a.gather_project(self.dir)
        names = [n for n, _ in files]
        self.assertEqual(names[0], "README.md")
        self.assertIn("src\\a.py", names)
        self.assertFalse(any("node_modules" in n or n.endswith(".png") for n in names))

    def test_conversation_history_is_not_cut_for_the_cloud(self):
        from gota import cloud
        sent = {}

        class C(cloud.OpenRouter):
            def _post(self, messages, on_delta=None, retries=1):
                sent["n"] = len(messages)
                return "ok"
        history = [("user" if i % 2 == 0 else "model", f"mensagem {i}") for i in range(300)]
        C("k").chat("k", "sistema", history, "pergunta final")
        self.assertEqual(sent["n"], 302)                       # system + all 300 + the question

class NetconfScope(unittest.TestCase):
    REQ = "Vlan acess 30:\n1 a 24; Usuarios\nTrunk:\n45 a 48; Uplinks\nPortas 49 a 52 devem ser desativadas\n"

    def test_listed_ports_include_sentences(self):
        from gota import netconf
        self.assertEqual(netconf.listed_ports(self.REQ), set(range(1, 25)) | set(range(45, 53)))

    def test_a_reset_wider_than_the_request_is_corrected_silently(self):
        from gota import netconf
        fixed = netconf.enforce_scope(self.REQ, "configure terminal\ndefault interface range GigabitEthernet1/0/1-52\ninterface range GigabitEthernet1/0/1-24\nend")
        self.assertIn("default interface range GigabitEthernet1/0/1-24", fixed)
        self.assertIn("default interface range GigabitEthernet1/0/45-52", fixed)
        self.assertNotIn("1-52", fixed)

    def test_requests_without_a_port_list_are_left_alone(self):
        from gota import netconf
        s = "default interface range GigabitEthernet1/0/1-52"
        self.assertEqual(netconf.enforce_scope("configure o switch", s), s)

    def test_the_validated_final_script_goes_through_the_scope_check(self):
        from gota import brain

        class Cloud:
            def cloud_ready(self): return True
            def cancel(self): pass
            def one_shot(self, system, user, image=None, on_delta=None):
                return "```cisco\nconfigure terminal\ndefault interface range GigabitEthernet1/0/1-52\nend\n```"
        b = brain.Brain(store.Profile(), store.Settings(), lambda: Cloud(), images=None)
        out = b.validated_config(self.REQ, "rascunho")
        self.assertNotIn("1-52", out)
        self.assertIn("1-24", out)

class ProblemLines(unittest.TestCase):
    OCR = ("Processing full backups started at 20/10/2026\nO tSSP06MB1011 Fug backup: 09Kt reference not set to an instance of an object\n"
           "O (SSP06MB101) Failed to backup some full backup filet s'app•ng the correspcnding incrementa/ backups\nBusy: Source 0% > Proxy 5% > Network 0% > Target 5%\n"
           "Network traffic verification detected no corrupted blocks\nO Processing finished with errcrs 't 21/10/2026 01:38:36\n")

    def test_every_cause_is_found_and_reassurance_is_not(self):
        lines = tools.problem_lines(self.OCR)
        self.assertEqual(len(lines), 3)
        self.assertIn("reference not set", lines[0])           # the specific cause first
        self.assertIn("Failed to backup", lines[1])
        self.assertIn("finished with err", lines[2])           # the summary only after the causes
        self.assertFalse(any("no corrupted blocks" in l for l in lines))

    def test_tiles_read_the_whole_screen_once_each_line(self):
        from PIL import Image
        p = Path(tempfile.mkdtemp()) / "blank.png"
        Image.new("RGB", (1200, 700), "white").save(p)
        self.assertIsInstance(tools.ocr_tiles(p), str)          # runs the parallel reading without error on a blank screen

class SpeakableText(unittest.TestCase):
    def test_quotes_markdown_and_odd_symbols_are_removed(self):
        out = brain.speakable_text("O JOB_TAPE_SEMANAL_SEG aparece como \u201cStopped / Failed\u201d, veja **Details** e [Tape] | fim em 21/10/2026.")
        self.assertEqual(out, "O JOB_TAPE_SEMANAL_SEG aparece como Stopped, Failed, veja Details e Tape, fim em 21/10/2026.")
        self.assertNotRegex(out, r"[\u201c\u201d*\[\]|]")

class GlitchCleaning(unittest.TestCase):
    BAD = ("Quem se une aos outros para|the purpose of Aggression|bater em você; se ainda causar ou Oncology participates in|participar de agressão contra você, não é seu amigo.")

    def test_bilingual_fragments_between_bars_are_dropped(self):
        self.assertEqual(brain.clean_glitch(self.BAD), "Quem se une aos outros para bater em você; se ainda causar ou participar de agressão contra você, não é seu amigo.")

    def test_pipelines_tables_and_code_are_untouched(self):
        for ok in ("Use Get-Process | Select Name no PowerShell.", "| a | b |\n|---|---|\n| 1 | 2 |", "```powershell\nGet-A|Get-B\n```\nfim"):
            self.assertEqual(brain.clean_glitch(ok), ok)

    def test_streaming_text_is_cleaned_before_it_is_shown_or_spoken(self):
        from gota import voice
        self.assertNotIn("|", voice.speakable(self.BAD))
        seen = []
        b = brain.Brain(store.Profile(), store.Settings(), lambda: None, images=None)
        b.on_partial = seen.append
        b.stream_to_ui()('{"action":"reply","text":"' + self.BAD + '"}')
        self.assertTrue(seen and "|" not in seen[-1])

class UiBehaviours(unittest.TestCase):
    def test_long_user_message_is_folded_with_ver_mais(self):
        import tkinter as tk
        from gota import widgets
        root = tk.Tk()
        root.withdraw()
        try:
            long_text = "\n".join(f"linha {i} do pedido de configuração" for i in range(20))
            card = widgets.bubble(root, long_text, True, 600)
            root.update()
            labels = lambda: [w.cget("text") for w in card.winfo_children()[0].winfo_children() if isinstance(w, tk.Label)]
            self.assertIn("Ver mais  ▾", labels())
            texts = lambda: "".join(w.get("1.0", "end") for w in card.winfo_children()[0].winfo_children() if isinstance(w, tk.Text))
            self.assertNotIn("linha 19", texts())                 # only a preview
            folded_h = card.winfo_reqheight()
            card.toggle()                                         # what a click on "Ver mais" does
            root.update()
            self.assertIn("linha 19", texts())                    # expanded: the whole message
            self.assertIn("Ver menos  ▴", labels())
            self.assertGreater(card.winfo_reqheight(), folded_h)
            short = widgets.bubble(root, "oi, tudo bem?", True, 600)
            self.assertFalse([w for w in short.winfo_children()[0].winfo_children() if isinstance(w, tk.Label)])   # short messages have no button
            ai = widgets.bubble(root, long_text, False, 600)                                                       # only the user's messages fold
            self.assertFalse([w for w in ai.winfo_children()[0].winfo_children() if isinstance(w, tk.Label)])
        finally:
            root.destroy()

    def test_dragging_a_maximized_window_restores_it_under_the_cursor(self):
        import tkinter as tk
        from gota import chrome
        root = tk.Tk()
        root.geometry("900x600+100+80")
        root.update()
        try:
            ch = chrome.Chrome(root, "t", None, dict(bg="#000", bar="#111", muted="#888", text="#fff", hover="#222"))
            root.update()
            ch.toggle_max()
            root.update()
            self.assertTrue(ch.maximized)
            ev = lambda x, y: type("E", (), {"x_root": x, "y_root": y})()
            ch._start_drag(ev(600, 20))
            ch._drag(ev(640, 60))
            root.update()
            self.assertFalse(ch.maximized)                          # grabbed the bar of a maximized window: it comes back to size
            self.assertTrue(root.geometry().startswith("900x600"))
            self.assertLess(abs(root.winfo_x() - (640 - ch._frac * 900)), 3)   # and sits under the cursor
        finally:
            root.destroy()

    def test_right_click_menu_offers_cut_copy_paste_select_all(self):
        import tkinter as tk
        from unittest import mock
        from gota import app
        root = tk.Tk()
        root.withdraw()
        try:
            entry = tk.Entry(root)
            entry.insert(0, "texto")
            entered = []
            with mock.patch.object(tk.Menu, "tk_popup", lambda self, x, y: entered.extend(self.entrycget(i, "label") for i in range(self.index("end") + 1) if self.type(i) != "separator")):
                app.App._edit_menu(root, type("E", (), {"widget": entry, "x_root": 5, "y_root": 5})())
            self.assertEqual(entered, ["Cortar", "Copiar", "Colar", "Selecionar tudo"])
        finally:
            root.destroy()

class CloudResilience(unittest.TestCase):
    class Settings:
        def get(self, k): return {"cloud_model": "slow/model", "engine": "openrouter"}.get(k)   # these tests are about the OpenRouter client

    def hybrid(self, behaviours):
        import time
        from gota import cloud

        class Fake:
            def __init__(self, key, model="x", effort="low"):
                self.key, self.model, self.effort, self.cancelled = key, model, effort, False
            def cancel(self): self.cancelled = True
            def chat(self, key, system, history, user_text, image=None, think=False, on_delta=None):
                kind, delay, text = behaviours.get(self.model, ("ok", 0, self.model))
                if kind == "gone":
                    raise cloud.ModelGone("retired")
                time.sleep(delay)
                if self.cancelled:
                    return "(cancelado)"
                on_delta and on_delta(text)
                return text
        self.fake = Fake
        self.saved = (cloud.OpenRouter, cloud.load_key, list(cloud.FALLBACK_MODELS))
        cloud.OpenRouter, cloud.load_key = Fake, lambda: "k"
        cloud.FALLBACK_MODELS[:] = ["spare/model"]
        h = cloud.Hybrid(type("L", (), {"chat": lambda *a, **k: "local", "cancel": lambda s: None})(), self.Settings())
        h.HEDGE_SECONDS = 0.2
        self.addCleanup(lambda: (setattr(cloud, "OpenRouter", self.saved[0]), setattr(cloud, "load_key", self.saved[1]), cloud.FALLBACK_MODELS.__setitem__(slice(None), self.saved[2])))
        return h

    def test_a_slow_model_is_raced_by_a_second_one(self):
        h = self.hybrid({"slow/model": ("ok", 1.5, "lento"), "spare/model": ("ok", 0, "rapido")})
        seen = []
        out = h.chat("k", "s", [], "oi", on_delta=seen.append)
        self.assertEqual(out, "rapido")
        self.assertEqual(seen, ["rapido"])                      # only the winner's words reach the screen

    def test_a_model_that_answers_in_time_is_not_raced(self):
        h = self.hybrid({"slow/model": ("ok", 0, "principal"), "spare/model": ("ok", 0, "reserva")})
        self.assertEqual(h.chat("k", "s", [], "oi"), "principal")

    def test_a_retired_model_is_replaced_and_the_user_is_told(self):
        h = self.hybrid({"slow/model": ("gone", 0, ""), "spare/model": ("ok", 0, "reserva")})
        self.assertEqual(h.chat("k", "s", [], "oi"), "reserva")
        self.assertIn("aposentado", h.notice)
        self.assertEqual(h.chat("k", "s", [], "de novo"), "reserva")   # and it stays on the replacement

    def test_text_only_models_hand_pictures_to_the_vision_chain(self):
        from gota import cloud
        cloud._MODALITIES.update({"txt/only": False, "see/it": True})
        calls = []

        class C(cloud.OpenRouter):
            def _post_one(self, messages, on_delta=None, retries=1):
                calls.append(self.model)
                return "visto"
        saved = list(cloud.VISION_MODELS)
        cloud.VISION_MODELS[:] = ["see/it"]
        orig = cloud.OpenRouter
        try:
            cloud.OpenRouter = C
            out = C("k", "txt/only").one_shot("s", "u", __file__.replace("test_core.py", "../gota/assets/cat/logo.png"))
        finally:
            cloud.OpenRouter = orig
            cloud.VISION_MODELS[:] = saved
        self.assertEqual(out, "visto")
        self.assertEqual(calls, ["see/it"])



class OpenCodeEngine(unittest.TestCase):
    """Gota Desktop 2: opencode's free models behind the same client interface (the server is faked here)."""

    def fake(self, reply, record):
        import io, json
        from gota import opencode

        class Resp(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): self.close()

        def call(path, body=None, method=None, timeout=0):
            record.append((method or ("POST" if body is not None else "GET"), path, body))
            if path == "/session":
                return Resp(json.dumps({"id": "ses_1"}).encode())
            if path.endswith("/message"):
                return Resp(json.dumps(reply).encode())
            return Resp(b"{}")
        saved = opencode._call
        opencode._call = call
        self.addCleanup(lambda: setattr(opencode, "_call", saved))
        return opencode

    def test_history_system_and_read_only_agent_go_to_the_server(self):
        rec = []
        oc = self.fake({"info": {}, "parts": [{"type": "text", "text": "Camberra."}]}, rec)
        out = oc.OpenCode("opencode/big-pickle").chat("k", "SISTEMA", [("user", "oi"), ("assistant", "olá")], "capital da Austrália?")
        self.assertEqual(out, "Camberra.")
        body = next(b for m, p, b in rec if p.endswith("/message"))
        self.assertEqual((body["model"], body["agent"], body["system"]), ({"providerID": "opencode", "modelID": "big-pickle"}, "plan", "SISTEMA"))
        text = body["parts"][0]["text"]
        self.assertIn("Usuário: oi", text)
        self.assertTrue(text.endswith("capital da Austrália?"))
        self.assertNotIn("tools", body)   # the tools are left alone: switching them off makes the free tier refuse the request

    def test_a_refusal_from_opencode_becomes_a_cloud_error(self):
        from gota import cloud
        oc = self.fake({"info": {"error": {"name": "APIError", "data": {"message": "limite"}}}, "parts": []}, [])
        with self.assertRaises(cloud.CloudError):
            oc.OpenCode().one_shot("s", "u")

    def test_the_bundled_executable_is_preferred(self):
        from gota import opencode
        exe = opencode.find_exe()
        self.assertTrue(exe is None or exe.lower().endswith("opencode.exe"))
        if (opencode.Path(opencode.__file__).resolve().parent.parent / "opencode" / "opencode.exe").exists():
            self.assertIn("\\opencode\\opencode.exe", exe.lower().replace("/", "\\"))



class CodingMode(unittest.TestCase):
    """The project chat carried out by opencode's build agent (the server is faked: only the translation is tested)."""

    def events(self, *evs):
        import json
        return [("data: " + json.dumps(e) + "\n").encode() for e in evs]

    def coder(self, evs, replies=None):
        import json
        from gota import coder as cm
        c = cm.Coder("C:/proj", "opencode/big-pickle", session="ses_1")
        calls = []

        def req(path, body=None, method=None, timeout=60):
            calls.append((path, body))
            if path.startswith("/event"):
                lines = self.events(*evs)

                class Stream:
                    def __iter__(self): return iter(lines)
                    def close(self): pass
                return Stream()
            class R:
                def close(self): pass
            return R()
        c._req = req
        c._json = lambda path, body=None, method=None, timeout=60: (calls.append((path, body)), (replies or {}).get(path, {"id": "ses_1"}))[1]
        return c, calls

    def test_steps_text_and_permission_are_translated(self):
        S = "ses_1"
        evs = [{"type": "message.updated", "properties": {"info": {"id": "m_u", "sessionID": S, "role": "user"}}},
               {"type": "message.part.updated", "properties": {"part": {"id": "p0", "messageID": "m_u", "sessionID": S, "type": "text", "text": "faça"}}},
               {"type": "message.updated", "properties": {"info": {"id": "m_a", "sessionID": S, "role": "assistant"}}},
               {"type": "message.part.updated", "properties": {"part": {"id": "p1", "messageID": "m_a", "sessionID": S, "type": "tool", "tool": "write",
                                                                        "state": {"status": "completed", "input": {"filePath": "C:/proj/src/a.py"}}}}},
               {"type": "permission.asked", "properties": {"id": "per_1", "sessionID": S, "permission": "bash", "patterns": ["whoami"]}},
               {"type": "message.part.updated", "properties": {"part": {"id": "p2", "messageID": "m_a", "sessionID": S, "type": "text", "text": ""}}},
               {"type": "message.part.delta", "properties": {"sessionID": S, "partID": "p2", "field": "text", "delta": "Pronto."}},
               {"type": "session.idle", "properties": {"sessionID": S}}]
        c, calls = self.coder(evs)
        asked, said = [], []
        out = c.run("faça", on_text=said.append, ask=lambda d: (asked.append(d), False)[1])
        self.assertEqual(out["text"], "Pronto.")
        self.assertEqual(out["steps"], ["write src\\a.py"] if "\\" in str(__import__("pathlib").Path("x/y")) else ["write src/a.py"])
        self.assertEqual(asked, ["bash: whoami"])
        self.assertIn(("/permission/per_1/reply", {"reply": "reject"}), calls)   # the user said no
        body = next(b for pth, b in calls if pth.endswith("/prompt_async"))
        self.assertEqual((body["agent"], body["model"]["modelID"]), ("build", "big-pickle"))
        self.assertEqual(said[-1], "Pronto.")   # the user's own message is not echoed back as the answer

    def test_slash_commands_go_to_opencode_as_commands(self):
        c, calls = self.coder([{"type": "session.idle", "properties": {"sessionID": "ses_1"}}], {"/session/ses_1/message?limit=10": []})
        c.run("/review main", ask=None)
        path, body = next((p, b) for p, b in calls if p.endswith("/command"))
        self.assertEqual((body["command"], body["arguments"]), ("review", "main"))

    def test_an_error_event_becomes_a_cloud_error(self):
        from gota import cloud
        c, _ = self.coder([{"type": "session.error", "properties": {"sessionID": "ses_1", "error": {"name": "APIError", "data": {"message": "limite"}}}}])
        with self.assertRaises(cloud.CloudError):
            c.run("x")

    def test_dangerous_commands_are_denied_and_unknown_ones_ask(self):
        from gota import coder as cm
        rules = cm.PERMISSIONS["bash"]
        self.assertEqual(rules["*"], "ask")
        self.assertEqual(rules["rm -rf*"], "deny")
        self.assertEqual(rules["git reset --hard*"], "deny")
        self.assertEqual(rules["pytest *"], "allow")
        self.assertEqual(list(rules)[0], "*")   # the last matching rule wins, so the catch-all must come first

    def test_the_server_gets_the_permission_rules(self):
        import inspect
        from gota import opencode
        self.assertIn("OPENCODE_CONFIG_CONTENT", inspect.getsource(opencode.Server.ensure))


if __name__ == "__main__":
    unittest.main()
