package com.aiagent

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioManager
import android.os.Build
import android.os.SystemClock
import android.view.ViewConfiguration
import androidx.core.content.ContextCompat

/**
 * Notices Volume Up being held, without the Accessibility service and in any app (videos too).
 *
 * Android doesn't let a normal app see the key itself, but it announces every volume change to
 * all apps. Holding the key makes the volume climb with the system's exact key-repeat rhythm,
 * which dragging the on-screen slider never has ([VolumeHoldDetector]). When that happens Gota
 * puts the volume back where it was and is called.
 *
 * Limitations, both because the volume doesn't move so there is nothing to notice: it can't work
 * when the volume is already at the maximum, nor with the screen off while nothing is playing
 * (Android ignores the volume keys then).
 */
class VolumeButtonWatcher(private val context: Context, private val onLongPress: () -> Unit) {

    private val audio = context.getSystemService(AudioManager::class.java)

    // The same key-repeat timing Android uses for the physical keys on this phone.
    private val detector = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
        VolumeHoldDetector(ViewConfiguration.getKeyRepeatTimeout().toLong(), ViewConfiguration.getKeyRepeatDelay().toLong())
    } else {
        VolumeHoldDetector(ViewConfiguration.getLongPressTimeout().toLong(), 50L)
    }
    private var ringerMode = audio.ringerMode
    private var ringerBefore = audio.ringerMode
    private var ringerChangedAt = 0L
    private var registered = false

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            when (intent.action) {
                VOLUME_CHANGED -> onVolume(
                    intent.getIntExtra(EXTRA_STREAM, -1),
                    intent.getIntExtra(EXTRA_VALUE, -1),
                    intent.getIntExtra(EXTRA_PREV_VALUE, -1)
                )
                AudioManager.RINGER_MODE_CHANGED_ACTION -> {
                    ringerBefore = ringerMode
                    ringerMode = audio.ringerMode
                    ringerChangedAt = SystemClock.elapsedRealtime()
                }
            }
        }
    }

    fun start() {
        if (registered) return
        val filter = IntentFilter().apply {
            addAction(VOLUME_CHANGED)
            addAction(AudioManager.RINGER_MODE_CHANGED_ACTION)
        }
        // Both are protected system broadcasts, so no other app can fake them.
        ContextCompat.registerReceiver(context, receiver, filter, ContextCompat.RECEIVER_EXPORTED)
        registered = true
    }

    fun stop() {
        if (!registered) return
        runCatching { context.unregisterReceiver(receiver) }
        registered = false
    }

    private fun onVolume(stream: Int, value: Int, prev: Int) {
        if (stream < 0 || stream == AudioManager.STREAM_VOICE_CALL) return
        if (audio.mode == AudioManager.MODE_IN_CALL || audio.mode == AudioManager.MODE_IN_COMMUNICATION) return
        val now = SystemClock.elapsedRealtime()
        when (val action = detector.onRise(stream, value, prev, now)) {
            is VolumeHoldDetector.Action.Restore -> restore(action.stream, action.level)
            is VolumeHoldDetector.Action.Held -> {
                action.restore.forEach { (s, level) -> restore(s, level) }
                // Holding the key on vibrate can also switch the phone to ring; undo that too.
                if (now - ringerChangedAt <= VolumeHoldDetector.WINDOW_MS && audio.ringerMode != ringerBefore) {
                    runCatching { audio.ringerMode = ringerBefore }
                }
                onLongPress()
            }
            VolumeHoldDetector.Action.None -> Unit
        }
    }

    private fun restore(stream: Int, level: Int) {
        runCatching { audio.setStreamVolume(stream, level, 0) }
    }

    companion object {
        // Hidden but long-standing Android broadcast sent on every volume change.
        private const val VOLUME_CHANGED = "android.media.VOLUME_CHANGED_ACTION"
        private const val EXTRA_STREAM = "android.media.EXTRA_VOLUME_STREAM_TYPE"
        private const val EXTRA_VALUE = "android.media.EXTRA_VOLUME_STREAM_VALUE"
        private const val EXTRA_PREV_VALUE = "android.media.EXTRA_PREV_VOLUME_STREAM_VALUE"
    }
}
