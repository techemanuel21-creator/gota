package com.aiagent

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.PixelFormat
import android.graphics.Rect
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.widget.FrameLayout
import kotlin.math.abs

/**
 * Lets the person call Gota by swiping inward from the left edge of the screen, over any app and
 * with Gota closed — without the Accessibility service. It's a small handle (a floating window,
 * the same "draw over other apps" permission the cat already uses) near the lower-left by default.
 *
 * You can drag the handle up or down to move it; the position is saved. When the keyboard opens,
 * if the handle would be behind it, the handle rises to just above the keyboard and drops back
 * when the keyboard closes.
 *
 * The visible bar is thin and short, but the window that catches the touch is a bit wider so the
 * swipe is easy to start from the edge.
 */
class EdgeTriggerOverlay(private val context: Context, private val onTrigger: () -> Unit) {

    private val wm = context.getSystemService(android.view.WindowManager::class.java)
    private val prefs = context.getSharedPreferences("gota", Context.MODE_PRIVATE)
    private val density = context.resources.displayMetrics.density
    private val screenH = context.resources.displayMetrics.heightPixels
    private fun dp(value: Float) = (value * density).toInt()

    private var container: View? = null
    private var params: android.view.WindowManager.LayoutParams? = null
    private val handler = Handler(Looper.getMainLooper())

    /** Saved distance from the bottom of the screen to the bottom of the handle. */
    private var savedBottom = prefs.getInt(PREF_Y, (screenH * DEFAULT_FROM_BOTTOM).toInt())
    private var keyboardHeight = 0

    fun show() {
        if (container != null || !Settings.canDrawOverlays(context)) return
        addHandle()
        handler.post(keyboardWatcher)
    }

    fun hide() {
        handler.removeCallbacks(keyboardWatcher)
        container?.let { runCatching { wm.removeView(it) } }
        container = null
        params = null
    }

    @SuppressLint("ClickableViewAccessibility")
    private fun addHandle() {
        // Transparent touch area, with a small coloured bar drawn inside it.
        val frame = FrameLayout(context)
        val bar = View(context).apply {
            setBackgroundResource(R.drawable.bg_edge_handle)
            alpha = 0.5f
        }
        frame.addView(bar, FrameLayout.LayoutParams(dp(BAR_WIDTH_DP), dp(BAR_HEIGHT_DP)).apply {
            gravity = Gravity.START or Gravity.CENTER_VERTICAL
        })

        val lp = android.view.WindowManager.LayoutParams(
            dp(TOUCH_WIDTH_DP), dp(TOUCH_HEIGHT_DP),
            android.view.WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            android.view.WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                android.view.WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS or
                android.view.WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.START or Gravity.BOTTOM
            x = 0
            y = savedBottom
        }

        var startX = 0f
        var startY = 0f
        var startBottom = 0
        var mode = Mode.UNDECIDED
        frame.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    startX = event.rawX
                    startY = event.rawY
                    startBottom = lp.y
                    mode = Mode.UNDECIDED
                    bar.animate().alpha(0.85f).setDuration(120).start()
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = event.rawX - startX
                    val dy = event.rawY - startY
                    if (mode == Mode.UNDECIDED && (abs(dx) > dp(10f) || abs(dy) > dp(10f))) {
                        mode = if (abs(dy) > abs(dx)) Mode.DRAG else Mode.SWIPE
                    }
                    when (mode) {
                        Mode.SWIPE -> if (dx > dp(SWIPE_DISTANCE_DP) && dx > abs(dy)) {
                            mode = Mode.DONE
                            onTrigger()
                        }
                        Mode.DRAG -> {
                            // Finger up (rawY smaller) raises the handle (bigger bottom margin).
                            val newBottom = (startBottom + (startY - event.rawY)).toInt()
                            savedBottom = newBottom.coerceIn(dp(16f), screenH - dp(TOUCH_HEIGHT_DP) - dp(48f))
                            applyPosition(animated = false)
                        }
                        else -> {}
                    }
                    true
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    bar.animate().alpha(0.5f).setDuration(200).start()
                    if (mode == Mode.DRAG) prefs.edit().putInt(PREF_Y, savedBottom).apply()
                    true
                }
                else -> false
            }
        }

        if (runCatching { wm.addView(frame, lp) }.isSuccess) {
            container = frame
            params = lp
        }
    }

    /** Puts the handle at its saved spot, or just above the keyboard when one is covering it. */
    private fun applyPosition(animated: Boolean) {
        val lp = params ?: return
        val view = container ?: return
        val target = if (keyboardHeight > 0 && savedBottom < keyboardHeight + dp(8f)) {
            keyboardHeight + dp(8f)
        } else {
            savedBottom
        }
        if (lp.y == target) return
        lp.y = target
        runCatching { wm.updateViewLayout(view, lp) }
    }

    // ---------- keyboard watching ----------

    // An overlay isn't told about another app's keyboard, so we poll the visible screen area:
    // when a keyboard is up, the bottom of that area rises by the keyboard's height.
    private val keyboardWatcher = object : Runnable {
        override fun run() {
            val view = container
            if (view != null) {
                val visible = Rect().also { view.getWindowVisibleDisplayFrame(it) }
                val full = view.rootView.height.takeIf { it > 0 } ?: screenH
                val kb = (full - visible.bottom).coerceAtLeast(0)
                val newHeight = if (kb > full * KEYBOARD_FRACTION) kb else 0
                if (newHeight != keyboardHeight) {
                    keyboardHeight = newHeight
                    applyPosition(animated = true)
                }
                handler.postDelayed(this, POLL_MS)
            }
        }
    }

    private enum class Mode { UNDECIDED, SWIPE, DRAG, DONE }

    companion object {
        private const val PREF_Y = "edge_handle_y"
        private const val DEFAULT_FROM_BOTTOM = 0.28f // near the lower app row the user pointed at
        private const val TOUCH_WIDTH_DP = 16f
        private const val TOUCH_HEIGHT_DP = 84f
        private const val BAR_WIDTH_DP = 5f
        private const val BAR_HEIGHT_DP = 46f
        private const val SWIPE_DISTANCE_DP = 36f
        private const val KEYBOARD_FRACTION = 0.15f
        private const val POLL_MS = 400L
    }
}
