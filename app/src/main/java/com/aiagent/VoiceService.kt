package com.aiagent

import android.animation.ObjectAnimator
import android.animation.ValueAnimator
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.PixelFormat
import android.graphics.drawable.AnimationDrawable
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Build
import android.os.Bundle
import android.os.IBinder
import android.provider.Settings
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.text.method.ScrollingMovementMethod
import android.view.Gravity
import android.view.LayoutInflater
import android.view.View
import android.view.WindowManager
import android.view.animation.AccelerateInterpolator
import android.view.animation.OvershootInterpolator
import android.widget.ImageView
import android.widget.TextView
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import com.aiagent.local.AgentLoop
import com.aiagent.local.ChatMessage
import com.aiagent.local.ChatStore
import com.aiagent.local.GemmaAgent
import com.aiagent.local.LocationHelper
import com.aiagent.local.ModelDownloader
import com.aiagent.local.Speaker
import com.aiagent.local.UserProfile
import com.aiagent.local.WakeWordModel
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import org.vosk.Model
import org.vosk.Recognizer
import org.vosk.android.RecognitionListener
import org.vosk.android.SpeechService
import java.io.File

/**
 * Gota by voice. Two ways to call it:
 *  - "button" (default, saves battery): hold Volume Up (see [VolumeButtonWatcher]); the
 *    microphone stays off until then.
 *  - "voice": listens offline for "Hey Gota" with Vosk (uses more battery).
 * Then Android's recognizer captures the question, the local model answers, and the cat
 * (sliding up from the bottom of the screen, over any app) speaks the reply.
 */
class VoiceService : Service() {

    private enum class CatMood { IDLE, LISTEN, THINK, READ, PAINT, TALK }

    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private lateinit var speaker: Speaker
    private var voskModel: Model? = null
    private var wakeListener: SpeechService? = null
    private var questionRecognizer: SpeechRecognizer? = null
    private var busy = false
    private var wakePaused = false
    private var catView: View? = null
    private var catText: TextView? = null
    private var catImage: ImageView? = null
    private var bob: ObjectAnimator? = null
    private var conversation = 0
    private var volumeButton: VolumeButtonWatcher? = null

