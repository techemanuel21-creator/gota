package com.aiagent

import android.accessibilityservice.AccessibilityService
import android.media.AudioManager
import android.os.Handler
import android.os.Looper
import android.view.KeyEvent
import android.view.accessibility.AccessibilityEvent

/**
 * Used for exactly one thing: noticing a long press of Volume Up, even with the screen off or the
 * app closed, so it can call Gota. This is the only Android capability that lets an app react to a
 * hardware key globally; it does not read or touch anything else on the screen.
 */
class AgentAccessibilityService : AccessibilityService() {

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
    }

    override fun onDestroy() {
        super.onDestroy()
        instance = null
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {}

    override fun onInterrupt() {}

    private val handler = Handler(Looper.getMainLooper())
    private var longPressFired = false
    private val volumeLongPress = Runnable {
        longPressFired = true
        VoiceService.trigger(this)
    }

    /**
     * Holding Volume Up for half a second calls Gota. A quick tap still raises the volume
     * (we re-apply it ourselves, since the key press is intercepted to measure how long it is).
     */
    override fun onKeyEvent(event: KeyEvent): Boolean {
        if (event.keyCode != KeyEvent.KEYCODE_VOLUME_UP || !VoiceService.running) return false
        when (event.action) {
            KeyEvent.ACTION_DOWN -> if (event.repeatCount == 0) {
                longPressFired = false
                handler.postDelayed(volumeLongPress, LONG_PRESS_MS)
            }
            KeyEvent.ACTION_UP -> {
                handler.removeCallbacks(volumeLongPress)
                if (!longPressFired) {
                    getSystemService(AudioManager::class.java).adjustSuggestedStreamVolume(
                        AudioManager.ADJUST_RAISE, AudioManager.USE_DEFAULT_STREAM_TYPE, AudioManager.FLAG_SHOW_UI
                    )
                }
            }
        }
        return true
    }

    companion object {
        private const val LONG_PRESS_MS = 450L

        @Volatile
        var instance: AgentAccessibilityService? = null
            private set

        fun isRunning(): Boolean = instance != null
    }
}
