package com.aiagent.local

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ImagePromptTest {

    @Test
    fun scenesWithoutFacesGetPhotoWords() {
        assertEquals(ImagePrompt.PHOTO, ImagePrompt.suffixFor("a rocky mountain lake at dawn, natural light"))
    }

    @Test
    fun facesAlsoGetEyeWords() {
        assertEquals("${ImagePrompt.PHOTO}, ${ImagePrompt.EYES}", ImagePrompt.suffixFor("a gray cat sitting on a roof"))
        assertEquals("${ImagePrompt.PHOTO}, ${ImagePrompt.EYES}", ImagePrompt.suffixFor("close-up portrait of an old man"))
    }

    @Test
    fun cartoonLikeRequestsGetCleanLineWords() {
        assertEquals("${ImagePrompt.ART}, ${ImagePrompt.EYES}", ImagePrompt.suffixFor("a cartoon cat on a roof"))
        assertEquals(ImagePrompt.ART, ImagePrompt.suffixFor("pixel art castle"))
        assertEquals(ImagePrompt.ART, ImagePrompt.suffixFor("3D render of a house"))
        assertEquals("${ImagePrompt.ART}, ${ImagePrompt.EYES}", ImagePrompt.suffixFor("anime girl with a sword"))
    }

    @Test
    fun paintingRequestsAreNotForcedIntoPhotos() {
        assertEquals(ImagePrompt.PAINTING, ImagePrompt.suffixFor("an oil painting of a harbour"))
        assertEquals(ImagePrompt.PAINTING, ImagePrompt.suffixFor("Watercolor flowers"))
    }

    @Test
    fun wordsInsideOtherWordsDoNotCount() {
        // "gender" contains "gen" but nothing here is a face or a style.
        assertEquals(ImagePrompt.PHOTO, ImagePrompt.suffixFor("a gender reveal party table"))
    }

    @Test
    fun holdingBecomesBeside() {
        assertEquals("a cat beside a teacup", ImagePrompt.sanitize("a cat holding a teacup"))
        assertEquals("a butler beside a tray", ImagePrompt.sanitize("A butler carrying a tray"))
    }

    @Test
    fun handsAndPawsAreDropped() {
        assertEquals("a cat beside a teacup", ImagePrompt.sanitize("a cat holding a teacup with his paws"))
        val result = ImagePrompt.sanitize("a man waving his hand at the camera, hands raised")
        assertFalse(result, result.contains("hand"))
        assertTrue(result, result.contains("a man waving"))
    }

    @Test
    fun otherWordsAreKept() {
        assertEquals("a gray cat on a roof, soft light", ImagePrompt.sanitize("A gray cat on a roof, soft light"))
        // "handsome" and "pawn" must survive: only whole words go.
        assertEquals("a handsome pawn", ImagePrompt.sanitize("a handsome pawn"))
    }
}
