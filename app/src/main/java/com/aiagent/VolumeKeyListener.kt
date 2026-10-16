package com.aiagent

import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioManager
import android.media.session.MediaSessionManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.KeyEvent
import org.lsposed.hiddenapibypass.HiddenApiBypass
import java.lang.reflect.Proxy

/**
 * Sees the volume keys themselves, without the Accessibility service, through Android's own
 * "volume key long-press listener" (a hidden system API made for exactly this).
 *
 * While it is set, Android keeps handling short presses as usual (the volume changes when the key
 * is released) and hands long presses to Gota instead: holding Volume Up calls Gota, holding
 * Volume Down keeps lowering the volume as always. Apps on screen that use the keys themselves,
 * like a camera's shutter, still get them first.
 *
 * It needs a permission that only a computer can grant, once (it survives reboots):
 *     adb shell pm grant com.aiagent android.permission.SET_VOLUME_KEY_LONG_PRESS_LISTENER
 */
class VolumeKeyListener(private val context: Context, private val onLongPress: () -> Unit) {

    private val audio = context.getSystemService(AudioManager::class.java)
    private val sessions = context.getSystemService(MediaSessionManager::class.java)
    private var calledForDownTime = -1L
    private var registered = false

    /** Returns false when the permission is missing or this phone doesn't allow it. */
    fun start(): Boolean {
        if (registered) return true
        if (!isAllowed(context)) return false
        return try {
            val listenerType = Class.forName("android.media.session.MediaSessionManager\$OnVolumeKeyLongPressListener")
            val listener = Proxy.newProxyInstance(listenerType.classLoader, arrayOf(listenerType)) { proxy, method, args ->
                when (method.name) {
                    "onVolumeKeyLongPress" -> { onKey(args[0] as KeyEvent); null }
                    "equals" -> proxy === args?.get(0)
                    "hashCode" -> System.identityHashCode(proxy)
                    "toString" -> "GotaVolumeKeyListener"
                    else -> null
                }
            }
            setListener(listenerType, listener)
            registered = true
            true
        } catch (e: Throwable) {
            Log.w(TAG, "Could not set the volume key long-press listener", e)
            false
        }
    }

    fun stop() {
        if (!registered) return
        runCatching {
            val listenerType = Class.forName("android.media.session.MediaSessionManager\$OnVolumeKeyLongPressListener")
            setListener(listenerType, null)
        }
        registered = false
    }

    private fun setListener(listenerType: Class<*>, listener: Any?) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            HiddenApiBypass.addHiddenApiExemptions("Landroid/media/session/MediaSessionManager;")
        }
        MediaSessionManager::class.java
            .getMethod("setOnVolumeKeyLongPressListener", listenerType, Handler::class.java)
            .invoke(sessions, listener, Handler(Looper.getMainLooper()))
    }

    /** Android sends here every event of a long press: the first down, the repeats and the up. */
    private fun onKey(event: KeyEvent) {
        if (event.action != KeyEvent.ACTION_DOWN) return
        when (event.keyCode) {
            KeyEvent.KEYCODE_VOLUME_UP -> if (event.downTime != calledForDownTime) {
                calledForDownTime = event.downTime // once per press, however long it is held
                onLongPress()
            }
            // Holding Volume Down still lowers the volume step by step, like before.
            KeyEvent.KEYCODE_VOLUME_DOWN -> audio.adjustSuggestedStreamVolume(
                AudioManager.ADJUST_LOWER, AudioManager.USE_DEFAULT_STREAM_TYPE, AudioManager.FLAG_SHOW_UI
            )
        }
    }

    companion object {
        private const val TAG = "VolumeKeyListener"
        const val PERMISSION = "android.permission.SET_VOLUME_KEY_LONG_PRESS_LISTENER"

        fun isAllowed(context: Context) =
            context.checkSelfPermission(PERMISSION) == PackageManager.PERMISSION_GRANTED
    }
}
