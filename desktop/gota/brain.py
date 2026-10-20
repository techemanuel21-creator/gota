"""Turns one request into an answer: instant answers first, then tools, then the Gemma model."""
import json, re
from datetime import datetime
from . import tools
from .tools import norm

WEEKDAYS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]

WAKE_PREFIXES = ["hey gota", "hei gota", "ei gota", "oi gota", "e gota", "ai gota", "rei gota", "hey gotta", "gota"]
FRESH_WORDS = re.compile(
    r"\b(noticia|noticias|novidade|novidades|aprovado|aprovada|aprovou|aprovaram|votacao|votou|sancionou|lei|leis|pec|stf|senado|"
    r"camara dos deputados|congresso|governo|presidente|ministro|prefeito|governador|eleicao|eleicoes|candidato|6x1|5x2|12x36|escala|"
    r"reforma|imposto|salario minimo|aposentadoria|inss|fgts|bolsa familia|cotacao|dolar|euro|bitcoin|ibovespa|selic|inflacao|preco|"
    r"precos|quanto custa|placar|campeonato|brasileirao|libertadores|copa do mundo|quem ganhou|quem venceu|proximo jogo|lancamento|"
    r"lancou|estreia|estreou|morreu|faleceu|aconteceu|acontecendo|atualmente|recentemente|ultimas)\b")
FRESH_PATTERNS = [re.compile(p) for p in (
    r"\bja (foi|foram|saiu|sairam|comecou|acabou|terminou|aprovaram|votaram|esta valendo|lancou|chegou|abriu|passou|mudou)\b",
    r"\bquando (vai|vao|comeca|comecam|sai|saem|estreia|abre|acaba|termina|sera|entra|passa a)\b",
    r"\b(vai|vao) (comecar|valer|mudar|aumentar|cair|subir|acabar|sair|estrear)\b",
    r"\b(entra|entrou|entrar) em vigor\b|\bem vigor\b|\b(passa|comeca) a valer\b", r"\b20[2-3]\d\b")]
TIME_WORDS = re.compile(r"\b(hoje|ontem|amanha|essa semana|esta semana|esse mes|este mes|esse ano|este ano|semana passada|mes passado)\b")
QUESTION_START = re.compile(
    r"^(?:(?:e|mas|entao|me diz|me diga|me fala|me conta|voce sabe|sabe|sabe me dizer|pode me dizer)\s+)?"
    r"(quem|qual|quais|quando|quanto|quanta|quantos|quantas|onde|aonde|por que|porque|pq|como|o que|oque|que|sera|existe|existem|tem|e verdade|ja|e possivel)\b")
COMMAND_START = re.compile(
    r"^(?:por favor\s+)?(abre|abra|abrir|liga|ligue|manda|mande|envia|envie|escreve|escreva|cria|crie|gera|gere|desenha|desenhe|faz|faca|"
    r"coloca|coloque|define|defina|programa|programe|lembra|lembre|anota|anote|traduz|traduza|resume|resuma|imagina|imagine|inventa|invente)\b")
CREATIVE = re.compile(r"\b(piada|poema|poesia|historia|historinha|cancao|musica|rima|redacao|imagem|imagens|desenho|ilustracao|papel de parede|wallpaper)\b")
REASONING = re.compile(
    r"\b(por que|porque|pq|explique|explica|como funciona|me ensina|ensina|passo a passo|qual a diferenca|diferenca entre|compare|"
    r"resolva|calcule|vale a pena|o que significa|significado de|o que voce acha|me explique)\b")
EXPLICIT_SEARCH = re.compile(r"^(?:por favor\s+)?(?:pesquise|pesquisa|pesquisar|procure|procura|procurar|busque|busca|buscar)"
                             r"(?:\s+(?:na internet|no google|na web))?(?:\s+(?:pra mim|para mim))?(?:\s+(?:sobre|por))?\s+(.+)$")