    private val voiceMode get() = getSharedPreferences("gota", MODE_PRIVATE).getString("wake_mode", "button") == "voice"

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        speaker = Speaker(this)
        if (!startInForeground()) {
            stopSelf()
            return
        }
        instance = this
        running = true
        volumeButton = VolumeButtonWatcher(this) { onWakeWord() }.also { it.start() }
        scope.launch { prepare() }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_RELOAD_MODE) scope.launch { applyMode() }
        return START_NOT_STICKY
    }

    private fun startInForeground(): Boolean {
        var types = ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
        if (LocationHelper.hasPermission(this)) types = types or ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION
        return try {
            ServiceCompat.startForeground(this, NOTIFICATION_ID, buildNotification("Preparando o Gota..."), types)
            true
        } catch (e: Exception) {
            false
        }
    }

    private fun buildNotification(text: String): Notification {
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, "Gota por voz", NotificationManager.IMPORTANCE_LOW))
        }
        val openApp = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Gota")
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setSmallIcon(R.drawable.ic_gota)
            .setContentIntent(openApp)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .build()
    }

    private fun updateNotification(text: String) {
        getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, buildNotification(text))
    }

    private fun idleHint() =
        if (voiceMode) "Diga \"Hey Gota\" para me chamar."
        else "Segure o botão de aumentar volume para me chamar."

    private suspend fun prepare() {
        try {
            if (!GemmaAgent.isLoaded()) {
                val modelFile = File(filesDir, ModelDownloader.MODEL_FILE_NAME)
                if (!modelFile.exists()) {
                    updateNotification("Abra o app do Gota para baixar o modelo de IA primeiro.")
                    return
                }
                updateNotification("Carregando a IA...")
                withContext(Dispatchers.IO) { GemmaAgent.load(applicationContext, modelFile.absolutePath) }
            }
            applyMode()
        } catch (e: Exception) {
            updateNotification("Não consegui preparar a voz: ${e.message}")
        }
    }

    /** Turns the always-on wake word on or off according to the chosen mode. */
    private suspend fun applyMode() {
        if (voiceMode) {
            if (voskModel == null) {
                if (!WakeWordModel.isReady(this)) updateNotification("Baixando o reconhecimento de voz (~30 MB)...")
                val dir = withContext(Dispatchers.IO) { WakeWordModel.ensure(this@VoiceService) }
                voskModel = withContext(Dispatchers.IO) { Model(dir.path) }
            }
        } else {
            stopWakeListening()
            voskModel?.close()
            voskModel = null
        }
        startWakeListening()
    }

    private fun startWakeListening() {
        busy = false
        if (!voiceMode || wakePaused) {
            updateNotification(idleHint())
            return
        }
        val model = voskModel ?: return
        stopWakeListening()
        try {
            val recognizer = Recognizer(model, SAMPLE_RATE, WAKE_GRAMMAR)
            wakeListener = SpeechService(recognizer, SAMPLE_RATE).also { it.startListening(wakeCallbacks) }
            updateNotification(idleHint())
        } catch (e: Exception) {
            updateNotification("Microfone indisponível: ${e.message}")
            scope.launch { delay(5000); startWakeListening() }
        }
    }

    private fun stopWakeListening() {
        wakeListener?.stop()
        wakeListener?.shutdown()
        wakeListener = null
    }

    private val wakeCallbacks = object : RecognitionListener {
        override fun onPartialResult(hypothesis: String?) = check(hypothesis, "partial")
        override fun onResult(hypothesis: String?) = check(hypothesis, "text")
        override fun onFinalResult(hypothesis: String?) = check(hypothesis, "text")
        override fun onError(exception: Exception?) {
            stopWakeListening()
            scope.launch { delay(2000); startWakeListening() }
        }
        override fun onTimeout() {
            stopWakeListening()
            startWakeListening()
        }
    }

    private fun check(hypothesis: String?, key: String) {
        if (busy || hypothesis == null) return
        val heard = runCatching { JSONObject(hypothesis).optString(key) }.getOrDefault("")
        if (heard.contains("gota")) onWakeWord()
    }

    fun onWakeWord() {
        if (busy) return
        busy = true
        stopWakeListening()
        showCat("Pois não, ${UserProfile.shortAddress(this)}?", CatMood.LISTEN)
        runCatching { ToneGenerator(AudioManager.STREAM_NOTIFICATION, 80).startTone(ToneGenerator.TONE_PROP_BEEP, 150) }
        scope.launch {
            delay(250)
            listenForQuestion()
        }
    }

    // ---------- the cat on screen ----------

    /** Slides the cat up from the bottom of the screen (over any app) with a speech bubble. */
    private fun showCat(text: String, mood: CatMood) {
        if (!Settings.canDrawOverlays(this)) return
        if (catView == null) {
            val view = LayoutInflater.from(this).inflate(R.layout.overlay_voice_cat, null)
            val params = WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT
            ).apply { gravity = Gravity.BOTTOM }
            catText = view.findViewById<TextView>(R.id.catText).also { it.movementMethod = ScrollingMovementMethod() }
            catImage = view.findViewById<ImageView>(R.id.catImage).also { it.setOnClickListener { dismissConversation() } }
            view.visibility = View.INVISIBLE
            if (runCatching { getSystemService(WindowManager::class.java).addView(view, params) }.isFailure) return
            catView = view
            view.post {
                view.translationY = view.height.toFloat()
                view.visibility = View.VISIBLE
                view.animate().translationY(0f).setDuration(450).setInterpolator(OvershootInterpolator(0.9f)).start()
            }
            startBobbing()
        }
        catText?.let {
            it.text = text
            it.scrollTo(0, 0)
        }
        setMood(mood)
    }

    private fun setMood(mood: CatMood) {
        val image = catImage ?: return
        val res = when (mood) {
            CatMood.LISTEN -> R.drawable.anim_cat_listen
            CatMood.IDLE -> R.drawable.anim_cat_idle
            // While thinking or searching he reads his book, turning the pages.
            CatMood.THINK, CatMood.READ -> R.drawable.anim_cat_read
            CatMood.PAINT -> R.drawable.anim_cat_paint
            CatMood.TALK -> R.drawable.anim_cat_talk
        }
        if (image.tag == res) return
        image.tag = res
        image.setImageResource(res)
        (image.drawable as? AnimationDrawable)?.start()
    }

    /** Gentle up-and-down breathing so the cat never looks frozen. */
    private fun startBobbing() {
        val image = catImage ?: return
        val px = 5f * resources.displayMetrics.density
        bob = ObjectAnimator.ofFloat(image, "translationY", 0f, -px).apply {
            duration = 900
            repeatMode = ValueAnimator.REVERSE
            repeatCount = ValueAnimator.INFINITE
            start()
        }
    }

    private fun updateCatText(text: String) {
        catText?.let {
            it.text = text
            it.scrollTo(0, 0)
        }
    }

    /** Slides the cat back down and removes it, then runs [after]. */
    private fun hideCat(after: () -> Unit = {}) {
        val view = catView
        if (view == null) {
            after()
            return
        }
        catView = null
        catText = null
        catImage = null
        bob?.cancel()
        bob = null
        view.animate().translationY(view.height.toFloat()).setDuration(350)
            .setInterpolator(AccelerateInterpolator())
            .withEndAction {
                runCatching { getSystemService(WindowManager::class.java).removeView(view) }
                after()
            }.start()
    }

    /** Tapping the cat cancels whatever it is doing. */
    private fun dismissConversation() {
        conversation++
        speaker.stop()
        destroyQuestionRecognizer()
        hideCat { startWakeListening() }
    }

    private fun finishConversation(delayMs: Long = 0) {
        scope.launch {
            delay(delayMs)
            hideCat { startWakeListening() }
        }
    }

    // ---------- listening ----------

    private fun listenForQuestion() {
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            val msg = "Perdão, não consigo entender perguntas por voz neste celular."
            showCat(msg, CatMood.TALK)
            speaker.speak(msg) { finishConversation() }
            return
        }
        updateNotification("Ouvindo...")
        val recognizer = SpeechRecognizer.createSpeechRecognizer(this)
        questionRecognizer = recognizer
        recognizer.setRecognitionListener(object : android.speech.RecognitionListener {
            // Some phones show the words as partial results and then hand back an empty final result.
            var heardSoFar = ""

            override fun onResults(results: Bundle?) {
                val question = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()
                    ?.takeIf { it.isNotBlank() } ?: heardSoFar
                destroyQuestionRecognizer()
                if (question.isBlank()) notHeard() else answer(AgentLoop.stripWakeWord(question))
            }

            override fun onPartialResults(partialResults: Bundle?) {
                partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()
                    ?.takeIf { it.isNotBlank() }?.let {
                        heardSoFar = it
                        updateCatText("\"$it\"")
                    }
            }

            override fun onError(error: Int) {
                destroyQuestionRecognizer()
                if (heardSoFar.isNotBlank()) answer(AgentLoop.stripWakeWord(heardSoFar)) else notHeard()
            }

            override fun onReadyForSpeech(params: Bundle?) {}
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(rmsdB: Float) {}
            override fun onBufferReceived(buffer: ByteArray?) {}
            override fun onEndOfSpeech() {}
            override fun onEvent(eventType: Int, params: Bundle?) {}
        })
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE, "pt-BR")
            .putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            .putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        recognizer.startListening(intent)
    }

    private fun notHeard() {
        showCat("Perdão, não ouvi. É só me chamar de novo.", CatMood.IDLE)
        finishConversation(1600)
    }

    private fun destroyQuestionRecognizer() {
        questionRecognizer?.destroy()
        questionRecognizer = null
    }

    // ---------- answering ----------

    private fun answer(question: String) {
        updateNotification("Você: $question")
        showCat("\"$question\"", CatMood.THINK)
        val id = conversation
        val history = ChatStore.voiceChat(this).messages.toList()
        ChatStore.append(this, ChatStore.VOICE_CHAT_ID, ChatMessage("user", question))
        exchangeListener?.invoke(ChatStore.VOICE_CHAT_ID)

        scope.launch {
            var replied = false
            AgentLoop(
                context = applicationContext,
                chatId = ChatStore.VOICE_CHAT_ID,
                history = history,
                spoken = true,
                onStatus = { status ->
                    if (id == conversation) {
                        updateNotification(status)
                        runOnMain { updateCatText("\"$question\"\n\n$status") }
                    }
                },
                onPhase = { phase ->
                    if (id == conversation) runOnMain {
                        when (phase) {
                            AgentLoop.Phase.SEARCHING -> {
                                setMood(CatMood.READ)
                                speaker.speak("Um momento, ${UserProfile.shortAddress(this@VoiceService)}. Vou pesquisar.")
                            }
                            AgentLoop.Phase.DRAWING -> setMood(CatMood.PAINT)
                            else -> setMood(CatMood.THINK)
                        }
                    }
                },
                onReply = reply@{ text, image ->
                    replied = true
                    ChatStore.append(applicationContext, ChatStore.VOICE_CHAT_ID, ChatMessage("gota", text, image))
                    exchangeListener?.invoke(ChatStore.VOICE_CHAT_ID)
                    if (id != conversation) return@reply
                    updateNotification(text)
                    runOnMain {
                        showCat(text, CatMood.TALK)
                        speaker.speak(text) { runOnMain { setMood(CatMood.IDLE) }; finishConversation(700) }
                    }
                }
            ).run(question)
            if (!replied) finishConversation()
        }
    }

    private fun runOnMain(block: () -> Unit) {
        scope.launch { block() }
    }

    /** Frees the microphone while the chat screen is dictating (only matters in "Hey Gota" mode). */
    fun pauseWake() {
        wakePaused = true
        if (!busy) stopWakeListening()
    }

    fun resumeWake() {
        wakePaused = false
        if (!busy) startWakeListening()
    }

    override fun onDestroy() {
        running = false
        instance = null
        volumeButton?.stop()
        volumeButton = null
        scope.cancel()
        bob?.cancel()
        catView?.let { view -> runCatching { getSystemService(WindowManager::class.java).removeView(view) } }
        catView = null
        stopWakeListening()
        destroyQuestionRecognizer()
        if (::speaker.isInitialized) speaker.shutdown()
        voskModel?.close()
        super.onDestroy()
    }

    companion object {
        private const val CHANNEL_ID = "gota_voice"
        private const val NOTIFICATION_ID = 7
        private const val SAMPLE_RATE = 16000f
        private const val WAKE_GRAMMAR = "[\"ei gota\", \"oi gota\", \"hey gota\", \"gota\", \"[unk]\"]"
        const val ACTION_RELOAD_MODE = "com.aiagent.RELOAD_MODE"

        @Volatile
        var running = false
            private set

        @Volatile
        var instance: VoiceService? = null
            private set

        /** Lets the chat screen refresh when a voice conversation is saved. */
        @Volatile
        var exchangeListener: ((chatId: String) -> Unit)? = null
    }
}
