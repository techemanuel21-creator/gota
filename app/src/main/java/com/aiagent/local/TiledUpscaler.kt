package com.aiagent.local

/**
 * Enlarges a picture with a model that only takes small fixed-size tiles (Real-ESRGAN here, 128 px
 * in, 512 px out). The picture is cut into overlapping tiles, each tile is enlarged by [run], and the
 * results are blended with soft edges so no seams show. Pure arithmetic, so it can be tested on a
 * computer with a fake [run].
 *
 * Pictures are planar: all red values, then all green, then all blue, each row after row.
 */
object TiledUpscaler {

    /** Where each tile starts along one axis; the last tile is moved back so it ends at the edge. */
    fun positions(size: Int, tile: Int, overlap: Int): IntArray {
        require(size >= tile) { "picture ($size) is smaller than a tile ($tile)" }
        val stride = tile - overlap
        val starts = ArrayList<Int>()
        var p = 0
        while (p + tile < size) {
            starts += p
            p += stride
        }
        starts += size - tile
        return starts.distinct().toIntArray()
    }

    /**
     * Weight of every output pixel of tile [index] (of [count]) along one axis: it fades in and out
     * over [ramp] pixels, except on the outer edges of the picture, where it stays at 1.
     */
    fun axisWeights(index: Int, count: Int, length: Int, ramp: Int): FloatArray = FloatArray(length) { u ->
        val left = if (index > 0) (u.toFloat() / ramp).coerceIn(MIN_WEIGHT, 1f) else 1f
        val right = if (index < count - 1) (((length - 1) - u).toFloat() / ramp).coerceIn(MIN_WEIGHT, 1f) else 1f
        minOf(left, right)
    }

    /**
     * @param rgb the square picture, planar, values 0..1, [size] × [size]
     * @param run enlarges one planar tile (3 × tile × tile) into 3 × (tile·scale) × (tile·scale); it may
     *            reuse its input array afterwards, so it must not keep it
     * @return opaque ARGB pixels of the enlarged picture, row after row
     */
    fun upscale(
        rgb: FloatArray,
        size: Int,
        tile: Int,
        overlap: Int,
        scale: Int,
        run: (FloatArray) -> FloatArray,
        onProgress: (done: Int, total: Int) -> Unit = { _, _ -> }
    ): IntArray {
        val starts = positions(size, tile, overlap)
        val out = size * scale
        val outPlane = out * out
        val plane = size * size
        val tilePixels = tile * tile
        val tileOut = tile * scale
        val tileOutPlane = tileOut * tileOut
        val ramp = overlap * scale

        val acc = FloatArray(3 * outPlane)
        val weightSum = FloatArray(outPlane)
        val tileIn = FloatArray(3 * tilePixels)
        val total = starts.size * starts.size
        var done = 0

        for ((iy, y0) in starts.withIndex()) {
            val wy = axisWeights(iy, starts.size, tileOut, ramp)
            for ((ix, x0) in starts.withIndex()) {
                val wx = axisWeights(ix, starts.size, tileOut, ramp)
                for (c in 0 until 3) {
                    for (y in 0 until tile) {
                        System.arraycopy(rgb, c * plane + (y0 + y) * size + x0, tileIn, c * tilePixels + y * tile, tile)
                    }
                }
                val up = run(tileIn)
                for (y in 0 until tileOut) {
                    val rowWeight = wy[y]
                    val dstRow = (y0 * scale + y) * out + x0 * scale
                    val srcRow = y * tileOut
                    for (x in 0 until tileOut) {
                        val w = rowWeight * wx[x]
                        val d = dstRow + x
                        weightSum[d] += w
                        acc[d] += up[srcRow + x] * w
                        acc[outPlane + d] += up[tileOutPlane + srcRow + x] * w
                        acc[2 * outPlane + d] += up[2 * tileOutPlane + srcRow + x] * w
                    }
                }
                onProgress(++done, total)
            }
        }

        fun channel(value: Float, weight: Float) = ((value / weight).coerceIn(0f, 1f) * 255f + 0.5f).toInt()
        return IntArray(outPlane) { i ->
            val w = weightSum[i]
            (0xFF shl 24) or (channel(acc[i], w) shl 16) or (channel(acc[outPlane + i], w) shl 8) or channel(acc[2 * outPlane + i], w)
        }
    }

    private const val MIN_WEIGHT = 1e-3f
}
