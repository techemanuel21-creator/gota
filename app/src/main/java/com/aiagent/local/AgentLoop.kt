package com.aiagent.local

import android.content.Context
import com.aiagent.AgentNotificationListenerService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

/**
 * Turns one request into an answer. Common requests (time, date, weather, agenda, greetings,
 * opening apps, "remember that...") are answered instantly without the model; everything else goes
 * to the on-device Gemma model, which can also decide to search the web, draw an image, or act on
 * the screen.
 */
class AgentLoop(
    private val context: Context,
    private val chatId: String,
    private val history: List<ChatMessage>,
    private val onStatus: (String) -> Unit,
    private val onReply: (text: String, image: String?) -> Unit,
    private val onPhase: (Phase) -> Unit = {},
    /** True when the answer will be spoken out loud (calls, voice button). */
    private val spoken: Boolean = false
) {

    enum class Phase { THINKING, SEARCHING, DRAWING }

    private val ptBr = Locale("pt", "BR")
    private val sir get() = UserProfile.shortAddress(context)
    private val fullName get() = UserProfile.address(context)
    private fun reply(text: String) = onReply(text, null)

    private fun systemPrompt(): String {
        val facts = UserProfile.facts(context)
        val pronoun = UserProfile.pronoun(context)
        return buildString {
            appendLine("Você é o Gota, o mordomo pessoal de $fullName: um gato mordomo clássico, educado, discreto e leal, que vive no celular.")
            appendLine("Fale sempre em português do Brasil, com acentuação correta, no tom de um mordomo clássico: formal, cordial e prestativo.")
            appendLine("Chame o dono de \"$sir\" e trate-o por \"$pronoun\". Exemplos de tom: \"Pois não, $sir.\", \"Às suas ordens.\", \"Com prazer, $sir.\"")
            if (spoken) {
                appendLine("Vocês estão conversando por voz, como numa ligação: suas respostas serão faladas em voz alta.")
                appendLine("Fale de forma natural e corrida, sem listas, emojis, símbolos ou links. Lembre-se de tudo o que já foi dito na conversa.")
            }
            if (facts.isNotEmpty()) {
                appendLine()
                appendLine("O que você já sabe sobre $fullName:")
                facts.forEach { appendLine("- $it") }
            }
            val calls = UserProfile.callNotes(context)
            if (calls.isNotEmpty()) {
                appendLine()
                appendLine("Do que vocês conversaram nas últimas ligações:")
                calls.forEach { appendLine("- $it") }
            }
            appendLine()
            append(
                """
                Responda SEMPRE com um único objeto JSON válido, sem nenhum texto antes ou depois.

                Como responder em texto:
                - Responda exatamente o que foi perguntado, nada além disso, começando já pela resposta.
                - Seja curto (1 ou 2 frases), com a elegância de um mordomo. Só se estenda se pedirem explicação.
                - Não acrescente conselhos, avisos ou perguntas no final. Se não souber, diga em uma frase, sem inventar.
                - Se a pessoa contar algo sobre si que valha lembrar (gostos, rotina, pessoas próximas, preferências),
                  inclua o campo "remember" com esse fato curto.

                Para conversar ou responder perguntas use:
                {"action":"reply","text":"sua resposta"}

                Exemplos:
                Pedido: "qual a capital da Austrália?"
                Resposta: {"action":"reply","text":"A capital da Austrália é Camberra, $sir."}
                Pedido: "eu adoro café sem açúcar"
                Resposta: {"action":"reply","text":"Anotado, $sir. Café sem açúcar, então.","remember":"Gosta de café sem açúcar"}
                Pedido: "me manda um resumo rápido do que é fotossíntese"
                Resposta: {"action":"reply","text":"É como a planta faz comida, $sir: usa luz do sol, água e gás carbônico para criar açúcar e soltar oxigênio."}
                Pedido: "bora, abre o zap pra mim"
                Resposta: {"action":"open_app","name":"WhatsApp"}
                Pedido: "tava pensando em pizza hoje"
                Resposta: {"action":"reply","text":"Excelente ideia, $sir. Quer que eu procure uma pizzaria perto?"}

                Você NÃO tem acesso aos contatos. Nunca invente número de telefone; se faltar o número, peça.

                Ações disponíveis (use UMA quando o pedido exigir):
                {"action":"open_app","name":"nome do app"}
                {"action":"call","number":"número dito pelo usuário"}
                {"action":"sms","number":"número","message":"texto"}
                {"action":"whatsapp","number":"número","message":"texto"}
                {"action":"open_url","url":"endereço"}
                {"action":"search_web","query":"o que pesquisar"}   (só se pedirem para ABRIR uma pesquisa no navegador)
                {"action":"set_alarm","hour":N,"minute":N,"label":"..."}
                {"action":"set_timer","seconds":N,"label":"..."}
                {"action":"create_event","title":"..."}
                {"action":"share","text":"..."}
                {"action":"count_unread","app":"nome do app"}
                {"action":"weather"}   (clima, temperatura, chuva)
                {"action":"generate_image","prompt":"descrição da imagem EM INGLÊS"}

                Criar imagens: escreva o prompt em inglês, curto e concreto (até 35 palavras), com o mais
                importante primeiro: o assunto e sua aparência, a ação, o cenário e o estilo pedido (se nada for
                pedido, uma foto realista). Mantenha fielmente o que a pessoa pediu, sem tirar nem inventar nada.
                Use luz natural, a menos que peçam algo noturno. NÃO escreva palavras de qualidade como "8k",
                "detailed" ou "masterpiece": o sistema acrescenta isso sozinho.

                Imagens: quando a mensagem vier com uma foto, você consegue vê-la. Responda sobre ela com "reply".
                Se pedirem para criar ou editar uma imagem a partir dela, use "generate_image" com um prompt em inglês
                que descreva a foto em detalhes e já com as mudanças pedidas.

                Seu conhecimento tem data de corte. Para notícias, política, leis, votações, esportes, preços,
                pessoas públicas, lançamentos ou qualquer fato que muda com o tempo — ou se não tiver certeza — use:
                {"action":"needs_search","query":"termos curtos para pesquisar no Google"}
                Se depender de onde a pessoa está, coloque a cidade na query.
                """.trimIndent()
            )
        }
    }

    suspend fun run(request: String, imagePath: String? = null) {
        val goal = stripWakeWord(request)
        val lower = AppCatalog.normalize(goal)

        if (imagePath == null) {
            // "outra" / "de novo" right after a picture: draw the same request again (new random draw).
            if (isRetryRequest(lower) && history.lastOrNull()?.image != null) {
                // (the last message in the chat is a picture, so "outra" means "another one")
                ImageGen.lastPrompt(context)?.let { runImage(it); return }
            }
            quickAnswer(goal, lower)?.let { reply(it); return }
            if (isWeatherQuery(lower)) { runWeather(goal); return }
            if (isBriefingQuery(lower)) { runBriefing(lower); return }
            if (tryOpenApp(goal)) return
            explicitSearch(goal)?.let { query -> runSearch(goal, withLocation(goal, searchQuery(query))); return }
            // News, laws, prices, games... the model's knowledge is old, so go straight to the web.
            if (!isCommand(lower) && needsFreshInfo(lower)) { runSearch(goal, withLocation(goal, searchQuery(goal))); return }
        }

        val agent = GemmaAgent.get() ?: run { reply("Perdão, $sir, minha mente ainda está carregando."); return }

        onPhase(Phase.THINKING)
        onStatus("Pensando...")

        val now = SimpleDateFormat("EEEE, dd/MM/yyyy HH:mm", ptBr).format(Date())
        val place = LocationHelper.currentPlace(context)
        val userText = buildString {
            append("[Agora: $now")
            if (place != null) append(" · Local: $place")
            append("]\n").append(goal.ifBlank { "O que você vê nesta imagem?" })
        }
        // The whole conversation goes in: the model keeps the recent part word for word and a digest of the rest.
        val turns = history.filter { it.text.isNotBlank() }.map {
            if (it.role == "user") Turn("user", it.text)
            else Turn("model", JSONObject().put("action", "reply").put("text", it.text).toString())
        }

        // Let the model reason step by step only on questions that need it (slower but sharper);
        // everyday commands stay fast.
        val think = imagePath == null && needsReasoning(lower)
        val raw = try {
            agent.chat(chatId, systemPrompt(), turns, userText, imagePath, think)
        } catch (e: Exception) {
            reply("Perdão, $sir, tive um problema ao pensar: ${e.message}")
            return
        }

        val json = extractJson(raw)
        if (json == null) {
            reply(if (looksLikeJson(raw) || raw.isBlank()) "Perdão, $sir, me confundi. Poderia repetir de outro modo?" else raw.trim())
            return
        }
        val asked = isQuestion(goal, lower)
        // Only keep facts the person told about themselves, never a question they asked.
        json.optString("remember").takeIf { it.isNotBlank() && !asked && isAboutThemselves(lower) }
            ?.let { UserProfile.remember(context, it) }

        when (json.optString("action")) {
            "reply" -> {
                val text = json.optString("text").ifBlank { "Pois não, $sir." }
                // A question the model couldn't really answer ("não sei", "anotado"...) goes to the web instead.
                if (imagePath == null && asked && isNonAnswer(text) && WebSearch.isOnline(context)) {
                    runSearch(goal, withLocation(goal, searchQuery(goal)))
                } else {
                    reply(text)
                }
            }

            "open_app" -> {
                val name = json.optString("name")
                val opened = DeviceActions.openAppLabel(context, name)
                reply(if (opened != null) "Abrindo o $opened, $sir." else "Não encontrei o app \"$name\", $sir.")
            }

            "call" -> withVerifiedNumber(goal, json) { number ->
                val ok = DeviceActions.dial(context, number)
                reply(if (ok) "Deixei o número $number pronto para ligar, $sir." else "Não consegui abrir o discador, $sir.")
            }

            "sms" -> withVerifiedNumber(goal, json) { number ->
                val ok = DeviceActions.sendSms(context, number, json.optString("message"))
                reply(if (ok) "A mensagem para $number está pronta, é só enviar, $sir." else "Não consegui abrir as mensagens, $sir.")
            }

            "whatsapp" -> withVerifiedNumber(goal, json) { number ->
                val ok = DeviceActions.openWhatsApp(context, number, json.optString("message"))
                reply(if (ok) "Abri o WhatsApp de $number com a mensagem pronta, $sir." else "Não consegui abrir o WhatsApp, $sir.")
            }

            "open_url" -> {
                val url = json.optString("url")
                reply(if (DeviceActions.openUrl(context, url)) "Abrindo $url, $sir." else "Não consegui abrir esse site, $sir.")
            }

            "search_web" -> {
                val query = json.optString("query")
                reply(if (DeviceActions.searchWeb(context, query)) "Abri a pesquisa por \"$query\", $sir." else "Não consegui pesquisar, $sir.")
            }

            "set_alarm" -> {
                val ok = DeviceActions.setAlarm(context, json.optInt("hour"), json.optInt("minute"), json.optString("label"))
                reply(if (ok) "Alarme ajustado, $sir." else "Não consegui ajustar o alarme, $sir.")
            }

            "set_timer" -> {
                val ok = DeviceActions.setTimer(context, json.optInt("seconds"), json.optString("label"))
                reply(if (ok) "Timer iniciado, $sir." else "Não consegui iniciar o timer, $sir.")
            }

            "create_event" -> {
                val title = json.optString("title")
                reply(if (DeviceActions.createEvent(context, title)) "Abri a agenda para \"$title\", $sir." else "Não consegui abrir a agenda, $sir.")
            }

            "share" -> reply(if (DeviceActions.shareText(context, json.optString("text"))) "Pronto para compartilhar, $sir." else "Não consegui compartilhar, $sir.")

            "count_unread" -> countUnread(json.optString("app"))

            "weather" -> runWeather(goal)

            "generate_image" -> runImage(json.optString("prompt").ifBlank { goal })

            "needs_search" -> runSearch(goal, withLocation(goal, searchQuery(json.optString("query").ifBlank { goal })))

            else -> reply(
                json.optString("text").ifBlank { json.optString("message") }
                    .ifBlank { "Perdão, $sir, me confundi. Poderia repetir de outro modo?" }
            )
        }
    }

    // ---------- instant answers (no model) ----------

    private fun quickAnswer(goal: String, lower: String): String? {
        timeOrDateAnswer(lower)?.let { return it }

        val greeting = lower.replace(Regex("\\b(gota|hey|ei)\\b"), "").trim()
        val hour = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)
        val salute = when (hour) { in 5..11 -> "Bom dia"; in 12..17 -> "Boa tarde"; else -> "Boa noite" }
        when (greeting) {
            "bom dia" -> return "Bom dia, $fullName. Em que posso servi-lo hoje?".adapt()
            "boa tarde" -> return "Boa tarde, $fullName. Em que posso servi-lo?".adapt()
            "boa noite" -> return "Boa noite, $fullName. Em que posso servi-lo?".adapt()
            "oi", "ola", "e ai", "opa", "" -> return "$salute, $fullName. Às suas ordens."
            "obrigado", "obrigada", "valeu", "muito obrigado", "muito obrigada" -> return "Disponha, $sir. É sempre um prazer."
            "tudo bem", "tudo bem com voce", "como voce esta", "como vai" -> return "Muito bem, $sir, obrigado por perguntar. Em que posso ajudar?"
        }
        if (lower == "qual e o seu nome" || lower == "qual o seu nome" || lower == "quem e voce" || lower == "qual seu nome") {
            return "Sou o Gota, $sir, seu mordomo pessoal."
        }
        if (lower == "qual e o meu nome" || lower == "qual o meu nome" || lower == "como eu me chamo" || lower == "quem sou eu") {
            return UserProfile.name(context)?.let { "O senhor é ${it}, naturalmente.".adapt() } ?: "Ainda não sei o seu nome, $sir."
        }

        Regex("^(?:me chame de|me chama de|pode me chamar de|meu nome e)\\s+(.+)$").find(lower)?.let {
            val name = goal.trim().split(Regex("\\s+")).takeLast(it.groupValues[1].split(" ").size).joinToString(" ")
                .trim(' ', '.', '!').replaceFirstChar { c -> c.uppercase() }
            UserProfile.save(context, name, UserProfile.treatment(context))
            return "Como desejar. A partir de agora, ${UserProfile.address(context)}."
        }

        Regex("^(?:lembre|lembra|lembre se|lembra que|lembre que|guarde|anote)\\s+(?:que\\s+|de que\\s+)?(.+)$").find(lower)?.let {
            val original = goal.trim().replace(Regex("^(?i)(lembre-se|lembre|lembra|guarde|anote)\\s+(de que |que )?"), "")
            UserProfile.remember(context, original.replaceFirstChar { c -> c.uppercase() })
            return "Anotado, $sir. Não esquecerei."
        }
        return null
    }

    /** Swaps "o senhor"/"servi-lo" for the right gender or for "você". */
    private fun String.adapt(): String = when (UserProfile.treatment(context)) {
        "senhora" -> replace("servi-lo", "servi-la").replace("O senhor", "A senhora")
        "senhor" -> this
        else -> replace("servi-lo", "ajudar").replace("O senhor", "Você")
    }

    /** Answers only what was asked: the time, the date, or both. Returns null if neither. */
    private fun timeOrDateAnswer(lower: String): String? {
        // Kept narrow on purpose: "que horas abre o mercado?" must NOT be answered with the clock.
        val asksTime = listOf(
            "que horas sao", "que hora e", "que horas e", "qual a hora", "qual e a hora",
            "horas agora", "hora agora", "horario agora"
        ).any { lower.contains(it) }
        val mentionsToday = lower.contains("hoje")
        val asksDate = mentionsToday && listOf("que dia", "qual dia", "data").any { lower.contains(it) }
        val asksWeekday = mentionsToday && lower.contains("dia da semana")
        if (!asksTime && !asksDate && !asksWeekday) return null

        val now = Date()
        val hora = SimpleDateFormat("HH:mm", ptBr).format(now)
        return when {
            asksTime && (asksDate || asksWeekday) ->
                "São $hora de ${SimpleDateFormat("EEEE, dd 'de' MMMM", ptBr).format(now)}, $sir."
            asksTime -> "São $hora, $sir."
            asksWeekday && !asksDate -> "Hoje é ${SimpleDateFormat("EEEE", ptBr).format(now)}, $sir."
            else -> "Hoje é ${SimpleDateFormat("EEEE, dd 'de' MMMM 'de' yyyy", ptBr).format(now)}, $sir."
        }
    }

    private val OPEN_REGEX = Regex(
        "^(?:(?:hey |ei )?gota[ ,]*)?(?:por favor[ ,]*)?(?:abre|abra|abrir|inicia|inicie|entra no|entra na|entrar no|entrar na)\\s+(?:o |a )?(?:app |aplicativo )?(.+?)(?:\\s+(?:por favor|pra mim|para mim))?$"
    )

    /** "abre o whats 2" → opens it right away, no model needed. */
    private fun tryOpenApp(goal: String): Boolean {
        val name = OPEN_REGEX.find(AppCatalog.normalize(goal))?.groupValues?.get(1)?.trim() ?: return false
        if (name.isBlank() || name.split(" ").size > 5) return false
        val matches = AppCatalog.find(context, name)
        val entry = matches.firstOrNull()
        if (entry == null) {
            reply("Não encontrei nenhum aplicativo chamado \"$name\", $sir.")
            return true
        }
        if (!AppCatalog.launch(context, entry)) {
            reply("Não consegui abrir o ${entry.displayLabel}, $sir.")
            return true
        }
        val hasOtherCopy = matches.any { it.label == entry.label && it.key != entry.key }
        val hint = if (hasOtherCopy && entry.isMainProfile && AppCatalog.aliasFor(context, entry) == null)
            " Para o outro, diga \"abrir o segundo ${entry.label}\" ou dê um apelido a ele." else ""
        reply("Abrindo o ${entry.displayLabel}, $sir.$hint")
        return true
    }

    private fun isWeatherQuery(lower: String): Boolean = listOf(
        "temperatura", "clima", "previsao do tempo", "vai chover", "esta chovendo", "ta chovendo",
        "frio hoje", "calor hoje", "quantos graus", "como esta o tempo", "como ta o tempo", "guarda chuva"
    ).any { lower.contains(it) }

    private fun isBriefingQuery(lower: String): Boolean = listOf(
        "informacoes do dia", "informacao do dia", "resumo do dia", "como esta meu dia", "como vai ser meu dia",
        "meu dia hoje", "minha agenda", "meus compromissos", "agenda de hoje", "agenda de amanha",
        "compromissos de hoje", "compromissos de amanha", "o que tenho hoje", "o que eu tenho hoje",
        "o que tenho amanha", "o que eu tenho amanha", "novidades do dia"
    ).any { lower.contains(it) }

    // ---------- deciding when to search ----------

    private val FRESH_WORDS = Regex(
        "\\b(noticia|noticias|novidade|novidades|aprovado|aprovada|aprovados|aprovadas|aprovou|aprovaram|aprovacao|" +
            "votacao|votou|votaram|vetou|sancionou|sancionado|sancionada|lei|leis|pec|stf|senado|camara dos deputados|" +
            "congresso|governo|presidente|ministro|prefeito|governador|eleicao|eleicoes|candidato|candidata|" +
            "6x1|5x2|12x36|escala|reforma|imposto|salario minimo|aposentadoria|inss|fgts|bolsa familia|" +
            "cotacao|dolar|euro|bitcoin|ibovespa|selic|inflacao|preco|precos|quanto custa|" +
            "placar|campeonato|brasileirao|libertadores|copa do mundo|quem ganhou|quem venceu|proximo jogo|" +
            "lancamento|lancou|estreia|estreou|morreu|faleceu|aconteceu|acontecendo|atualmente|recentemente|ultimas)\\b"
    )

    private val FRESH_PATTERNS = listOf(
        Regex("\\bja (foi|foram|saiu|sairam|comecou|comecaram|acabou|terminou|aprovaram|votaram|esta valendo|ta valendo|vale|lancou|lancaram|chegou|abriu|passou|mudou|teve)\\b"),
        Regex("\\bquando (vai|vao|comeca|comecam|sai|saem|estreia|estreiam|abre|abrem|acaba|acabam|termina|terminam|sera|entra|passa a)\\b"),
        Regex("\\b(vai|vao) (comecar|valer|mudar|aumentar|cair|subir|acabar|sair|estrear)\\b"),
        Regex("\\b(entra|entrou|entrar) em vigor\\b|\\bem vigor\\b|\\b(passa|comeca) a valer\\b"),
        Regex("\\b20[2-3]\\d\\b")
    )

    private val TIME_WORDS = Regex("\\b(hoje|ontem|amanha|essa semana|esta semana|esse mes|este mes|esse ano|este ano|semana passada|mes passado|ano que vem)\\b")

    private val QUESTION_START = Regex(
        "^(?:(?:e|mas|entao|me diz|me diga|me fala|me conta|voce sabe|vc sabe|sabe|sabe me dizer|pode me dizer)\\s+)?" +
            "(quem|qual|quais|quando|quanto|quanta|quantos|quantas|onde|aonde|por que|porque|pq|como|o que|oque|que|sera|existe|existem|tem|e verdade|ja|e possivel)\\b"
    )

    private val COMMAND_START = Regex(
        "^(?:por favor\\s+)?(abre|abra|abrir|liga|ligue|ligar|manda|mande|mandar|envia|envie|enviar|escreve|escreva|cria|crie|criar|" +
            "gera|gere|gerar|desenha|desenhe|faz|faca|fazer|coloca|coloque|bota|bote|define|defina|programa|programe|toca|toque|" +
            "lembra|lembre|anota|anote|traduz|traduza|resume|resuma|compartilha|compartilhe|imagina|imagine|inventa|invente|me acorda|me acorde)\\b"
    )

    private val CREATIVE = Regex(
        "\\b(piada|poema|poesia|historia|historinha|cancao|musica|rima|redacao|imagem|imagens|desenho|ilustracao|papel de parede|wallpaper)\\b"
    )

    private val EXPLICIT_SEARCH = Regex(
        "^(?:por favor\\s+)?(?:pesquise|pesquisa|pesquisar|procure|procura|procurar|busque|busca|buscar|da uma pesquisada)" +
            "(?:\\s+(?:na internet|no google|na web))?(?:\\s+(?:pra mim|para mim))?(?:\\s+(?:sobre|por))?\\s+(.+)$"
    )

    private fun isCommand(lower: String) = COMMAND_START.containsMatchIn(lower) || CREATIVE.containsMatchIn(lower)

    private fun isQuestion(goal: String, lower: String) =
        goal.contains('?') || QUESTION_START.containsMatchIn(lower) || FRESH_PATTERNS.take(3).any { it.containsMatchIn(lower) }

    private val REASONING = Regex(
        "\\b(por que|porque|pq|explique|explica|como funciona|como faco|como faço|me ensina|ensina|passo a passo|" +
            "qual a diferenca|diferenca entre|compare|compara|resolva|calcule|quanto e|quanto é|vale a pena|" +
            "o que significa|significado de|me ajude a pensar|o que voce acha|o que você acha|me explique)\\b"
    )

    /** True for questions that gain from step-by-step thinking (not quick commands). */
    private fun needsReasoning(lower: String): Boolean =
        REASONING.containsMatchIn(lower) || (lower.contains('?') && lower.split(" ").size > 8)

    private fun needsFreshInfo(lower: String): Boolean =
        FRESH_WORDS.containsMatchIn(lower) || FRESH_PATTERNS.any { it.containsMatchIn(lower) } ||
            (TIME_WORDS.containsMatchIn(lower) && QUESTION_START.containsMatchIn(lower))

    /** "pesquisa o preço do dólar" → "o preço do dólar" (answered here, not opened in the browser). */
    private fun explicitSearch(goal: String): String? {
        val lower = AppCatalog.normalize(goal)
        val match = EXPLICIT_SEARCH.find(lower) ?: return null
        val prefix = lower.substring(0, match.groups[1]!!.range.first).trim()
        return dropPrefix(goal, prefix).ifBlank { null }
    }

    private fun isAboutThemselves(lower: String) =
        Regex("\\b(eu|meu|minha|meus|minhas|me chamo|moro|trabalho|gosto|prefiro|adoro|odeio|sou|tenho)\\b").containsMatchIn(lower)

    private val NON_ANSWERS = listOf(
        "nao sei", "nao tenho informac", "nao tenho acesso", "nao tenho dados", "nao possuo", "data de corte",
        "nao consigo saber", "nao consigo verificar", "nao tenho como saber", "nao tenho certeza", "informacoes atualizadas",
        "dados atualizados", "recomendo verificar", "recomendo consultar", "sugiro consultar", "sugiro verificar",
        "registrad", "anotado", "compreendido", "entendido", "nao encontrei"
    )

    private fun isNonAnswer(text: String): Boolean {
        val n = AppCatalog.normalize(text)
        return NON_ANSWERS.any { n.contains(it) }
    }

    private val NUMBER_WORDS = mapOf(
        "um" to 1, "uma" to 1, "dois" to 2, "duas" to 2, "tres" to 3, "quatro" to 4, "cinco" to 5, "seis" to 6,
        "sete" to 7, "oito" to 8, "nove" to 9, "dez" to 10, "onze" to 11, "doze" to 12,
        "vinte e quatro" to 24, "trinta e seis" to 36, "quarenta e oito" to 48
    )

    private val SCHEDULE_REGEX: Regex by lazy {
        val words = (NUMBER_WORDS.keys + "três").sortedByDescending { it.length }.joinToString("|")
        Regex("(?<![\\p{L}\\d])(\\d{1,2}|$words)\\s+(?:por|x)\\s+(\\d{1,2}|$words)(?![\\p{L}\\d])", RegexOption.IGNORE_CASE)
    }

    /** Writes the query the way news sites do ("escala seis por um" → "escala 6x1") and drops filler words. */
    private fun searchQuery(text: String): String {
        fun num(word: String) = word.toIntOrNull() ?: NUMBER_WORDS[AppCatalog.normalize(word)] ?: word
        val q = SCHEDULE_REGEX.replace(text) { m -> "${num(m.groupValues[1])}x${num(m.groupValues[2])}" }
        val filler = Regex("^(você sabe|voce sabe|vc sabe|sabe me dizer|sabe|me diz|me diga|me fala|me conta|pode me dizer)[,\\s]+(se\\s+)?", RegexOption.IGNORE_CASE)
        return filler.replace(q.trim(), "").trim(' ', '?', '!', '.', ',')
    }

    // ---------- tools ----------

    private suspend fun runBriefing(lower: String) {
        val tomorrow = lower.contains("amanha")
        onStatus("Consultando sua agenda...")
        val pronoun = UserProfile.pronoun(context).replaceFirstChar { it.uppercase() }
        val dayWord = if (tomorrow) "amanhã" else "hoje"
        val parts = mutableListOf<String>()

        if (!tomorrow) {
            val hour = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)
            val salute = when (hour) { in 5..11 -> "Bom dia"; in 12..17 -> "Boa tarde"; else -> "Boa noite" }
            parts += "$salute, $fullName. Hoje é ${SimpleDateFormat("EEEE, dd 'de' MMMM", ptBr).format(Date())}."
        }

        if (!CalendarHelper.hasPermission(context)) {
            parts += "Ainda não tenho acesso à sua agenda; é só permitir o calendário nas configurações do Gota."
        } else {
            val events = withContext(Dispatchers.IO) { CalendarHelper.events(context, if (tomorrow) 1 else 0) }
            parts += when (events.size) {
                0 -> "$pronoun não tem compromissos na agenda $dayWord."
                1 -> "$pronoun tem um compromisso $dayWord: ${CalendarHelper.describe(events)}."
                else -> "$pronoun tem ${events.size} compromissos $dayWord: ${CalendarHelper.describe(events)}."
            }
        }

        val coords = LocationHelper.coordinates(context)
        if (!tomorrow && coords != null && WebSearch.isOnline(context)) {
            runCatching {
                withContext(Dispatchers.IO) { Weather.brief(coords.first, coords.second, LocationHelper.currentCity(context)) }
            }.getOrNull()?.takeIf { it.isNotBlank() }?.let { parts += it }
        }
        reply(parts.joinToString(" "))
    }

    private suspend fun runWeather(goal: String) {
        val coords = LocationHelper.coordinates(context)
        if (coords == null) {
            reply(
                if (LocationHelper.hasPermission(context)) "Ainda estou localizando onde ${UserProfile.pronoun(context)} está. Tente de novo em instantes, $sir."
                else "Preciso da permissão de localização para consultar o clima, $sir."
            )
            return
        }
        if (!WebSearch.isOnline(context)) {
            reply("Estou sem internet no momento, $sir, então não consigo consultar o clima.")
            return
        }
        onStatus("Consultando o clima...")
        val text = try {
            withContext(Dispatchers.IO) { Weather.answer(goal, coords.first, coords.second, LocationHelper.currentCity(context)) }
        } catch (e: Exception) {
            "Não consegui consultar a previsão agora."
        }
        reply("${text.removeSuffix(".")}, $sir.")
    }

    private fun countUnread(appName: String) {
        val listener = AgentNotificationListenerService.instance
        val pkg = DeviceActions.resolvePackageName(context, appName)
        when {
            listener == null -> reply("O leitor de notificações está desligado, $sir.")
            pkg == null -> reply("Não encontrei o app \"$appName\", $sir.")
            else -> {
                val count = listener.countUnreadFor(pkg)
                reply(
                    if (count < 0) "Não consegui ler as notificações, $sir."
                    else "Há $count notificações do $appName na sua barra agora, $sir. Pode haver mais conversas não lidas dentro do app."
                )
            }
        }
    }

    /**
     * Pictures are drawn on the phone itself, with or without internet. The painter's model is
     * downloaded on Wi-Fi the first time the app is used; if it isn't there yet, say why and what to do.
     */
    private suspend fun runImage(prompt: String) {
        onPhase(Phase.DRAWING)
        onStatus("Pintando a imagem...")
        ImageGen.rememberPrompt(context, prompt)
        try {
            val uri = withContext(Dispatchers.IO) { ImageGen.generate(context, prompt) }
            onReply(
                "Aqui está, $sir. Já guardei na galeria, no álbum ${ImageGen.ALBUM}. " +
                    "Se não ficou bom, peça \"outra\" que eu tento de novo.",
                uri.toString()
            )
        } catch (e: ImageGen.NotReadyException) {
            reply(notReadyMessage(e))
        } catch (e: Throwable) {
            reply("Perdão, $sir, não consegui pintar a imagem agora (${(e.message ?: e.javaClass.simpleName).take(100)}).")
        }
    }

    /** Explains why the painter can't draw yet, and starts fetching it when that's free (Wi-Fi). */
    private fun notReadyMessage(e: ImageGen.NotReadyException): String {
        val size = ImageGen.variant(context).sizeMb
        val detail = e.detail?.let { " (detalhe: $it)" }.orEmpty()
        val whatFailed = if (e.gpuFailed) "A versão do desenho pela placa de vídeo não funcionou neste celular$detail, então usarei a do processador. " else ""
        ImageGen.startDownload(context, onlyOnWifi = true)
        return when {
            ImageGen.downloading ->
                "${whatFailed}Estou baixando meu pintor ($size MB, uma única vez), $sir: ${ImageGen.downloadPercent}% pronto. Quando terminar, é só pedir de novo."
            ImageGen.canDownloadNow(context) ->
                "${whatFailed}Preciso baixar meu pintor uma única vez ($size MB), $sir. Já comecei; aviso quando terminar."
            else ->
                "${whatFailed}Preciso baixar meu pintor uma única vez ($size MB), $sir. Conecte-se a um Wi-Fi e abra o Gota que eu baixo sozinho; depois você desenha mesmo sem internet."
        }
    }

    private suspend fun runSearch(goal: String, query: String) {
        if (!WebSearch.isOnline(context)) {
            reply("Estou sem internet no momento, $sir, e preciso pesquisar para responder isso.")
            return
        }
        onPhase(Phase.SEARCHING)
        onStatus("Pesquisando...")
        val result = try {
            withContext(Dispatchers.IO) { WebSearch.search(query) }
        } catch (e: Exception) {
            WebSearch.Result(emptyList(), emptyList())
        }
        if (result.isEmpty) {
            reply("Pesquisei, $sir, mas não encontrei nada sobre isso.")
            return
        }
        val agent = GemmaAgent.get() ?: run { reply("Perdão, $sir, minha mente ainda está carregando."); return }

        onStatus("Lendo o que encontrei...")
        val today = SimpleDateFormat("dd 'de' MMMM 'de' yyyy", ptBr).format(Date())
        val system = """
            Você é o Gota, mordomo pessoal de $fullName. Responda em português do Brasil, com acentuação
            correta, no tom cordial de um mordomo clássico, chamando o dono de "$sir". Hoje é $today.
            Você pesquisou na internet e recebeu trechos. Responda à pergunta direto, em 1 ou 2 frases,
            como quem já sabe a resposta:
            - Os trechos estão em ordem do MAIS RECENTE para o mais antigo. O trecho 1 é o mais novo; cada um
              começa com a data entre parênteses.
            - Baseie a resposta no estado MAIS RECENTE dos fatos. Se um trecho antigo diz "vai acontecer" e um
              mais novo diz que "aconteceu/foi aprovado", vale o mais novo. Nunca responda com uma previsão
              antiga se já existe um trecho mais recente dizendo o que de fato ocorreu.
            - Para perguntas de "já foi...?", "quando...", "qual o último/mais recente", prefira o trecho 1.
            - Inclua o dado principal (número, data, nome) e diga datas por extenso ("ontem, 14 de outubro").
            - O 'Contexto' no fim pode estar desatualizado; só use se os trechos datados não bastarem.
            - Nunca mencione "trechos", "resultados", "pesquisa" ou sites, e não sugira onde conferir.
            - Não acrescente nada que não foi perguntado.
            - Se nada responder, diga só: "Não encontrei essa informação agora, $sir."
            Responda em texto simples, sem JSON e sem listas.
        """.trimIndent()
        val user = buildString {
            append("Pergunta: $goal\n\nTrechos (1 = mais recente):\n")
            result.snippets.forEachIndexed { i, s -> append("${i + 1}. $s\n") }
            // Full-page text has no date, so it's background only, to avoid dragging in stale facts.
            if (result.pages.isNotEmpty()) {
                append("\nContexto (sem data, pode estar desatualizado):\n")
                result.pages.forEach { append("$it\n") }
            }
        }
        val raw = try {
            agent.oneShot(system, user)
        } catch (e: Exception) {
            reply("Encontrei algo, $sir, mas não consegui ler: ${e.message}")
            return
        }
        val json = extractJson(raw)
        val text = json?.optString("text")?.ifBlank { null } ?: raw.trim().ifBlank { null }
        reply(text ?: "Não encontrei essa informação agora, $sir.")
    }

    /**
     * Only acts if the number the model returned appears literally in what the person said —
     * this stops the model from inventing a phone number for a contact it cannot know.
     */
    private inline fun withVerifiedNumber(goal: String, json: JSONObject, action: (String) -> Unit) {
        val number = json.optString("number")
        val numberDigits = number.filter { it.isDigit() }
        val goalDigits = goal.filter { it.isDigit() }
        if (numberDigits.length < 8 || !goalDigits.contains(numberDigits)) {
            reply("Não tenho esse número, $sir; não acesso seus contatos. Poderia me dizer o número completo?")
            return
        }
        action(number)
    }

    private val LOCAL_HINTS = listOf(
        "perto", "proximo", "aqui", "regiao", "minha cidade", "clima", "tempo", "previsao", "chuva",
        "temperatura", "restaurante", "farmacia", "mercado", "hospital", "posto", "cinema", "loja", "aberto", "transito"
    )

    /** Adds the user's city to location-dependent searches if the model forgot to. */
    private fun withLocation(goal: String, query: String): String {
        val city = LocationHelper.currentCity(context) ?: return query
        if (query.contains(city, ignoreCase = true)) return query
        val text = AppCatalog.normalize("$goal $query")
        return if (LOCAL_HINTS.any { text.contains(it) }) "$query $city" else query
    }

    /** Tolerates code fences and a missing closing brace, which small models produce often. */
    private fun extractJson(raw: String): JSONObject? {
        val cleaned = raw.replace("```json", "").replace("```", "").trim()
        val start = cleaned.indexOf('{')
        if (start == -1) return null
        val tail = cleaned.substring(start)
        val end = tail.lastIndexOf('}')
        val candidates = buildList {
            if (end != -1) add(tail.substring(0, end + 1))
            add("$tail}")
            add("$tail\"}")
        }
        for (candidate in candidates) {
            try {
                return JSONObject(candidate)
            } catch (e: Exception) { /* try the next repair */ }
        }
        return null
    }

    private fun looksLikeJson(raw: String) = raw.contains("\"action\"")

    companion object {
        private val RETRY = Regex(
            "^(?:(?:gera|gere|faz|faca|cria|crie|desenha|desenhe|tenta|tente|manda|mande)\\s+)?(?:(?:a|uma|essa)\\s+)?" +
                "(?:outra|outro|de novo|novamente|mais uma|nova)(?:\\s+(?:vez|imagem|versao|opcao|variacao|foto|desenho))?$|" +
                "^(?:refaz|refaca|refazer)(?:\\s+(?:a imagem|isso|esse desenho))?$"
        )

        /** "outra", "de novo", "gera outra imagem"... (already normalized: lower case, no accents). */
        fun isRetryRequest(lower: String) = RETRY.matches(lower)

        // Including the ways speech recognition mishears "hey Gota" ("pegou tô").
        private val WAKE_PREFIXES = listOf(
            "hey gota", "hei gota", "ei gota", "oi gota", "e gota", "ai gota", "rei gota", "hey gotta", "ei gotta",
            "pegou o to", "pegou to", "pegou ta", "pegou tu", "gota"
        )

        /** "Ei Gota, que horas são" → "Que horas são". */
        fun stripWakeWord(text: String): String {
            val norm = AppCatalog.normalize(text)
            val prefix = WAKE_PREFIXES.firstOrNull { norm.startsWith("$it ") } ?: return text.trim()
            return dropPrefix(text, prefix).replaceFirstChar { it.uppercase() }
        }

        /** Removes the leading words of [text] whose normalized form is [normalizedPrefix], keeping accents in the rest. */
        fun dropPrefix(text: String, normalizedPrefix: String): String {
            val words = text.trim().split(Regex("\\s+"))
            for (i in 1..words.size) {
                if (AppCatalog.normalize(words.take(i).joinToString(" ")) == normalizedPrefix) {
                    return words.drop(i).joinToString(" ").trimStart(',', '.', '!', '?', ':', '-', ' ')
                }
            }
            return text.trim()
        }
    }
}
