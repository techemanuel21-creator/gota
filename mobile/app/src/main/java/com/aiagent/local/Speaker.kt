package com.aiagent.local

import android.content.Context
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import java.util.Locale
import java.util.UUID

/** Text-to-speech in Brazilian Portuguese, preferring a male voice when one is installed. */
class Speaker(context: Context) : TextToSpeech.OnInitListener {

    private val tts = TextToSpeech(context.applicationContext, this)
    @Volatile private var ready = false
    private val pending = mutableListOf<Pair<String, () -> Unit>>()
    private val callbacks = mutableMapOf<String, () -> Unit>()

    override fun onInit(status: Int) {
        if (status != TextToSpeech.SUCCESS) return
        tts.language = Locale("pt", "BR")
        selectMaleVoice()
        tts.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) {}
            override fun onDone(utteranceId: String?) = finish(utteranceId)
            @Deprecated("Deprecated in Java")
            override fun onError(utteranceId: String?) = finish(utteranceId)
            override fun onError(utteranceId: String?, errorCode: Int) = finish(utteranceId)
            // Interrupted with stop(): whoever interrupted decides what comes next.
            override fun onStop(utteranceId: String?, interrupted: Boolean) {
                synchronized(callbacks) { callbacks.remove(utteranceId) }
            }
        })
        ready = true
        synchronized(pending) {
            pending.forEach { (text, done) -> speakNow(text, done) }
            pending.clear()
        }
    }

    private fun finish(utteranceId: String?) {
        val done = synchronized(callbacks) { callbacks.remove(utteranceId) }
        done?.invoke()
    }

    private fun selectMaleVoice() {
        val voices = tts.voices?.filter {
            it.locale.language == "pt" && (it.locale.country.isEmpty() || it.locale.country == "BR")
        } ?: emptyList()
        val male = voices.firstOrNull { voice ->
            val name = voice.name.lowercase()
            val featureMale = voice.features?.any { it.contains("male", true) && !it.contains("female", true) } == true
            featureMale || MALE_HINTS.any { name.contains(it) }
        }
        // Classic butler delivery: a little deeper and unhurried.
        if (male != null) {
            tts.voice = male
            tts.setPitch(0.88f)
        } else {
            // No male voice installed: deepen the default one so it sounds more masculine.
            tts.setPitch(0.72f)
        }
        tts.setSpeechRate(0.92f)
    }

    fun speak(text: String, onDone: () -> Unit = {}) {
        val clean = text.replace(Regex("[*_#`>]"), "")
            .replace(Regex("[\\p{So}\\p{Cn}]"), "")
            .trim()
        if (clean.isEmpty()) {
            onDone()
            return
        }
        if (!ready) {
            synchronized(pending) { pending.add(clean to onDone) }
            return
        }
        speakNow(clean, onDone)
    }

    private fun speakNow(text: String, onDone: () -> Unit) {
        val id = UUID.randomUUID().toString()
        synchronized(callbacks) { callbacks[id] = onDone }
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, Bundle(), id)
    }

    fun stop() = tts.stop()

    fun shutdown() {
        tts.stop()
        tts.shutdown()
    }

    companion object {
        // Samsung TTS marks male voices with "SMTm"; Google uses these ids for pt-BR male voices.
        private val MALE_HINTS = listOf("smtm", "-male", "_male", "ptd", "ped")
    }
}
