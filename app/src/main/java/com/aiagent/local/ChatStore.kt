package com.aiagent.local

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID

data class ChatMessage(
    val role: String,               // "user" or "gota"
    val text: String,
    val image: String? = null,      // file path or content:// uri
    val time: Long = System.currentTimeMillis()
)

data class Chat(
    val id: String,
    var title: String,
    var updatedAt: Long,
    val messages: MutableList<ChatMessage>
) {
    val isVoice get() = id == ChatStore.VOICE_CHAT_ID
}

/** Conversations saved as small JSON files, one per chat. */
object ChatStore {

    const val VOICE_CHAT_ID = "voice"
    private const val DEFAULT_TITLE = "Nova conversa"
    private val lock = Any()

    private fun dir(context: Context) = File(context.filesDir, "chats").also { it.mkdirs() }
    private fun file(context: Context, id: String) = File(dir(context), "$id.json")

    fun list(context: Context): List<Chat> = synchronized(lock) {
        dir(context).listFiles { f -> f.extension == "json" }
            ?.mapNotNull { runCatching { parse(it.readText()) }.getOrNull() }
            ?.sortedByDescending { it.updatedAt }
            ?: emptyList()
    }

    fun get(context: Context, id: String): Chat? = synchronized(lock) {
        val f = file(context, id)
        if (!f.exists()) null else runCatching { parse(f.readText()) }.getOrNull()
    }

    fun create(context: Context, title: String = DEFAULT_TITLE): Chat = synchronized(lock) {
        val chat = Chat(UUID.randomUUID().toString(), title, System.currentTimeMillis(), mutableListOf())
        save(context, chat)
        chat
    }

    fun voiceChat(context: Context): Chat = synchronized(lock) {
        get(context, VOICE_CHAT_ID) ?: Chat(VOICE_CHAT_ID, "Conversas por voz", System.currentTimeMillis(), mutableListOf())
            .also { save(context, it) }
    }

    fun append(context: Context, chatId: String, message: ChatMessage): Chat = synchronized(lock) {
        val chat = get(context, chatId)
            ?: Chat(chatId, DEFAULT_TITLE, System.currentTimeMillis(), mutableListOf())
        chat.messages.add(message)
        chat.updatedAt = System.currentTimeMillis()
        if (chat.title == DEFAULT_TITLE && message.role == "user" && message.text.isNotBlank()) {
            chat.title = message.text.take(40).let { if (message.text.length > 40) "$it…" else it }
        }
        save(context, chat)
        chat
    }

    fun delete(context: Context, id: String) = synchronized(lock) {
        file(context, id).delete()
    }

    private fun save(context: Context, chat: Chat) {
        val arr = JSONArray()
        chat.messages.forEach { m ->
            arr.put(JSONObject().put("role", m.role).put("text", m.text).put("image", m.image ?: JSONObject.NULL).put("time", m.time))
        }
        val json = JSONObject()
            .put("id", chat.id).put("title", chat.title).put("updatedAt", chat.updatedAt).put("messages", arr)
        file(context, chat.id).writeText(json.toString())
    }

    private fun parse(text: String): Chat {
        val json = JSONObject(text)
        val arr = json.getJSONArray("messages")
        val messages = (0 until arr.length()).map { i ->
            val m = arr.getJSONObject(i)
            ChatMessage(
                role = m.getString("role"),
                text = m.optString("text"),
                image = if (m.isNull("image")) null else m.optString("image"),
                time = m.optLong("time")
            )
        }.toMutableList()
        return Chat(json.getString("id"), json.optString("title", DEFAULT_TITLE), json.optLong("updatedAt"), messages)
    }
}
