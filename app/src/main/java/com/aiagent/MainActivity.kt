package com.aiagent

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.drawable.AnimationDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.view.Gravity
import android.view.View
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.core.view.GravityCompat
import androidx.drawerlayout.widget.DrawerLayout
import androidx.lifecycle.lifecycleScope
import com.aiagent.local.AgentLoop
import com.aiagent.local.CalendarHelper
import com.aiagent.local.Chat
import com.aiagent.local.ChatMessage
import com.aiagent.local.ChatStore
import com.aiagent.local.GemmaAgent
import com.aiagent.local.ImageGen
import com.aiagent.local.LocationHelper
import com.aiagent.local.ModelDownloader
import com.aiagent.local.UserProfile
import com.google.android.material.button.MaterialButton
import com.google.android.material.switchmaterial.SwitchMaterial
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import java.util.UUID

class MainActivity : AppCompatActivity() {

    private enum class Step {
        NAME, NOTIFICATIONS, MICROPHONE, LOCATION, CALENDAR, NOTIFICATION_LISTENER, OVERLAY, MODEL, READY
    }

    private lateinit var drawer: DrawerLayout
    private lateinit var btnMenu: TextView
    private lateinit var chatTitle: TextView
    private lateinit var stepScroll: ScrollView
    private lateinit var stepIcon: TextView
    private lateinit var stepTitle: TextView
    private lateinit var stepDescription: TextView
    private lateinit var stepInput: EditText
    private lateinit var treatmentGroup: RadioGroup
    private lateinit var stepProgress: ProgressBar
    private lateinit var stepProgressText: TextView
    private lateinit var stepAction: MaterialButton
    private lateinit var stepSkip: TextView

    private lateinit var chatGroup: LinearLayout
    private lateinit var chatScroll: ScrollView
    private lateinit var chatContainer: LinearLayout
    private lateinit var inputGoal: EditText
    private lateinit var btnSend: TextView
    private lateinit var btnMic: TextView
    private lateinit var btnCall: TextView
    private lateinit var attachmentRow: LinearLayout
    private lateinit var attachmentThumb: ImageView
    private lateinit var bubbleSwitch: SwitchMaterial
    private lateinit var voiceSwitch: SwitchMaterial
    private lateinit var chatList: LinearLayout

    private var modelJob: Job? = null
    private var editingProfile = false
    private var pendingImage: String? = null
    private var dictation: SpeechRecognizer? = null
    private var dictating = false
    private var dictationBase = ""

    private val prefs by lazy { getSharedPreferences("gota", MODE_PRIVATE) }
    private val ptBr = Locale("pt", "BR")

    private var currentChatId: String
        get() = prefs.getString("current_chat", null) ?: ChatStore.create(this).id.also { currentChatId = it }
        set(value) = prefs.edit().putString("current_chat", value).apply()

