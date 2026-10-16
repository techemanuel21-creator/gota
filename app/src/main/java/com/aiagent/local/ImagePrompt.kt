package com.aiagent.local

/**
 * Words added after the person's request when asking the painter for a picture. The painter is a
 * tiny one-step model, and quality words steer it towards sharp, clean results. They go at the END
 * (see [ClipTokenizer.encode]), so a long request is shortened before these words are.
 */
object ImagePrompt {

    private val PAINTERLY = Regex("\\b(oil painting|painting|watercolou?r|impressionis\\w*|brush ?strokes?|gouache|acrylic)\\b")
    private val STYLED = Regex(
        "\\b(cartoon|anime|manga|comic|illustration|drawing|sketch|pixel art|vector|3d render|render|digital art|" +
            "logo|icon|flat design|clay|lego|isometric|low poly|cel.?shaded)\\b"
    )

    const val PHOTO = "RAW photo, sharp focus, highly detailed, natural lighting, realistic textures, 8k uhd"
    const val ART = "clean crisp lines, highly detailed, sharp focus, smooth shading, high quality"
    const val PAINTING = "highly detailed, beautiful, masterpiece, high quality"

    fun suffixFor(prompt: String): String {
        val p = prompt.lowercase()
        return when {
            PAINTERLY.containsMatchIn(p) -> PAINTING
            STYLED.containsMatchIn(p) -> ART
            else -> PHOTO
        }
    }
}
