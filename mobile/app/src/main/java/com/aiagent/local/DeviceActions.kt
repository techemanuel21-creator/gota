package com.aiagent.local

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.AlarmClock
import android.provider.CalendarContract

object DeviceActions {

    private val KNOWN_PACKAGES = mapOf(
        "whatsapp" to "com.whatsapp",
        "instagram" to "com.instagram.android",
        "facebook" to "com.facebook.katana",
        "messenger" to "com.facebook.orca",
        "telegram" to "org.telegram.messenger",
        "gmail" to "com.google.android.gm",
        "youtube" to "com.google.android.youtube",
        "chrome" to "com.android.chrome"
    )

    fun resolvePackageName(context: Context, nameOrPackage: String): String? {
        AppCatalog.find(context, nameOrPackage).firstOrNull()?.let { return it.packageName }
        val pm = context.packageManager
        val lower = nameOrPackage.trim().lowercase()
        KNOWN_PACKAGES[lower]?.let { pkg ->
            try {
                pm.getPackageInfo(pkg, 0)
                return pkg
            } catch (e: Exception) { /* not installed, fall through */ }
        }
        try {
            pm.getPackageInfo(nameOrPackage, 0)
            return nameOrPackage
        } catch (e: Exception) { /* not a package name, fall through */ }
        val launcherIntent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val apps = pm.queryIntentActivities(launcherIntent, 0)
        return apps.firstOrNull { it.loadLabel(pm).toString().contains(nameOrPackage, ignoreCase = true) }
            ?.activityInfo?.packageName
    }

    /** Opens the best match (nicknames first). Returns the label opened, or null. */
    fun openAppLabel(context: Context, spoken: String): String? {
        val entry = AppCatalog.find(context, spoken).firstOrNull() ?: return null
        return if (AppCatalog.launch(context, entry)) entry.displayLabel else null
    }

    fun openApp(context: Context, nameOrPackage: String): Boolean {
        if (openAppLabel(context, nameOrPackage) != null) return true
        val pkg = resolvePackageName(context, nameOrPackage) ?: return false
        val intent = context.packageManager.getLaunchIntentForPackage(pkg) ?: return false
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)
        return true
    }

    fun dial(context: Context, number: String): Boolean = tryStart(context) {
        Intent(Intent.ACTION_DIAL, Uri.parse("tel:$number"))
    }

    fun sendSms(context: Context, number: String, message: String): Boolean = tryStart(context) {
        Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:$number")).apply {
            putExtra("sms_body", message)
        }
    }

    fun openWhatsApp(context: Context, number: String, message: String): Boolean = tryStart(context) {
        val cleanNumber = number.filter { it.isDigit() }
        Intent(Intent.ACTION_VIEW, Uri.parse("https://wa.me/$cleanNumber?text=" + Uri.encode(message)))
    }

    fun openUrl(context: Context, url: String): Boolean {
        val fixed = if (url.startsWith("http://") || url.startsWith("https://")) url else "https://$url"
        return tryStart(context) { Intent(Intent.ACTION_VIEW, Uri.parse(fixed)) }
    }

    fun searchWeb(context: Context, query: String): Boolean = tryStart(context) {
        Intent(Intent.ACTION_VIEW, Uri.parse("https://www.google.com/search?q=" + Uri.encode(query)))
    }

    fun setAlarm(context: Context, hour: Int, minute: Int, label: String): Boolean = tryStart(context) {
        Intent(AlarmClock.ACTION_SET_ALARM).apply {
            putExtra(AlarmClock.EXTRA_HOUR, hour)
            putExtra(AlarmClock.EXTRA_MINUTES, minute)
            putExtra(AlarmClock.EXTRA_MESSAGE, label)
        }
    }

    fun setTimer(context: Context, seconds: Int, label: String): Boolean = tryStart(context) {
        Intent(AlarmClock.ACTION_SET_TIMER).apply {
            putExtra(AlarmClock.EXTRA_LENGTH, seconds)
            putExtra(AlarmClock.EXTRA_MESSAGE, label)
        }
    }

    fun createEvent(context: Context, title: String): Boolean = tryStart(context) {
        Intent(Intent.ACTION_INSERT).apply {
            data = CalendarContract.Events.CONTENT_URI
            putExtra(CalendarContract.Events.TITLE, title)
        }
    }

    fun shareText(context: Context, text: String): Boolean = tryStart(context) {
        val sendIntent = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, text)
        }
        Intent.createChooser(sendIntent, null)
    }

    private inline fun tryStart(context: Context, builder: () -> Intent): Boolean {
        return try {
            val intent = builder().addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent)
            true
        } catch (e: ActivityNotFoundException) {
            false
        }
    }
}
