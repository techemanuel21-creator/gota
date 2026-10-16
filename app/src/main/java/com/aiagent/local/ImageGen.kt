package com.aiagent.local

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.ContentValues
import android.content.Context
import android.graphics.Bitmap
import android.media.MediaScannerConnection
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
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
 * Creates images 100% on the phone, with no internet, using SDXS-512 DreamShaper: a distilled
 * Stable Diffusion that draws a 512×512 picture in a single step. It runs on the GPU (Vulkan);
 * if this phone's GPU can't run it, the processor version is used instead. Because one step makes
 * smooth, painterly pictures, they get a finishing pass ([ImageEnhancer]) and quality words are
 * added to the request ([ImagePrompt]). Pictures go to the gallery, in the "GOTA IA" album.
 *
 * The model is downloaded once, on Wi-Fi, when the app is first used.
 */
object ImageGen {

    private const val REPO = "https://huggingface.co/software-mansion/react-native-executorch-sdxs-512-dreamshaper/resolve/main/"
    private const val TOKENIZER_REPO = "https://huggingface.co/IDKiro/sdxs-512-dreamshaper/resolve/main/tokenizer/"

    enum class Variant(val url: String, val fileName: String, val sizeMb: Int) {
        GPU(REPO + "vulkan/sdxs_512_dreamshaper_vulkan_fp16.pte", "sdxs_gpu.pte", 840),
        CPU(REPO + "xnnpack/sdxs_512_dreamshaper_xnnpack_fp32.pte", "sdxs_cpu.pte", 1679)
    }

    /** The painter can't draw yet: not downloaded, or its graphics-card version failed ([gpuFailed]). */
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

    /** Why the graphics-card version failed (kept to show in the chat, for diagnosis). */
    fun lastError(context: Context): String? = prefs(context).getString("last_error", null)

    /** True on an unmetered connection (Wi-Fi), where a big download costs nothing. */
    fun canDownloadNow(context: Context): Boolean {
        val cm = context.getSystemService(ConnectivityManager::class.java) ?: return false
        val caps = cm.getNetworkCapabilities(cm.activeNetwork ?: return false) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) && !cm.isActiveNetworkMetered
    }

    /** Downloads the image model in the background (once). [onlyOnWifi] avoids spending mobile data unasked. */
    fun startDownload(context: Context, onlyOnWifi: Boolean = false) {
        val app = context.applicationContext
        if (downloading || isReady(app)) return
        if (onlyOnWifi && !canDownloadNow(app)) return
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
                notifyDone(app, "Gerador de imagens pronto", "Já posso criar imagens. É só pedir.")
            } catch (e: Exception) {
                notifyDone(app, "Download do gerador de imagens parou", "Abra o Gota no Wi-Fi para eu continuar de onde parou.")
            } finally {
                downloading = false
            }
        }
    }

    /** Blocking. Draws the picture on the phone and returns its gallery Uri. */
    fun generate(context: Context, prompt: String): Uri = synchronized(this) {
        // A GPU driver crash kills the app before any catch runs; the marker left behind tells us next time.
        if (prefs(context).getBoolean("gpu_running", false)) giveUpOnGpu(context, "o app fechou durante um desenho anterior")
        if (!isReady(context)) {
            throw NotReadyException(gpuFailed = prefs(context).getBoolean("gpu_failed", false), detail = lastError(context))
        }
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
        saveToGallery(context, finish(pixels))
    }

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
        // The request first, then quality words that are kept even if the request is long.
        val ids = clip.encode(prompt, ImagePrompt.suffixFor(prompt))

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

    /** Planar RGB in 0..1 → enlarged, sharpened picture → JPEG. */
    private fun finish(rgb: FloatArray): ByteArray {
        val plane = SIZE * SIZE
        fun channel(v: Float) = (v * 255f + 0.5f).toInt().coerceIn(0, 255)
        val argb = IntArray(plane) { i ->
            (0xFF shl 24) or (channel(rgb[i]) shl 16) or (channel(rgb[plane + i]) shl 8) or channel(rgb[2 * plane + i])
        }
        val big = ImageEnhancer.enhance(argb, SIZE, SIZE)
        val bitmap = Bitmap.createBitmap(big.pixels, big.width, big.height, Bitmap.Config.ARGB_8888)
        val out = ByteArrayOutputStream()
        bitmap.compress(Bitmap.CompressFormat.JPEG, 93, out)
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
            .setContentTitle("Baixando o gerador de imagens")
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
