package com.aiagent.local

import android.content.Context
import org.json.JSONArray

/** What Gota knows about its owner: name, how to address them, and facts learned in conversation. */
object UserProfile {

    private const val PREFS = "gota_profile"
    private const val MAX_FACTS = 40
    private const val MAX_CALL_NOTES = 10

    private fun prefs(context: Context) = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun name(context: Context): String? = prefs(context).getString("name", null)?.takeIf { it.isNotBlank() }

    /** "senhor", "senhora" or "" (just the name). */
    fun treatment(context: Context): String = prefs(context).getString("treatment", "senhor") ?: "senhor"

    fun isSet(context: Context) = name(context) != null

    fun save(context: Context, name: String, treatment: String) {
        prefs(context).edit().putString("name", name.trim()).putString("treatment", treatment).apply()
    }

    /** e.g. "senhor Emanuel", or just "Emanuel". */
    fun address(context: Context): String {
        val name = name(context) ?: return treatment(context).ifBlank { "senhor" }
        val t = treatment(context)
        return if (t.isBlank()) name else "$t $name"
    }

    /** Short form for the end of sentences: "senhor" / "senhora" / the name. */
    fun shortAddress(context: Context): String {
        val t = treatment(context)
        return if (t.isNotBlank()) t else name(context) ?: "senhor"
    }

    /** "o senhor" / "a senhora" / "você". */
    fun pronoun(context: Context): String = when (treatment(context)) {
        "senhor" -> "o senhor"
        "senhora" -> "a senhora"
        else -> "você"
    }

    fun facts(context: Context): List<String> {
        val raw = prefs(context).getString("facts", "[]") ?: "[]"
        val arr = runCatching { JSONArray(raw) }.getOrDefault(JSONArray())
        return (0 until arr.length()).map { arr.getString(it) }
    }

    /** One-line summaries of recent calls, so Gota remembers them in later conversations too. */
    fun callNotes(context: Context): List<String> {
        val arr = runCatching { JSONArray(prefs(context).getString("call_notes", "[]")) }.getOrDefault(JSONArray())
        return (0 until arr.length()).map { arr.getString(it) }
    }

    fun addCallNote(context: Context, note: String) {
        val clean = note.trim()
        if (clean.length < 5) return
        val current = callNotes(context).toMutableList()
        current.add(clean.take(300))
        while (current.size > MAX_CALL_NOTES) current.removeAt(0)
        prefs(context).edit().putString("call_notes", JSONArray(current).toString()).apply()
    }

    fun remember(context: Context, fact: String) {
        val clean = fact.trim().removeSuffix(".")
        if (clean.length < 3) return
        val current = facts(context).filterNot { it.equals(clean, ignoreCase = true) }.toMutableList()
        current.add(clean)
        while (current.size > MAX_FACTS) current.removeAt(0)
        prefs(context).edit().putString("facts", JSONArray(current).toString()).apply()
    }
}
