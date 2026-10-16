package com.aiagent

/**
 * Decides, from volume changes alone, whether the Volume Up *key* is being held (see
 * [VolumeButtonWatcher]), and not the volume slider being dragged on screen.
 *
 * A held key has a machine rhythm: one step when it goes down, then Android waits its fixed
 * key-repeat pause ([repeatTimeoutMs], ~0.4–0.5 s) and repeats it one step every
 * [repeatDelayMs] (~50 ms) like a metronome. A finger dragging the slider never keeps that
 * rhythm, and taps are far too slow. Gota is called once the pause and two more on-beat repeats
 * are seen. Pure logic, testable with made-up timings.
 */
class VolumeHoldDetector(private val repeatTimeoutMs: Long, private val repeatDelayMs: Long) {

    sealed class Action {
        /** Nothing to do. */
        object None : Action()

        /** The key is still held after Gota was called: put this stream back to [level]. */
        data class Restore(val stream: Int, val level: Int) : Action()

        /** Held: put these streams back (stream to level) and call Gota. */
        data class Held(val restore: Map<Int, Int>) : Action()
    }

    /** A possible key press on one stream, from the level it had before ([baseline]). */
    private class Press(val baseline: Int, val step: Int, val downAt: Long, val downValue: Int) {
        var last = downAt
        var value = downValue
        /** The first repeat, found after the system pause; later repeats must keep its beat. */
        var beatAt = -1L
        var beatValue = 0
        var rebeats = 0
    }

    private val presses = HashMap<Int, Press>()
    private var restoreTargets: Map<Int, Int> = emptyMap()
    private var restoringUntil = 0L

    /** Call for every volume change on [stream]; [now] in milliseconds. */
    fun onRise(stream: Int, value: Int, prev: Int, now: Long): Action {
        if (value <= prev) return Action.None

        // Gota was already called and the key is still held: keep the volume where it was.
        if (now < restoringUntil) {
            restoringUntil = now + RELEASE_GAP_MS
            return restoreTargets[stream]?.let { Action.Restore(stream, it) } ?: Action.None
        }

        val press = presses[stream]?.takeIf { now - it.last <= repeatTimeoutMs + PAUSE_LATE_MS + 150 }
        if (press == null) return startPress(stream, value, prev, now)
        val steps = (value - press.value) / press.step
        if (steps < 1 || (value - press.value) % press.step != 0 || steps > MAX_MERGED_STEPS) {
            return startPress(stream, value, prev, now)
        }

        if (press.beatAt < 0) {
            // Waiting for the first repeat: it comes after the system's fixed pause.
            val late = now - press.downAt - repeatTimeoutMs - (steps - 1) * repeatDelayMs
            if (late < -PAUSE_EARLY_MS || late > PAUSE_LATE_MS) return startPress(stream, value, prev, now)
            press.beatAt = now - (steps - 1) * repeatDelayMs
            press.beatValue = press.downValue + press.step
        } else {
            // Following repeats keep the beat (a merged broadcast may carry two at once).
            val beats = (value - press.beatValue) / press.step
            val off = now - (press.beatAt + beats * repeatDelayMs)
            if (off < -BEAT_EARLY_MS || off > BEAT_LATE_MS) {
                if (press.rebeats >= MAX_REBEATS) return startPress(stream, value, prev, now)
                // A delayed broadcast: pick the beat up again from here.
                press.rebeats++
                press.beatAt = now
                press.beatValue = value
            } else if (beats >= BEATS_FOR_HOLD) {
                restoreTargets = presses.filterValues { now - it.last <= RELEASE_GAP_MS }.mapValues { it.value.baseline } +
                    (stream to press.baseline)
                presses.clear()
                restoringUntil = now + RELEASE_GAP_MS
                return Action.Held(restoreTargets)
            }
        }
        press.last = now
        press.value = value
        return Action.None
    }

    /** This rise could be a key going down: remember it and wait for the pause. */
    private fun startPress(stream: Int, value: Int, prev: Int, now: Long): Action {
        presses[stream] = Press(prev, (value - prev).coerceAtLeast(1), now, value)
        return Action.None
    }

    companion object {
        /** Tolerance around the system pause before the first repeat. */
        const val PAUSE_EARLY_MS = 80L
        const val PAUSE_LATE_MS = 250L

        /** Tolerance around each later beat (broadcasts arrive a little late, never early by much). */
        const val BEAT_EARLY_MS = 30L
        const val BEAT_LATE_MS = 70L

        /** Repeats after the first one needed to be sure. */
        const val BEATS_FOR_HOLD = 2
        const val MAX_MERGED_STEPS = 3
        const val MAX_REBEATS = 2

        /** After Gota is called, the key counts as released once the volume stops rising this long. */
        const val RELEASE_GAP_MS = 700L

        /** How far back to look for a ringer-mode change caused by the same hold. */
        const val WINDOW_MS = 1500L
    }
}
