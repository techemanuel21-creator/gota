package com.aiagent.local

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.ContentValues
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.media.MediaScannerConnection
import android.net.ConnectivityManager
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.core.app.NotificationCompat
import com.aiagent.R
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import org.pytorch.executorch.EValue
import org.pytorch.executorch.Module
import org.pytorch.executorch.Tensor
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.util.Random

/**
 * Creates images. With internet it uses Z-Image Turbo, a free service (no account) that makes a
 * sharp 1024×1024 picture — much better than anything that fits on the phone. Offline it falls
 * back to SDXS-512 DreamShaper, a tiny Stable Diffusion that runs on the phone's GPU (Vulkan),
 * and whose model is downloaded the first time it is actually needed. Pictures go straight to the
 * gallery, in the "GOTA IA" album.
 */
object ImageGen {

    private const val Z_IMAGE_SPACE = "https://tongyi-mai-z-image-turbo.hf.space"
    private const val FLUX_SPACE = "https://black-forest-labs-flux-1-schnell.hf.space"
    private const val USER_AGENT = "GotaApp/1.0 (Android)"

    const val SERVICE_Z_IMAGE = "Z-Image"
    const val SERVICE_FLUX = "FLUX"
    const val SERVICE_POLLINATIONS = "Pollinations"

    private const val REPO = "https://huggingface.co/software-mansion/react-native-executorch-sdxs-512-dreamshaper/resolve/main/"
    private const val TOKENIZER_REPO = "https://huggingface.co/IDKiro/sdxs-512-dreamshaper/resolve/main/tokenizer/"

    enum class Variant(val url: String, val fileName: String, val sizeMb: Int) {
        GPU(REPO + "vulkan/sdxs_512_dreamshaper_vulkan_fp16.pte", "sdxs_gpu.pte", 840),
        CPU(REPO + "xnnpack/sdxs_512_dreamshaper_xnnpack_fp32.pte", "sdxs_cpu.pte", 1679)
    }

    /** The on-device painter can't draw yet: not downloaded, or its graphics-card version failed ([gpuFailed]). */
    class NotReadyException(val gpuFailed: Boolean, val detail: String?) : Exception("on-device image model not ready")

    /** Gallery album (folder Pictures/GOTA IA) where every picture he paints is saved. */
    const val ALBUM = "GOTA IA"

    // The single-step scheduler collapses to a linear mix of the noise and the UNet output.
    private const val TIMESTEP = 999L
    private const val SAMPLE_COEFF = 14.642591f
    private const val NOISE_COEFF = -14.579279f
    private const val SIZE = 512
    private val LATENT_SHAPE = longArrayOf(1, 4, 64, 64)

    private const val CHANNEL_ID = "gota_images"
    private const val NOTIFICATION_ID = 4107

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    @Volatile
    var downloading = false
        private set

    @Volatile
    var downloadPercent = 0
        private set

    private var tokenizer: ClipTokenizer? = null

    private fun dir(context: Context) = File(context.filesDir, "imagegen").apply { mkdirs() }
    private fun prefs(context: Context) = context.getSharedPreferences("gota_imagegen", Context.MODE_PRIVATE)

    /** GPU unless this phone already failed with it. */
    fun variant(context: Context): Variant =
        if (prefs(context).getBoolean("gpu_failed", false)) Variant.CPU else Variant.GPU

    fun isReady(context: Context): Boolean {
        val d = dir(context)
        return File(d, variant(context).fileName).exists() && File(d, "vocab.json").exists() && File(d, "merges.txt").exists()
    }

    /** Downloads the image model in the background (once). [onlyOnWifi] avoids spending mobile data unasked. */
    fun startDownload(context: Context, onlyOnWifi: Boolean = false) {
        val app = context.applicationContext
        if (downloading || isReady(app)) return
        if (onlyOnWifi && isMetered(app)) return
        downloading = true
        downloadPercent = 0
        scope.launch {
            val variant = variant(app)
            try {
                val d = dir(app)
                listOf("vocab.json", "merges.txt").forEach { name ->
                    val file = File(d, name)
                    if (!file.exists()) download(TOKENIZER_REPO + name, file) {}
                }
                notifyProgress(app, 0, variant)
                var last = -1
                download(variant.url, File(d, variant.fileName)) { percent ->
                    downloadPercent = percent
                    if (percent != last) {
                        last = percent
                        notifyProgress(app, percent, variant)
                    }
                }
                notifyDone(app, "Gerador de imagens pronto", "Já posso criar imagens sem internet. É só pedir.")
            } catch (e: Exception) {
                notifyDone(app, "Download do gerador de imagens parou", "Peça uma imagem de novo para eu continuar de onde parou.")
            } finally {
                downloading = false
            }
        }
    }

