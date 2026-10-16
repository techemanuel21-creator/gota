package com.aiagent.local

import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class ClipTokenizerTest {

    private fun resource(name: String) = javaClass.classLoader!!.getResource("clip/$name")!!.readText()

    private val vocabText = resource("vocab.json")
    private val tokenizer = ClipTokenizer(vocabText, resource("merges.txt"))

    @Test
    fun knownIds() {
        val ids = tokenizer.encode("A photo of a cat")
        assertEquals(77, ids.size)
        assertArrayEquals(longArrayOf(49406, 320, 1125, 539, 320, 2368, 49407, 49407), ids.copyOf(8))
    }

    @Test
    fun piecesRebuildTheText() {
        val json = JSONObject(vocabText)
        val reverse = HashMap<Long, String>()
        json.keys().forEach { reverse[json.getInt(it).toLong()] = it }
        val text = "a cute gray cat butler with round glasses, serving tea in a sunny victorian living-room, detailed"
        val ids = tokenizer.encode(text)
        val end = ids.indexOfFirst { it == 49407L }
        val rebuilt = ids.slice(1 until end).joinToString("") { reverse[it]!! }.replace("</w>", " ").trim()
        assertEquals(text.replace(",", " ,").replace("-", " - ").replace(Regex("\\s+"), " "), rebuilt.replace(Regex("\\s+"), " "))
    }

    @Test
    fun suffixKeepsItsWordsEvenWhenTheTextIsLong() {
        val suffix = ImagePrompt.PHOTO
        val tail = tokenizer.tokens(suffix).map { it.toLong() }
        val ids = tokenizer.encode((1..200).joinToString(" ") { "cat" }, suffix)
        assertEquals(77, ids.size)
        assertEquals(49406L, ids[0])
        val end = ids.indexOfFirst { it == 49407L }
        assertEquals(76, end) // the long text filled every free slot
        assertEquals(tail, ids.slice((end - tail.size) until end))
        assertEquals(2368L, ids[1]) // the text is what got shortened, from its end
    }

    @Test
    fun shortTextThenSuffixHasNoGap() {
        val ids = tokenizer.encode("a cat", "sharp focus")
        val expected = listOf(49406L) + tokenizer.tokens("a cat").map { it.toLong() } +
            tokenizer.tokens("sharp focus").map { it.toLong() } + 49407L
        assertEquals(expected, ids.take(expected.size))
        assertTrue(ids.drop(expected.size).all { it == 49407L })
    }

    @Test
    fun emptySuffixBehavesLikePlainEncode() {
        assertArrayEquals(tokenizer.encode("a photo of a cat"), tokenizer.encode("a photo of a cat", ""))
    }

    @Test
    fun longPromptsAreCut() {
        val ids = tokenizer.encode((1..200).joinToString(" ") { "cat" })
        assertEquals(77, ids.size)
        assertEquals(49406L, ids[0])
        assertEquals(2368L, ids[75])
        assertEquals(49407L, ids[76])
    }

    /**
     * With GOTA_TOKENS pointing at a JSON of {prompt: [77 ids]} made by the official Hugging Face
     * tokenizer, every prompt must give exactly the same ids here.
     */
    @Test
    fun matchesTheOfficialTokenizer() {
        val path = System.getenv("GOTA_TOKENS")
        org.junit.Assume.assumeTrue(path != null)
        val reference = JSONObject(File(path!!).readText())
        val mismatches = reference.keys().asSequence().mapNotNull { prompt ->
            val expected = reference.getJSONArray(prompt).let { arr -> LongArray(arr.length()) { arr.getLong(it) } }
            val ours = tokenizer.encode(prompt)
            if (ours.contentEquals(expected)) null
            else "$prompt\n  expected ${expected.take(30)}\n  ours     ${ours.take(30)}"
        }.toList()
        assertTrue("token ids differ from the official tokenizer:\n" + mismatches.joinToString("\n"), mismatches.isEmpty())
    }
}
