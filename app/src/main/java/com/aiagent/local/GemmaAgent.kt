package com.aiagent.local

import android.content.Context
import com.google.ai.edge.litertlm.Backend
import com.google.ai.edge.litertlm.Content
import com.google.ai.edge.litertlm.Contents
import com.google.ai.edge.litertlm.Conversation
import com.google.ai.edge.litertlm.ConversationConfig
import com.google.ai.edge.litertlm.Engine
import com.google.ai.edge.litertlm.EngineConfig
import com.google.ai.edge.litertlm.Message
import com.google.ai.edge.litertlm.SamplerConfig
import com.google.ai.edge.litertlm.ThinkingConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.ByteArrayOutputStream

/** A previous turn to replay into a fresh conversation: role is "user" or "model". */
data class Turn(val role: String, val text: String)

/**
 * Wraps the on-device Gemma model. The main chat keeps ONE live conversation so the long system
 * prompt and earlier turns stay in the model's cache: follow-up messages only process the new text,
 * which is much faster than starting over each time. One-off tasks (search summaries, screen
 * control) temporarily replace it; the chat conversation is rebuilt from saved history afterwards.
 */
class GemmaAgent private constructor(private val engine: Engine) {

    private val mutex = Mutex()
    private var live: Conversation? = null
    private var liveKey: String? = null
    private var liveChars = 0

    private val sampler = SamplerConfig(topK = 40, topP = 0.95, temperature = 0.4)

    suspend fun chat(
        key: String,
        systemPrompt: String,
        history: List<Turn>,
        userText: String,
        imagePath: String? = null
    ): String = mutex.withLock {
        withContext(Dispatchers.IO) {
            val wantedKey = "$key|${systemPrompt.hashCode()}"
            if (live == null || liveKey != wantedKey || liveChars > MAX_LIVE_CHARS) {
                closeLive()
                val turns = history.takeLast(MAX_REPLAY_TURNS)
                val older = history.dropLast(MAX_REPLAY_TURNS)
                // Older turns don't fit word for word, so they come back as a short digest.
                val system = if (older.isEmpty()) systemPrompt else systemPrompt + "\n\n" + digest(older)
                val replay = turns.map { if (it.role == "user") Message.user(it.text) else Message.model(it.text) }
                live = engine.createConversation(
                    ConversationConfig(
                        systemInstruction = Contents.of(system),
                        initialMessages = replay,
                        samplerConfig = sampler,
                        thinkingConfig = ThinkingConfig(false)
                    )
                )
                liveKey = wantedKey
                liveChars = system.length + turns.sumOf { it.text.length }
            }
            val reply = send(live!!, userText, imagePath)
            liveChars += userText.length + reply.length
            reply
        }
    }

    suspend fun oneShot(systemPrompt: String, userText: String, imagePath: String? = null): String = mutex.withLock {
        withContext(Dispatchers.IO) {
            closeLive()
            engine.createConversation(
                ConversationConfig(
                    systemInstruction = Contents.of(systemPrompt),
                    samplerConfig = sampler,
                    thinkingConfig = ThinkingConfig(false)
                )
            ).use { send(it, userText, imagePath) }
        }
    }

    private fun send(conversation: Conversation, userText: String, imagePath: String?): String {
        val message = if (imagePath != null && visionAvailable) {
            Message.user(Contents.of(Content.ImageFile(imagePath), Content.Text(userText)))
        } else {
            Message.user(userText)
        }
        val reply = conversation.sendMessage(message)
        val text = reply.contents.contents.filterIsInstance<Content.Text>().joinToString("") { it.text }
        return decodeByteLevelArtifacts(text)
    }

