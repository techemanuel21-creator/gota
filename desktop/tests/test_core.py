"""Core checks. Run: python -m unittest discover -s tests  (from the desktop folder)."""
import json, os, sys, tempfile, unittest
from pathlib import Path

os.environ["GOTA_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gota import brain, store, tools
from gota.imagegen import ClipTokenizer, suffix_for, PHOTO, ART, PAINTING

CLIP = Path(__file__).resolve().parents[2] / "app/src/test/resources/clip"
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
        self.assertEqual(got["title"], "olá mundo")
        self.assertEqual(c.voice()["id"], "voice")
        self.assertEqual(c.list()[0]["id"], "voice")


if __name__ == "__main__":
    unittest.main()
