package com.aiagent

import com.aiagent.VolumeHoldDetector.Action
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class VolumeHoldDetectorTest {

    private val music = 3
    private val ring = 2
    private val notification = 5

    /** Feeds (time, from, to) rises on one stream and returns every action. */
    private fun VolumeHoldDetector.feed(stream: Int, vararg events: Triple<Long, Int, Int>) =
        events.map { (t, from, to) -> onRise(stream, to, from, t) }

    private fun held(actions: List<Action>) = actions.filterIsInstance<Action.Held>()

    @Test
    fun singleTapIsIgnored() {
        val d = VolumeHoldDetector()
        assertTrue(held(d.feed(music, Triple(0L, 5, 6))).isEmpty())
    }

    @Test
    fun quickTapsAreIgnored() {
        val d = VolumeHoldDetector()
        // Even very fast tapping (150 ms apart) never reaches the key-repeat speed.
        val actions = d.feed(music, Triple(0L, 5, 6), Triple(150L, 6, 7), Triple(300L, 7, 8), Triple(450L, 8, 9), Triple(600L, 9, 10))
        assertTrue(held(actions).isEmpty())
    }

    @Test
    fun slowerTapsAreIgnored() {
        val d = VolumeHoldDetector()
        val actions = d.feed(music, Triple(0L, 5, 6), Triple(400L, 6, 7), Triple(800L, 7, 8), Triple(1200L, 8, 9))
        assertTrue(held(actions).isEmpty())
    }

    @Test
    fun holdCallsGotaAndRestoresTheVolume() {
        val d = VolumeHoldDetector()
        val actions = d.feed(music, Triple(0L, 5, 6), Triple(500L, 6, 7), Triple(550L, 7, 8), Triple(600L, 8, 9))
        assertEquals(listOf(Action.None, Action.None, Action.None, Action.Held(mapOf(music to 5))), actions)
    }

    @Test
    fun stillHoldingAfterwardKeepsTheVolumeDown() {
        val d = VolumeHoldDetector()
        d.feed(music, Triple(0L, 5, 6), Triple(500L, 6, 7), Triple(550L, 7, 8), Triple(600L, 8, 9))
        // We put it back to 5; the next repeats raise it to 6 again and must be undone, without calling Gota twice.
        val after = d.feed(music, Triple(650L, 5, 6), Triple(700L, 5, 6))
        assertEquals(listOf(Action.Restore(music, 5), Action.Restore(music, 5)), after)
    }

    @Test
    fun aTapAfterReleaseIsNormalAgain() {
        val d = VolumeHoldDetector()
        d.feed(music, Triple(0L, 5, 6), Triple(500L, 6, 7), Triple(550L, 7, 8), Triple(600L, 8, 9))
        assertEquals(Action.None, d.onRise(music, 6, 5, 3000L))
    }

    @Test
    fun coalescedRepeatsStillCount() {
        val d = VolumeHoldDetector()
        // Android may merge quick broadcasts: two steps arrive together 100 ms later.
        val actions = d.feed(music, Triple(0L, 5, 6), Triple(500L, 6, 7), Triple(600L, 7, 9))
        assertEquals(Action.Held(mapOf(music to 5)), actions.last())
    }

    @Test
    fun finerVolumeStepsWork() {
        val d = VolumeHoldDetector()
        val actions = d.feed(music, Triple(0L, 50, 60), Triple(500L, 60, 70), Triple(550L, 70, 80), Triple(600L, 80, 90))
        assertEquals(Action.Held(mapOf(music to 50)), actions.last())
    }

    @Test
    fun longHoldDelaySettingStillWorks() {
        val d = VolumeHoldDetector()
        // "Touch and hold delay" set to long: repeats start 1.5 s later. The first step stays, the rest is undone.
        val actions = d.feed(music, Triple(0L, 5, 6), Triple(1500L, 6, 7), Triple(1550L, 7, 8), Triple(1600L, 8, 9))
        assertEquals(Action.Held(mapOf(music to 6)), actions.last())
    }

    @Test
    fun nearTheMaximumThereIsNothingToSee() {
        val d = VolumeHoldDetector()
        // 14 -> 15 is the top: after that the volume can't rise, so no more broadcasts arrive.
        val actions = d.feed(music, Triple(0L, 13, 14), Triple(500L, 14, 15))
        assertTrue(held(actions).isEmpty())
    }

    @Test
    fun linkedStreamsAreRestoredTogether() {
        val d = VolumeHoldDetector()
        // Ringtone and notification volume move together on some phones.
        val actions = mutableListOf<Action>()
        for ((t, from, to) in listOf(Triple(0L, 5, 6), Triple(500L, 6, 7), Triple(550L, 7, 8), Triple(600L, 8, 9))) {
            actions += d.onRise(notification, to, from, t)
            actions += d.onRise(ring, to, from, t)
        }
        // Gota is called once, putting both back; the twin rise right after is just undone.
        assertEquals(listOf(Action.Held(mapOf(ring to 5, notification to 5))), held(actions))
        assertEquals(Action.Restore(ring, 5), actions.last())
    }

    @Test
    fun loweringIsIgnored() {
        val d = VolumeHoldDetector()
        val actions = d.feed(music, Triple(0L, 9, 8), Triple(500L, 8, 7), Triple(550L, 7, 6), Triple(600L, 6, 5))
        assertTrue(actions.all { it == Action.None })
    }
}
