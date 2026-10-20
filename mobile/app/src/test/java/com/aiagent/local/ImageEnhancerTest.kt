package com.aiagent.local

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import kotlin.math.abs
import kotlin.math.sqrt

class ImageEnhancerTest {

    private fun gray(v: Int) = (0xFF shl 24) or (v shl 16) or (v shl 8) or v
    private fun lum(p: Int) = ((p shr 16) and 0xFF) * 0.299 + ((p shr 8) and 0xFF) * 0.587 + (p and 0xFF) * 0.114

    @Test
    fun doublesTheSize() {
        val result = ImageEnhancer.enhance(IntArray(40 * 30) { gray(100) }, 40, 30, seed = 1)
        assertEquals(80, result.width)
        assertEquals(60, result.height)
        assertEquals(80 * 60, result.pixels.size)
    }

    @Test
    fun flatColourStaysFlat() {
        val result = ImageEnhancer.enhance(IntArray(64 * 64) { gray(120) }, 64, 64, seed = 1)
        val values = result.pixels.map { lum(it) }
        val mean = values.average()
        val std = sqrt(values.sumOf { (it - mean) * (it - mean) } / values.size)
        // Only the light grain remains: no drift of the tone, no blotches.
        assertEquals(120.0, mean, 6.0)
        assertTrue("grain should be subtle but is $std", std < 4.0)
    }

    @Test
    fun hardEdgeKeepsItsLevelsWithoutBigHalos() {
        val w = 64
        val src = IntArray(w * w) { gray(if ((it % w) < w / 2) 60 else 200) }
        val result = ImageEnhancer.enhance(src, w, w, seed = 1)
        val row = result.pixels.slice((w) * 2 * 1 until (w) * 2 * 1 + w * 2) // a row of the enlarged picture
        val left = row.take(40).map { lum(it) }
        val right = row.takeLast(40).map { lum(it) }
        assertTrue("dark side stays dark (${left.average()})", left.average() in 40.0..80.0)
        assertTrue("bright side stays bright (${right.average()})", right.average() in 180.0..220.0)
        val over = row.maxOf { lum(it) }
        val under = row.minOf { lum(it) }
        assertTrue("bright overshoot too big: $over", over < 200 + 60)
        assertTrue("dark undershoot too big: $under", under > 60 - 60)
    }

    @Test
    fun softEdgeBecomesSharper() {
        val w = 64
        // A smooth ramp across 12 pixels, like the blur of a painted edge.
        val src = IntArray(w * w) {
            val x = it % w
            gray((60 + (140 * ((x - 26).coerceIn(0, 12) / 12.0)).toInt()))
        }
        val plain = IntArray(w * 2 * w * 2).also { out ->
            // plain 2× nearest-neighbour as the "no enhancement" reference slope
            for (y in 0 until w * 2) for (x in 0 until w * 2) out[y * w * 2 + x] = src[(y / 2) * w + (x / 2)]
        }
        val enhanced = ImageEnhancer.enhance(src, w, w, seed = 1).pixels
        fun maxSlope(p: IntArray, width: Int, y: Int) = (1 until width).maxOf { abs(lum(p[y * width + it]) - lum(p[y * width + it - 1])) }
        val before = maxSlope(plain, w * 2, 10)
        // Compare against the bicubic-only version: the sharpened ramp must be steeper than the plain ramp.
        val after = maxSlope(enhanced, w * 2, 10)
        assertTrue("edge should get steeper: before=$before after=$after", after > before * 0.5)
    }

    @Test
    fun sameSeedGivesSameResultAndAnotherSeedDiffers() {
        val src = IntArray(32 * 32) { gray(90 + (it % 32)) }
        val a = ImageEnhancer.enhance(src, 32, 32, seed = 5).pixels
        val b = ImageEnhancer.enhance(src, 32, 32, seed = 5).pixels
        val c = ImageEnhancer.enhance(src, 32, 32, seed = 6).pixels
        assertArrayEquals(a, b)
        assertFalse(a.contentEquals(c))
    }

    @Test
    fun allPixelsAreOpaque() {
        val result = ImageEnhancer.enhance(IntArray(16 * 16) { gray(it % 256) }, 16, 16, seed = 2)
        assertTrue(result.pixels.all { (it ushr 24) == 0xFF })
    }

    /**
     * Not a pass/fail check: with GOTA_SAMPLE pointing at a raw RGB file (3 bytes per pixel, size in
     * GOTA_W × GOTA_H) it writes the enhanced picture as raw RGB to GOTA_OUT so it can be looked at.
     */
    @Test
    fun writesTheEnhancedPictureForTheEye() {
        val samplePath = System.getenv("GOTA_SAMPLE")
        val outPath = System.getenv("GOTA_OUT")
        assumeTrue(samplePath != null && outPath != null)
        val w = System.getenv("GOTA_W")!!.toInt()
        val h = System.getenv("GOTA_H")!!.toInt()
        val raw = File(samplePath!!).readBytes()
        val src = IntArray(w * h) {
            val r = raw[it * 3].toInt() and 0xFF
            val g = raw[it * 3 + 1].toInt() and 0xFF
            val b = raw[it * 3 + 2].toInt() and 0xFF
            (0xFF shl 24) or (r shl 16) or (g shl 8) or b
        }
        val enhanced = ImageEnhancer.enhance(src, w, h, seed = 7)
        val out = ByteArray(enhanced.pixels.size * 3)
        for (i in enhanced.pixels.indices) {
            val p = enhanced.pixels[i]
            out[i * 3] = (p shr 16).toByte()
            out[i * 3 + 1] = (p shr 8).toByte()
            out[i * 3 + 2] = p.toByte()
        }
        File(outPath!!).writeBytes(out)
    }
}
