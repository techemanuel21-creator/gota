package com.aiagent

import android.Manifest
import android.animation.ObjectAnimator
import android.animation.ValueAnimator
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.drawable.AnimationDrawable
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.text.method.ScrollingMovementMethod
import android.view.View
import android.view.WindowManager
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.addCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.aiagent.local.AgentLoop
import com.aiagent.local.AppCatalog
import com.aiagent.local.Chat
import com.aiagent.local.ChatMessage
import com.aiagent.local.ChatStore
import com.aiagent.local.GemmaAgent
import com.aiagent.local.Speaker
import com.aiagent.local.UserProfile
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * A "phone call" with Gota: he answers, listens, thinks (reading his book), answers out loud and
 * listens again, until you hang up. Everything said is kept as text in its own conversation (no
 * audio is stored), and a one-line summary is saved so he remembers the call later.
 */
class CallActivity : AppCompatActivity() {

    private enum class Mood { IDLE, LISTEN, THINK, PAINT, TALK }

    private lateinit var cat: ImageView
    private lateinit var pulse: View
    private lateinit var status: TextView
    private lateinit var caption: TextView
    private lateinit var muteButton: TextView
    private lateinit var muteLabel: TextView

    private lateinit var speaker: Speaker
    private lateinit var chatId: String
    private var recognizer: SpeechRecognizer? = null
    private val handler = Handler(Looper.getMainLooper())

    private var startedAt = 0L
    private var connected = false
    private var ended = false
    private var muted = false
    private var onHold = false
    private var listening = false
    private var thinking = false
    private var speaking = false
    private var silentTurns = 0
    private var heardSoFar = ""
    private var errorsInRow = 0
    private var turn = 0 // bumped on every new step so late callbacks from an interrupted one are ignored
    private var wakePaused = false
    private var bob: ObjectAnimator? = null
    private var ringPulse: ValueAnimator? = null

