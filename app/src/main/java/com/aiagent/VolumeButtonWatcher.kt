package com.aiagent

import android.content.Context
import android.media.AudioManager
import android.media.VolumeProvider
import android.media.session.MediaSession
import android.media.session.PlaybackState
import android.os.Handler
import android.os.Looper

/**
 * Notices a long press of Volume Up without the Accessibility service. Gota keeps a silent media
 * session with its own volume control, so Android hands it the volume keys (also with the screen
 * off) whenever no other app is playing audio. Nothing is ever played.
 *
 * Short presses are passed on to the real volume, so the buttons keep working as usual. While
 * music or a video plays in another app, the keys go to that app instead (and Gota can't be
 * called this way until it stops); during phone calls the buttons only change the call volume.
 */
class VolumeButtonWatcher(context: Context, private val onLongPress: () -> Unit) {

    private val audio = context.getSystemService(AudioManager::class.java)
    private val handler = Handler(Looper.getMainLooper())
    private var session: MediaSession? = MediaSession(context, "GotaVolumeButton")
    private var pressing = false
    private var fired = false

    private val longPress = Runnable {
        fired = true
        onLongPress()
    }

    // Safety net in case a release never arrives: forget the press instead of staying stuck.
    private val giveUp = Runnable {
        handler.removeCallbacks(longPress)
        pressing = false
    }

    fun start() {
        val s = session ?: return
        // Android sends a +1 when Volume Up goes down (again on key repeat while held), -1 for
        // Volume Down, and 0 when the key is let go.
        s.setPlaybackToRemote(object : VolumeProvider(VOLUME_CONTROL_RELATIVE, 100, 50) {
            override fun onAdjustVolume(direction: Int) = handle(direction)
        })
        // The system only routes the volume keys to a session that says it is playing.
        s.setPlaybackState(PlaybackState.Builder().setState(PlaybackState.STATE_PLAYING, 0, 0f).build())
        s.isActive = true
    }

    fun stop() {
        handler.removeCallbacks(longPress)
        handler.removeCallbacks(giveUp)
        session?.let {
            it.isActive = false
            it.release()
        }
        session = null
    }

    private fun handle(direction: Int) {
        val inCall = audio.mode == AudioManager.MODE_IN_CALL || audio.mode == AudioManager.MODE_IN_COMMUNICATION
        when {
            direction < 0 -> adjust(AudioManager.ADJUST_LOWER)
            direction > 0 && inCall -> adjust(AudioManager.ADJUST_RAISE)
            direction > 0 && !pressing -> {
                pressing = true
                fired = false
                handler.postDelayed(longPress, LONG_PRESS_MS)
                handler.postDelayed(giveUp, GIVE_UP_MS)
            }
            direction > 0 -> Unit // key repeat while held
            pressing -> { // released
                handler.removeCallbacks(longPress)
                handler.removeCallbacks(giveUp)
                pressing = false
                if (!fired) adjust(AudioManager.ADJUST_RAISE)
            }
        }
    }

    private fun adjust(direction: Int) {
        audio.adjustSuggestedStreamVolume(direction, AudioManager.USE_DEFAULT_STREAM_TYPE, AudioManager.FLAG_SHOW_UI)
    }

    companion object {
        private const val LONG_PRESS_MS = 450L
        private const val GIVE_UP_MS = 4000L
    }
}
