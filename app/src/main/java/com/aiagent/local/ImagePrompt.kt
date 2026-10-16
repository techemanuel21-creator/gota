package com.aiagent.local

/**
 * Prepares a picture request for the painter, a tiny one-step model that is good at faces and
 * simple scenes but draws hands and paws badly:
 *  - [sanitize] takes out the words that make it draw them ("holding a cup", "his paws"...);
 *  - [suffixFor] adds quality words after the request (sharp photo, clean lines or painting) and,
 *    when there is a face, "detailed eyes".
 * The quality words go at the END (see [ClipTokenizer.encode]), so a long request is shortened
 * before they are.
 */
object ImagePrompt {

    private val PAINTERLY = Regex("\\b(oil painting|painting|watercolou?r|impressionis\\w*|brush ?strokes?|gouache|acrylic)\\b")
    private val STYLED = Regex(
        "\\b(cartoon|anime|manga|comic|illustration|drawing|sketch|pixel art|vector|3d render|render|digital art|" +
            "logo|icon|flat design|clay|lego|isometric|low poly|cel.?shaded)\\b"
    )
    private val FACE = Regex(
        "\\b(cats?|kittens?|dogs?|pupp(?:y|ies)|person|people|man|men|woman|women|girl|boy|child|portrait|face|" +
            "butler|lady|gentleman|king|queen|robot|fox|wolf|lion|bear|owl|horse|elf|wizard|knight)\\b"
    )

    private val HOLDING = Regex("\\b(holding|carrying|gripping|clutching|serving|pouring|grasping)\\b")
    private val HANDS = Regex("\\b(?:with\\s+(?:his|her|its|their|both|two)\\s+)?(?:hands?|paws?|fingers?)\\b")

    const val PHOTO = "RAW photo, sharp focus, highly detailed, natural lighting, realistic textures, 8k uhd"
    const val ART = "clean crisp lines, highly detailed, sharp focus, smooth shading, high quality"
    const val PAINTING = "highly detailed, beautiful, masterpiece, high quality"
    const val EYES = "detailed eyes, symmetrical face"

    /** "a cat holding a teacup with his paws" → "a cat beside a teacup". */
    fun sanitize(prompt: String): String =
        prompt.lowercase()
            .replace(HANDS, " ")
            .replace(HOLDING, "beside")
            .replace(Regex("\\s{2,}"), " ")
            .replace(Regex("\\s+,"), ",")
            .trim()

    fun suffixFor(prompt: String): String {
        val p = prompt.lowercase()
        val base = when {
            PAINTERLY.containsMatchIn(p) -> PAINTING
            STYLED.containsMatchIn(p) -> ART
            else -> PHOTO
        }
        return if (FACE.containsMatchIn(p)) "$base, $EYES" else base
    }
}