    private val sir get() = UserProfile.shortAddress(this)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_call)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        cat = findViewById(R.id.callCat)
        pulse = findViewById(R.id.callPulse)
        status = findViewById(R.id.callStatus)
        caption = findViewById<TextView>(R.id.callCaption).also { it.movementMethod = ScrollingMovementMethod() }
        muteButton = findViewById(R.id.callMute)
        muteLabel = findViewById(R.id.callMuteLabel)

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            Toast.makeText(this, "Preciso do microfone para a ligação.", Toast.LENGTH_LONG).show()
            finish()
            return
        }

        speaker = Speaker(this)
        val title = "📞 Ligação · " + SimpleDateFormat("dd/MM HH:mm", Locale("pt", "BR")).format(Date())
        chatId = ChatStore.create(this, title).id
        VoiceService.instance?.let {
            it.pauseWake() // "Hey Gota" mode would otherwise keep the microphone busy
            wakePaused = true
        }

        cat.setOnClickListener { interrupt() }
        muteButton.setOnClickListener { toggleMute() }
        findViewById<View>(R.id.callHangup).setOnClickListener { hangUp() }
        onBackPressedDispatcher.addCallback(this) { hangUp() }

        setMood(Mood.IDLE)
        startBobbing()
        ring()
    }

    // ---------- call flow ----------

    private fun ring() {
        status.text = "Chamando…"
        ringPulse = ValueAnimator.ofFloat(0.85f, 1.08f).apply {
            duration = 650
            repeatMode = ValueAnimator.REVERSE
            repeatCount = ValueAnimator.INFINITE
            addUpdateListener { setPulse(it.animatedValue as Float) }
            start()
        }
        tone(ToneGenerator.TONE_SUP_RINGTONE, 1100, 45)
        handler.postDelayed({ if (!ended) answer() }, 1300)
    }

    private fun answer() {
        ringPulse?.cancel()
        setPulse(1f)
        connected = true
        startedAt = System.currentTimeMillis()
        tick()
        val hello = "Alô, ${UserProfile.address(this)}. Às suas ordens."
        ChatStore.append(this, chatId, ChatMessage("gota", hello))
        say(hello) { listen() }
    }

    private fun tick() {
        if (ended) return
        val seconds = (System.currentTimeMillis() - startedAt) / 1000
        status.text = String.format(Locale.US, "%02d:%02d", seconds / 60, seconds % 60) + if (muted) " · mudo" else ""
        handler.postDelayed({ tick() }, 1000)
    }

    private fun say(text: String, then: () -> Unit) {
        val step = ++turn
        speaking = true
        setMood(Mood.TALK)
        showCaption(text, fromUser = false)
        speaker.speak(text) {
            runOnUiThread {
                if (step != turn || ended) return@runOnUiThread
                speaking = false
                then()
            }
        }
    }

    private fun listen() {
        if (ended || muted || onHold || thinking || speaking) return
        // A fresh recognizer for every turn: some phones return empty results when one is reused.
        destroyRecognizer()
        val rec = SpeechRecognizer.createSpeechRecognizer(this).also {
            it.setRecognitionListener(listener)
            recognizer = it
        }
        heardSoFar = ""
        listening = true
        setMood(Mood.LISTEN)
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE, "pt-BR")
            .putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            .putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        runCatching { rec.startListening(intent) }.onFailure { retryListen(600) }
    }

    private fun stopListening() {
        listening = false
        destroyRecognizer()
        setPulse(1f)
    }

    private fun destroyRecognizer() {
        runCatching { recognizer?.destroy() }
        recognizer = null
    }

    /** What was heard: the final result, or — when the phone gives back an empty one — the last partial text. */
    private fun finishHearing(finalText: String?) {
        val text = finalText?.takeIf { it.isNotBlank() } ?: heardSoFar
        heardSoFar = ""
        if (text.isBlank()) onSilence() else onHeard(text)
    }

    private fun retryListen(delayMs: Long) {
        handler.postDelayed({ listen() }, delayMs)
    }

    private val listener = object : RecognitionListener {
        override fun onResults(results: Bundle?) {
            if (!listening) return
            listening = false
            setPulse(1f)
            finishHearing(results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull())
        }

        override fun onPartialResults(partialResults: Bundle?) {
            partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()
                ?.takeIf { it.isNotBlank() }?.let {
                    heardSoFar = it
                    showCaption("“$it”", fromUser = true)
                }
        }

        override fun onError(error: Int) {
            if (!listening) return
            listening = false
            setPulse(1f)
            // Words already showed up on screen: answer them, whatever the recognizer says now.
            if (heardSoFar.isNotBlank()) {
                finishHearing(null)
                return
            }
            when (error) {
                SpeechRecognizer.ERROR_NO_MATCH, SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> onSilence()
                SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS ->
                    say("Perdão, $sir, preciso da permissão do microfone para conversar.") { hangUp() }
                SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> {
                    destroyRecognizer()
                    retryListen(400)
                }
                else -> {
                    if (++errorsInRow >= 4) {
                        say("Perdão, $sir, estou com dificuldade para ouvir. Vou desligar; é só me ligar de novo.") { hangUp() }
                    } else {
                        retryListen(600)
                    }
                }
            }
        }

        override fun onRmsChanged(rmsdB: Float) {
            if (listening) setPulse(1f + ((rmsdB + 2f) / 12f).coerceIn(0f, 1f) * 0.16f)
        }

        override fun onReadyForSpeech(params: Bundle?) {}
        override fun onBeginningOfSpeech() {}
        override fun onBufferReceived(buffer: ByteArray?) {}
        override fun onEndOfSpeech() {}
        override fun onEvent(eventType: Int, params: Bundle?) {}
    }

    /** Nobody spoke: keep listening, check in after a while, and hang up if the line stays quiet. */
    private fun onSilence() {
        silentTurns++
        when {
            silentTurns >= 6 -> say("Vou desligar, então, $sir. Quando precisar, é só me ligar.") { hangUp() }
            silentTurns == 3 -> say("Ainda está aí, $sir?") { listen() }
            else -> retryListen(200)
        }
    }

    private fun onHeard(raw: String) {
        silentTurns = 0
        errorsInRow = 0
        val text = AgentLoop.stripWakeWord(raw)
        if (isGoodbye(text)) {
            ChatStore.append(this, chatId, ChatMessage("user", text))
            val bye = "Até logo, $sir. Foi um prazer."
            ChatStore.append(this, chatId, ChatMessage("gota", bye))
            say(bye) { hangUp() }
            return
        }
        think(text)
    }

    private fun think(text: String) {
        val step = ++turn
        thinking = true
        setMood(Mood.THINK)
        showCaption("“$text”", fromUser = true)
        val history = ChatStore.get(this, chatId)?.messages?.toList().orEmpty()
        ChatStore.append(this, chatId, ChatMessage("user", text))

        lifecycleScope.launch {
            var replied = false
            AgentLoop(
                context = applicationContext,
                chatId = chatId,
                history = history,
                spoken = true,
                onStatus = { },
                onPhase = { phase ->
                    if (step == turn && !ended) when (phase) {
                        AgentLoop.Phase.SEARCHING -> speaker.speak("Um momento, $sir. Vou pesquisar.")
                        AgentLoop.Phase.DRAWING -> setMood(Mood.PAINT)
                        else -> {}
                    }
                },
                onReply = { reply, image ->
                    replied = true
                    ChatStore.append(applicationContext, chatId, ChatMessage("gota", reply, image))
                    if (step == turn && !ended) {
                        thinking = false
                        say(reply) { listen() }
                    }
                }
            ).run(text)
            if (!replied && step == turn && !ended) {
                thinking = false
                listen()
            }
        }
    }

    private fun isGoodbye(text: String): Boolean {
        val n = AppCatalog.normalize(text)
        if (n.length > 40) return false
        return GOODBYES.any { Regex("\\b$it\\b").containsMatchIn(n) }
    }

    // ---------- buttons ----------

    /** Tapping the cat while he talks cuts him off and hands the word back to you. */
    private fun interrupt() {
        if (!speaking || ended) return
        turn++
        speaker.stop()
        speaking = false
        listen()
    }

    private fun toggleMute() {
        muted = !muted
        muteButton.isSelected = muted
        muteLabel.text = if (muted) "Mudo ligado" else "Mudo"
        if (muted) {
            stopListening()
            if (!speaking && !thinking) {
                setMood(Mood.IDLE)
                showCaption("Microfone mudo. Toque no 🎙️ para voltar a falar.", fromUser = false)
            }
        } else {
            listen()
        }
    }

    private fun hangUp() {
        if (ended) return
        ended = true
        turn++
        handler.removeCallbacksAndMessages(null)
        ringPulse?.cancel()
        bob?.cancel()
        destroyRecognizer()
        if (::speaker.isInitialized) speaker.shutdown()
        tone(ToneGenerator.TONE_PROP_PROMPT, 250, 40)
        if (wakePaused) VoiceService.instance?.resumeWake()

        if (::chatId.isInitialized) {
            val chat = ChatStore.get(this, chatId)
            if (chat == null || chat.messages.none { it.role == "user" }) {
                ChatStore.delete(this, chatId) // nothing was said: don't keep an empty call around
            } else {
                getSharedPreferences("gota", MODE_PRIVATE).edit().putString("current_chat", chatId).apply()
                rememberCall(applicationContext, chat)
            }
        }
        finish()
    }

    override fun onStop() {
        super.onStop()
        // App hidden or screen off: put the call on hold instead of listening in the background.
        if (!ended && !isFinishing) {
            onHold = true
            stopListening()
        }
    }

    override fun onStart() {
        super.onStart()
        if (onHold) {
            onHold = false
            if (connected) listen()
        }
    }

    override fun onDestroy() {
        if (!ended) hangUp()
        super.onDestroy()
    }

    // ---------- the cat ----------

    private fun setMood(mood: Mood) {
        // On a call he holds an old rotary telephone to his cheek (except while painting a picture).
        val res = when (mood) {
            Mood.IDLE -> R.drawable.anim_phone_idle
            Mood.LISTEN -> R.drawable.anim_phone_listen
            Mood.THINK -> R.drawable.anim_phone_think
            Mood.PAINT -> R.drawable.anim_cat_paint
            Mood.TALK -> R.drawable.anim_phone_talk
        }
        if (cat.tag == res) return
        cat.tag = res
        cat.setImageResource(res)
        (cat.drawable as? AnimationDrawable)?.start()
    }

    private fun tone(type: Int, durationMs: Int, volume: Int) {
        runCatching {
            val generator = ToneGenerator(AudioManager.STREAM_MUSIC, volume)
            generator.startTone(type, durationMs)
            Handler(Looper.getMainLooper()).postDelayed({ generator.release() }, durationMs + 200L)
        }
    }

    private fun setPulse(scale: Float) {
        pulse.scaleX = scale
        pulse.scaleY = scale
    }

    private fun startBobbing() {
        val lift = -6f * resources.displayMetrics.density
        bob = ObjectAnimator.ofFloat(cat, View.TRANSLATION_Y, 0f, lift).apply {
            duration = 900
            repeatMode = ValueAnimator.REVERSE
            repeatCount = ValueAnimator.INFINITE
            start()
        }
    }

    private fun showCaption(text: String, fromUser: Boolean) {
        caption.text = text
        caption.setTextColor(ContextCompat.getColor(this, if (fromUser) R.color.accent else R.color.text_primary))
        caption.scrollTo(0, 0)
    }

    companion object {
        private val GOODBYES = listOf(
            "tchau", "ate logo", "ate mais", "ate depois", "pode desligar", "desliga", "desligar",
            "encerra", "encerrar", "tenho que ir", "preciso ir", "era so isso", "so isso obrigado"
        )

        private val memoryScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

        /** Saves one sentence about the call so Gota remembers it in future conversations. */
        private fun rememberCall(context: Context, chat: Chat) {
            val agent = GemmaAgent.get() ?: return
            val date = SimpleDateFormat("dd/MM", Locale("pt", "BR")).format(Date(chat.updatedAt))
            val transcript = chat.messages.joinToString("\n") {
                (if (it.role == "user") "Dono: " else "Gota: ") + it.text.take(300)
            }.takeLast(3500)
            memoryScope.launch {
                val raw = runCatching {
                    agent.oneShot(
                        "Você resume ligações entre o Gota (um mordomo) e o dono dele. Em português do Brasil, escreva UMA " +
                            "frase curta (até 30 palavras) com os assuntos e fatos importantes da ligação, para o Gota lembrar " +
                            "depois. Comece com \"Em $date\". Responda só com a frase, sem JSON.",
                        transcript
                    )
                }.getOrNull() ?: return@launch
                val note = if (raw.trim().startsWith("{")) {
                    runCatching { JSONObject(raw.trim()).optString("text") }.getOrNull().orEmpty()
                } else raw
                UserProfile.addCallNote(context, note.trim().trim('"'))
            }
        }
    }
}
