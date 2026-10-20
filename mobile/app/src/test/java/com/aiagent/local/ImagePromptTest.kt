package com.aiagent.local

import org.junit.Assert.assertEquals
import org.junit.Test

class ImagePromptTest {

    @Test
    fun plainRequestsGetPhotoWords() {
        assertEquals(ImagePrompt.PHOTO, ImagePrompt.suffixFor("a gray cat sitting on a roof, natural light"))
    }

    @Test
    fun cartoonLikeRequestsGetCleanLineWords() {
        assertEquals(ImagePrompt.ART, ImagePrompt.suffixFor("a cartoon cat on a roof"))
        assertEquals(ImagePrompt.ART, ImagePrompt.suffixFor("pixel art knight"))
        assertEquals(ImagePrompt.ART, ImagePrompt.suffixFor("3D render of a house"))
        assertEquals(ImagePrompt.ART, ImagePrompt.suffixFor("anime girl with a sword"))
    }

    @Test
    fun paintingRequestsAreNotForcedIntoPhotos() {
        assertEquals(ImagePrompt.PAINTING, ImagePrompt.suffixFor("an oil painting of a harbour"))
        assertEquals(ImagePrompt.PAINTING, ImagePrompt.suffixFor("Watercolor flowers"))
    }

    @Test
    fun wordsInsideOtherWordsDoNotCount() {
        // "rendering" / "drawings" aren't styles by themselves; "render" as a whole word is.
        assertEquals(ImagePrompt.PHOTO, ImagePrompt.suffixFor("a photo of a gender reveal party"))
    }
}
