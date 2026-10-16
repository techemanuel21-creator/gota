package com.aiagent.local

import android.content.Context
import org.pytorch.executorch.EValue
import org.pytorch.executorch.Module
import org.pytorch.executorch.Tensor
import java.io.File

/**
 * The two finishing models that take the painter's raw output from "rough" to clean:
 *  - the full Stable Diffusion image decoder, which turns the painter's latents into a picture
 *    without the jagged edges and odd eyes of the tiny decoder built into the painter;
 *  - Real-ESRGAN, which enlarges the 512 px picture to 2048 px and sharpens hair, fabric and edges.
 *
 * Both ship inside the app (they are small enough, and nothing has to be downloaded), are copied once
 * to the phone's storage, and run through the same ExecuTorch engine as the painter. They are slow
 * (tens of seconds) and use a lot of memory, so each is loaded, used and released in turn.
 */
object ImageRefiner {

    private const val ASSET_DIR = "imagegen"
    const val VAE = "vae_decoder_fp32.pte"
    const val ESRGAN = "esrgan_x4_128_fp32.pte"

    private const val SIZE = 512
    private const val TILE = 128
    private const val OVERLAP = 32
    private const val SCALE = 4

    /** Side of the finished picture, in pixels. */
    const val OUTPUT_SIZE = SIZE * SCALE

    /** True when this build of the app carries both models. */
    fun isBundled(context: Context): Boolean {
        val names = runCatching { context.assets.list(ASSET_DIR)?.toSet() }.getOrNull() ?: return false
        return VAE in names && ESRGAN in names
    }

    private fun file(context: Context, name: String) = File(File(context.filesDir, ASSET_DIR).apply { mkdirs() }, name)

    /** Copies the models out of the app package (once, or again after an update that changed them). */
    fun prepare(context: Context) {
        for (name in listOf(VAE, ESRGAN)) {
            val target = file(context, name)
            val size = context.assets.openFd("$ASSET_DIR/$name").use { it.length }
            if (target.exists() && target.length() == size) continue
            val temp = File(target.path + ".part")
            context.assets.open("$ASSET_DIR/$name").use { input -> temp.outputStream().use { input.copyTo(it, 1 shl 20) } }
            if (target.exists()) target.delete()
            check(temp.renameTo(target)) { "could not store $name" }
        }
    }

    /** Latents from the painter (4×64×64) → planar RGB, 0..1, 3×512×512. */
    fun decode(context: Context, latents: FloatArray): FloatArray {
        val module = Module.load(file(context, VAE).path, Module.LOAD_MODE_MMAP)
        try {
            return module.execute("forward", EValue.from(Tensor.fromBlob(latents, longArrayOf(1, 4, 64, 64))))[0]
                .toTensor().dataAsFloatArray
        } finally {
            module.destroy()
        }
    }

    /** Planar RGB 3×512×512 → ARGB pixels of the 2048×2048 picture. */
    fun upscale(context: Context, rgb: FloatArray, onProgress: (done: Int, total: Int) -> Unit): IntArray {
        val module = Module.load(file(context, ESRGAN).path, Module.LOAD_MODE_MMAP)
        try {
            return TiledUpscaler.upscale(rgb, SIZE, TILE, OVERLAP, SCALE, run = { tile ->
                module.execute("forward", EValue.from(Tensor.fromBlob(tile, longArrayOf(1, 3, TILE.toLong(), TILE.toLong()))))[0]
                    .toTensor().dataAsFloatArray
            }, onProgress = onProgress)
        } finally {
            module.destroy()
        }
    }
}
