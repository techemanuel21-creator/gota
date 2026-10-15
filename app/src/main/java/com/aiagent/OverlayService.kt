package com.aiagent

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.graphics.PixelFormat
import android.os.Build
import android.os.IBinder
import android.view.Gravity
import android.view.LayoutInflater
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.EditText
import android.widget.TextView
import androidx.core.app.NotificationCompat
import com.aiagent.local.AgentLoop
import com.aiagent.local.ChatMessage
import com.aiagent.local.ChatStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlin.math.abs

class OverlayService : Service() {

    private lateinit var windowManager: WindowManager
    private var bubbleView: View? = null
    private var panelView: View? = null
    private val scope = CoroutineScope(Dispatchers.Main + Job())

    override fun onCreate() {
        super.onCreate()
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
        startForegroundNotification()
        showBubble()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun startForegroundNotification() {
        val channelId = "agent_overlay"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(channelId, "Bolha do Gota", NotificationManager.IMPORTANCE_LOW)
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
        val notification = NotificationCompat.Builder(this, channelId)
            .setContentTitle("Gota está na tela")
            .setContentText("Toque na bolha para falar com o Gota")
            .setSmallIcon(R.drawable.ic_gota)
            .build()
        startForeground(1, notification)
    }

    private fun showBubble() {
        val inflater = LayoutInflater.from(this)
        val view = inflater.inflate(R.layout.overlay_bubble, null)
        bubbleView = view

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        )
        params.gravity = Gravity.TOP or Gravity.START
        params.x = 0
        params.y = 300

        var lastX = 0
        var lastY = 0
        var initialX = 0
        var initialY = 0
        var moved = false

        view.setOnTouchListener { v, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    lastX = event.rawX.toInt()
                    lastY = event.rawY.toInt()
                    initialX = params.x
                    initialY = params.y
                    moved = false
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = event.rawX.toInt() - lastX
                    val dy = event.rawY.toInt() - lastY
                    if (abs(dx) > 10 || abs(dy) > 10) moved = true
                    params.x = initialX + dx
                    params.y = initialY + dy
                    windowManager.updateViewLayout(view, params)
                    true
                }
                MotionEvent.ACTION_UP -> {
                    if (!moved) togglePanel()
                    true
                }
                else -> false
            }
        }

        windowManager.addView(view, params)
    }

    private fun togglePanel() {
        if (panelView != null) {
            hidePanel()
            return
        }

        val inflater = LayoutInflater.from(this)
        val view = inflater.inflate(R.layout.overlay_panel, null)
        panelView = view

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        )
        params.gravity = Gravity.TOP or Gravity.START
        params.x = 0
        params.y = 400

        val panelLog = view.findViewById<TextView>(R.id.panelLog)
        val panelInput = view.findViewById<EditText>(R.id.panelInput)
        val panelSend = view.findViewById<TextView>(R.id.panelSend)
        val panelClose = view.findViewById<TextView>(R.id.panelClose)

        var baseLog = ""
        fun commitFinal(msg: String) {
            baseLog += (if (baseLog.isEmpty()) "" else "\n") + msg
            panelLog.text = baseLog
        }
        fun setStatus(msg: String) {
            panelLog.text = baseLog + (if (baseLog.isEmpty()) "" else "\n") + msg
        }

        panelSend.setOnClickListener {
            val goal = panelInput.text.toString().trim()
            if (goal.isEmpty()) return@setOnClickListener
            panelInput.setText("")
            commitFinal("Você: $goal")
            setStatus("Pensando...")
            val history = ChatStore.voiceChat(this).messages.toList()
            ChatStore.append(this, ChatStore.VOICE_CHAT_ID, ChatMessage("user", goal))
            scope.launch {
                AgentLoop(
                    context = applicationContext,
                    chatId = ChatStore.VOICE_CHAT_ID,
                    history = history,
                    onStatus = { msg -> setStatus(msg) },
                    onReply = { msg, image ->
                        ChatStore.append(applicationContext, ChatStore.VOICE_CHAT_ID, ChatMessage("gota", msg, image))
                        commitFinal("Gota: $msg")
                    }
                ).run(goal)
            }
        }

        panelClose.setOnClickListener { hidePanel() }

        windowManager.addView(view, params)
    }

    private fun hidePanel() {
        panelView?.let { runCatching { windowManager.removeView(it) } }
        panelView = null
    }

    override fun onDestroy() {
        super.onDestroy()
        bubbleView?.let { runCatching { windowManager.removeView(it) } }
        hidePanel()
        scope.coroutineContext[Job]?.cancel()
    }
}
