package com.aiagent.local

import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test

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
    fun longPromptsAreCut() {
        val ids = tokenizer.encode((1..200).joinToString(" ") { "cat" })
        assertEquals(77, ids.size)
        assertEquals(49406L, ids[0])
        assertEquals(2368L, ids[75])
        assertEquals(49407L, ids[76])
    }
}
