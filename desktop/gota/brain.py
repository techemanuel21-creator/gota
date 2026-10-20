"""Turns one request into an answer: instant answers first, then tools, then the Gemma model."""
import json, re, time
from pathlib import Path
from datetime import datetime
from . import agent as agent_mod, kb, quick, skills as skills_mod, tools, outlook as outlook_mod, whatsapp as wa_mod
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
SCREEN_WORDS = re.compile(r"\b(tela|print|captura|screenshot|esta vendo|ta vendo|olha (isso|aqui|essa|esse)|olhe (isso|aqui)|esse erro|essa janela|"
                          r"le a tela|leia a tela|analisa a tela|analise a tela)\b")
AGENT_WORDS = re.compile(
    r"\b(pasta|pastas|arquivo|arquivos|diretorio|planilha|excel|csv|pdf|docx|relatorio|comando|powershell|terminal|processo|processos|"
    r"disco|espaco em disco|memoria ram|uso de cpu|cpu|temperatura do|portas abertas|conexoes|rede local|adaptador|ping|git|commit|"
    r"docker|zip|compacta|descompacta|converte|converter|log|logs|renomeia|renomear|organiza|organizar|limpa|limpar|temporarios|cache|"
    r"agende|monitora|monitorar|avise quando|variaveis de ambiente|sql|banco de dados|sqlite|traduz|traduza|"
    r"transcreve|transcrever|varredura|segredos|requisicao|testes|pytest|modo agente)\b")
TECH_WORDS = re.compile(
    r"\b(windows|linux|ubuntu|debian|centos|rhel|powershell|cmd|registro|firewall|vpn|dns|dhcp|active directory|gpo|ldap|kerberos|"
    r"ransomware|malware|virus|phishing|cve|vulnerabilidade|pentest|nmap|ssh|rdp|smb|kubernetes|k8s|veeam|backup|restore|restauracao|"
    r"raid|iscsi|vmware|vsphere|esxi|hyper v|proxmox|servidor|bsod|tela azul|evento|event id|bash|regex|ssl|tls|"
    r"certificado|protocolo|vlan|switch|roteador|snmp|zabbix|prometheus|grafana|nginx|apache|iis|ciberseguranca|"
    r"infraestrutura|hardening|criptografia|siem|edr|incidente|auditoria|iso 27001|nist|mitre|owasp|exchange|"
    r"azure|aws|nuvem|terraform|ansible|jenkins|monitoramento|latencia|subnet|bgp|ospf|snapshot)\b")
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


def reply_text_so_far(acc):
    """The text of an answer that is still being written: the "text" of a reply JSON (even half-written), or plain text.
    None while the model is writing an action (nothing to show), "" while it is still before the text."""
    s = acc.lstrip()
    if s.startswith("```"):                    # a ```json fence around the JSON
        s = s.split("\n", 1)[1] if "\n" in s else ""
    if not s.startswith("{"):
        return s
    act = re.search(r'"action"\s*:\s*"(\w+)"', s)
    if act and act.group(1) not in ("reply", "final"):   # "final" is the agent's closing answer
        return None
    t = re.search(r'"text"\s*:\s*"', s)
    if not t:
        return ""
    raw, out, i = s[t.end():], [], 0
    simple = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "/": "/"}
    while i < len(raw):
        c = raw[i]
        if c == "\\":
            if i + 1 >= len(raw):
                break
            n = raw[i + 1]
            if n == "u":
                if i + 6 > len(raw):
                    break
                try:
                    out.append(chr(int(raw[i + 2:i + 6], 16)))
                except ValueError:
                    pass
                i += 6
                continue
            out.append(simple.get(n, n))
            i += 2
            continue
        if c == '"':
            break
        out.append(c)
        i += 1
    return "".join(out)