OPEN_RE = re.compile(r"^(?:(?:hey |ei )?gota[ ,]*)?(?:por favor[ ,]*)?(?:abre|abra|abrir|inicia|inicie|entra no|entra na)\s+(?:o |a )?(?:app |aplicativo |programa )?(.+?)(?:\s+(?:por favor|pra mim|para mim))?$")
RETRY = re.compile(r"^(?:(?:gera|gere|faz|faca|cria|crie|desenha|desenhe|tenta|tente|manda|mande)\s+)?(?:(?:a|uma|essa)\s+)?"
                   r"(?:outra|outro|de novo|novamente|mais uma|nova)(?:\s+(?:vez|imagem|versao|opcao|variacao|foto|desenho))?$|"
                   r"^(?:refaz|refaca|refazer)(?:\s+(?:a imagem|isso|esse desenho))?$")
WEATHER_WORDS = ("temperatura", "clima", "previsao do tempo", "vai chover", "esta chovendo", "ta chovendo", "frio hoje", "calor hoje",
                 "quantos graus", "como esta o tempo", "como ta o tempo", "guarda chuva")
BRIEFING_WORDS = ("informacoes do dia", "informacao do dia", "resumo do dia", "como esta meu dia", "como vai ser meu dia", "meu dia hoje",
                  "minha agenda", "meus compromissos", "agenda de hoje", "agenda de amanha", "compromissos de hoje", "compromissos de amanha",
                  "o que tenho hoje", "o que eu tenho hoje", "o que tenho amanha", "o que eu tenho amanha", "novidades do dia")
LOCAL_HINTS = ("perto", "proximo", "aqui", "regiao", "minha cidade", "clima", "tempo", "previsao", "chuva", "temperatura", "restaurante",
               "farmacia", "mercado", "hospital", "posto", "cinema", "loja", "aberto", "transito")
NON_ANSWERS = ("nao sei", "nao tenho informac", "nao tenho acesso", "nao tenho dados", "data de corte", "nao consigo saber",
               "nao tenho como saber", "informacoes atualizadas", "recomendo verificar", "recomendo consultar", "sugiro consultar",
               "registrad", "anotado", "compreendido", "entendido", "nao encontrei")
NUMBER_WORDS = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9,
                "dez": 10, "onze": 11, "doze": 12, "vinte e quatro": 24, "trinta e seis": 36, "quarenta e oito": 48}
_SCHEDULE = re.compile(r"(?<![\w])(\d{1,2}|" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")\s+(?:por|x)\s+(\d{1,2}|" +
                       "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")(?![\w])", re.I)


def is_retry(lower): return bool(RETRY.match(lower))


def strip_wake_word(text):
    n = norm(text)
    for p in WAKE_PREFIXES:
        if n.startswith(p + " "):
            words = text.strip().split()
            for i in range(1, len(words) + 1):
                if norm(" ".join(words[:i])) == p:
                    rest = " ".join(words[i:]).lstrip(",.!?:- ")
                    return rest[:1].upper() + rest[1:]
    return text.strip()


def search_query(text):
    def num(w): return str(NUMBER_WORDS.get(norm(w), w)) if not w.isdigit() else w
    q = _SCHEDULE.sub(lambda m: f"{num(m.group(1))}x{num(m.group(2))}", text)
    q = re.sub(r"^(você sabe|voce sabe|vc sabe|sabe me dizer|sabe|me diz|me diga|me fala|me conta|pode me dizer)[,\s]+(se\s+)?", "", q.strip(), flags=re.I)
    return q.strip(" ?!.,")