    /** A picture made online and which service made it. */
    class OnlineImage(val uri: Uri, val service: String)

    /** Every online service failed; [details] says why for each one. */
    class OnlineFailed(val details: String) : IOException(details)

    /**
     * Blocking (network). Tries the free services from best to simplest and saves the first
     * picture that comes back: Z-Image Turbo (sharp, 1024px), FLUX.1 schnell, and, as a last
     * resort, the older Pollinations model (softer, with a small watermark).
     */
    fun generateOnline(context: Context, prompt: String): OnlineImage {
        val attempts = listOf<Pair<String, () -> ByteArray>>(
            SERVICE_Z_IMAGE to { gradio(Z_IMAGE_SPACE, "generate", zImageData(prompt)) },
            SERVICE_FLUX to { gradio(FLUX_SPACE, "infer", fluxData(prompt)) },
            SERVICE_POLLINATIONS to { pollinations(prompt) }
        )
        val errors = mutableListOf<String>()
        for ((name, attempt) in attempts) {
            try {
                return OnlineImage(saveToGallery(context, reencode(attempt())), name)
            } catch (e: Throwable) {
                errors += "$name: ${e.message ?: e.javaClass.simpleName}".take(90)
            }
        }
        throw OnlineFailed(errors.joinToString(" | "))
    }

    // prompt, resolution, seed, steps, time shift, random seed, gallery
    private fun zImageData(prompt: String) = JSONArray()
        .put(prompt).put("1024x1024 ( 1:1 )").put(Random().nextInt(2_000_000_000)).put(8).put(3.0).put(false).put(JSONArray())

    // prompt, seed, randomize seed, width, height, steps
    private fun fluxData(prompt: String) = JSONArray().put(prompt).put(0).put(true).put(1024).put(1024).put(4)

    private fun pollinations(prompt: String): ByteArray {
        val url = "https://image.pollinations.ai/prompt/" + Uri.encode(prompt) +
            "?width=1024&height=1024&nologo=true&seed=${Random().nextInt(1_000_000)}"
        return httpGet(url, 45_000).also { if (it.size < 1000) throw IOException("resposta vazia") }
    }

    /** Gradio's HTTP API: start a job, wait for the "complete" event, then download the picture. */
    private fun gradio(space: String, endpoint: String, data: JSONArray): ByteArray {
        val start = httpPost("$space/gradio_api/call/$endpoint", JSONObject().put("data", data).toString())
        val eventId = JSONObject(String(start)).getString("event_id")
        val events = String(httpGet("$space/gradio_api/call/$endpoint/$eventId", 100_000))
        val result = events.substringAfterLast("event: complete", "")
        if (result.isEmpty()) {
            // These Spaces run on shared "ZeroGPU": people without an account get a small daily GPU
            // allowance (per internet address), and past it the service fails at once with an empty
            // error. That is by far the usual cause, so say so.
            val error = events.substringAfter("event: error", "").lineSequence()
                .firstOrNull { it.trim().startsWith("data:") }?.substringAfter("data:")?.trim()?.trim('"')
            throw IOException(error?.takeIf { it.isNotBlank() && it != "null" } ?: "cota gratuita do dia esgotada ou serviço ocupado")
        }
        val url = Regex("\"url\":\\s*\"([^\"]+)\"").find(result)?.groupValues?.get(1)
            ?: throw IOException("a resposta veio sem imagem")
        return httpGet(if (url.startsWith("/")) space + url else url, 60_000)
    }

