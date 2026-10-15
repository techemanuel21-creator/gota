package com.aiagent.local

import java.io.File
import java.net.HttpURLConnection
import java.net.URL

object ModelDownloader {

    const val MODEL_URL =
        "https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm/resolve/main/gemma-4-E2B-it.litertlm"
    const val MODEL_FILE_NAME = "gemma4_e2b.litertlm"
    const val MODEL_SIZE_MB_APPROX = 2468

    fun deleteLegacyModels(filesDir: File) {
        listOf("model.task", "model_qwen15b.task", "model_qwen15b.task.part").forEach {
            val legacy = File(filesDir, it)
            if (legacy.exists()) legacy.delete()
        }
    }

    fun download(destFile: File, onProgress: (percent: Int, downloadedMb: Long, totalMb: Long) -> Unit) {
        val tmpFile = File(destFile.parentFile, destFile.name + ".part")
        var connection = (URL(MODEL_URL).openConnection() as HttpURLConnection)
        connection.instanceFollowRedirects = true
        connection.connectTimeout = 20000
        connection.readTimeout = 20000
        connection.connect()

        if (connection.responseCode in 300..399) {
            val redirectUrl = connection.getHeaderField("Location")
            connection.disconnect()
            connection = (URL(redirectUrl).openConnection() as HttpURLConnection)
            connection.instanceFollowRedirects = true
            connection.connectTimeout = 20000
            connection.readTimeout = 20000
            connection.connect()
        }

        val total = connection.contentLengthLong
        connection.inputStream.use { input ->
            tmpFile.outputStream().use { output ->
                val buffer = ByteArray(64 * 1024)
                var downloaded = 0L
                var lastPercent = -1
                while (true) {
                    val read = input.read(buffer)
                    if (read == -1) break
                    output.write(buffer, 0, read)
                    downloaded += read
                    val percent = if (total > 0) ((downloaded * 100) / total).toInt() else 0
                    if (percent != lastPercent) {
                        lastPercent = percent
                        onProgress(percent, downloaded / (1024 * 1024), total / (1024 * 1024))
                    }
                }
            }
        }
        connection.disconnect()

        if (destFile.exists()) destFile.delete()
        tmpFile.renameTo(destFile)
    }
}
