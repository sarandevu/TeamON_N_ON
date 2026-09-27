package com.edgeppg.app.behavior

import com.edgeppg.app.challenge.BehavioralObservation
import com.edgeppg.app.challenge.BehavioralOutcome
import com.edgeppg.app.challenge.ChallengeSpec
import com.edgeppg.app.optical.OpticalFlashOverlay
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch

/**
 * Stage 15 Task 4 — Behaviour-runner coroutine.
 *
 * The coroutine driver on top of the pure [BehavioralRunner] matcher.
 * Iterates through a [ChallengeSpec] list, drives the optical flash
 * overlay for [ChallengeSpec.OpticalFlash] entries, waits for the
 * per-challenge timeout, and emits a [BehaviourEvent] for each
 * lifecycle tick.
 *
 * Events the UI subscribes to:
 *  - [BehaviourEvent.PromptShown] — challenge is on-screen, awaiting
 *    response. The UI typically displays the challenge text.
 *  - [BehaviourEvent.FlashStarted] / [BehaviourEvent.FlashEnded] —
 *    optical flash boundaries (for status / accessibility).
 *  - [BehaviourEvent.Observation] — the matcher produced a
 *    [BehavioralObservation] for the current challenge (match,
 *    wrong, timeout, or contaminated).
 *  - [BehaviourEvent.AllComplete] — every challenge in the list has
 *    been processed; the UI can advance to the next session state.
 *
 * Lifecycle:
 *  - The runner takes an external [CoroutineScope] (typically a
 *    `lifecycleScope` from the host activity). Cancellation of that
 *    scope aborts the runner.
 *  - `start(challenges)` is idempotent within a single scope; a
 *    second call after a successful run is a no-op.
 */
