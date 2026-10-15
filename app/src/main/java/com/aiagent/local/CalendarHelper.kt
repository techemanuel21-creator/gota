package com.aiagent.local

import android.Manifest
import android.content.ContentUris
import android.content.Context
import android.content.pm.PackageManager
import android.provider.CalendarContract
import androidx.core.content.ContextCompat
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale

/**
 * Reads events from every calendar synced to the phone (Google, Samsung, and Outlook when
 * "Sincronizar calendários" is on in the Outlook app).
 */
object CalendarHelper {

    data class Event(val title: String, val begin: Long, val allDay: Boolean)

    fun hasPermission(context: Context) =
        ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALENDAR) == PackageManager.PERMISSION_GRANTED

    fun events(context: Context, dayOffset: Int): List<Event> {
        if (!hasPermission(context)) return emptyList()
        val start = Calendar.getInstance().apply {
            add(Calendar.DAY_OF_YEAR, dayOffset)
            set(Calendar.HOUR_OF_DAY, 0); set(Calendar.MINUTE, 0); set(Calendar.SECOND, 0); set(Calendar.MILLISECOND, 0)
        }
        val end = (start.clone() as Calendar).apply { add(Calendar.DAY_OF_YEAR, 1) }

        val uri = CalendarContract.Instances.CONTENT_URI.buildUpon().also {
            ContentUris.appendId(it, start.timeInMillis)
            ContentUris.appendId(it, end.timeInMillis)
        }.build()
        val projection = arrayOf(
            CalendarContract.Instances.TITLE,
            CalendarContract.Instances.BEGIN,
            CalendarContract.Instances.ALL_DAY
        )
        val result = mutableListOf<Event>()
        runCatching {
            context.contentResolver.query(uri, projection, null, null, "${CalendarContract.Instances.BEGIN} ASC")?.use { c ->
                while (c.moveToNext()) {
                    val title = c.getString(0)?.takeIf { it.isNotBlank() } ?: "Compromisso sem título"
                    result.add(Event(title, c.getLong(1), c.getInt(2) == 1))
                }
            }
        }
        return result.distinctBy { it.title to it.begin }
    }

    /** "reunião às 09:00, dentista às 15:30 e aniversário da Ana (o dia todo)". */
    fun describe(events: List<Event>): String {
        val fmt = SimpleDateFormat("HH:mm", Locale("pt", "BR"))
        val parts = events.map { e -> if (e.allDay) "${e.title} (o dia todo)" else "${e.title} às ${fmt.format(e.begin)}" }
        return when (parts.size) {
            0 -> ""
            1 -> parts[0]
            else -> parts.dropLast(1).joinToString(", ") + " e " + parts.last()
        }
    }
}
