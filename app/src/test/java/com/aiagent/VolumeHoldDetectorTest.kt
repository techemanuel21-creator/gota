package com.aiagent

import com.aiagent.VolumeHoldDetector.Action
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class VolumeHoldDetectorTest {

    private val music = 3
    private val ring = 2
    private val notification = 5

    /** Android's default key-repeat timing: 400 ms pause, then every 50 ms. */
    private fun detector() = VolumeHoldDetector(repeatTimeoutMs = 400, repeatDelayMs = 50)

    /** Feeds (time, from, to) rises on one stream and returns every action. */
    private fun VolumeHoldDetector.feed(stream: Int, vararg events: Triple<Long, Int, Int>) =
        events.map { (t, from, to) -> onRise(stream, to, from, t) }

    private fun held(actions: List<Action>) = actions.filterIsInstance<Action.Held>()

    /** One-step rises at the given [times], starting from level [from]. */
    private fun steps(from: Int, vararg times: Long) =
        times.mapIndexed { i, t -> Triple(t, from + i, from + i + 1) }.toTypedArray()

    // ---------- the key held ----------

    @Test
    fun holdCallsGotaAndRestoresTheVolume() {
        val actions = detector().feed(music, *steps(5, 0, 400, 450, 500))
        assertEquals(listOf(Action.None, Action.None, Action.None, Action.Held(mapOf(music to 5))), actions)
    }

    @Test
    fun holdWithBroadcastDelaysStillWorks() {
        val actions = detector().feed(music, *steps(5, 0, 425, 478, 531))
        assertEquals(Action.Held(mapOf(music to 5)), actions.last())
    }

    @Test
    fun oneLateBroadcastIsForgiven() {
        // The 3rd repeat arrives 120 ms late; the beat is picked up again from there.
        val actions = detector().feed(music, *steps(5, 0, 400, 450, 620, 650, 700))
        assertEquals(Action.Held(mapOf(music to 5)), actions.last())
    }

    @Test
    fun mergedBroadcastStillCounts() {
        // Two repeats delivered together, 100 ms after the first one.
        val actions = detector().feed(music, Triple(0L, 5, 6), Triple(410L, 6, 7), Triple(510L, 7, 9))
        assertEquals(Action.Held(mapOf(music to 5)), actions.last())
    }

    @Test
    fun stillHoldingAfterwardKeepsTheVolumeDown() {
        val d = detector()
        d.feed(music, *steps(5, 0, 400, 450, 500))
        // We put it back to 5; the next repeats raise it again and must be undone, without calling Gota twice.
        assertEquals(listOf(Action.Restore(music, 5), Action.Restore(music, 5)), d.feed(music, Triple(550L, 5, 6), Triple(600L, 5, 6)))
    }

    @Test
    fun aTapAfterReleaseIsNormalAgain() {
        val d = detector()
        d.feed(music, *steps(5, 0, 400, 450, 500))
        assertEquals(Action.None, d.onRise(music, 6, 5, 3000L))
    }

    @Test
    fun finerVolumeStepsWork() {
        val actions = detector().feed(music, Triple(0L, 50, 60), Triple(400L, 60, 70), Triple(450L, 70, 80), Triple(500L, 80, 90))
        assertEquals(Action.Held(mapOf(music to 50)), actions.last())
    }

    @Test
    fun longHoldDelaySettingWorks() {
        // "Touch and hold delay" set to long: the pause before repeating is 1.5 s.
        val actions = VolumeHoldDetector(1500, 50).feed(music, *steps(5, 0, 1500, 1550, 1600))
        assertEquals(Action.Held(mapOf(music to 5)), actions.last())
    }

    @Test
    fun linkedStreamsAreRestoredTogether() {
        val d = detector()
        // Ringtone and notification volume move together on some phones.
        val actions = mutableListOf<Action>()
        for ((t, from, to) in steps(5, 0, 400, 450, 500)) {
            actions += d.onRise(notification, to, from, t)
            actions += d.onRise(ring, to, from, t)
        }
        // Gota is called once, putting both back; the twin rise right after is just undone.
        assertEquals(listOf(Action.Held(mapOf(ring to 5, notification to 5))), held(actions))
        assertEquals(Action.Restore(ring, 5), actions.last())
    }

    // ---------- taps ----------

    @Test
    fun singleTapIsIgnored() {
        assertTrue(held(detector().feed(music, Triple(0L, 5, 6))).isEmpty())
    }

    @Test
    fun quickTapsAreIgnored() {
        assertTrue(held(detector().feed(music, *steps(5, 0, 150, 300, 450, 600, 750))).isEmpty())
    }

    @Test
    fun tapsAtThePauseLengthAreIgnored() {
        // Tapping every 400 ms matches the pause once, but never the 50 ms beat after it.
        assertTrue(held(detector().feed(music, *steps(5, 0, 400, 800, 1200, 1600, 2000))).isEmpty())
    }

    // ---------- the on-screen slider ----------

    @Test
    fun tapThenDraggingTheSliderIsIgnored() {
        // The case reported on the phone: one tap, then the volume bar dragged up with a finger.
        val actions = detector().feed(
            music, Triple(0L, 5, 6),
            Triple(900L, 6, 7), Triple(935L, 7, 8), Triple(960L, 8, 10), Triple(1000L, 10, 11),
            Triple(1020L, 11, 12), Triple(1070L, 12, 13), Triple(1090L, 13, 14)
        )
        assertTrue(held(actions).isEmpty())
    }

    @Test
    fun tapThenSteadyDragIsIgnored() {
        // Even a perfectly steady drag doesn't have the pause right after the tap.
        assertTrue(held(detector().feed(music, *steps(5, 0, 1000, 1050, 1100, 1150, 1200))).isEmpty())
    }

    @Test
    fun draggingTheSliderAloneIsIgnored() {
        assertTrue(held(detector().feed(music, *steps(3, 0, 30, 75, 100, 160, 190, 240, 260))).isEmpty())
        assertTrue(held(detector().feed(music, *steps(3, 0, 50, 100, 150, 200, 250, 300))).isEmpty())
    }

    // ---------- nothing to see ----------

    @Test
    fun nearTheMaximumThereIsNothingToSee() {
        // 14 -> 15 is the top: after that the volume can't rise, so no more broadcasts arrive.
        assertTrue(held(detector().feed(music, Triple(0L, 13, 14), Triple(400L, 14, 15))).isEmpty())
    }

    @Test
    fun loweringIsIgnored() {
        val actions = detector().feed(music, Triple(0L, 9, 8), Triple(400L, 8, 7), Triple(450L, 7, 6), Triple(500L, 6, 5))
        assertTrue(actions.all { it == Action.None })
    }
}
