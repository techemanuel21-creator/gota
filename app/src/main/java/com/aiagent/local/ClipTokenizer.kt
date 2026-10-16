package com.aiagent.local

import org.json.JSONObject

/**
 * The CLIP tokenizer used by Stable Diffusion text encoders: lower-cased, byte-level BPE where the
 * last piece of every word ends in "</w>". Always returns 77 ids: start token, the prompt, end
 * token, then padding (long prompts are cut, so the important words should come first).
 */
class ClipTokenizer(vocabJson: String, mergesTxt: String) {

    private val vocab: Map<String, Int>
    private val ranks: Map<String, Int>
    private val byteToChar = bytesToUnicode()
    private val cache = HashMap<String, List<String>>()

    init {
        val json = JSONObject(vocabJson)
        vocab = HashMap<String, Int>(json.length() * 2).apply {
            json.keys().forEach { put(it, json.getInt(it)) }
        }
        ranks = HashMap<String, Int>(MAX_MERGES * 2).apply {
            mergesTxt.lineSequence()
                .filter { it.isNotBlank() && !it.startsWith("#version") }
                .take(MAX_MERGES)
                .forEachIndexed { rank, line -> put(line, rank) }
        }
    }

    /** The token ids of [text] alone, without the start/end markers. */
    fun tokens(text: String): List<Int> {
        val clean = text.replace(Regex("\\s+"), " ").trim().lowercase()
        val ids = ArrayList<Int>()
        for (match in PATTERN.findAll(clean)) {
            val mapped = buildString {
                match.value.toByteArray(Charsets.UTF_8).forEach { append(byteToChar[it.toInt() and 0xFF]) }
            }
            for (piece in bpe(mapped)) vocab[piece]?.let { ids += it }
        }
        return ids
    }

    fun encode(text: String): LongArray = pack(tokens(text))

    /**
     * Encodes [text] followed by [suffix], keeping the whole suffix even when the text is long: the
     * text is the part that gets cut. Used to add quality words to a picture request.
     */
    fun encode(text: String, suffix: String): LongArray {
        val tail = tokens(suffix)
        val room = (MAX_TOKENS - 2 - tail.size).coerceAtLeast(0)
        return pack(tokens(text).take(room) + tail)
    }

    private fun pack(ids: List<Int>): LongArray {
        val out = LongArray(MAX_TOKENS) { END_ID }
        out[0] = START_ID
        val count = minOf(ids.size, MAX_TOKENS - 2)
        for (i in 0 until count) out[i + 1] = ids[i].toLong()
        out[count + 1] = END_ID
        return out
    }

    /** Merges the best-ranked neighbouring pair over and over, exactly like the reference CLIP code. */
    private fun bpe(token: String): List<String> {
        cache[token]?.let { return it }
        var word: List<String> = token.dropLast(1).map { it.toString() } + (token.last() + "</w>")
        while (word.size > 1) {
            var best = -1
            var bestRank = Int.MAX_VALUE
            for (i in 0 until word.size - 1) {
                val rank = ranks["${word[i]} ${word[i + 1]}"] ?: continue
                if (rank < bestRank) {
                    bestRank = rank
                    best = i
                }
            }
            if (best == -1) break
            val first = word[best]
            val second = word[best + 1]
            val merged = ArrayList<String>(word.size)
            var i = 0
            while (i < word.size) {
                if (i < word.size - 1 && word[i] == first && word[i + 1] == second) {
                    merged += first + second
                    i += 2
                } else {
                    merged += word[i]
                    i++
                }
            }
            word = merged
        }
        cache[token] = word
        return word
    }

    companion object {
        const val MAX_TOKENS = 77
        private const val START_ID = 49406L
        private const val END_ID = 49407L
        private const val MAX_MERGES = 49152 - 256 - 2

        private val PATTERN = Regex(
            """<\|startoftext\|>|<\|endoftext\|>|'s|'t|'re|'ve|'m|'ll|'d|[\p{L}]+|[\p{N}]|[^\s\p{L}\p{N}]+""",
            RegexOption.IGNORE_CASE
        )

        /** GPT-2/CLIP mapping of each byte to a printable character. */
        private fun bytesToUnicode(): CharArray {
            val bytes = ((33..126) + (161..172) + (174..255)).toMutableList()
            val chars = bytes.toMutableList()
            var n = 0
            for (b in 0..255) {
                if (b !in bytes) {
                    bytes += b
                    chars += 256 + n
                    n++
                }
            }
            val table = CharArray(256)
            bytes.forEachIndexed { i, b -> table[b] = chars[i].toChar() }
            return table
        }
    }
}
