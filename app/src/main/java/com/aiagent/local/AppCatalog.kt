package com.aiagent.local

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.LauncherApps
import android.graphics.drawable.Drawable
import android.os.Process
import android.os.UserHandle
import android.os.UserManager
import org.json.JSONObject
import java.text.Normalizer

data class AppEntry(
    val label: String,
    val packageName: String,
    val className: String,
    val user: UserHandle,
    val userSerial: Long,
    val isMainProfile: Boolean
) {
    /** Stable id used to store nicknames. */
    val key get() = "$packageName/$className#$userSerial"

    /** Dual Messenger copies get a marker so the two WhatsApps can be told apart. */
    val displayLabel get() = if (isMainProfile) label else "$label (2º)"
}

/**
 * Lists launchable apps across every profile of this phone (including Samsung Dual Messenger
 * copies) and resolves spoken names, giving priority to nicknames the owner created.
 */
object AppCatalog {

    private const val ALIAS_PREFS = "gota_app_aliases"

    fun normalize(text: String): String =
        Normalizer.normalize(text.lowercase(), Normalizer.Form.NFD)
            .replace(Regex("\\p{Mn}+"), "")
            .replace(Regex("[^a-z0-9 ]"), " ")
            .replace(Regex("\\s+"), " ")
            .trim()

    fun all(context: Context): List<AppEntry> {
        val launcher = context.getSystemService(LauncherApps::class.java)
        val users = context.getSystemService(UserManager::class.java)
        val me = Process.myUserHandle()
        val profiles = runCatching { launcher.profiles }.getOrDefault(listOf(me))
        val entries = profiles.flatMap { user ->
            runCatching {
                launcher.getActivityList(null, user).map { info ->
                    AppEntry(
                        label = info.label.toString(),
                        packageName = info.componentName.packageName,
                        className = info.componentName.className,
                        user = user,
                        userSerial = users.getSerialNumberForUser(user),
                        isMainProfile = user == me
                    )
                }
            }.getOrDefault(emptyList())
        }
        return entries.filter { it.packageName != context.packageName }
            .sortedWith(compareBy({ !it.isMainProfile }, { it.label.lowercase() }))
    }

    fun icon(context: Context, entry: AppEntry): Drawable? = runCatching {
        val launcher = context.getSystemService(LauncherApps::class.java)
        launcher.getActivityList(entry.packageName, entry.user)
            .firstOrNull { it.componentName.className == entry.className }
            ?.getBadgedIcon(0)
    }.getOrNull()

    // ---- nicknames ----

    fun aliases(context: Context): Map<String, String> {
        val raw = context.getSharedPreferences(ALIAS_PREFS, Context.MODE_PRIVATE).getString("map", "{}") ?: "{}"
        val json = runCatching { JSONObject(raw) }.getOrDefault(JSONObject())
        return json.keys().asSequence().associateWith { json.getString(it) }
    }

    fun aliasFor(context: Context, entry: AppEntry): String? =
        aliases(context).entries.firstOrNull { it.value == entry.key }?.key

    /** Sets (or clears, when [alias] is blank) the nickname of an app. */
    fun setAlias(context: Context, entry: AppEntry, alias: String) {
        val map = aliases(context).filterValues { it != entry.key }.toMutableMap()
        val clean = normalize(alias)
        if (clean.isNotBlank()) map[clean] = entry.key
        context.getSharedPreferences(ALIAS_PREFS, Context.MODE_PRIVATE).edit()
            .putString("map", JSONObject(map as Map<*, *>).toString()).apply()
    }

    // ---- lookup ----

    private val SECOND_COPY_WORDS = listOf("2", "dois", "segundo", "segunda", "outro", "outra", "dual", "clone", "duplicado")

    /** Best matches for what the person said, nicknames first. */
    fun find(context: Context, spoken: String): List<AppEntry> {
        val query = normalize(spoken)
            .removePrefix("o ").removePrefix("a ").removePrefix("app ").removePrefix("aplicativo ").trim()
        if (query.isBlank()) return emptyList()
        val apps = all(context)

        aliases(context)[query]?.let { key -> apps.firstOrNull { it.key == key }?.let { return listOf(it) } }
        // Nickname contained in a longer phrase ("abre o whats 2 por favor").
        aliases(context).entries.sortedByDescending { it.key.length }
            .firstOrNull { (alias, _) -> " $query ".contains(" $alias ") }
            ?.let { (_, key) -> apps.firstOrNull { it.key == key }?.let { return listOf(it) } }

        val wantsSecond = SECOND_COPY_WORDS.any { " $query ".contains(" $it ") }
        val name = SECOND_COPY_WORDS.fold(" $query ") { acc, w -> acc.replace(" $w ", " ") }.trim()
            .let { if (it == "whats" || it == "zap" || it == "zapzap") "whatsapp" else it }

        val matches = apps.filter {
            val label = normalize(it.label)
            label == name || label.contains(name) || (name.length >= 4 && name.contains(label))
        }.sortedWith(compareBy({ normalize(it.label) != name }, { it.label.length }))

        if (matches.isEmpty()) return emptyList()
        return if (wantsSecond) {
            val second = matches.filter { !it.isMainProfile } +
                matches.filter { it.isMainProfile && normalize(it.label) != name }
            second.ifEmpty { matches }
        } else {
            matches.sortedBy { !it.isMainProfile }
        }
    }

    fun launch(context: Context, entry: AppEntry): Boolean = runCatching {
        if (entry.isMainProfile) {
            val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
                .setComponent(ComponentName(entry.packageName, entry.className))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED)
            context.startActivity(intent)
        } else {
            context.getSystemService(LauncherApps::class.java)
                .startMainActivity(ComponentName(entry.packageName, entry.className), entry.user, null, null)
        }
        true
    }.getOrDefault(false)
}
