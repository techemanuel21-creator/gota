package com.aiagent.local

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.util.Base64
import java.net.HttpURLConnection
import java.net.URL
import java.text.Normalizer
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

object WebSearch {

    data class Result(val snippets: List<String>, val pages: List<String>) {
        val isEmpty get() = snippets.isEmpty() && pages.isEmpty()
    }

    fun isOnline(context: Context): Boolean {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager ?: return false
        val network = cm.activeNetwork ?: return false
        val capabilities = cm.getNetworkCapabilities(network) ?: return false
        return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
                capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
    }

    private const val USER_AGENT =
        "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
    private val BLOCK_REGEX = Regex("""<li class="b_algo"[\s\S]*?</li>""")
    private val SNIPPET_REGEX = Regex("""<p class="b_lineclamp\d?"[^>]*>(.*?)</p>""", RegexOption.DOT_MATCHES_ALL)
    private val LINK_REGEX = Regex("""href="(https?://[^"]+)"""")
    private val PARAGRAPH_REGEX = Regex("""<p[^>]*>([\s\S]*?)</p>""", RegexOption.IGNORE_CASE)
    private val NOISE_REGEX = Regex("""<(script|style|nav|header|footer|aside|form)[\s\S]*?</\1>""", RegexOption.IGNORE_CASE)

    /** Blocking (network). Returns search snippets plus readable text from the top pages. */
    fun search(query: String, maxSnippets: Int = 8, maxPages: Int = 2): Result {
        val html = get("https://www.bing.com/search?q=" + Uri.encode(query) + "&setlang=pt-BR&cc=BR", 600_000)
            ?: return Result(emptyList(), emptyList())

        val blocks = BLOCK_REGEX.findAll(html).map { it.value }.toList()
        val snippets = blocks.mapNotNull { block ->
            SNIPPET_REGEX.find(block)?.groupValues?.get(1)?.let { stripHtml(it) }?.takeIf { it.isNotBlank() }
        }.map { dated(it) }.sortedBy { it.second }.map { it.first }.take(maxSnippets)

        val keywords = normalize(query).split(" ").filter { it.length > 3 }
        val pages = blocks.mapNotNull { block -> LINK_REGEX.findAll(block).firstNotNullOfOrNull { realUrl(it.groupValues[1]) } }
            .distinct()
            .filterNot { it.contains("youtube.com") || it.endsWith(".pdf") }
            .take(maxPages)
            .mapNotNull { url -> runCatching { readableText(url, keywords) }.getOrNull() }
            .filter { it.isNotBlank() }

        return Result(snippets, pages)
    }

    private val RELATIVE_AGE = Regex("""^(\d+)\s+(minutos?|horas?|dias?|semanas?|m[eê]s|meses)\s+atr[aá]s\s*·?\s*""", RegexOption.IGNORE_CASE)
    private val ABSOLUTE_DATE = Regex("""^(\d{1,2}) de (jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\.? de (\d{4})\s*·?\s*""", RegexOption.IGNORE_CASE)
    private val MONTHS = listOf("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
    private const val UNDATED_HOURS = 24L * 60

    /**
     * Turns "1 dia atrás · O Senado..." into "(14/10/2026) O Senado..." and returns its age in hours,
     * so the newest news comes first and the model knows when each piece was written.
     */
    private fun dated(snippet: String): Pair<String, Long> {
        val now = System.currentTimeMillis()
        val format = SimpleDateFormat("dd/MM/yyyy", Locale("pt", "BR"))
        RELATIVE_AGE.find(snippet)?.let { m ->
            val n = m.groupValues[1].toLong()
            val unit = normalize(m.groupValues[2])
            val hours = when {
                unit.startsWith("minuto") -> 0L
                unit.startsWith("hora") -> n
                unit.startsWith("dia") -> n * 24
                unit.startsWith("semana") -> n * 24 * 7
                else -> n * 24 * 30
            }
            return "(${format.format(Date(now - hours * 3_600_000))}) ${snippet.substring(m.range.last + 1)}" to hours
        }
        ABSOLUTE_DATE.find(snippet)?.let { m ->
            val month = MONTHS.indexOf(normalize(m.groupValues[2]))
            val day = Calendar.getInstance().apply { set(m.groupValues[3].toInt(), month, m.groupValues[1].toInt()) }
            val hours = ((now - day.timeInMillis) / 3_600_000).coerceAtLeast(0)
            return "(${format.format(day.time)}) ${snippet.substring(m.range.last + 1)}" to hours
        }
        return snippet to UNDATED_HOURS
    }

    private fun get(url: String, maxBytes: Int): String? = runCatching {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.setRequestProperty("User-Agent", USER_AGENT)
        connection.setRequestProperty("Accept-Language", "pt-BR,pt;q=0.9")
        connection.connectTimeout = 8000
        connection.readTimeout = 8000
        connection.instanceFollowRedirects = true
        val bytes = connection.inputStream.use { input ->
            val buffer = ByteArray(maxBytes)
            var total = 0
            while (total < maxBytes) {
                val read = input.read(buffer, total, maxBytes - total)
                if (read <= 0) break
                total += read
            }
            buffer.copyOf(total)
        }
        connection.disconnect()
        String(bytes, Charsets.UTF_8)
    }.getOrNull()

    /** Bing wraps result links; the real address is base64 in the "u=a1..." parameter. */
    private fun realUrl(href: String): String? {
        val clean = href.replace("&amp;", "&")
        val encoded = Regex("""[?&]u=a1([^&]+)""").find(clean)?.groupValues?.get(1)
        if (encoded != null) {
            val padded = encoded + "=".repeat((4 - encoded.length % 4) % 4)
            return runCatching { String(Base64.decode(padded, Base64.URL_SAFE), Charsets.UTF_8) }.getOrNull()
        }
        return clean.takeIf { it.startsWith("http") && !it.contains("bing.com") }
    }

    /** Pulls the paragraphs most related to the question, capped so it fits the model's context. */
    private fun readableText(url: String, keywords: List<String>, maxChars: Int = 1500): String {
        val html = get(url, 400_000) ?: return ""
        val body = NOISE_REGEX.replace(html, " ")
        val paragraphs = PARAGRAPH_REGEX.findAll(body)
            .map { stripHtml(it.groupValues[1]) }
            .filter { it.length > 60 }
            .toList()
        if (paragraphs.isEmpty()) return ""
        val ranked = paragraphs.sortedByDescending { p ->
            val n = normalize(p)
            keywords.count { n.contains(it) }
        }
        val out = StringBuilder()
        for (p in ranked) {
            if (out.length + p.length > maxChars) break
            out.append(p).append(' ')
        }
        if (out.isEmpty()) out.append(ranked.first().take(maxChars))
        return out.toString().trim()
    }

    private fun normalize(text: String): String =
        Normalizer.normalize(text.lowercase(), Normalizer.Form.NFD).replace(Regex("\\p{Mn}+"), "")

    private val NAMED_ENTITIES = mapOf(
        "nbsp" to " ", "amp" to "&", "quot" to "\"", "apos" to "'", "lt" to "<", "gt" to ">",
        "aacute" to "á", "agrave" to "à", "acirc" to "â", "atilde" to "ã", "eacute" to "é", "ecirc" to "ê",
        "iacute" to "í", "oacute" to "ó", "ocirc" to "ô", "otilde" to "õ", "uacute" to "ú", "ccedil" to "ç",
        "Aacute" to "Á", "Eacute" to "É", "Oacute" to "Ó", "Ccedil" to "Ç", "Atilde" to "Ã",
        "middot" to "·", "hellip" to "…", "ndash" to "–", "mdash" to "—", "ordm" to "º", "ordf" to "ª"
    )

    /** Removes tags and decodes entities like "&#227;" (ã) so accented words reach the model intact. */
    private fun stripHtml(input: String): String {
        val noTags = input.replace(Regex("<[^>]*>"), "")
        val decoded = Regex("&(#x[0-9a-fA-F]+|#\\d+|[a-zA-Z]+);").replace(noTags) { m ->
            val code = m.groupValues[1]
            when {
                code.startsWith("#x") -> code.substring(2).toIntOrNull(16)?.let { String(Character.toChars(it)) }
                code.startsWith("#") -> code.substring(1).toIntOrNull()?.let { String(Character.toChars(it)) }
                else -> NAMED_ENTITIES[code]
            } ?: m.value
        }
        return decoded.replace(' ', ' ').replace(Regex("\\s+"), " ").trim()
    }
}