    // If the person says "no" to a popup we move on instead of asking forever.
    private val notificationPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (!granted) skip("notifications")
            refresh()
        }

    private var enableVoiceAfterMicGrant = false
    private var dictateAfterMicGrant = false
    private var callAfterMicGrant = false

    private val micPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (!granted) skip("mic")
            refresh()
            if (granted && enableVoiceAfterMicGrant) voiceSwitch.isChecked = true
            if (granted && dictateAfterMicGrant) startDictation()
            if (granted && callAfterMicGrant) startCall()
            enableVoiceAfterMicGrant = false
            dictateAfterMicGrant = false
            callAfterMicGrant = false
        }

    private val locationPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { result ->
            if (result.values.none { it }) skip("location") else LocationHelper.warmUp(this)
            refresh()
        }

    private val calendarPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (!granted) skip("calendar")
            refresh()
        }

    private val pickImage = registerForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) attachImage(uri)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        drawer = findViewById(R.id.drawer)
        btnMenu = findViewById(R.id.btnMenu)
        chatTitle = findViewById(R.id.chatTitle)
        stepScroll = findViewById(R.id.stepScroll)
        stepIcon = findViewById(R.id.stepIcon)
        stepTitle = findViewById(R.id.stepTitle)
        stepDescription = findViewById(R.id.stepDescription)
        stepInput = findViewById(R.id.stepInput)
        treatmentGroup = findViewById(R.id.treatmentGroup)
        stepProgress = findViewById(R.id.stepProgress)
        stepProgressText = findViewById(R.id.stepProgressText)
        stepAction = findViewById(R.id.stepAction)
        stepSkip = findViewById(R.id.stepSkip)
        chatGroup = findViewById(R.id.chatGroup)
        chatScroll = findViewById(R.id.chatScroll)
        chatContainer = findViewById(R.id.chatContainer)
        inputGoal = findViewById(R.id.inputGoal)
        btnSend = findViewById(R.id.btnSend)
        btnMic = findViewById(R.id.btnMic)
        attachmentRow = findViewById(R.id.attachmentRow)
        attachmentThumb = findViewById(R.id.attachmentThumb)
        bubbleSwitch = findViewById(R.id.bubbleSwitch)
        voiceSwitch = findViewById(R.id.voiceSwitch)
        chatList = findViewById(R.id.chatList)

        btnMenu.setOnClickListener {
            renderChatList()
            drawer.openDrawer(GravityCompat.START)
        }
        btnSend.setOnClickListener { sendGoal() }
        btnMic.setOnClickListener { toggleDictation() }
        btnCall = findViewById(R.id.btnCall)
        btnCall.setOnClickListener { startCall() }
        findViewById<View>(R.id.btnAttach).setOnClickListener {
            pickImage.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
        }
        findViewById<View>(R.id.attachmentRemove).setOnClickListener { clearAttachment() }
        voiceSwitch.setOnCheckedChangeListener { _, checked -> onVoiceToggled(checked) }
        bubbleSwitch.setOnCheckedChangeListener { _, checked ->
            if (checked) {
                if (Settings.canDrawOverlays(this)) {
                    startForegroundService(Intent(this, OverlayService::class.java))
                } else {
                    bubbleSwitch.isChecked = false
                    startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
                }
            } else {
                stopService(Intent(this, OverlayService::class.java))
            }
        }

        findViewById<View>(R.id.btnNewChat).setOnClickListener {
            openChat(ChatStore.create(this).id)
            drawer.closeDrawers()
        }
        findViewById<View>(R.id.btnAliases).setOnClickListener {
            drawer.closeDrawers()
            startActivity(Intent(this, AppAliasesActivity::class.java))
        }
        findViewById<View>(R.id.btnProfile).setOnClickListener {
            drawer.closeDrawers()
            editingProfile = true
            refresh()
        }
        val wakeGroup = findViewById<RadioGroup>(R.id.wakeModeGroup)
        wakeGroup.check(if (prefs.getString("wake_mode", "button") == "voice") R.id.wakeVoice else R.id.wakeButton)
        wakeGroup.setOnCheckedChangeListener { _, id ->
            prefs.edit().putString("wake_mode", if (id == R.id.wakeVoice) "voice" else "button").apply()
            if (VoiceService.running) {
                startService(Intent(this, VoiceService::class.java).setAction(VoiceService.ACTION_RELOAD_MODE))
            }
        }

        refresh()
    }

    override fun onResume() {
        super.onResume()
        LocationHelper.warmUp(this)
        VoiceService.exchangeListener = { chatId ->
            runOnUiThread { if (chatId == currentChatId && chatGroup.visibility == View.VISIBLE) renderChat() }
        }
        refresh()
    }

    override fun onPause() {
        VoiceService.exchangeListener = null
        stopDictation()
        super.onPause()
    }

    // ---------- setup steps ----------

    private fun hasPermission(permission: String) =
        ContextCompat.checkSelfPermission(this, permission) == PackageManager.PERMISSION_GRANTED

    private fun skipped(key: String) = prefs.getBoolean("skip_$key", false)
    private fun skip(key: String) = prefs.edit().putBoolean("skip_$key", true).apply()

    private fun currentStep(): Step {
        if (editingProfile || !UserProfile.isSet(this)) return Step.NAME
        if (!isNotificationPermissionGranted() && !skipped("notifications")) return Step.NOTIFICATIONS
        if (!hasPermission(Manifest.permission.RECORD_AUDIO) && !skipped("mic")) return Step.MICROPHONE
        if (!LocationHelper.hasPermission(this) && !skipped("location")) return Step.LOCATION
        if (!CalendarHelper.hasPermission(this) && !skipped("calendar")) return Step.CALENDAR
        if (!isNotificationListenerEnabled() && !skipped("listener")) return Step.NOTIFICATION_LISTENER
        if (!Settings.canDrawOverlays(this) && !skipped("overlay")) return Step.OVERLAY
        if (!GemmaAgent.isLoaded()) return Step.MODEL
        return Step.READY
    }

    private fun isNotificationPermissionGranted(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return true
        return hasPermission(Manifest.permission.POST_NOTIFICATIONS)
    }

    private fun isNotificationListenerEnabled() =
        NotificationManagerCompat.getEnabledListenerPackages(this).contains(packageName)

    private fun refresh() {
        when (currentStep()) {
            Step.NAME -> showNameStep()
            Step.NOTIFICATIONS -> showStep(
                "🔔", "Permitir notificações",
                "Para o Gota avisar quando estiver por perto, ouvindo ou com a bolha ligada.",
                "Permitir", { notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS) }, "notifications"
            )
            Step.MICROPHONE -> showStep(
                "🎙️", "Permitir microfone",
                "Para conversar com o Gota por voz e ditar mensagens. O microfone só é usado quando você o chama.",
                "Permitir", { micPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO) }, "mic"
            )
            Step.LOCATION -> showStep(
                "📍", "Permitir localização",
                "Para o Gota informar o clima e responder coisas da sua região.",
                "Permitir", {
                    locationPermissionLauncher.launch(
                        arrayOf(Manifest.permission.ACCESS_COARSE_LOCATION, Manifest.permission.ACCESS_FINE_LOCATION)
                    )
                }, "location"
            )
            Step.CALENDAR -> showStep(
                "📅", "Permitir agenda",
                "Para o Gota ler seus compromissos do dia. Funciona com a agenda do Google, da Samsung e do Outlook (ative \"Sincronizar calendários\" no app do Outlook).",
                "Permitir", { calendarPermissionLauncher.launch(Manifest.permission.READ_CALENDAR) }, "calendar"
            )
            Step.NOTIFICATION_LISTENER -> showStep(
                "🔎", "Ativar Leitor de Notificações",
                "Permite que o Gota diga quantas notificações você tem em cada app (ex: WhatsApp).",
                "Abrir Configurações", { startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)) }, "listener"
            )
            Step.OVERLAY -> showStep(
                "🪟", "Permitir sobreposição",
                "Para o Gota aparecer na tela sobre outros apps quando você o chamar.",
                "Permitir", {
                    startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
                }, "overlay"
            )
            Step.MODEL -> {
                showStep(
                    "🧠", "Preparando o Gota",
                    "Baixando a inteligência do Gota (~${ModelDownloader.MODEL_SIZE_MB_APPROX / 1000.0} GB, uma vez só — use Wi-Fi). Depois disso ela roda no próprio celular, mesmo sem internet.",
                    null, null, null
                )
                ensureModelLoading()
            }
            Step.READY -> showChat()
        }
    }

    private fun showStep(
        icon: String, title: String, description: String,
        buttonText: String?, onAction: (() -> Unit)?, skipKey: String?
    ) {
        stepScroll.visibility = View.VISIBLE
        chatGroup.visibility = View.GONE
        btnMenu.visibility = View.GONE
        bubbleSwitch.visibility = View.GONE
        voiceSwitch.visibility = View.GONE
        stepInput.visibility = View.GONE
        treatmentGroup.visibility = View.GONE
        chatTitle.text = ""
        stepIcon.text = icon
        stepTitle.text = title
        stepDescription.text = description
        if (buttonText != null && onAction != null) {
            stepAction.visibility = View.VISIBLE
            stepAction.text = buttonText
            stepAction.setOnClickListener { onAction() }
            stepProgress.visibility = View.GONE
            stepProgressText.visibility = View.GONE
        } else {
            stepAction.visibility = View.GONE
        }
        stepSkip.visibility = if (skipKey != null) View.VISIBLE else View.GONE
        stepSkip.setOnClickListener {
            skipKey?.let { skip(it) }
            refresh()
        }
    }

    private fun showNameStep() {
        showStep(
            "🎩", "Muito prazer, eu sou o Gota",
            "Serei seu mordomo pessoal. Como devo chamá-lo?",
            if (editingProfile) "Salvar" else "Continuar", { saveName() }, null
        )
        stepInput.visibility = View.VISIBLE
        treatmentGroup.visibility = View.VISIBLE
        if (stepInput.text.isNullOrBlank()) UserProfile.name(this)?.let { stepInput.setText(it) }
        when (UserProfile.treatment(this)) {
            "senhora" -> treatmentGroup.check(R.id.treatMadam)
            "" -> treatmentGroup.check(R.id.treatName)
            else -> treatmentGroup.check(R.id.treatSir)
        }
    }

    private fun saveName() {
        val name = stepInput.text.toString().trim()
        if (name.isEmpty()) {
            stepInput.error = "Digite seu nome"
            return
        }
        val treatment = when (treatmentGroup.checkedRadioButtonId) {
            R.id.treatMadam -> "senhora"
            R.id.treatName -> ""
            else -> "senhor"
        }
        UserProfile.save(this, name.replaceFirstChar { it.uppercase() }, treatment)
        editingProfile = false
        refresh()
    }

    private fun ensureModelLoading() {
        if (modelJob != null) return
        modelJob = lifecycleScope.launch {
            try {
                ModelDownloader.deleteLegacyModels(filesDir)
                val modelFile = File(filesDir, ModelDownloader.MODEL_FILE_NAME)
                if (!modelFile.exists()) {
                    setDownloadProgress(0, "Baixando...")
                    withContext(Dispatchers.IO) {
                        ModelDownloader.download(modelFile) { percent, downMb, totalMb ->
                            runOnUiThread { setDownloadProgress(percent, "Baixando... ${downMb} MB de ${totalMb} MB") }
                        }
                    }
                }
                setDownloadProgress(100, "Acordando o Gota...")
                if (!GemmaAgent.isLoaded()) {
                    withContext(Dispatchers.IO) { GemmaAgent.load(applicationContext, modelFile.absolutePath) }
                }
                // Gets the offline image model ready too, but only on Wi-Fi so it never eats mobile data.
                ImageGen.startDownload(applicationContext, onlyOnWifi = true)
                modelJob = null
                refresh()
            } catch (e: Exception) {
                modelJob = null
                stepDescription.text = "Não consegui preparar o Gota: ${e.message}"
                stepProgress.visibility = View.GONE
                stepProgressText.visibility = View.GONE
                stepAction.visibility = View.VISIBLE
                stepAction.text = "Tentar novamente"
                stepAction.setOnClickListener { refresh() }
            }
        }
    }

    private fun setDownloadProgress(percent: Int, label: String) {
        stepProgress.visibility = View.VISIBLE
        stepProgress.progress = percent
        stepProgressText.visibility = View.VISIBLE
        stepProgressText.text = label
        stepAction.visibility = View.GONE
    }

    // ---------- chat screen ----------

    private fun showChat() {
        stepScroll.visibility = View.GONE
        chatGroup.visibility = View.VISIBLE
        btnMenu.visibility = View.VISIBLE
        btnCall.visibility = View.VISIBLE
        bubbleSwitch.visibility = View.VISIBLE
        voiceSwitch.visibility = View.VISIBLE

        val voiceWanted = prefs.getBoolean("voice_enabled", false) && hasPermission(Manifest.permission.RECORD_AUDIO)
        if (voiceWanted && !VoiceService.running) startForegroundService(Intent(this, VoiceService::class.java))
        setVoiceSwitchSilently(voiceWanted || VoiceService.running)
        renderChat()
    }

    /** Opens the call screen: a continuous spoken conversation saved as its own chat. */
    private fun startCall() {
        if (!hasPermission(Manifest.permission.RECORD_AUDIO)) {
            callAfterMicGrant = true
            micPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
            return
        }
        stopDictation()
        startActivity(Intent(this, CallActivity::class.java))
    }

    private fun openChat(id: String) {
        currentChatId = id
        clearAttachment()
        renderChat()
    }

    private fun currentChat(): Chat =
        ChatStore.get(this, currentChatId) ?: ChatStore.create(this).also { currentChatId = it.id }

    private fun renderChat() {
        val chat = currentChat()
        chatTitle.text = if (chat.isVoice) "🎙️ ${chat.title}" else chat.title
        chatContainer.removeAllViews()
        if (chat.messages.isEmpty()) {
            val hour = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)
            val salute = when (hour) { in 5..11 -> "Bom dia"; in 12..17 -> "Boa tarde"; else -> "Boa noite" }
            val serve = when (UserProfile.treatment(this)) { "senhora" -> "servi-la"; "" -> "ajudar"; else -> "servi-lo" }
            addBubble("$salute, ${UserProfile.address(this)}. Em que posso $serve?", isUser = false)
        }
        chat.messages.forEach { m -> addMessage(m) }
    }

    private fun renderChatList() {
        chatList.removeAllViews()
        val chats = ChatStore.list(this).let { list ->
            (list.filter { it.isVoice } + list.filterNot { it.isVoice }).ifEmpty { listOf(ChatStore.voiceChat(this)) }
        }
        val dateFmt = SimpleDateFormat("dd/MM HH:mm", ptBr)
        chats.forEach { chat ->
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(dp(12), dp(10), dp(12), dp(10))
                if (chat.id == currentChatId) setBackgroundResource(R.drawable.bg_input)
                setOnClickListener {
                    openChat(chat.id)
                    drawer.closeDrawers()
                }
                setOnLongClickListener {
                    confirmDelete(chat)
                    true
                }
            }
            row.addView(TextView(this).apply {
                text = if (chat.isVoice) "🎙️ ${chat.title}" else chat.title
                setTextColor(ContextCompat.getColor(this@MainActivity, R.color.text_primary))
                textSize = 15f
                maxLines = 1
            })
            row.addView(TextView(this).apply {
                text = dateFmt.format(Date(chat.updatedAt))
                setTextColor(ContextCompat.getColor(this@MainActivity, R.color.text_secondary))
                textSize = 11f
            })
            chatList.addView(row, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
                topMargin = dp(4)
            })
        }
    }

    private fun confirmDelete(chat: Chat) {
        AlertDialog.Builder(this)
            .setTitle("Apagar conversa?")
            .setMessage("\"${chat.title}\" será apagada.")
            .setPositiveButton("Apagar") { _, _ ->
                ChatStore.delete(this, chat.id)
                if (chat.id == currentChatId) openChat(ChatStore.create(this).id)
                renderChatList()
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    private fun sendGoal() {
        if (dictating) stopDictation()
        val goal = inputGoal.text.toString().trim()
        val image = pendingImage
        if (goal.isEmpty() && image == null) return
        inputGoal.setText("")
        clearAttachment(deleteFile = false)

        val chatId = currentChatId
        val history = currentChat().messages.toList()
        val userMessage = ChatMessage("user", goal, image)
        ChatStore.append(this, chatId, userMessage)
        if (history.isEmpty()) chatContainer.removeAllViews()
        addMessage(userMessage)
        chatTitle.text = currentChat().title

        var status: StatusBubble? = addStatusBubble("Pensando...")
        lifecycleScope.launch {
            AgentLoop(
                context = applicationContext,
                chatId = chatId,
                history = history,
                onStatus = { msg -> runOnUiThread { status?.label?.text = msg } },
                onPhase = { phase ->
                    runOnUiThread {
                        status?.animate(if (phase == AgentLoop.Phase.DRAWING) R.drawable.anim_cat_paint else R.drawable.anim_cat_read)
                    }
                },
                onReply = { text, replyImage ->
                    ChatStore.append(applicationContext, chatId, ChatMessage("gota", text, replyImage))
                    runOnUiThread {
                        if (chatId != currentChatId) return@runOnUiThread
                        status?.let { chatContainer.removeView(it.root) }
                        status = null
                        addMessage(ChatMessage("gota", text, replyImage))
                    }
                }
            ).run(goal, image)
        }
    }

    /** The "thinking" bubble: the little cat reading (or painting) next to what he is doing. */
    private class StatusBubble(val root: View, val cat: ImageView, val label: TextView) {
        fun animate(res: Int) {
            if (cat.tag == res) return
            cat.tag = res
            cat.setImageResource(res)
            (cat.drawable as? AnimationDrawable)?.start()
        }
    }

    private fun addStatusBubble(text: String): StatusBubble {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(8), dp(6), dp(14), dp(6))
            setBackgroundResource(R.drawable.bubble_agent)
        }
        val cat = ImageView(this)
        row.addView(cat, LinearLayout.LayoutParams(dp(44), dp(44)))
        val label = TextView(this).apply {
            this.text = text
            setTextColor(0xFFFFFFFF.toInt())
            alpha = 0.7f
            textSize = 14f
            setPadding(dp(8), 0, 0, 0)
        }
        row.addView(label)
        chatContainer.addView(row, bubbleParams(isUser = false))
        chatScroll.post { chatScroll.fullScroll(View.FOCUS_DOWN) }
        return StatusBubble(row, cat, label).also { it.animate(R.drawable.anim_cat_read) }
    }

    private fun addMessage(message: ChatMessage) {
        val isUser = message.role == "user"
        message.image?.let { addImageBubble(it, isUser) }
        if (message.text.isNotBlank()) addBubble(message.text, isUser)
    }

    private fun addBubble(text: String, isUser: Boolean, muted: Boolean = false): TextView {
        val bubble = TextView(this).apply {
            this.text = text
            setTextColor(0xFFFFFFFF.toInt())
            alpha = if (muted) 0.6f else 1f
            textSize = 15f
            setLineSpacing(0f, 1.1f)
            setTextIsSelectable(!muted)
            setPadding(dp(14), dp(10), dp(14), dp(10))
            setBackgroundResource(if (isUser) R.drawable.bubble_user else R.drawable.bubble_agent)
            maxWidth = (resources.displayMetrics.widthPixels * 0.8).toInt()
        }
        chatContainer.addView(bubble, bubbleParams(isUser))
        chatScroll.post { chatScroll.fullScroll(View.FOCUS_DOWN) }
        return bubble
    }

    private fun addImageBubble(source: String, isUser: Boolean) {
        val uri = if (source.startsWith("content:") || source.startsWith("file:")) Uri.parse(source) else Uri.fromFile(File(source))
        val image = ImageView(this).apply {
            adjustViewBounds = true
            maxWidth = dp(240)
            maxHeight = dp(320)
            scaleType = ImageView.ScaleType.FIT_CENTER
            clipToOutline = true
            setBackgroundResource(R.drawable.bubble_agent)
            runCatching { setImageURI(uri) }
            if (source.startsWith("content:")) setOnClickListener {
                runCatching {
                    startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, "image/*").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
                }
            }
        }
        chatContainer.addView(image, bubbleParams(isUser))
        chatScroll.post { chatScroll.fullScroll(View.FOCUS_DOWN) }
    }

    private fun bubbleParams(isUser: Boolean) =
        LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
            topMargin = dp(4)
            bottomMargin = dp(4)
            gravity = if (isUser) Gravity.END else Gravity.START
        }

    // ---------- attachments ----------

    /** Copies the chosen photo, shrunk to at most 1024 px, so it is small and readable by the model. */
    private fun attachImage(uri: Uri) {
        lifecycleScope.launch {
            val file = withContext(Dispatchers.IO) {
                runCatching {
                    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                    contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds) }
                    var sample = 1
                    while (maxOf(bounds.outWidth, bounds.outHeight) / sample > 2048) sample *= 2
                    val bitmap = contentResolver.openInputStream(uri)?.use {
                        BitmapFactory.decodeStream(it, null, BitmapFactory.Options().apply { inSampleSize = sample })
                    } ?: return@runCatching null
                    val scale = 1024f / maxOf(bitmap.width, bitmap.height)
                    val scaled = if (scale < 1f) Bitmap.createScaledBitmap(bitmap, (bitmap.width * scale).toInt(), (bitmap.height * scale).toInt(), true) else bitmap
                    val dir = File(filesDir, "attachments").apply { mkdirs() }
                    File(dir, "${UUID.randomUUID()}.jpg").also { out ->
                        out.outputStream().use { scaled.compress(Bitmap.CompressFormat.JPEG, 85, it) }
                    }
                }.getOrNull()
            }
            if (file == null) {
                addBubble("Perdão, não consegui abrir essa imagem.", isUser = false)
                return@launch
            }
            pendingImage?.let { File(it).delete() }
            pendingImage = file.absolutePath
            attachmentThumb.setImageURI(Uri.fromFile(file))
            attachmentRow.visibility = View.VISIBLE
        }
    }

    private fun clearAttachment(deleteFile: Boolean = true) {
        if (deleteFile) pendingImage?.let { File(it).delete() }
        pendingImage = null
        attachmentRow.visibility = View.GONE
        attachmentThumb.setImageDrawable(null)
    }

    // ---------- dictation (microphone next to the text field) ----------

    private fun toggleDictation() {
        if (dictating) stopDictation() else startDictation()
    }

    private fun startDictation() {
        if (!hasPermission(Manifest.permission.RECORD_AUDIO)) {
            dictateAfterMicGrant = true
            prefs.edit().putBoolean("skip_mic", false).apply()
            micPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
            return
        }
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            addBubble("Perdão, este celular não tem reconhecimento de voz disponível.", isUser = false)
            return
        }
        dictating = true
        VoiceService.instance?.pauseWake()
        btnMic.text = "⏹"
        btnMic.setBackgroundResource(R.drawable.bg_circle_gradient)
        dictationBase = inputGoal.text.toString().trim()
        listenOnce()
    }

    /** Android stops listening after a pause; we restart until the person taps the button again. */
    private fun listenOnce() {
        dictation?.destroy()
        val recognizer = SpeechRecognizer.createSpeechRecognizer(this)
        dictation = recognizer
        recognizer.setRecognitionListener(object : android.speech.RecognitionListener {
            override fun onPartialResults(partialResults: Bundle?) {
                val partial = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull() ?: return
                showDictated(partial)
            }

            override fun onResults(results: Bundle?) {
                val text = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().orEmpty()
                if (text.isNotBlank()) dictationBase = join(dictationBase, text)
                showDictated("")
                if (dictating) listenOnce()
            }

            override fun onError(error: Int) {
                if (dictating && (error == SpeechRecognizer.ERROR_NO_MATCH || error == SpeechRecognizer.ERROR_SPEECH_TIMEOUT)) {
                    listenOnce()
                } else {
                    stopDictation()
                }
            }

            override fun onReadyForSpeech(params: Bundle?) {}
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(rmsdB: Float) {}
            override fun onBufferReceived(buffer: ByteArray?) {}
            override fun onEndOfSpeech() {}
            override fun onEvent(eventType: Int, params: Bundle?) {}
        })
        recognizer.startListening(
            Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                .putExtra(RecognizerIntent.EXTRA_LANGUAGE, "pt-BR")
                .putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
        )
    }

    private fun join(a: String, b: String) = listOf(a, b).filter { it.isNotBlank() }.joinToString(" ")

    private fun showDictated(partial: String) {
        inputGoal.setText(join(dictationBase, partial).replaceFirstChar { it.uppercase() })
        inputGoal.setSelection(inputGoal.text.length)
    }

    private fun stopDictation() {
        if (!dictating) return
        dictating = false
        dictation?.destroy()
        dictation = null
        btnMic.text = "🎤"
        btnMic.setBackgroundResource(R.drawable.bg_input)
        VoiceService.instance?.resumeWake()
    }

    // ---------- voice service switch ----------

    private fun onVoiceToggled(checked: Boolean) {
        if (!checked) {
            prefs.edit().putBoolean("voice_enabled", false).apply()
            stopService(Intent(this, VoiceService::class.java))
            return
        }
        if (!hasPermission(Manifest.permission.RECORD_AUDIO)) {
            setVoiceSwitchSilently(false)
            prefs.edit().putBoolean("skip_mic", false).apply()
            enableVoiceAfterMicGrant = true
            micPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
            return
        }
        prefs.edit().putBoolean("voice_enabled", true).apply()
        startForegroundService(Intent(this, VoiceService::class.java))
        val how = if (prefs.getString("wake_mode", "button") == "voice") "dizer \"Hey Gota\""
        else "segurar o botão de aumentar volume por meio segundo"
        addBubble("Às suas ordens. Para me chamar, é só $how, mesmo com o app fechado.", isUser = false)
    }

    private fun setVoiceSwitchSilently(checked: Boolean) {
        voiceSwitch.setOnCheckedChangeListener(null)
        voiceSwitch.isChecked = checked
        voiceSwitch.setOnCheckedChangeListener { _, isChecked -> onVoiceToggled(isChecked) }
    }

    override fun onBackPressed() {
        if (drawer.isDrawerOpen(GravityCompat.START)) drawer.closeDrawers()
        else if (editingProfile && UserProfile.isSet(this)) {
            editingProfile = false
            refresh()
        } else {
            @Suppress("DEPRECATION")
            super.onBackPressed()
        }
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()
}