class Brain:
    def __init__(self, profile, settings, llm_getter, images, on_status=lambda s: None, notify=lambda t: None):
        self.p, self.settings, self.llm, self.images = profile, settings, llm_getter, images
        self.on_status, self.notify = on_status, notify
        self.last_image_prompt = None

    # ------------------------------------------------------------------ prompts
    def system_prompt(self, spoken=False):
        p, sir = self.p, self.p.sir()
        s = [f"Você é o Gota, o mordomo pessoal de {p.address()}: um gato mordomo clássico, educado, discreto e leal, que vive no computador.",
             "Fale sempre em português do Brasil, com acentuação correta, no tom de um mordomo clássico: formal, cordial e prestativo.",
             f"Chame o dono de \"{sir}\" e trate-o por \"{p.pronoun()}\". Exemplos de tom: \"Pois não, {sir}.\", \"Às suas ordens.\", \"Com prazer, {sir}.\""]
        if spoken:
            s += ["Vocês estão conversando por voz: suas respostas serão faladas em voz alta.",
                  "Fale de forma natural e corrida, sem listas, emojis, símbolos ou links. Lembre-se de tudo o que já foi dito na conversa."]
        if p.d["facts"]:
            s += ["", f"O que você já sabe sobre {p.address()}:"] + [f"- {f}" for f in p.d["facts"]]
        if p.d["call_notes"]:
            s += ["", "Do que vocês conversaram nas últimas ligações:"] + [f"- {n}" for n in p.d["call_notes"]]
        s.append(f"""
Responda SEMPRE com um único objeto JSON válido, sem nenhum texto antes ou depois.

Regra de ouro: seja extremamente factual e rigoroso. Responda estritamente com base em fatos conhecidos ou nos dados fornecidos nesta conversa.
Se não souber a resposta exata ou a informação não estiver clara, diga: "Não tenho informações suficientes para responder com certeza, {sir}."
Sob hipótese alguma invente dados, datas, números, fontes, eventos ou nomes.

Como responder em texto:
- Responda exatamente o que foi perguntado, nada além disso, começando já pela resposta.
- Seja curto (1 ou 2 frases), com a elegância de um mordomo. Só se estenda se pedirem explicação.
- Não acrescente conselhos, avisos ou perguntas no final.
- Se a pessoa contar algo sobre si que valha lembrar (gostos, rotina, pessoas próximas, preferências), inclua o campo "remember" com esse fato curto.

Para conversar ou responder perguntas use:
{{"action":"reply","text":"sua resposta"}}

Exemplos:
Pedido: "qual a capital da Austrália?"
Resposta: {{"action":"reply","text":"A capital da Austrália é Camberra, {sir}."}}
Pedido: "eu adoro café sem açúcar"
Resposta: {{"action":"reply","text":"Anotado, {sir}. Café sem açúcar, então.","remember":"Gosta de café sem açúcar"}}
Pedido: "bora, abre o zap pra mim"
Resposta: {{"action":"open_app","name":"WhatsApp"}}
Pedido: "tava pensando em pizza hoje"
Resposta: {{"action":"reply","text":"Excelente ideia, {sir}. Quer que eu procure uma pizzaria?"}}

Você NÃO tem acesso aos contatos. Nunca invente número de telefone.

Ações disponíveis (use UMA quando o pedido exigir):
{{"action":"open_app","name":"nome do programa"}}
{{"action":"whatsapp","number":"número dito pelo usuário","message":"texto"}}
{{"action":"open_url","url":"endereço"}}
{{"action":"search_web","query":"o que pesquisar"}}   (só se pedirem para ABRIR uma pesquisa no navegador)
{{"action":"set_alarm","hour":N,"minute":N,"label":"..."}}
{{"action":"set_timer","seconds":N,"label":"..."}}
{{"action":"share","text":"..."}}   (copiar um texto para a área de transferência)
{{"action":"weather"}}   (clima, temperatura, chuva)
{{"action":"generate_image","prompt":"descrição da imagem EM INGLÊS"}}

Criar imagens: escreva o prompt em inglês, curto e concreto (até 35 palavras), com o mais importante primeiro: o assunto e sua aparência,
a ação, o cenário e o estilo pedido (se nada for pedido, uma foto realista). Mantenha fielmente o que a pessoa pediu, sem tirar nem inventar nada.
NÃO escreva palavras de qualidade como "8k", "detailed" ou "masterpiece": o sistema acrescenta isso sozinho.

Imagens: quando a mensagem vier com uma foto, você consegue vê-la. Responda sobre ela com "reply".

Seu conhecimento tem data de corte. Para notícias, política, leis, votações, esportes, preços, pessoas públicas, lançamentos ou qualquer fato
que muda com o tempo, ou se não tiver certeza, use:
{{"action":"needs_search","query":"termos curtos para pesquisar no Google"}}
Se depender de onde a pessoa está, coloque a cidade na query.""")
        return "\n".join(s)

    # ------------------------------------------------------------------ entry point
    def run(self, request, history, chat_id, image=None, spoken=False, on_phase=lambda p: None):
        """history: [(role, text)] of this chat. Returns (text, image_path_or_None)."""
        self.on_phase = on_phase
        goal = strip_wake_word(request)
        lower = norm(goal)
        sir = self.p.sir()
        if image is None:
            if is_retry(lower) and self.last_image_prompt:
                return self.draw(self.last_image_prompt)
            quick = self.quick_answer(goal, lower)
            if quick:
                return quick, None
            if any(w in lower for w in WEATHER_WORDS):
                return self.weather(goal), None
            if any(w in lower for w in BRIEFING_WORDS):
                return self.briefing(lower), None
            opened = self.try_open_app(goal)
            if opened:
                return opened, None
            m = EXPLICIT_SEARCH.match(lower)
            if m:
                q = self.drop_prefix(goal, lower[:m.start(1)].strip())
                return self.search(goal, self.with_location(goal, search_query(q)))
            if not self.is_command(lower) and self.needs_fresh(lower):
                return self.search(goal, self.with_location(goal, search_query(goal)))

        llm = self.llm()
        if llm is None:
            return f"Perdão, {sir}, minha mente ainda está carregando.", None
        on_phase("thinking")
        self.on_status("Pensando...")
        loc = tools.location() if tools._loc else None
        now = datetime.now()
        where = f" · Local: {loc['city']}" if loc and loc.get("city") else ""
        user_text = f"[Agora: {WEEKDAYS[now.weekday()]}, {now:%d/%m/%Y %H:%M}{where}]\n" + (goal or "O que você vê nesta imagem?")
        turns = [(r, t if r == "user" else json.dumps({"action": "reply", "text": t}, ensure_ascii=False)) for r, t in history if t.strip()]
        think = image is None and self.needs_reasoning(lower)
        try:
            raw = llm.chat(chat_id, self.system_prompt(spoken), turns, user_text, image, think)
        except Exception as e:
            return f"Perdão, {sir}, tive um problema ao pensar: {e}", None
        data = self.extract_json(raw)
        if data is None:
            bad = '"action"' in raw or not raw.strip()
            return (f"Perdão, {sir}, me confundi. Poderia repetir de outro modo?" if bad else raw.strip()), None
        asked = bool(self.is_question(goal, lower))
        if data.get("remember") and not asked and re.search(r"\b(eu|meu|minha|meus|minhas|me chamo|moro|trabalho|gosto|prefiro|adoro|odeio|sou|tenho)\b", lower):
            self.p.remember(str(data["remember"]))
        return self.act(data, goal, lower, image, asked)

    # ------------------------------------------------------------------ actions
    def act(self, d, goal, lower, image, asked):
        sir = self.p.sir()
        a = d.get("action")
        if a == "reply":
            text = d.get("text") or f"Pois não, {sir}."
            if image is None and asked and any(n in norm(text) for n in NON_ANSWERS) and tools.is_online():
                return self.search(goal, self.with_location(goal, search_query(goal)))
            return text, None
        if a == "open_app":
            return self.open_named(str(d.get("name", ""))), None
        if a == "whatsapp":
            digits = re.sub(r"\D", "", str(d.get("number", "")))
            if len(digits) < 8 or digits not in re.sub(r"\D", "", goal):
                return f"Não tenho esse número, {sir}; não acesso seus contatos. Poderia me dizer o número completo?", None
            from urllib.parse import quote
            tools.open_url(f"https://wa.me/{digits}?text={quote(str(d.get('message', '')))}")
            return f"Abri o WhatsApp de {digits} com a mensagem pronta, {sir}.", None
        if a == "open_url":
            tools.open_url(str(d.get("url", "")))
            return f"Abrindo {d.get('url')}, {sir}.", None
        if a == "search_web":
            from urllib.parse import quote
            tools.open_url("https://www.google.com/search?q=" + quote(str(d.get("query", ""))))
            return f"Abri a pesquisa por \"{d.get('query')}\", {sir}.", None
        if a == "set_timer":
            secs = int(d.get("seconds") or 0)
            tools.add_timer(secs, str(d.get("label", "")), self.notify)
            return f"Timer de {secs // 60} min {secs % 60} s iniciado, {sir}.", None
        if a == "set_alarm":
            t = tools.add_alarm(int(d.get("hour") or 0), int(d.get("minute") or 0), str(d.get("label", "")), self.notify)
            return f"Alarme ajustado para {t:%H:%M}, {sir}.", None
        if a == "share":
            self.notify("__clipboard__:" + str(d.get("text", "")))
            return f"Copiei o texto para a área de transferência, {sir}.", None
        if a == "weather":
            return self.weather(goal), None
        if a == "generate_image":
            return self.draw(str(d.get("prompt") or goal))
        if a == "needs_search":
            return self.search(goal, self.with_location(goal, search_query(str(d.get("query") or goal))))
        if a in ("call", "sms", "count_unread"):
            return f"Isso só é possível no celular, {sir}. No computador não tenho acesso a ligações, mensagens de texto ou notificações.", None
        return (d.get("text") or d.get("message") or f"Perdão, {sir}, me confundi. Poderia repetir de outro modo?"), None

    def draw(self, prompt):
        sir = self.p.sir()
        self.last_image_prompt = prompt
        self.on_phase("drawing")
        self.on_status("Pintando a imagem...")
        try:
            path = self.images.generate(prompt, self.on_status)
        except self.images.NotReady as e:
            return str(e), None
        except Exception as e:
            return f"Perdão, {sir}, não consegui pintar a imagem agora ({str(e)[:100]}).", None
        return f"Aqui está, {sir}. Já guardei em {path.parent}. Se não ficou bom, peça \"outra\" que eu tento de novo.", str(path)

    def search(self, goal, query):
        sir = self.p.sir()
        if not tools.is_online():
            return f"Estou sem internet no momento, {sir}, e preciso pesquisar para responder isso.", None
        self.on_phase("searching")
        self.on_status("Pesquisando...")
        try:
            snippets, pages = tools.web_search(query)
        except Exception:
            snippets, pages = [], []
        if not snippets and not pages:
            return f"Pesquisei, {sir}, mas não encontrei nada sobre isso.", None
        llm = self.llm()
        if llm is None:
            return f"Perdão, {sir}, minha mente ainda está carregando.", None
        self.on_status("Lendo o que encontrei...")
        today = datetime.now()
        system = f"""Você é o Gota, mordomo pessoal de {self.p.address()}. Responda em português do Brasil, com acentuação correta, no tom cordial de um mordomo clássico, chamando o dono de "{sir}". Hoje é {today.day} de {MONTHS[today.month - 1]} de {today.year}.
Você pesquisou na internet e recebeu trechos. Responda à pergunta direto, em 1 ou 2 frases, como quem já sabe a resposta:
- Os trechos estão em ordem do MAIS RECENTE para o mais antigo. O trecho 1 é o mais novo; cada um começa com a data entre parênteses.
- Baseie a resposta no estado MAIS RECENTE dos fatos. Se um trecho antigo diz "vai acontecer" e um mais novo diz que "aconteceu/foi aprovado", vale o mais novo.
- Para perguntas de "já foi...?", "quando...", "qual o último/mais recente", prefira o trecho 1.
- Inclua o dado principal (número, data, nome) e diga datas por extenso ("ontem, 14 de outubro").
- O 'Contexto' no fim pode estar desatualizado; só use se os trechos datados não bastarem.
- Nunca mencione "trechos", "resultados", "pesquisa" ou sites, e não sugira onde conferir.
- Não acrescente nada que não foi perguntado.
- Seja estritamente factual: use apenas o que está nos trechos. Se eles não trouxerem a resposta com clareza, diga só: "Não tenho informações suficientes para responder com certeza, {sir}." Nunca invente dados, datas, fontes ou eventos.
Responda em texto simples, sem JSON e sem listas."""
        user = f"Pergunta: {goal}\n\nTrechos (1 = mais recente):\n" + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(snippets))
        if pages:
            user += "\n\nContexto (sem data, pode estar desatualizado):\n" + "\n".join(pages)
        try:
            raw = llm.one_shot(system, user)
        except Exception as e:
            return f"Encontrei algo, {sir}, mas não consegui ler: {e}", None
        data = self.extract_json(raw)
        return ((data or {}).get("text") or raw.strip() or f"Não encontrei essa informação agora, {sir}."), None

    def weather(self, goal):
        sir = self.p.sir()
        if not tools.is_online():
            return f"Estou sem internet no momento, {sir}, então não consigo consultar o clima."
        self.on_status("Consultando o clima...")
        try:
            return tools.weather_answer(goal, sir)
        except Exception:
            return f"Não consegui consultar a previsão agora, {sir}."

    def briefing(self, lower):
        sir, tomorrow = self.p.sir(), "amanha" in lower
        self.on_status("Consultando sua agenda...")
        pron = self.p.pronoun().capitalize()
        word = "amanhã" if tomorrow else "hoje"
        parts = []
        if not tomorrow:
            now = datetime.now()
            salute = "Bom dia" if 5 <= now.hour < 12 else "Boa tarde" if now.hour < 18 else "Boa noite"
            parts.append(f"{salute}, {self.p.address()}. Hoje é {WEEKDAYS[now.weekday()]}, {now.day} de {MONTHS[now.month - 1]}.")
        events = tools.calendar_events(1 if tomorrow else 0)
        if events is None:
            parts.append("Não consegui acessar a agenda: preciso do Outlook clássico instalado neste computador.")
        elif not events:
            parts.append(f"{pron} não tem compromissos na agenda {word}.")
        else:
            desc = "; ".join(f"às {h} {t}" for h, t in events)
            parts.append(f"{pron} tem {'um compromisso' if len(events) == 1 else f'{len(events)} compromissos'} {word}: {desc}.")
        if not tomorrow and tools.is_online():
            try:
                parts.append(tools.weather_answer("clima", sir).rsplit(f" {sir.capitalize()}.", 1)[0] + ".")
            except Exception:
                pass
        return " ".join(parts)

    # ------------------------------------------------------------------ apps
    def open_named(self, name):
        sir = self.p.sir()
        found = tools.find_app(name, self.settings.get("aliases"))
        if not found:
            return f"Não encontrei nenhum programa chamado \"{name}\", {sir}."
        try:
            tools.launch(found[1])
        except Exception as e:
            return f"Não consegui abrir o {found[0]}, {sir}."
        return f"Abrindo o {found[0]}, {sir}."

    def try_open_app(self, goal):
        m = OPEN_RE.match(norm(goal))
        if not m:
            return None
        name = m.group(1).strip()
        if not name or len(name.split()) > 5:
            return None
        return self.open_named(name)

    # ------------------------------------------------------------------ quick answers (no model)
    def quick_answer(self, goal, lower):
        p, sir = self.p, self.p.sir()
        t = self.time_or_date(lower)
        if t:
            return t
        greeting = re.sub(r"\b(gota|hey|ei)\b", "", lower).strip()
        now = datetime.now()
        salute = "Bom dia" if 5 <= now.hour < 12 else "Boa tarde" if now.hour < 18 else "Boa noite"
        serve = {"senhora": "servi-la", "": "ajudar"}.get(p.treatment, "servi-lo")
        if greeting in ("bom dia", "boa tarde", "boa noite"):
            return f"{greeting.capitalize()}, {p.address()}. Em que posso {serve}?"
        if greeting in ("oi", "ola", "e ai", "opa", ""):
            return f"{salute}, {p.address()}. Às suas ordens."
        if greeting in ("obrigado", "obrigada", "valeu", "muito obrigado", "muito obrigada"):
            return f"Disponha, {sir}. É sempre um prazer."
        if greeting in ("tudo bem", "tudo bem com voce", "como voce esta", "como vai"):
            return f"Muito bem, {sir}, obrigado por perguntar. Em que posso ajudar?"
        if lower in ("qual e o seu nome", "qual o seu nome", "quem e voce", "qual seu nome"):
            return f"Sou o Gota, {sir}, seu mordomo pessoal."
        if lower in ("qual e o meu nome", "qual o meu nome", "como eu me chamo", "quem sou eu"):
            return f"{p.address().capitalize()}, naturalmente."
        m = re.match(r"^(?:me chame de|me chama de|pode me chamar de|meu nome e)\s+(.+)$", lower)
        if m:
            n = " ".join(goal.strip().split()[-len(m.group(1).split()):]).strip(" .!")
            p.set_name(n, p.treatment)
            return f"Como desejar. A partir de agora, {p.address()}."
        m = re.match(r"^(?:lembre|lembra|lembre se|lembra que|lembre que|guarde|anote)\s+(?:que\s+|de que\s+)?(.+)$", lower)
        if m:
            fact = re.sub(r"^(?i:lembre-se|lembre|lembra|guarde|anote)\s+(de que |que )?", "", goal.strip())
            p.remember(fact[:1].upper() + fact[1:])
            return f"Anotado, {sir}. Não esquecerei."
        return None

    def time_or_date(self, lower):
        sir = self.p.sir()
        asks_time = any(x in lower for x in ("que horas sao", "que hora e", "que horas e", "qual a hora", "qual e a hora", "horas agora", "hora agora"))
        today = "hoje" in lower
        asks_date = today and any(x in lower for x in ("que dia", "qual dia", "data"))
        asks_week = today and "dia da semana" in lower
        if not (asks_time or asks_date or asks_week):
            return None
        n = datetime.now()
        date = f"{WEEKDAYS[n.weekday()]}, {n.day} de {MONTHS[n.month - 1]}"
        if asks_time and (asks_date or asks_week):
            return f"São {n:%H:%M} de {date}, {sir}."
        if asks_time:
            return f"São {n:%H:%M}, {sir}."
        if asks_week and not asks_date:
            return f"Hoje é {WEEKDAYS[n.weekday()]}, {sir}."
        return f"Hoje é {date} de {n.year}, {sir}."

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def drop_prefix(text, normalized_prefix):
        words = text.strip().split()
        for i in range(1, len(words) + 1):
            if norm(" ".join(words[:i])) == normalized_prefix:
                return " ".join(words[i:]).lstrip(",.!?:- ")
        return text.strip()

    @staticmethod
    def is_command(lower): return bool(COMMAND_START.search(lower) or CREATIVE.search(lower))

    @staticmethod
    def is_question(goal, lower):
        return "?" in goal or bool(QUESTION_START.search(lower)) or any(p.search(lower) for p in FRESH_PATTERNS[:3])

    @staticmethod
    def needs_fresh(lower):
        return bool(FRESH_WORDS.search(lower) or any(p.search(lower) for p in FRESH_PATTERNS) or (TIME_WORDS.search(lower) and QUESTION_START.search(lower)))

    @staticmethod
    def needs_reasoning(lower): return bool(REASONING.search(lower) or ("?" in lower and len(lower.split()) > 8))

    def with_location(self, goal, query):
        loc = tools.location() if tools.is_online() else None
        city = (loc or {}).get("city")
        if not city or city.lower() in query.lower():
            return query
        return f"{query} {city}" if any(h in norm(goal + " " + query) for h in LOCAL_HINTS) else query

    @staticmethod
    def extract_json(raw):
        s = raw.replace("```json", "").replace("```", "").strip()
        i = s.find("{")
        if i == -1:
            return None
        tail = s[i:]
        end = tail.rfind("}")
        for cand in ([tail[:end + 1]] if end != -1 else []) + [tail + "}", tail + '"}']:
            try:
                return json.loads(cand)
            except Exception:
                continue
        return None
