package com.aiagent

/**
 * Decides, from volume changes alone, whether Volume Up is being held (see [VolumeButtonWatcher]).
 *
 * Holding the key makes Android repeat it about every 50 ms (after a ~0.5 s pause), so the
 * volume climbs faster than any finger can tap. Gota is called once two of those machine-speed
 * steps are seen; taps, however quick, never are. Pure logic, testable with made-up timings.
 */
class VolumeHoldDetector {

    sealed class Action {
        /** Nothing to do. */
        object None : Action()

        /** The key is still held after Gota was called: put this stream back to [level]. */
        data class Restore(val stream: Int, val level: Int) : Action()

        /** Held: put these streams back (stream to level) and call Gota. */
        data class Held(val restore: Map<Int, Int>) : Action()
    }

    /** One run of volume rises on a stream, from the level it had before ([baseline]). */
    private class Burst(val baseline: Int, val step: Int, var last: Long, var value: Int, var fastSteps: Int = 0)

    private val bursts = HashMap<Int, Burst>()
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

        val burst = bursts[stream]?.takeIf { now - it.last <= BURST_GAP_MS }
        if (burst == null) {
            bursts[stream] = Burst(prev, (value - prev).coerceAtLeast(1), now, value)
            return Action.None
        }
        val steps = (value - burst.value) / burst.step
        if (steps >= 1 && (now - burst.last) <= steps * MACHINE_STEP_MS) burst.fastSteps += steps
        burst.last = now
        burst.value = value
        if (burst.fastSteps < FAST_STEPS_FOR_HOLD) return Action.None

        restoreTargets = bursts.filterValues { now - it.last <= BURST_GAP_MS }.mapValues { it.value.baseline }
        bursts.clear()
        restoringUntil = now + RELEASE_GAP_MS
        return Action.Held(restoreTargets)
    }

    companion object {
        /** A step this soon after the previous one can only come from the key being held. */
        const val MACHINE_STEP_MS = 120L
        const val FAST_STEPS_FOR_HOLD = 2

        /** Rises closer than this belong to the same press (covers the ~0.5 s pause before repeats). */
        const val BURST_GAP_MS = 1000L

        /** After Gota is called, the key counts as released once the volume stops rising this long. */
        const val RELEASE_GAP_MS = 700L

        /** How far back to look for a ringer-mode change caused by the same hold. */
        const val WINDOW_MS = 1500L
    }
}
