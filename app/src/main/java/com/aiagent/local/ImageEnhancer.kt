package com.aiagent.local

import java.util.Random
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.exp

/**
 * Finishing touches for the 512×512 pictures of the on-device painter, which draws in a single
 * step and so looks smooth, almost like oil paint. Pure pixel maths (no Android classes), so it can
 * be tested on a computer:
 *  1. enlarges to 1024×1024 with bicubic (Catmull-Rom) interpolation, much crisper than the
 *     gallery's own smooth zoom;
 *  2. sharpens fine detail, on brightness only so colours don't get fringes, with a limit so
 *     edges don't grow halos;
 *  3. adds "clarity" (contrast in medium-sized areas) to take away the flat painted look;
 *  4. adds a very light film grain, which makes surfaces read as texture instead of paint;
 *  5. a touch of contrast and colour.
 */
object ImageEnhancer {

    class Result(val pixels: IntArray, val width: Int, val height: Int)

    /** [argb] are opaque ARGB pixels, row by row. Returns the picture at twice the size. */
    fun enhance(argb: IntArray, width: Int, height: Int, seed: Long = System.nanoTime()): Result {
        require(argb.size == width * height) { "pixel count does not match the size" }
        val w2 = width * 2
        val h2 = height * 2

        val r = FloatArray(width * height) { ((argb[it] shr 16) and 0xFF).toFloat() }
        val g = FloatArray(width * height) { ((argb[it] shr 8) and 0xFF).toFloat() }
        val b = FloatArray(width * height) { (argb[it] and 0xFF).toFloat() }
        val rr = upscale2x(r, width, height)
        val gg = upscale2x(g, width, height)
        val bb = upscale2x(b, width, height)

        val n = w2 * h2
        val luma = FloatArray(n) { 0.299f * rr[it] + 0.587f * gg[it] + 0.114f * bb[it] }

        // Fine detail: difference between the picture and a slightly blurred copy.
        val fine = gaussianBlur(luma, w2, h2, FINE_SIGMA)
        // Medium-scale contrast ("clarity").
        val broad = boxBlurApprox(luma, w2, h2, BROAD_RADIUS)

        val noise = Random(seed)
        val out = IntArray(n)
        for (i in 0 until n) {
            val y = luma[i]
            var delta = (y - fine[i]) * SHARPEN_AMOUNT
            delta = delta.coerceIn(-SHARPEN_LIMIT, SHARPEN_LIMIT)

            // Clarity matters most in the middle tones; bright and dark areas are left alone.
            val mid = 1f - abs(y / 127.5f - 1f)
            delta += (y - broad[i]) * CLARITY_AMOUNT * mid

            // Grain, a little stronger in the middle tones too, the same on every colour channel.
            delta += (noise.nextGaussian().toFloat()) * GRAIN_SIGMA * (0.45f + 0.55f * mid)

            var red = rr[i] + delta
            var green = gg[i] + delta
            var blue = bb[i] + delta

            // Gentle colour: a little more saturation, and a very light S-curve for contrast.
            val gray = 0.299f * red + 0.587f * green + 0.114f * blue
            red = gray + (red - gray) * SATURATION
            green = gray + (green - gray) * SATURATION
            blue = gray + (blue - gray) * SATURATION
            out[i] = (0xFF shl 24) or (tone(red) shl 16) or (tone(green) shl 8) or tone(blue)
        }
        return Result(out, w2, h2)
    }

    /** Clamps to 0..255 after a light S-curve (a blend with smoothstep) that deepens shadows and brightens lights. */
    private fun tone(v: Float): Int {
        val x = (v / 255f).coerceIn(0f, 1f)
        val smooth = x * x * (3f - 2f * x)
        val curved = x + CONTRAST * (smooth - x)
        return (curved * 255f + 0.5f).toInt()
    }

    // ---------- bicubic upscaling ----------

    /** Catmull-Rom weights for the four neighbours around a position [t] (0..1) between two pixels. */
    private fun weights(t: Float): FloatArray {
        val t2 = t * t
        val t3 = t2 * t
        return floatArrayOf(
            -0.5f * t3 + t2 - 0.5f * t,
            1.5f * t3 - 2.5f * t2 + 1f,
            -1.5f * t3 + 2f * t2 + 0.5f * t,
            0.5f * t3 - 0.5f * t2
        )
    }