    /** Whatever format the service returned (PNG, WebP, JPEG) → a good JPEG for the gallery. */
    private fun reencode(bytes: ByteArray): ByteArray {
        val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size) ?: throw IOException("imagem corrompida")
        val out = ByteArrayOutputStream()
        bitmap.compress(Bitmap.CompressFormat.JPEG, 92, out)
        bitmap.recycle()
        return out.toByteArray()
    }

    private fun httpPost(url: String, json: String): ByteArray {
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = 20_000; c.readTimeout = 60_000; c.requestMethod = "POST"; c.doOutput = true
        c.setRequestProperty("Content-Type", "application/json")
        c.setRequestProperty("User-Agent", USER_AGENT)
        try {
            c.outputStream.use { it.write(json.toByteArray()) }
            if (c.responseCode !in 200..299) throw IOException("HTTP ${c.responseCode}")
            return c.inputStream.use { it.readBytes() }
        } finally { c.disconnect() }
    }

    private fun httpGet(url: String, readTimeout: Int): ByteArray {
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = 20_000; c.readTimeout = readTimeout; c.instanceFollowRedirects = true
        c.setRequestProperty("User-Agent", USER_AGENT)
        try {
            if (c.responseCode !in 200..299) throw IOException("HTTP ${c.responseCode}")
            return c.inputStream.use { it.readBytes() }
        } finally { c.disconnect() }
    }

    /** Blocking. Draws the picture on the phone and returns its gallery Uri. */
    fun generate(context: Context, prompt: String): Uri = synchronized(this) {
        // A GPU driver crash kills the app before any catch runs; the marker left behind tells us next time.
        if (prefs(context).getBoolean("gpu_running", false)) giveUpOnGpu(context, "o app fechou durante um desenho anterior")
        if (!isReady(context)) throw NotReadyException(gpuFailed = variant(context) == Variant.CPU && gpuFailed(context), detail = lastError(context))
        val variant = variant(context)
        val modelFile = File(dir(context), variant.fileName)
        if (variant == Variant.GPU) prefs(context).edit().putBoolean("gpu_running", true).commit()
        val pixels = try {
            run(context, modelFile, prompt)
        } catch (e: Throwable) {
            if (variant == Variant.GPU) {
                giveUpOnGpu(context, "${e.javaClass.simpleName}: ${e.message}".take(160))
                // The processor version may already be on the phone: use it right away.
                return@synchronized generate(context, prompt)
            }
            throw e
        } finally {
            prefs(context).edit().putBoolean("gpu_running", false).commit()
        }
        saveToGallery(context, toJpeg(pixels))
    }

    private fun gpuFailed(context: Context) = prefs(context).getBoolean("gpu_failed", false)

    /** Why the graphics-card version failed (kept to show in the chat, for diagnosis). */
    fun lastError(context: Context): String? = prefs(context).getString("last_error", null)

    /** This GPU can't run the model: switch to the processor version for good (downloaded on Wi-Fi only). */
    private fun giveUpOnGpu(context: Context, reason: String) {
        prefs(context).edit()
            .putBoolean("gpu_failed", true).putBoolean("gpu_running", false).putString("last_error", reason).commit()
        File(dir(context), Variant.GPU.fileName).delete()
        startDownload(context, onlyOnWifi = true)
    }

    private fun run(context: Context, modelFile: File, prompt: String): FloatArray {
        val clip = tokenizer ?: ClipTokenizer(
            File(dir(context), "vocab.json").readText(),
            File(dir(context), "merges.txt").readText()
        ).also { tokenizer = it }
        val ids = clip.encode(prompt)

        val module = Module.load(modelFile.path, Module.LOAD_MODE_MMAP)
        try {
            val embeddings = module.execute(
                "encode", EValue.from(Tensor.fromBlob(ids, longArrayOf(1, ClipTokenizer.MAX_TOKENS.toLong())))
            )[0].toTensor().dataAsFloatArray

            val random = Random(System.nanoTime())
            val latents = FloatArray(4 * 64 * 64) { random.nextGaussian().toFloat() }
            val noise = module.execute(
                "denoise",
                EValue.from(Tensor.fromBlob(latents, LATENT_SHAPE)),
                EValue.from(Tensor.fromBlob(longArrayOf(TIMESTEP), longArrayOf(1))),
                EValue.from(Tensor.fromBlob(embeddings, longArrayOf(1, ClipTokenizer.MAX_TOKENS.toLong(), 768)))
            )[0].toTensor().dataAsFloatArray
            for (i in latents.indices) latents[i] = SAMPLE_COEFF * latents[i] + NOISE_COEFF * noise[i]

            return module.execute("decode", EValue.from(Tensor.fromBlob(latents, LATENT_SHAPE)))[0].toTensor().dataAsFloatArray
        } finally {
            module.destroy()
        }
    }

    /** Planar RGB in 0..1 → JPEG. */
    private fun toJpeg(rgb: FloatArray): ByteArray {
        val plane = SIZE * SIZE
        fun channel(v: Float) = (v * 255f + 0.5f).toInt().coerceIn(0, 255)
        val argb = IntArray(plane) { i ->
            (0xFF shl 24) or (channel(rgb[i]) shl 16) or (channel(rgb[plane + i]) shl 8) or channel(rgb[2 * plane + i])
        }
        val bitmap = Bitmap.createBitmap(argb, SIZE, SIZE, Bitmap.Config.ARGB_8888)
        val out = ByteArrayOutputStream()
        bitmap.compress(Bitmap.CompressFormat.JPEG, 95, out)
        bitmap.recycle()
        return out.toByteArray()
    }

    /** Resumes a half-finished download (".part" file) instead of starting over. */
    private fun download(url: String, dest: File, onProgress: (Int) -> Unit) {
        val part = File(dest.path + ".part")
        val already = if (part.exists()) part.length() else 0L
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.instanceFollowRedirects = true
        connection.connectTimeout = 20_000
        connection.readTimeout = 30_000
        if (already > 0) connection.setRequestProperty("Range", "bytes=$already-")
        try {
            val code = connection.responseCode
            if (code !in 200..299) throw IOException("HTTP $code")
            val resumed = code == 206
            var done = if (resumed) already else 0L
            val total = done + connection.contentLengthLong
            connection.inputStream.use { input ->
                FileOutputStream(part, resumed).use { output ->
                    val buffer = ByteArray(256 * 1024)
                    while (true) {
                        val read = input.read(buffer)
                        if (read == -1) break
                        output.write(buffer, 0, read)
                        done += read
                        if (total > 0) onProgress(((done * 100) / total).toInt())
                    }
                }
            }
        } finally {
            connection.disconnect()
        }
        if (dest.exists()) dest.delete()
        if (!part.renameTo(dest)) throw IOException("rename failed")
    }

    private fun isMetered(context: Context): Boolean =
        context.getSystemService(ConnectivityManager::class.java)?.isActiveNetworkMetered ?: true

    private fun notificationManager(context: Context): NotificationManager {
        val manager = context.getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, "Gerador de imagens", NotificationManager.IMPORTANCE_LOW))
        }
        return manager
    }

    private fun notifyProgress(context: Context, percent: Int, variant: Variant) {
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_gota)
            .setContentTitle("Baixando o gerador de imagens offline")
            .setContentText("$percent% de ${variant.sizeMb} MB · só desta vez")
            .setProgress(100, percent, false)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .build()
        runCatching { notificationManager(context).notify(NOTIFICATION_ID, notification) }
    }

    private fun notifyDone(context: Context, title: String, text: String) {
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_gota)
            .setContentTitle(title)
            .setContentText(text)
            .setAutoCancel(true)
            .build()
        runCatching { notificationManager(context).notify(NOTIFICATION_ID, notification) }
    }

    private fun saveToGallery(context: Context, bytes: ByteArray): Uri {
        val name = "gota_${System.currentTimeMillis()}.jpg"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val resolver = context.contentResolver
            val values = ContentValues().apply {
                put(MediaStore.Images.Media.DISPLAY_NAME, name)
                put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
                put(MediaStore.Images.Media.RELATIVE_PATH, Environment.DIRECTORY_PICTURES + "/" + ALBUM)
                put(MediaStore.Images.Media.IS_PENDING, 1)
            }
            val uri = resolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values)
                ?: throw IllegalStateException("Não consegui salvar na galeria.")
            resolver.openOutputStream(uri)?.use { it.write(bytes) }
            values.clear()
            values.put(MediaStore.Images.Media.IS_PENDING, 0)
            resolver.update(uri, values, null, null)
            return uri
        }
        @Suppress("DEPRECATION")
        val dir = File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES), ALBUM).apply { mkdirs() }
        val file = File(dir, name).apply { writeBytes(bytes) }
        MediaScannerConnection.scanFile(context, arrayOf(file.path), arrayOf("image/jpeg"), null)
        return Uri.fromFile(file)
    }
}