class BehaviourRunner(
    private val scope: CoroutineScope,
    private val flashOverlay: OpticalFlashOverlay? = null,
    /** Pulled from the camera pipeline each frame the UI gets a new
     *  FaceMesh result. The runner consumes the latest snapshot. */
    @Volatile var latestMeshPoints: FloatArray? = null,
    @Volatile var latestContaminationFlag: Boolean = false,
) {

    sealed class BehaviourEvent {
        data class PromptShown(val spec: ChallengeSpec, val index: Int, val total: Int) :
            BehaviourEvent()
        data class FlashStarted(val spec: ChallengeSpec) : BehaviourEvent()
        data class FlashEnded(val spec: ChallengeSpec) : BehaviourEvent()
        data class Observation(val observation: BehavioralObservation) :
            BehaviourEvent()
        object AllComplete : BehaviourEvent()
    }

    private val _events = MutableSharedFlow<BehaviourEvent>(
        replay = 0, extraBufferCapacity = 16
    )
    val events: SharedFlow<BehaviourEvent> = _events.asSharedFlow()

    @Volatile private var running: Boolean = false
    private var runJob: Job? = null

    fun isRunning(): Boolean = running

    /**
     * Kick off the coroutine that walks through [challenges] and emits
     * events. Safe to call once per [scope] lifetime. A second call
     * while a run is in flight is a no-op.
     */
    fun start(challenges: List<ChallengeSpec>) {
        // Temporary lifecycle diagnostics for the first-launch
        // investigation (hackathon): proves start() is reached, with
        // how many challenges, and whether a previous run is stuck.
        com.edgeppg.app.Log.stage("behavior",
            "runner.start(${challenges.size}) running=$running scope=$scope")
        if (running) return
        running = true
        runJob = scope.launch(Dispatchers.Default) {
            try {
                com.edgeppg.app.Log.stage("behavior", "runAll begin")
                runAll(challenges)
                com.edgeppg.app.Log.stage("behavior", "runAll end")
            } catch (t: Throwable) {
                com.edgeppg.app.Log.error("behavior", "runAll failed", t)
            } finally {
                running = false
            }
        }
    }

    /**
     * External cancel. Safe to call from the activity's onDestroy.
     * Idempotent.
     */
    fun cancel() {
        runJob?.cancel()
        runJob = null
        running = false
        flashOverlay?.cancel()
    }

    private suspend fun runAll(challenges: List<ChallengeSpec>) {
        val total = challenges.size
        for ((index, spec) in challenges.withIndex()) {
            _events.emit(BehaviourEvent.PromptShown(spec, index, total))
            if (spec is ChallengeSpec.OpticalFlash) {
                _events.emit(BehaviourEvent.FlashStarted(spec))
                flashOverlay?.showFlash(spec.color, spec.deltaPct, spec.durationMs)
                // Wait the full flash duration so the rPPG DSP / camera
                // sees a real stimulus on the face. The Stage 4 DSP
                // (FR-OPT-3) is responsible for temporal separation.
                delay(spec.durationMs)
                _events.emit(BehaviourEvent.FlashEnded(spec))
                // An optical flash challenge is a passive stimulus —
                // there's no "user response" to wait for. Emit a MATCH
                // observation so the row assembler records the
                // presence of the challenge. A real device test
                // (PR-VAL-1) would correlate the camera signal with
                // the flash; that correlation lives in the DSP.
                _events.emit(
                    BehaviourEvent.Observation(
                        BehavioralObservation(
                            spec = spec,
                            observed = BehavioralOutcome.MATCH,
                            latencyMs = spec.durationMs,
                            success = true,
                        )
                    )
                )
                if (index < total - 1) {
                    delay(1200L)
                }
                continue
            }
            // Behavioral challenge: wait for the timeout window.
            // Continuously sample incoming mesh updates so if the user completes
            // the requested action comfortably, we record the match immediately
            // without forcing them to hold an uncomfortable pose until the full
            // timeout expires. If they take longer, allow up to the full timeoutMs.
            val started = System.currentTimeMillis()
            val timeoutMs = spec.timeoutMs
            var lastObs: BehavioralObservation? = null
            while (System.currentTimeMillis() - started < timeoutMs) {
                delay(60L)
                if (latestContaminationFlag) break
                val now = System.currentTimeMillis()
                val mesh = latestMeshPoints
                val gaze = if (mesh != null && mesh.size >= MeshLandmarks.LEFT_IRIS_CENTER * 3 + 3) {
                    GazeEstimator.estimate(mesh)
                } else null
                val pose = if (mesh != null && mesh.size >= MeshLandmarks.CHIN * 3 + 3) {
                    HeadPoseSolver.estimate(mesh)
                } else null
                val obs = BehavioralRunner.observe(
                    requested = spec,
                    startedAtMs = started,
                    nowMs = now,
                    gaze = gaze,
                    pose = pose,
                    contaminationFlag = latestContaminationFlag,
                )
                lastObs = obs
                // If an active challenge matched, pause briefly to ensure stable hold
                if (spec !is ChallengeSpec.RemainStill && obs.success) {
                    delay(400L)
                    break
                }
            }
            val now = System.currentTimeMillis()
            val observation = lastObs ?: run {
                val mesh = latestMeshPoints
                val gaze = if (mesh != null && mesh.size >= MeshLandmarks.LEFT_IRIS_CENTER * 3 + 3) {
                    GazeEstimator.estimate(mesh)
                } else null
                val pose = if (mesh != null && mesh.size >= MeshLandmarks.CHIN * 3 + 3) {
                    HeadPoseSolver.estimate(mesh)
                } else null
                BehavioralRunner.observe(
                    requested = spec,
                    startedAtMs = started,
                    nowMs = now,
                    gaze = gaze,
                    pose = pose,
                    contaminationFlag = latestContaminationFlag,
                )
            }
            _events.emit(BehaviourEvent.Observation(observation))
            if (index < total - 1) {
                delay(2000L)
            }
        }
        _events.emit(BehaviourEvent.AllComplete)
    }
}
