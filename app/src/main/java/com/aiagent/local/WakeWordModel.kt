package com.aiagent.local

import android.content.Context
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.zip.ZipInputStream

/** Downloads and unpacks the small offline Portuguese Vosk model used to detect "Hey Gota". */
object WakeWordModel {

    private const val MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip"
    private const val DIR_NAME = "vosk-pt"

    fun modelDir(context: Context): File = File(context.filesDir, DIR_NAME)

    fun isReady(context: Context): Boolean = File(modelDir(context), "READY").exists()

    /** Blocking; call off the main thread. Returns the folder that contains the model files. */
    fun ensure(context: Context): File {
        val target = modelDir(context)
        if (isReady(context)) return modelRoot(target)

        target.deleteRecursively()
        target.mkdirs()
        val connection = URL(MODEL_URL).openConnection() as HttpURLConnection
        connection.instanceFollowRedirects = true
        connection.connectTimeout = 20000
        connection.readTimeout = 20000
        connection.inputStream.use { input ->
            ZipInputStream(input.buffered()).use { zip ->
                var entry = zip.nextEntry
                while (entry != null) {
                    val out = File(target, entry.name)
                    if (!out.canonicalPath.startsWith(target.canonicalPath)) {
                        throw SecurityException("Entrada de zip inválida: ${entry.name}")
                    }
                    if (entry.isDirectory) {
                        out.mkdirs()
                    } else {
                        out.parentFile?.mkdirs()
                        out.outputStream().use { zip.copyTo(it) }
                    }
                    zip.closeEntry()
                    entry = zip.nextEntry
                }
            }
        }
        connection.disconnect()
        File(target, "READY").writeText("ok")
        return modelRoot(target)
    }

    /** Older models keep final.mdl at the top level, newer ones under am/. */
    private fun modelRoot(target: File): File {
        fun isModel(dir: File) = File(dir, "final.mdl").exists() || File(dir, "am/final.mdl").exists()
        if (isModel(target)) return target
        return target.listFiles()?.firstOrNull { it.isDirectory && isModel(it) } ?: target
    }
}
