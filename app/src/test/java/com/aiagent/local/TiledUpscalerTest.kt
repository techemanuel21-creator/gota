package com.aiagent.local

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Random
import kotlin.math.abs

class TiledUpscalerTest {

    @Test
    fun tilesCoverTheWholePictureAndEndAtTheEdge() {
        assertArrayEquals(intArrayOf(0, 96, 192, 288, 384), TiledUpscaler.positions(512, 128, 32))
        assertArrayEquals(intArrayOf(0, 96, 192, 288, 372), TiledUpscaler.positions(500, 128, 32))
        assertArrayEquals(intArrayOf(0), TiledUpscaler.positions(128, 128, 32))
    }

    @Test
    fun everyPixelIsCoveredByAtLeastOneTile() {
        for (size in listOf(128, 129, 200, 257, 512)) {
            val covered = BooleanArray(size)
            for (start in TiledUpscaler.positions(size, 128, 32)) for (i in start until start + 128) covered[i] = true
            assertTrue("size $size", covered.all { it })
        }
    }

    @Test
    fun edgesFadeOnlyBetweenTiles() {
        val first = TiledUpscaler.axisWeights(0, 3, 64, 16)
        val middle = TiledUpscaler.axisWeights(1, 3, 64, 16)
        val last = TiledUpscaler.axisWeights(2, 3, 64, 16)
        assertEquals(1f, first[0], 0f)            // the picture's own edge is never faded
        assertTrue(first[63] < 0.1f)               // it fades out towards the next tile
        assertTrue(middle[0] < 0.1f && middle[63] < 0.1f)
        assertEquals(1f, middle[32], 0f)
        assertTrue(last[0] < 0.1f)
        assertEquals(1f, last[63], 0f)
    }

    /** With a "model" that just repeats pixels, blending the tiles must give back exactly that. */
    @Test
    fun blendingTilesGivesTheSamePictureAsEnlargingItWhole() {
        val size = 70
        val tile = 32
        val scale = 4
        val random = Random(3)
        val rgb = FloatArray(3 * size * size) { random.nextFloat() }

        val fake: (FloatArray) -> FloatArray = { t ->
            val out = FloatArray(3 * tile * scale * tile * scale)
            for (c in 0 until 3) for (y in 0 until tile * scale) for (x in 0 until tile * scale) {
                out[c * tile * scale * tile * scale + y * tile * scale + x] = t[c * tile * tile + (y / scale) * tile + (x / scale)]
            }
            out
        }
        val result = TiledUpscaler.upscale(rgb, size, tile, overlap = 8, scale = scale, run = fake)

        val big = size * scale
        assertEquals(big * big, result.size)
        var worst = 0
        for (c in 0 until 3) for (y in 0 until big) for (x in 0 until big) {
            val expected = (rgb[c * size * size + (y / scale) * size + (x / scale)] * 255f + 0.5f).toInt()
            val shift = 16 - 8 * c
            val actual = (result[y * big + x] shr shift) and 0xFF
            worst = maxOf(worst, abs(expected - actual))
        }
        assertTrue("worst difference $worst levels", worst <= 1)
        assertTrue(result.all { (it ushr 24) == 0xFF })
    }

    @Test
    fun reportsProgress() {
        val calls = ArrayList<Pair<Int, Int>>()
        val size = 40
        TiledUpscaler.upscale(FloatArray(3 * size * size), size, 32, 8, 2, run = { FloatArray(3 * 64 * 64) }) { done, total -> calls += done to total }
        assertEquals(4, calls.size)               // 2 × 2 tiles
        assertEquals(4 to 4, calls.last())
    }
}
