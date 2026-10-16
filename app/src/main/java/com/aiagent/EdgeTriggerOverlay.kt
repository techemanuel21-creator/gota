package com.aiagent

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.PixelFormat
import android.graphics.Rect
import android.os.Build
import android.provider.Settings
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewTreeObserver
import android.view.WindowManager
import kotlin.math.abs

/**
 * Lets the person call Gota by swiping inward from the left edge of the screen, over any app and
 * with Gota closed — without the Accessibility service. It's a thin handle (a floating window, the
 * same "draw over other apps" permission the cat already uses) near the lower-left, where the user
 * pointed. A plain tap elsewhere is never touched; only a deliberate edge swipe triggers it.
 *
 * While a keyboard is on screen the handle hides itself, so it never eats a key press. That is
 * detected with a second, invisible, full-screen window whose visible area shrinks when the
 * keyboard shows (no Accessibility, no special permission).
 */
class EdgeTriggerOverlay(private val context: Context, private val onTrigger: () -> Unit) {

    private val wm = context.getSystemService(WindowManager::class.java)
    private val density = context.resources.displayMetrics.density
    private fun dp(value: Float) = (value * density).toInt()

    private var handle: View? = null
    private var keyboardProbe: View? = null
    private var hiddenForKeyboard = false
    private var added = false

    fun show() {
        if (added || !Settings.canDrawOverlays(context)) return
        added = true
        addHandle()
        addKeyboardProbe()
    }

    fun hide() {
        added = false
        handle?.let { runCatching { wm.removeView(it) } }
        keyboardProbe?.let { runCatching { wm.removeView(it) } }
        handle = null
        keyboardProbe = null
    }

    // ---------- the edge handle ----------

    @SuppressLint("ClickableViewAccessibility")
    private fun addHandle() {
        val view = View(context).apply {
            setBackgroundResource(R.drawable.bg_edge_handle)
            alpha = 0.55f
        }
        val params = WindowManager.LayoutParams(
            dp(TOUCH_WIDTH_DP), dp(HEIGHT_DP),
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.START or Gravity.BOTTOM
            x = 0
            y = dp(BOTTOM_MARGIN_DP)
        }

        var startX = 0f
        var startY = 0f
        var swiping = false
        view.setOnTouchListener { v, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    startX = event.rawX
                    startY = event.rawY
                    swiping = false
                    v.animate().alpha(0.9f).setDuration(120).start()
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = event.rawX - startX
                    val dy = event.rawY - startY
                    if (!swiping && dx > dp(SWIPE_DISTANCE_DP) && dx > abs(dy)) {
                        swiping = true
                        onTrigger()
                    }
                    true
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    v.animate().alpha(0.55f).setDuration(200).start()
                    true
                }
                else -> false
            }
        }
        if (runCatching { wm.addView(view, params) }.isSuccess) handle = view
    }

    private fun setHandleVisible(visible: Boolean) {
        val view = handle ?: return
        val params = view.layoutParams as WindowManager.LayoutParams
        // Width 0 makes it untouchable too, so a key press underneath goes straight to the keyboard.
        val wanted = if (visible) dp(TOUCH_WIDTH_DP) else 0
        if (params.width == wanted) return
        params.width = wanted
        view.visibility = if (visible) View.VISIBLE else View.GONE
        runCatching { wm.updateViewLayout(view, params) }
    }

    // ---------- keyboard detection ----------

    private fun addKeyboardProbe() {
        val probe = View(context)
        val params = WindowManager.LayoutParams(
            dp(1f), WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT
        ).apply { gravity = Gravity.START or Gravity.BOTTOM }

        val listener = ViewTreeObserver.OnGlobalLayoutListener {
            val probeView = keyboardProbe ?: return@OnGlobalLayoutListener
            val visible = Rect().also { probeView.getWindowVisibleDisplayFrame(it) }
            val full = probeView.rootView.height
            // When a keyboard (or any big system panel) is up, the visible frame shrinks a lot.
            val keyboardUp = full > 0 && (full - visible.bottom) > full * KEYBOARD_FRACTION
            if (keyboardUp != hiddenForKeyboard) {
                hiddenForKeyboard = keyboardUp
                setHandleVisible(!keyboardUp)
            }
        }
        if (runCatching { wm.addView(probe, params) }.isSuccess) {
            keyboardProbe = probe
            probe.viewTreeObserver.addOnGlobalLayoutListener(listener)
        }
    }

    companion object {
        private const val TOUCH_WIDTH_DP = 14f
        private const val HEIGHT_DP = 150f
        private const val BOTTOM_MARGIN_DP = 230f
        private const val SWIPE_DISTANCE_DP = 36f
        private const val KEYBOARD_FRACTION = 0.18f
    }
}