    /** Doubles a single channel. Output pixel centres fall a quarter pixel either side of each source pixel. */
    private fun upscale2x(src: FloatArray, w: Int, h: Int): FloatArray {
        val w2 = w * 2
        val h2 = h * 2
        // Two phases: the output pixel 2i sits 0.25 before source pixel i, the one at 2i+1 sits 0.25 after.
        val wEven = weights(0.75f) // between i-1 and i, closer to i
        val wOdd = weights(0.25f)  // between i and i+1, closer to i

        // Horizontal pass: w × h → w2 × h
        val tmp = FloatArray(w2 * h)
        for (y in 0 until h) {
            val row = y * w
            for (x in 0 until w) {
                val xm = (x - 1).coerceAtLeast(0)
                val xp = (x + 1).coerceAtMost(w - 1)
                val xpp = (x + 2).coerceAtMost(w - 1)
                val xmm = (x - 2).coerceAtLeast(0)
                // even output (2x): taps at x-2, x-1, x, x+1 with phase 0.75
                tmp[y * w2 + 2 * x] =
                    wEven[0] * src[row + xmm] + wEven[1] * src[row + xm] + wEven[2] * src[row + x] + wEven[3] * src[row + xp]
                // odd output (2x+1): taps at x-1, x, x+1, x+2 with phase 0.25
                tmp[y * w2 + 2 * x + 1] =
                    wOdd[0] * src[row + xm] + wOdd[1] * src[row + x] + wOdd[2] * src[row + xp] + wOdd[3] * src[row + xpp]
            }
        }
        // Vertical pass: w2 × h → w2 × h2
        val out = FloatArray(w2 * h2)
        for (y in 0 until h) {
            val ym = (y - 1).coerceAtLeast(0)
            val yp = (y + 1).coerceAtMost(h - 1)
            val ypp = (y + 2).coerceAtMost(h - 1)
            val ymm = (y - 2).coerceAtLeast(0)
            for (x in 0 until w2) {
                out[(2 * y) * w2 + x] =
                    (wEven[0] * tmp[ymm * w2 + x] + wEven[1] * tmp[ym * w2 + x] + wEven[2] * tmp[y * w2 + x] + wEven[3] * tmp[yp * w2 + x])
                        .coerceIn(0f, 255f)
                out[(2 * y + 1) * w2 + x] =
                    (wOdd[0] * tmp[ym * w2 + x] + wOdd[1] * tmp[y * w2 + x] + wOdd[2] * tmp[yp * w2 + x] + wOdd[3] * tmp[ypp * w2 + x])
                        .coerceIn(0f, 255f)
            }
        }
        return out
    }

    // ---------- blurs ----------

    /** Separable Gaussian blur with edges repeated. */
    private fun gaussianBlur(src: FloatArray, w: Int, h: Int, sigma: Float): FloatArray {
        val radius = ceil(sigma * 3f).toInt()
        val kernel = FloatArray(2 * radius + 1)
        var sum = 0f
        for (i in kernel.indices) {
            val d = (i - radius).toFloat()
            kernel[i] = exp(-(d * d) / (2f * sigma * sigma))
            sum += kernel[i]
        }
        for (i in kernel.indices) kernel[i] /= sum

        val tmp = FloatArray(w * h)
        for (y in 0 until h) {
            val row = y * w
            for (x in 0 until w) {
                var acc = 0f
                for (k in -radius..radius) acc += kernel[k + radius] * src[row + (x + k).coerceIn(0, w - 1)]
                tmp[row + x] = acc
            }
        }
        val out = FloatArray(w * h)
        for (y in 0 until h) {
            for (x in 0 until w) {
                var acc = 0f
                for (k in -radius..radius) acc += kernel[k + radius] * tmp[(y + k).coerceIn(0, h - 1) * w + x]
                out[y * w + x] = acc
            }
        }
        return out
    }

    /** Three box blurs in a row, which approximates a wide Gaussian very cheaply. */
    private fun boxBlurApprox(src: FloatArray, w: Int, h: Int, radius: Int): FloatArray {
        var cur = src
        repeat(3) { cur = boxBlurVertical(boxBlurHorizontal(cur, w, h, radius), w, h, radius) }
        return cur
    }

    private fun boxBlurHorizontal(src: FloatArray, w: Int, h: Int, r: Int): FloatArray {
        val out = FloatArray(w * h)
        val size = (2 * r + 1).toFloat()
        for (y in 0 until h) {
            val row = y * w
            var acc = 0f
            for (k in -r..r) acc += src[row + k.coerceIn(0, w - 1)]
            for (x in 0 until w) {
                out[row + x] = acc / size
                acc += src[row + (x + r + 1).coerceAtMost(w - 1)] - src[row + (x - r).coerceAtLeast(0)]
            }
        }
        return out
    }

    private fun boxBlurVertical(src: FloatArray, w: Int, h: Int, r: Int): FloatArray {
        val out = FloatArray(w * h)
        val size = (2 * r + 1).toFloat()
        for (x in 0 until w) {
            var acc = 0f
            for (k in -r..r) acc += src[k.coerceIn(0, h - 1) * w + x]
            for (y in 0 until h) {
                out[y * w + x] = acc / size
                acc += src[(y + r + 1).coerceAtMost(h - 1) * w + x] - src[(y - r).coerceAtLeast(0) * w + x]
            }
        }
        return out
    }

    // Tuned by eye on soft, painterly 512 px pictures (see the unit test that writes a before/after).
    private const val FINE_SIGMA = 1.5f
    private const val SHARPEN_AMOUNT = 0.9f
    private const val SHARPEN_LIMIT = 26f
    private const val BROAD_RADIUS = 12
    private const val CLARITY_AMOUNT = 0.22f
    private const val GRAIN_SIGMA = 1.6f
    private const val SATURATION = 1.05f
    private const val CONTRAST = 0.35f
}