class Brain:
    def __init__(self, profile, settings, llm_getter, images, on_status=lambda s: None, notify=lambda t: None):
        self.p, self.settings, self.llm, self.images = profile, settings, llm_getter, images
        self.on_status, self.notify = on_status, notify
        self.last_image_prompt = None
        self.confirm = lambda text, danger: False   # replaced by the window
        self.confirm_message = None                 # (found, requested, message, extra) -> (ok, edited text); the window or the call replaces it
        self.hide_window = lambda hide: None        # hides Gota's own windows while the screen is captured
        self._tried = {}         # subjects Gota already tried to learn in this session
        self.on_phase = lambda p: None
        self.on_partial = None   # set by the window/voice for the length of one request: called with the answer as it is being written
        self.gen = 0  # raised by cancel(): work started under an older value must stop and hand back nothing
        self.outlook, self.whatsapp = outlook_mod.Outlook(settings), wa_mod.WhatsApp(settings)
        self.agent = agent_mod.Agent(self, lambda t, d: self.confirm(t, d), lambda s: self.on_status(s))

    # ------------------------------------------------------------------ prompts
    def system_prompt(self, spoken=False):
        """The fixed instructions. Kept short and identical for typing, voice and calls: the model reads them once per conversation (about 10 ms per word)."""
        p, sir = self.p, self.p.sir()
        s = [f'Você é o Gota, mordomo pessoal de {p.address()}: um gato mordomo clássico, educado e leal que vive no computador. '
             f'Fale em português do Brasil, com acentuação correta, formal e cordial; chame o dono de "{sir}" (trate por "{p.pronoun()}"). Ex.: "Pois não, {sir}.", "Às suas ordens."']
        if p.d["facts"]:
            s += ["", f"O que você já sabe sobre {p.address()}:"] + [f"- {f}" for f in p.d["facts"]]
        if p.d["call_notes"]:
            s += ["", "Das últimas ligações:"] + [f"- {n}" for n in p.d["call_notes"]]
        s.append(f"""
Responda SEMPRE com UM objeto JSON válido e nada fora dele (sem cerca ```json em volta; os blocos de código ficam só dentro de "text").
Seja rigorosamente factual: nunca invente dados, datas, números, fontes, nomes nem telefones (você não tem acesso a contatos). Se não souber: "Não tenho informações suficientes para responder com certeza, {sir}."
Texto: responda só o que foi perguntado, já pela resposta, em 1 ou 2 frases elegantes, sem conselhos nem perguntas no fim. Comandos e códigos vão em bloco com crases triplas e a linguagem, dentro de "text" (```powershell ... ```). Se a pessoa contar algo pessoal que valha lembrar, acrescente "remember":"fato curto".
Conversar: {{"action":"reply","text":"..."}}
Ações (UMA quando o pedido exigir):
{{"action":"open_app","name":"programa"}}  {{"action":"whatsapp","number":"número dito","message":"texto"}} (só se disser um NÚMERO)  {{"action":"open_url","url":"..."}}  {{"action":"search_web","query":"..."}} (só para ABRIR pesquisa no navegador)
{{"action":"set_alarm","hour":N,"minute":N,"label":"..."}}  {{"action":"set_timer","seconds":N,"label":"..."}}  {{"action":"share","text":"..."}} (copiar texto)  {{"action":"weather"}}  {{"action":"generate_image","prompt":"descrição EM INGLÊS"}}
{{"action":"look_at_screen","screen":N}} fotografa a tela e responde olhando; "screen" só se indicou uma tela (número de "Telas:" ou "all" para todas), senão usa a tela da janela ativa dele
{{"action":"whatsapp_send","contact":"nome","message":"texto ou vazio","screenshot":true,"screen":N,"region":"parte da tela"}} envia mensagem e/ou print a um CONTATO pelo WhatsApp conectado; "contact" é o nome EXATAMENTE como o usuário falou (não corrija nem troque a grafia, ex.: "Emanuel SP" continua "Emanuel SP"); "screenshot" se pediu print; "region" só se pediu apenas uma parte; "message" é o texto na voz do próprio dono (primeira pessoa), nunca como Gota ou IA; se ele corrige um rascunho que acabou de recusar ("não explique...", "mais curto"), refaça whatsapp_send com o texto corrigido
{{"action":"outlook","kind":"agenda","days":N}} agenda/compromissos (N dias a partir de hoje)   {{"action":"outlook","kind":"emails","unread":false,"days":N}} ler/analisar e-mails (importantes, pendentes de resposta, não lidos)
{{"action":"use_computer","background":false}} (com "background":true se a pessoa pedir para fazer em segundo plano ou avisar depois) VOCÊ executar algo neste computador agora: arquivos, pastas, comandos, processos, rede, disco, git, relatórios, tarefas agendadas. Pergunta de COMO fazer algo ("como eu...", "qual o comando...", "como se faz") NÃO é use_computer: é ask_expert, e a resposta mostra o comando em bloco de código
{{"action":"ask_expert","query":"pergunta técnica completa e autônoma"}} TI, segurança, Windows, Linux, redes, backup, Veeam: responde por conhecimento
{{"action":"needs_search","query":"termos curtos"}} para notícias, leis, esportes, preços, pessoas públicas, lançamentos, o que muda com o tempo ou se tiver dúvida (cidade na query se depender do local)
Escolha pela intenção da frase inteira (vem de voz, é informal) e pela conversa até aqui; se a pessoa corrige ou complementa, siga o assunto. "query" deve ser completa e autônoma, resolvendo o que já foi dito.
Se a resposta depende do que ela vê ou faz agora no computador (janela, console, job, erro, "aqui", "isso", "esse"), use look_at_screen: não pesquise nem responda de cabeça. Se pede para MANDAR algo a alguém, é whatsapp_send, mesmo citando tela ou print.
Exemplos:
"qual a capital da Austrália?" -> {{"action":"reply","text":"Camberra, {sir}."}}
"eu adoro café sem açúcar" -> {{"action":"reply","text":"Anotado, {sir}.","remember":"Gosta de café sem açúcar"}}
"abre o zap" -> {{"action":"open_app","name":"WhatsApp"}}
"tem um job no Veeam aí com problema, analisa" -> {{"action":"look_at_screen"}}
"me explica esse erro aqui" / "o que significa esse aviso?" / "esse backup deu warning, por quê?" -> {{"action":"look_at_screen"}}
"analisa a segunda tela" (com "Telas:") -> {{"action":"look_at_screen","screen":2}}
"vê o que tá rolando nas duas telas" / "analisa todas as telas" (com "Telas:") -> {{"action":"look_at_screen","screen":"all"}}
"como funciona o RAID 5?" -> {{"action":"ask_expert","query":"como funciona o RAID 5"}}
"mostra os arquivos da pasta downloads" -> {{"action":"use_computer"}}
"como eu listo os serviços em execução no PowerShell?" -> {{"action":"ask_expert","query":"comando do PowerShell para listar os serviços em execução"}}
"lista os serviços que estão rodando" -> {{"action":"use_computer"}}
"tira um print da tela e manda pro João" -> {{"action":"whatsapp_send","contact":"João","message":"","screenshot":true}}
"manda um print da metade direita pra Maria dizendo olha isso" -> {{"action":"whatsapp_send","contact":"Maria","message":"olha isso","screenshot":true,"region":"metade direita da tela"}}
"manda pro Carlos que eu chego em 10 minutos" -> {{"action":"whatsapp_send","contact":"Carlos","message":"Estou chegando em 10 minutos","screenshot":false}}
"qual minha agenda de hoje no Outlook?" -> {{"action":"outlook","kind":"agenda","days":1}}
"no Outlook, quais e-mails importantes ainda preciso responder?" -> {{"action":"outlook","kind":"emails","unread":false,"days":14}}
Imagens: o prompt vai em inglês, curto (até 35 palavras), fiel ao pedido, sem "8k", "detailed" ou "masterpiece". Se a mensagem vier com uma foto, você a vê: responda com "reply".""")
        return "\n".join(s)

    # ------------------------------------------------------------------ entry point
    def run(self, request, history, chat_id, image=None, spoken=False, on_phase=lambda p: None, project=None):
        """history: [(role, text)] of this chat. Returns (text, image_path_or_None)."""
        self.on_phase = on_phase
        self.spoken, self.history = spoken, history
        goal = strip_wake_word(request)
        if project and image is None:   # a coding chat: everything goes to the project agent, working inside that folder
            on_phase("working")
            return self.agent.run_project(goal, project, history), None
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
                if "outlook" in lower or self.outlook.connected():   # the connected Outlook is the source of the agenda, not the old desktop-Outlook shortcut
                    return self.outlook_answer(goal, {"kind": "agenda", "days": 2 if "amanha" in lower else 1}), None
                return self.briefing(lower), None
            opened = self.try_open_app(goal)
            if opened:
                return opened, None
            m = EXPLICIT_SEARCH.match(lower)
            if m:
                q = self.drop_prefix(goal, lower[:m.start(1)].strip())
                return self.search(goal, self.with_location(goal, search_query(q)))

        llm = self.llm()
        if llm is None:
            if image is None and not self.is_command(lower) and self.needs_fresh(lower):
                return self.search(goal, self.with_location(goal, search_query(goal)))
            return f"Perdão, {sir}, minha mente ainda está carregando.", None
        on_phase("thinking")
        self.on_status("Pensando...")
        loc = tools.location() if tools._loc else None
        now = datetime.now()
        where = f" · Local: {loc['city']}" if loc and loc.get("city") else ""
        screens = tools.screens_note(self.screen_nicks())   # which screens exist and where the cursor is (empty with a single screen)
        extra = (" · " + screens if screens else "") + (" · RESPOSTA FALADA: fale natural e corrido, sem listas, emojis, símbolos nem links" if spoken else "")
        user_text = f"[Agora: {WEEKDAYS[now.weekday()]}, {now:%d/%m/%Y %H:%M}{where}{extra}]\n" + (goal or "O que você vê nesta imagem?")
        turns = [(r, t if r == "user" else json.dumps({"action": "reply", "text": t}, ensure_ascii=False)) for r, t in history if t.strip()]
        try:
            # first pass without the slow "thinking" mode: it is enough to decide what to do (look at the screen, search, answer...)
            will_override = image is None and tools.is_online() and bool(self.is_question(goal, lower)) and not self.is_command(lower) and (self.needs_fresh(lower) or bool(TECH_WORDS.search(lower)))
            raw = llm.chat(chat_id, self.system_prompt(), turns, user_text, image, False, on_delta=None if will_override else self.stream_to_ui())
        except Exception as e:
            return f"Perdão, {sir}, tive um problema ao pensar: {e}", None
        data = self.extract_json(raw)
        if data is None and '"reply"' in raw:   # a reply whose code block broke the JSON (raw line breaks inside the text): take the text as it is
            m = re.search(r'"text"\s*:\s*"(.*)"\s*\}?\s*$', raw.strip(), re.S)
            if m:
                data = {"action": "reply", "text": m.group(1).replace('\\n', '\n').replace('\\"', '"')}
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
        if a == "look_at_screen":
            self.on_phase("thinking")
            return self.look_at_screen(goal, spoken=self.spoken, history=self.history, screen=self.parse_screen(goal) or d.get("screen")), None
        if a == "whatsapp_send":
            self.on_phase("working")
            d["screen"] = self.parse_screen(goal) or d.get("screen")
            return self.whatsapp_send(goal, d), None
        if a == "outlook":
            self.on_phase("working")
            return self.outlook_answer(goal, d), None
        if a == "use_computer":
            if d.get("background") in (True, "true", 1):   # "faz isso em segundo plano e me avisa": he keeps talking while the task runs
                task = self.agent.run_background(goal, lambda t: self.notify(f"Terminei a tarefa em segundo plano, {sir}: {t['result'][:400]}"))
                return f"Certo, {sir}. Cuido disso em segundo plano (tarefa {task['id']}) e aviso quando terminar.", None
            self.on_phase("working")
            return self.agent.run(goal, self.history), None
        if a == "ask_expert":
            self.on_phase("thinking")
            return self.expert_answer(goal, spoken=self.spoken, query=str(d.get("query") or "") or None), None
        if a == "reply":
            text = d.get("text") or f"Pois não, {sir}."
            if image is None and asked and tools.is_online():  # safety nets: facts that change, and IT answers that should come from the knowledge base
                if self.needs_fresh(lower) and not self.is_command(lower):
                    return self.search(goal, self.with_location(goal, search_query(goal)))
                if TECH_WORDS.search(lower) and not self.is_command(lower):
                    return self.expert_answer(goal, spoken=self.spoken), None
            if image is None and asked and any(n in norm(text) for n in NON_ANSWERS) and tools.is_online():
                if TECH_WORDS.search(lower) or not self.needs_fresh(lower):   # it does not know: learn the documentation and answer from it
                    return self.expert_answer(goal), None
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

    def recent(self, n=6, chars=240):
        """The last turns of this conversation as plain text, so the specialised paths answer knowing what was already said."""
        out = []
        for r, t in list(getattr(self, "history", []))[-n:]:
            if r != "user":
                try:
                    t = json.loads(t).get("text") or t
                except Exception:
                    pass
            if t.strip():
                out.append(("Dono: " if r == "user" else "Gota: ") + re.sub(r"\s+", " ", t)[:chars])
        return "\n".join(out)

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
        ctx = self.recent()
        user = (f"Conversa até agora (para entender a pergunta):\n{ctx}\n\n" if ctx else "") + f"Pergunta: {goal}\n\nTrechos (1 = mais recente):\n" + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(snippets))
        if pages:
            user += "\n\nContexto (sem data, pode estar desatualizado):\n" + "\n".join(pages)
        try:
            raw = llm.one_shot(system, user, on_delta=self.stream_to_ui())
        except Exception as e:
            return f"Encontrei algo, {sir}, mas não consegui ler: {e}", None
        data = self.extract_json(raw)
        return ((data or {}).get("text") or raw.strip() or f"Não encontrei essa informação agora, {sir}."), None

    EXPERT = """Você é o Gota, especialista sênior em cibersegurança, infraestrutura de TI, Windows, Linux, redes, backup e recuperação (inclusive Veeam), linha de comando e automação, e mordomo pessoal de {who}. Fale português do Brasil, formal e objetivo, chamando o dono de "{sir}".
Responda usando principalmente o MATERIAL abaixo (sua base de conhecimento). Regras:
- Se o material trouxer uma HABILIDADE (procedimento passo a passo), siga os passos dela na ordem e use os comandos dela; adapte só os nomes ao caso.
- Seja estritamente factual. Se o material não cobrir a pergunta com clareza, diga o que sabe com certeza e que não tem informação suficiente para o resto. Nunca invente comandos, parâmetros, versões, portas ou valores.
- Dê a resposta direta e, quando for útil, o comando exato em um bloco de código com crases triplas e a linguagem (```powershell, ```bash, ```cmd ...), com a explicação fora do bloco. Explique em poucas frases, sem enrolar.
- Em temas de segurança ofensiva, ajude apenas em contexto autorizado e defensivo.
- Cite a fonte pelo nome entre parênteses no final (fonte: ...). Responda em texto simples."""

    def expert_answer(self, goal, spoken=False, image=None, query=None):
        """Answers IT questions from the knowledge base; when it has nothing good it learns from the internet first."""
        sir = self.p.sir()
        llm = self.llm()
        q = query or goal
        hits = kb.search(q, 4)
        skill_hits = [h for h in skills_mod.search(q, 3) if not h[1]["name"].startswith("desenvolver")][:2]
        learned = []
        if not skill_hits and not kb.good_enough(hits, q) and tools.is_online() and tools.norm(q) not in self._tried:   # one attempt per subject per session
            self._tried[tools.norm(q)] = time.time()
            self.on_phase("searching")
            learned = self.learn_topic(q)
            hits = kb.search(q, 4)
        if (not hits or hits[0][0] < 4.5) and not skill_hits and llm is not None and len(kb.listing()) > 5:
            # weak match: the notes (often English documentation) may use other words than the question; search again with its English keywords
            try:
                terms = str(llm.one_shot("Traduza para inglês técnico as palavras-chave desta pergunta (no máximo 8 palavras, separadas por espaço, sem frases).", q)).strip().splitlines()[0][:120]
                alt = kb.search(q + " " + terms, 4)
                if alt and (not hits or alt[0][0] > hits[0][0]):
                    hits = alt
            except Exception:
                pass
        if not hits and not skill_hits:
            msg = "Não tenho informações suficientes na minha base e não consegui material novo" + ("" if tools.is_online() else " (estou sem internet)")
            return f"{msg}, {sir}."
        self.on_status("Consultando minha base de conhecimento...")
        kb_part = "\n\n".join(f"[{t}] (fonte: {src})\n{txt[:1100]}" for _, t, src, txt in hits[:1 if skill_hits else 3])[:900 if skill_hits else 3200]   # every extra line costs seconds of reading
        material = (skills_mod.prompt_block(skill_hits, 1400) + ("\n\n" if kb_part else "") if skill_hits else "") + kb_part
        system = self.EXPERT.format(who=self.p.address(), sir=sir) + ("\nSua resposta será falada em voz alta: sem listas nem símbolos." if spoken else "")
        try:
            ctx = self.recent()
            out = llm.one_shot(system, f"MATERIAL:\n{material}\n\n" + (f"CONVERSA ATÉ AGORA:\n{ctx}\n\n" if ctx else "") + f"PERGUNTA: {goal}", image, on_delta=self.stream_to_ui())
        except Exception as e:
            return f"Encontrei o material, {sir}, mas não consegui ler: {e}"
        data = self.extract_json(out)
        text = ((data or {}).get("text") or out).strip()
        if learned and not spoken:
            text += f"\n\n(Aprendi isto agora e guardei na minha base: {learned[0][:60]}.)"
        return text

    def stream_to_ui(self):
        """A callback for the model that forwards the growing answer text to on_partial (None if nobody listens)."""
        cb = self.on_partial
        if cb is None:
            return None
        last = {"t": None}

        def on_delta(acc):
            t = reply_text_so_far(acc)
            if t is None or t == last["t"]:
                return
            last["t"] = t
            cb(t)
        return on_delta

    def warm(self, chat_id, history):
        """Has the model read the instructions and this chat in the background, so the next message is answered without that wait."""
        llm = self.llm()
        if llm is None:
            return
        turns = [(r, t if r == "user" else json.dumps({"action": "reply", "text": t}, ensure_ascii=False)) for r, t in history if t.strip()]
        try:
            llm.warm(chat_id, self.system_prompt(), turns)
        except Exception:
            pass

    def cancel(self):
        """Stops whatever is running: interrupts the model and tells long tasks (agent steps, WhatsApp sending) to give up."""
        self.gen += 1
        try:
            llm = self.llm()
            if llm is not None:
                llm.cancel()
        except Exception:
            pass

    def screen_nicks(self):
        """{screen number: nickname} for the screens he named in the Telas window (kept by the screen's position and size)."""
        names = self.settings.get("screen_names") or {}
        return {m["n"]: names[m["key"]] for m in tools.monitors() if names.get(m.get("key"))}

    def parse_screen(self, text):
        return tools.parse_screen(text, {tools.norm(v): n for n, v in self.screen_nicks().items()})

    def capture(self, screen=None):
        """Photographs a screen (hiding Gota's own windows). screen: a number from "Telas:", "all", or None for the one with the active window.
        Returns (PIL image at full size, description, is_several_screens). Raises ValueError with a sentence for the user if the screen does not exist."""
        from PIL import ImageGrab
        sir = self.p.sir()
        mons = tools.monitors()
        rect, which, big = None, "a tela do computador", False
        if len(mons) > 1:
            want = str(screen).strip().lower() if screen not in (None, "", 0) else ""
            if want in ("all", "todas", "todos", "ambas", "ambos"):
                rect = (min(m["rect"][0] for m in mons), min(m["rect"][1] for m in mons), max(m["rect"][2] for m in mons), max(m["rect"][3] for m in mons))
                which, big = f"todas as {len(mons)} telas lado a lado", True
            else:
                active = tools.active_monitor(mons)
                if want and not want.isdigit() and want != "other":   # the model passed a nickname
                    want = str(next((n for n, v in self.screen_nicks().items() if tools.norm(v) == tools.norm(want)), want))
                if want == "other":
                    pick = next((m for m in mons if m is not active), active)
                else:
                    pick = next((m for m in mons if str(m["n"]) == want), None) if want.isdigit() else active
                if pick is None:
                    raise ValueError(f"Não encontrei a tela {want}, {sir}; vejo {len(mons)} telas conectadas (de 1 a {max(m['n'] for m in mons)}).")
                nick = self.screen_nicks().get(pick["n"])
                rect, which = pick["rect"], (f"a tela \"{nick}\" (tela {pick['n']}, {pick['where']})" if nick else f"a tela {pick['n']} ({pick['where']})")
        if rect is None and mons:
            rect = mons[0]["rect"]   # a single screen: still its exact rectangle
        self.hide_window(True)
        time.sleep(0.5)
        try:
            try:
                shot = tools.grab_rect(*rect) if rect else ImageGrab.grab(all_screens=False)
            except Exception:
                shot = ImageGrab.grab(bbox=rect, all_screens=True) if rect else ImageGrab.grab(all_screens=False)
        finally:
            self.hide_window(False)
        try:   # a line in the log, to see afterwards which screen was really photographed
            import sys
            sys.stderr.write(f"[captura] {which} rect={rect} tamanho={shot.size} telas={[(m['n'], m['rect']) for m in mons]}\n")
        except Exception:
            pass
        return shot, which, big

    def locate_region(self, shot, description):
        """Asks the vision model where on the picture the described part is. Returns (x0, y0, x1, y1) as fractions 0..1, or None for the whole picture."""
        import tempfile
        llm = self.llm()
        small = shot.copy()
        small.thumbnail((1280, 1280))
        path = Path(tempfile.gettempdir()) / "gota_locate.jpg"
        small.convert("RGB").save(path, quality=85)
        system = ('Você localiza uma parte de uma imagem de tela. Responda SOMENTE JSON {"x0":N,"y0":N,"x1":N,"y1":N} com a caixa que envolve a parte pedida, '
                  "em frações da imagem de 0 a 1 (x0,y0 = canto superior esquerdo; x1,y1 = canto inferior direito; 0,0,1,1 é a imagem toda). Meia tela da direita é 0.5,0,1,1.")
        try:
            data = self.extract_json(llm.one_shot(system, f"Parte pedida: {description}", str(path))) or {}
            x0, y0, x1, y1 = (float(data[k]) for k in ("x0", "y0", "x1", "y1"))
        except Exception:
            return None
        x0, y0, x1, y1 = max(0.0, min(x0, x1)), max(0.0, min(y0, y1)), min(1.0, max(x0, x1)), min(1.0, max(y0, y1))
        if (x1 - x0) < 0.08 or (y1 - y0) < 0.08 or (x1 - x0) * (y1 - y0) > 0.97:
            return None
        return x0, y0, x1, y1

    def learn_topic(self, topic, on_status=None):
        """Teaches Gota something it does not know. For a programming library it reads the package registry (README with examples) and its
        documentation site; for anything else the model writes precise search queries for the OFFICIAL documentation. Every page is checked to
        really be about the subject, then kept in the knowledge base for good. Returns the titles saved."""
        on_status = on_status or self.on_status
        queries, package, ecosystem = None, "", "none"
        llm = self.llm()
        if llm is not None:
            try:
                out = llm.one_shot('Você prepara a pesquisa de documentação. Dado um assunto técnico, responda SOMENTE JSON: '
                                   '{"queries":["consulta curta em inglês com os termos técnicos exatos","outra"],"package":"nome exato do pacote","ecosystem":"python|npm|none"}. '
                                   'Se o assunto for uma biblioteca de programação, "package" é o nome exato dela no PyPI (python) ou no npm e "ecosystem" diz onde; senão package "" e ecosystem "none". '
                                   'As consultas devem conter o nome próprio exato da biblioteca, ferramenta ou produto e a palavra documentation.', topic)
                data = self.extract_json(out) or {}
                queries = [str(q).strip() for q in (data.get("queries") or []) if str(q).strip()][:2] or None
                package, ecosystem = str(data.get("package") or "").strip(), str(data.get("ecosystem") or "none").lower()
            except Exception:
                pass
        saved = []
        if package and ecosystem in ("python", "npm"):
            saved = kb.learn_package(package, ecosystem, on_status)
        if not saved:
            saved = kb.learn(topic, on_status, queries=queries)
        return saved

    def draft_message(self, goal, contact, hint):
        """Writes the message the owner wants to send, in HIS voice, from the conversation and what he just asked (not as the assistant)."""
        llm = self.llm()
        if llm is None:
            return hint
        name = self.p.name or self.p.address()
        system = (f"Você escreve mensagens de WhatsApp em nome de {name} para {contact}. Escreva COMO ELE MESMO, em primeira pessoa, de forma natural, curta e educada, em português do Brasil. "
                  "Nunca se apresente como Gota, assistente ou inteligência artificial e não explique o que você é nem o que faz, a menos que o pedido mande. "
                  f"Se o pedido traz o texto exato, use-o sem mudar. Se pedir para se apresentar, apresente {name} (use o nome dele). "
                  "Se o pedido corrige um rascunho recusado há pouco na conversa (ex.: não explique isso, mais curto, mude para...), aplique a correção a esse rascunho. "
                  "Responda SOMENTE com o texto da mensagem, sem aspas e sem comentários.")
        ctx = self.recent(8, 300)
        try:
            out = llm.one_shot(system, (f"Conversa até agora:\n{ctx}\n\n" if ctx else "") + f"Pedido atual: {goal}\nRascunho do assistente (pode estar errado): {hint or '(nenhum)'}")
        except Exception:
            return hint
        data = self.extract_json(out)
        text = str((data or {}).get("text") or (data or {}).get("message") or out).strip()
        text = re.sub(r"^(mensagem|texto)\s*:\s*", "", text, flags=re.I).strip().strip('"“”')
        return text or hint

    @staticmethod
    def _echoes(message, goal):
        """True when `message` is mostly the words of the request itself ("tire um print e mande para o João"), not something to tell the contact."""
        m = set(tools.norm(message).split())
        g = set(tools.norm(goal).split())
        cmd = {"print", "tela", "manda", "mande", "envia", "envie", "whatsapp", "tire", "tira", "foto", "janela", "screenshot", "pra", "para"}
        return bool(m) and (len(m & g) / len(m) >= 0.6 or len(m & cmd) >= 2)

    def whatsapp_send(self, goal, d):
        """Sends a message and/or a screenshot (all of a screen, or just the part described) to a WhatsApp contact, after the user confirms."""
        sir = self.p.sir()
        if not self.whatsapp.connected():
            return f"O WhatsApp ainda não está conectado, {sir}, então não consigo fazer isso no momento. Conecte-o no menu lateral, em Conexões."
        contact = str(d.get("contact") or "").strip()
        message = str(d.get("message") or "").strip()
        if not contact:
            return f"Para quem devo enviar, {sir}?"
        image, shown = None, ""
        if d.get("screenshot"):
            self.on_status("Tirando o print…")
            try:
                shot, which, big = self.capture(d.get("screen"))
            except ValueError as e:
                return str(e)
            part = str(d.get("region") or "").strip()
            box = self.locate_region(shot, part) if part else None
            if box:
                w, h = shot.size
                shot = shot.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))
                shown = f"print de {part} ({which})"
            else:
                shown = f"print de {which}" + (f" (não consegui isolar “{part}”, vai a tela inteira)" if part else "")
            import tempfile
            shot.thumbnail((2400, 2400))
            image = Path(tempfile.gettempdir()) / "gota_print.jpg"
            shot.convert("RGB").save(image, quality=92)
        if image is not None and message and self._echoes(message, goal):
            message = ""   # the model copied the user's request into the message: send just the picture and let him add text in the window
        if not message and image is None:
            return f"O que devo enviar para {contact}, {sir}?"
        if message:
            self.on_status("Escrevendo a mensagem…")
            message = self.draft_message(goal, contact, message)
        what = " e ".join(x for x in ((f"a mensagem “{message}”" if message else ""), shown) if x)

        started = self.gen
        sent_text = {"v": message}

        def confirm(found):
            if self.gen != started:
                return False
            if self.confirm_message is not None:
                ok, edited = self.confirm_message(found, contact, message, shown)
                if ok and edited is not None:
                    sent_text["v"] = edited.strip()
                return (ok, edited)
            return self.confirm(f"Enviar no WhatsApp para “{found}” (você pediu “{contact}”):\n{what}", False)
        try:
            found = self.whatsapp.send(contact, message, image, confirm=confirm, on_status=self.on_status, names=[self.p.name] if self.p.name else [])
        except wa_mod.NotConnected:
            return f"A sessão do WhatsApp expirou, {sir}. Conecte-o de novo em Conexões."
        except wa_mod.Cancelled:
            return f"Certo, {sir}, não enviei nada."
        except Exception as e:
            return f"Não consegui enviar pelo WhatsApp, {sir}: {str(e)[:200]}"
        what = " e ".join(x for x in ((f"a mensagem “{sent_text['v']}”" if sent_text["v"] else ""), shown) if x)
        return f"Enviei para {found}, {sir}: {what}."

    def outlook_answer(self, goal, d):
        """Reads the calendar or the inbox from Outlook and answers the user's question about it."""
        sir = self.p.sir()
        if not self.outlook.connected():
            return f"O Outlook ainda não está conectado, {sir}. Entre na sua conta no menu lateral, em Conexões, e eu consulto sua agenda e seus e-mails."
        kind = str(d.get("kind") or "").lower()
        llm = self.llm()
        today = datetime.now()
        try:
            if kind == "agenda":
                self.on_status("Consultando sua agenda…")
                days = max(1, min(31, int(d.get("days") or 1)))
                data = self.outlook.agenda(days, today.replace(hour=0, minute=0, second=0, microsecond=0))
                material = "AGENDA:\n" + ("\n".join(f"- {e['start']} a {e['end']}: {e['title']}" + (f" ({e['where']})" if e["where"] else "") + (" [reunião online]" if e["online"] else "") + (" [dia inteiro]" if e["all_day"] else "") for e in data) or "(nenhum compromisso)")
            else:
                self.on_status("Lendo seus e-mails…")
                data = self.outlook.emails(25, bool(d.get("unread")), int(d.get("days") or 14))
                material = "E-MAILS DA CAIXA DE ENTRADA (mais novos primeiro):\n" + ("\n".join(
                    f"{i + 1}. [{m['received']}] de {m['from']} | assunto: {m['subject']} | {'NÃO LIDO' if m['unread'] else 'lido'} | importância {m['importance']}"
                    f"{' | marcado com bandeira' if m['flagged'] else ''}{' | com anexo' if m['attachments'] else ''} | {'você JÁ respondeu' if m['answered'] else 'sem resposta sua'} | trecho: {m['preview']}"
                    for i, m in enumerate(data)) or "(nenhum e-mail no período)")
        except outlook_mod.NotConnected:
            return f"A sessão do Outlook expirou, {sir}. Entre de novo em Conexões."
        except Exception as e:
            return f"Não consegui ler o Outlook agora, {sir}: {str(e)[:160]}"
        if llm is None:
            return f"Minha mente ainda está carregando, {sir}."
        system = (f'Você é o Gota, mordomo e assistente executivo de {self.p.address()}. Responda em português do Brasil, chamando-o de "{sir}". Hoje é {WEEKDAYS[today.weekday()]}, {today:%d/%m/%Y %H:%M}. '
                  "Use SOMENTE os dados do Outlook abaixo; não invente compromissos, remetentes nem conteúdo. "
                  "Em agenda: cite os compromissos em ordem, com horário e título, de forma natural. "
                  "Em e-mails que exigem resposta: considere importante o que veio de pessoa (não de sistema automático), tem pedido, pergunta, prazo, importância alta ou bandeira, e ainda está 'sem resposta sua'; "
                  "diga quem enviou, o assunto e por que precisa de resposta, no máximo 5, os mais urgentes primeiro. Se nada exigir resposta, diga isso."
                  + (" Fale sem listas nem símbolos, como numa conversa." if self.spoken else " Pode usar linhas curtas."))
        ctx = self.recent()
        try:
            out = llm.one_shot(system, (f"Conversa até agora:\n{ctx}\n\n" if ctx else "") + f"Pedido: {goal}\n\n{material}", on_delta=self.stream_to_ui())
        except Exception as e:
            return f"Li o Outlook, {sir}, mas não consegui resumir: {e}"
        data = self.extract_json(out)
        return ((data or {}).get("text") or out).strip()

    SCREEN_SYSTEM = ("Você é o Gota, especialista sênior em TI: Veeam (backup, fita, restauração), VMware (vSphere, vCenter, ESXi), Hyper-V, Nutanix, Windows Server, Linux, redes, segurança, "
                      "armazenamento, backup e desenvolvimento de software, e mordomo de {who}. Você está olhando {which} do computador dele. Recebe a IMAGEM e o TEXTO LIDO DA TELA (OCR, pode ter "
                      "pequenos erros de leitura): use o texto para ler com exatidão mensagens, códigos de erro, nomes de jobs, servidores e datas. Responda ao que foi perguntado. "
                      "Quando a tela mostrar erro, falha, aviso ou algo anormal, SEMPRE explique como especialista: 1) o que está acontecendo, citando o texto exato da tela; "
                      "2) a causa provável; 3) como corrigir, em passos e com comandos quando houver; 4) o que verificar se não resolver. Use o MATERIAL DA BASE quando ajudar. "
                      "Nunca invente o que não está na tela; se algo não estiver legível, diga. Português do Brasil, chamando-o de \"{sir}\". "
                      "NOMES: copie nomes de jobs, servidores e mensagens EXATAMENTE como aparecem no texto lido (principalmente na LINHA SELECIONADA); se não conseguir ler o nome com certeza, diga \"o job selecionado\" e NUNCA invente um nome. A causa deve vir das linhas de erro da tela (ex.: Error: ...), não de suposição pelo status. "
                      "SEJA BREVE: responda em até 4 frases curtas (comece citando o nome do job ou item selecionado e o texto exato do erro, a causa provável e a ação principal para corrigir) e termine perguntando "
                      "se ele quer os passos detalhados. Só detalhe passos, comandos e verificações se ele pedir. Comandos (quando pedidos) em blocos ```.")

    def look_at_screen(self, question, spoken=False, history=(), screen=None, image_path=None):
        """Photographs the screen the user means (or uses `image_path`), reads its text with OCR, adds what Gota knows (knowledge base, skills,
        documentation learned from the internet for the error on screen) and answers as an IT specialist."""
        sir = self.p.sir()
        llm = self.llm()
        if llm is None:
            return f"Minha mente ainda está carregando, {sir}."
        self.on_status("Olhando a tela...")
        if image_path:
            from PIL import Image
            shot, which, big = Image.open(image_path).convert("RGB"), "a tela do computador", False
        else:
            try:
                shot, which, big = self.capture(screen)
            except ValueError as e:
                return str(e)
        import tempfile
        tmp = Path(tempfile.gettempdir())
        full = tmp / "gota_screen_full.png"
        shot.convert("RGB").save(full)
        self.on_status("Lendo o texto da tela...")
        seen = tools.ocr_image(full, 2 if shot.width <= 2600 else 1)[:2800]
        small = shot.copy()
        small.thumbnail((2200, 1300) if big else (1280, 1280))
        path = tmp / "gota_screen.jpg"
        small.convert("RGB").save(path, quality=85)

        # what Gota already knows about what is on screen (and, for an unknown error, the documentation from the internet)
        problems = tools.problem_lines(seen)
        row = ""
        row_img = tools.selected_row_crop(full)   # the highlighted line of a list (e.g. the selected Veeam job), magnified and read by the vision model: exact names
        if row_img:
            self.on_status("Lendo o item selecionado...")
            try:
                row = (llm.one_shot("Você lê texto de imagens de telas. Responda apenas com o texto exato.",
                                    "Copie literalmente o texto desta linha de tabela (nome, tipo, status, resultado).", str(row_img)) or "").strip()[:400]
            except Exception:
                row = ""
        if not problems:   # the OCR could not read the (small) error text: ask the vision model to quote it, so the lookup has something to match
            self.on_status("Procurando a mensagem de erro...")
            try:
                quote = llm.one_shot("Você lê telas de sistemas de TI. Responda apenas com o texto exato.",
                                     "Copie literalmente a mensagem de erro, falha ou aviso mais importante visível nesta imagem (nome do job/serviço e frase do erro). "
                                     "Se não houver nenhuma, responda: nenhuma.", str(path))
                quote = (quote or "").strip().splitlines()[0][:200] if (quote or "").strip() else ""
                if quote and tools.norm(quote).strip(" .") not in ("nenhuma", "nenhum"):
                    problems = [quote]
                    seen = f"{seen}\n{quote}"
            except Exception:
                pass
        probe = f"{question} {' '.join(problems)} {seen}"[:1400]
        skill_hits = [h for h in skills_mod.search(" ".join(problems) or probe, 3) or skills_mod.search(probe, 3) if not h[1]["name"].startswith("desenvolver")][:2]
        kb_hits = kb.search(" ".join(problems) or probe, 3) or kb.search(probe, 3)
        if not skill_hits and not (kb_hits and kb.good_enough(kb_hits, probe)) and problems and tools.is_online() and tools.norm(problems[0]) not in self._tried:
            self._tried[tools.norm(problems[0])] = time.time()
            self.on_status("Procurando a documentação deste erro...")
            try:
                self.learn_topic(problems[0][:140])
            except Exception:
                pass
            kb_hits = kb.search(probe, 3)
        material = skills_mod.prompt_block(skill_hits, 2000) if skill_hits else ""
        if kb_hits and (len(material) < 1800):
            material += ("\n\n" if material else "") + "\n\n".join(f"[{t}] (fonte: {src})\n{txt[:900]}" for _, t, src, txt in kb_hits[:2])
        system = self.SCREEN_SYSTEM.format(who=self.p.address(), which=which, sir=sir) + (" Será FALADO em voz alta: no máximo 3 frases curtas (até uns 350 caracteres), sem listas nem símbolos." if spoken else "")
        self.on_status("Analisando o que vejo...")
        try:
            recent = "\n".join(f"{'Usuário' if r == 'user' else 'Gota'}: {t[:300]}" for r, t in list(history)[-4:] if t.strip())
            ask = ((f"Conversa até agora:\n{recent}\n\n" if recent else "") + f"O usuário disse: {question or 'Descreva e analise o que está na tela.'}\n"
                   + (f"\nLINHA SELECIONADA NA TELA (lida ampliada: o nome do job/item está aqui): {row}\n" if row else "")
                   + (f"\nTEXTO LIDO DA TELA (OCR):\n{seen}\n" if seen else "") + (f"\nMATERIAL DA BASE:\n{material[:2400]}\n" if material else "")
                   + "\nEntenda o que ele quer saber a partir da frase dele e responda.")
            out = llm.one_shot(system, ask, str(path), on_delta=self.stream_to_ui())
        except Exception as e:
            return f"Não consegui analisar a tela, {sir}: {e}"
        data = self.extract_json(out)
        return ((data or {}).get("text") or out).strip()

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
        calc = quick.answer(goal)   # arithmetic, percentages, conversions: exact and instant, no model needed
        if calc:
            return f"{calc}, {sir}."
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
    def needs_reasoning(lower): return bool(REASONING.search(lower))

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