    /** The start of the conversation plus as much of the most recent part as fits in [DIGEST_CHARS]. */
    private fun digest(older: List<Turn>): String {
        val lines = older.map { turn ->
            val text = if (turn.role == "user") turn.text
            else runCatching { JSONObject(turn.text).optString("text") }.getOrNull()?.ifBlank { null } ?: turn.text
            (if (turn.role == "user") "Dono: " else "Você: ") + text.replace(Regex("\\s+"), " ").take(160)
        }
        val head = lines.take(2)
        val tail = ArrayList<String>()
        var budget = DIGEST_CHARS - head.sumOf { it.length }
        for (line in lines.drop(head.size).asReversed()) {
            if (line.length > budget) break
            tail.add(0, line)
            budget -= line.length
        }
        return buildString {
            appendLine("Antes, nesta mesma conversa, já foi dito (lembre-se disso):")
            head.forEach { appendLine(it) }
            if (lines.size > head.size + tail.size) appendLine("[...]")
            tail.forEach { appendLine(it) }
        }
    }

    private fun closeLive() {
        runCatching { live?.close() }
        live = null
        liveKey = null
        liveChars = 0
    }

    /** Forget the cached conversation (e.g. when the user switches chats). */
    suspend fun reset() = mutex.withLock { withContext(Dispatchers.IO) { closeLive() } }

    fun close() {
        closeLive()
        engine.close()
    }

    companion object {
        // Rough budget so the 4096-token context never overflows (~3 chars per token).
        private const val MAX_LIVE_CHARS = 9000
        private const val MAX_REPLAY_TURNS = 8
        private const val DIGEST_CHARS = 1500

        @Volatile
        private var instance: GemmaAgent? = null

        @Volatile
        var visionAvailable = true
            private set

        fun get(): GemmaAgent? = instance

        fun isLoaded(): Boolean = instance != null

        fun load(context: Context, modelPath: String): GemmaAgent {
            instance?.close()
            // Try with image understanding; if this phone can't load the vision part, run text-only.
            val engine = try {
                Engine(
                    EngineConfig(
                        modelPath = modelPath,
                        backend = Backend.CPU(),
                        visionBackend = Backend.CPU(),
                        maxNumTokens = 4096,
                        maxNumImages = 1,
                        cacheDir = context.cacheDir.path
                    )
                ).also { it.initialize() }
            } catch (e: Exception) {
                visionAvailable = false
                Engine(
                    EngineConfig(modelPath = modelPath, backend = Backend.CPU(), maxNumTokens = 4096, cacheDir = context.cacheDir.path)
                ).also { it.initialize() }
            }
            val agent = GemmaAgent(engine)
            instance = agent
            return agent
        }

        /**
         * Byte-level BPE tokenizers (GPT-2 style) represent each UTF-8 byte as a printable
         * character. If a runtime forgets to map those back, accented text comes out like
         * "OlÃ¡" or "6ÃĹ1". This rebuilds the real UTF-8 sequence only where a lead byte is
         * followed by valid continuation bytes, so correctly encoded text is never touched.
         */
        private val BYTE_EXCLUDED: List<Int> = (0..32) + (127..160) + listOf(173)

        private fun byteOf(c: Char): Int? {
            val code = c.code
            return when {
                code in 0xA1..0xAC || code in 0xAE..0xFF -> code
                code in 0x100 until 0x100 + BYTE_EXCLUDED.size -> BYTE_EXCLUDED[code - 0x100]
                else -> null
            }
        }

        private fun continuationCount(lead: Int): Int = when (lead) {
            in 0xC2..0xDF -> 1
            in 0xE0..0xEF -> 2
            in 0xF0..0xF4 -> 3
            else -> 0
        }

        fun decodeByteLevelArtifacts(text: String): String {
            val out = StringBuilder(text.length)
            var i = 0
            while (i < text.length) {
                val lead = byteOf(text[i])
                val needed = lead?.let { continuationCount(it) } ?: 0
                if (lead != null && needed > 0 && i + needed < text.length) {
                    val bytes = ByteArrayOutputStream()
                    bytes.write(lead)
                    var ok = true
                    for (k in 1..needed) {
                        val b = byteOf(text[i + k])
                        if (b == null || b !in 0x80..0xBF) {
                            ok = false
                            break
                        }
                        bytes.write(b)
                    }
                    if (ok) {
                        out.append(String(bytes.toByteArray(), Charsets.UTF_8))
                        i += needed + 1
                        continue
                    }
                }
                out.append(text[i])
                i++
            }
            return out.toString()
        }
    }
}
