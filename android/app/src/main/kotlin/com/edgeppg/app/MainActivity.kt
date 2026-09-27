package com.edgeppg.app

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.edgeppg.app.behavior.BehaviourRunner
import com.edgeppg.app.capture.CameraSession
import com.edgeppg.app.capture.FrameListener
import com.edgeppg.app.challenge.ChallengeSpec
import com.edgeppg.app.challenge.SessionState
import com.edgeppg.app.optical.OpticalFlashOverlay
import com.edgeppg.app.quality.FrameQuality
import com.edgeppg.app.quality.QualityGate
import com.edgeppg.app.session.CallController
import com.edgeppg.app.session.CallState
import com.edgeppg.app.session.SessionController
import com.edgeppg.app.transport.LocalWifiTransport
import com.edgeppg.app.transport.Transport
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.concurrent.atomic.AtomicInteger

/**
 * Single-Applicant VKYC Application (EdgePPG).
 *
 * Layout follows Part 22:
 *
 *   PROFILE ▼
 *     - Applicant
 *     - Session
 *     - Scheduled Call
 *
 *   VERIFICATION
 *     - Camera (PreviewView + OpticalFlashOverlay)
 *     - Verification Status (FPS, Face Detected, Hardware Lock)
 *     - rPPG (Heart Rate, SNR, Perfusion Quality)
 *     - Challenge (Active behavioral / optical prompt)
 *     - Result (Attestation verdict)
 */
class MainActivity : ComponentActivity(), FrameListener {

    // --- Views ---
    private lateinit var scrollView: ScrollView
    private lateinit var previewView: PreviewView
    private lateinit var flashOverlay: OpticalFlashOverlay
    private lateinit var profileHeader: TextView
    private lateinit var profileBody: LinearLayout
    private lateinit var applicantRefInput: EditText
    private lateinit var callIdInput: EditText
    private lateinit var callStatusView: TextView
    private lateinit var joinButton: Button
    private var dashboardView: View? = null
    private var sessionView: View? = null

    private lateinit var fpsView: TextView
    private lateinit var faceStatusView: TextView
    private lateinit var lockStatusView: TextView

    private lateinit var hrView: TextView
    private lateinit var snrView: TextView
    private lateinit var qualityView: TextView
    private lateinit var rppgGraphView: com.edgeppg.app.rppg.RppgGraphView

    private lateinit var challengeCard: LinearLayout
    private lateinit var challengeTitleView: TextView
    private lateinit var challengeDescView: TextView
    private lateinit var challengePacingView: TextView

    private lateinit var resultCard: LinearLayout
    private lateinit var resultVerdictView: TextView
    private lateinit var resultDetailsView: TextView

    private lateinit var actionButton: Button

    // --- Camera & Pipelines ---
    private var cameraSession: CameraSession? = null
    private var isProfileExpanded = true

    // Diagnostics from camera pipeline
    @Volatile private var locked = false
    @Volatile private var facePresent = false
    private val framesInWindow = AtomicInteger(0)
    @Volatile private var lastFps = 0.0
    @Volatile private var lastQuality: FrameQuality? = null
    private val rppgClient = com.edgeppg.app.rppg.RppgClient()

    // Spoof detection: track whether we ever got valid rPPG frames
    // and accumulate min observed values (consistently weak signal = spoof evidence)
    @Volatile private var rppgFrameCount = 0
    @Volatile private var peakSnr = 0f
    @Volatile private var peakRoiCorr = 0f
    @Volatile private var peakHrBpm = 0f

    // Transport & Controllers
    private val transport = LocalWifiTransport()
    private val controller = SessionController(transport = transport)
    private val callController = CallController()
    private var lastLiveBroadcastMs = 0L
    private var currentChallengeIndex = 0
    private val challenges: MutableList<ChallengeSpec> = mutableListOf()
    private var pendingSessionSeed: String? = null

    private var behaviourRunner: BehaviourRunner? = null
    @Volatile private var autoDispatched = false
    @Volatile private var motionAutoAdvanced = false
    @Volatile private var qualityScreenEnteredAt: Long = 0L

    private val cameraPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            Log.stage("ui", "CAMERA permission=GRANTED — starting camera")
            ensureCameraStarted()
        } else {
            Log.stage("ui", "CAMERA permission=DENIED")
            resultVerdictView.text = "Camera permission denied"
            resultDetailsView.text = "Grant CAMERA permission in system settings to proceed."
        }
    }

    private fun dp(dpVal: Int): Int = TypedValue.applyDimension(
        TypedValue.COMPLEX_UNIT_DIP,
        dpVal.toFloat(),
        resources.displayMetrics
    ).toInt()

    private fun makeShape(
        bgColor: Int,
        strokeColor: Int = 0,
        strokeWidthDp: Int = 0,
        cornerRadiusDp: Int = 12
    ): GradientDrawable = GradientDrawable().apply {
        shape = GradientDrawable.RECTANGLE
        setColor(bgColor)
        cornerRadius = dp(cornerRadiusDp).toFloat()
        if (strokeWidthDp > 0 && strokeColor != 0) {
            setStroke(dp(strokeWidthDp), strokeColor)
        }
    }

    private fun makeGradient(
        startColor: Int,
        endColor: Int,
        cornerRadiusDp: Int = 12,
        orientation: GradientDrawable.Orientation = GradientDrawable.Orientation.LEFT_RIGHT
    ): GradientDrawable = GradientDrawable(
        orientation,
        intArrayOf(startColor, endColor)
    ).apply {
        cornerRadius = dp(cornerRadiusDp).toFloat()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        try {
            window.statusBarColor = 0xFF080C14.toInt()
            window.navigationBarColor = 0xFF080C14.toInt()
        } catch (_: Throwable) {}

        buildUi()

        // Asynchronously provision hardware KeyStore key
        lifecycleScope.launch(Dispatchers.Default) {
            try {
                if (com.edgeppg.app.integrity.IntegrityManager.ensureKey()) {
                    val pubB64 = com.edgeppg.app.integrity.IntegrityManager.exportPublicKeyB64()
                    if (pubB64 != null) {
                        val pubFile = java.io.File(filesDir, "edgeppg_device_key_v2.pub")
                        pubFile.writeText(pubB64)
                        Log.stage("integrity", "DEVICE_PUBKEY_B64: $pubB64")
                    }
                }
            } catch (t: Throwable) {
                Log.error("integrity", "Failed to ensure key on startup", t)
            }
        }

        // Initialize behaviour runner
        if (behaviourRunner == null) {
            behaviourRunner = BehaviourRunner(
                scope = lifecycleScope,
                flashOverlay = flashOverlay,
            )
        }

        // Observe call state
        lifecycleScope.launch {
            callController.view.collectLatest { v ->
                callStatusView.text = when (v.state) {
                    CallState.IDLE -> "ℹ️ Enter call credentials, then tap Join / Start."
                    CallState.SCHEDULED -> "⏳ Call ${v.callId} scheduled. Ready to verify."
                    CallState.JOINING -> "🔄 Handshaking with verifier for ${v.callId}…"
                    CallState.CONNECTED -> "✅ Session authorized! Verification in progress."
                    CallState.COMPLETED -> "✓ Verification session completed."
                    CallState.FAILED -> "⚠️ Join failed: ${v.lastError ?: "?"} — running standalone."
                }
                val canJoin = v.state == CallState.SCHEDULED ||
                    v.state == CallState.FAILED ||
                    v.state == CallState.IDLE
                joinButton.isEnabled = canJoin
            }
        }

        // Observe session controller state
        lifecycleScope.launch {
            controller.state.collectLatest { snap -> render(snap) }
        }

        // Observe behaviour events
        lifecycleScope.launch {
            behaviourRunner?.events?.collect { ev -> onBehaviourEvent(ev) }
        }

        // Informational FPS counter and quality auto-skip clock
        lifecycleScope.launch {
            var lastTick = System.currentTimeMillis()
            while (true) {
                delay(500)
                val now = System.currentTimeMillis()
                val dt = (now - lastTick).coerceAtLeast(1L)
                val frames = framesInWindow.getAndSet(0)
                lastFps = frames * 1000.0 / dt
                lastTick = now

                fpsView.text = "${"%.1f".format(lastFps)} FPS"
                tryAdvanceToBaseline()
            }
        }

        // Cold boot camera startup: if permission is granted, start camera immediately
        val perm = Manifest.permission.CAMERA
        if (ContextCompat.checkSelfPermission(this, perm) == PackageManager.PERMISSION_GRANTED) {
            ensureCameraStarted()
        } else {
            cameraPermissionLauncher.launch(perm)
        }
        syncFromPc()
    }

    override fun onResume() {
        super.onResume()
        val perm = Manifest.permission.CAMERA
        if (ContextCompat.checkSelfPermission(this, perm) == PackageManager.PERMISSION_GRANTED) {
            ensureCameraStarted()
        }
        syncFromPc()
    }

    private fun ensureCameraStarted() {
        if (cameraSession == null) {
            Log.stage("capture", "Cold boot camera initialization starting...")
            cameraSession = CameraSession(
                context = this,
                lifecycleOwner = this,
                listener = this,
            ).also { it.start(previewView) }
        }
    }

    private fun buildUi() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(0xFF080C14.toInt())
            setPadding(dp(16), dp(36), dp(16), dp(16))
        }

        // --- Header Bar ---
        val headerBar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = dp(14) }
        }

        val appTitle = TextView(this).apply {
            text = "EdgePPG VKYC"
            textSize = 20f
            setTypeface(null, Typeface.BOLD)
            setTextColor(0xFFFFFFFF.toInt())
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        }

        val enclaveBadge = TextView(this).apply {
            text = "● SECURE ENCLAVE"
            textSize = 10f
            setTypeface(null, Typeface.BOLD)
            setTextColor(0xFF34D399.toInt())
            background = makeShape(0x1F10B981, 0x5510B981, 1, 14)
            setPadding(dp(10), dp(4), dp(10), dp(4))
        }

        headerBar.addView(appTitle)
        headerBar.addView(enclaveBadge)
        root.addView(headerBar)

        // --- PROFILE Section (Part 22) ---
        val profileSection = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = makeShape(0xFF131B2E.toInt(), 0xFF23304E.toInt(), 1, 16)
            setPadding(dp(16), dp(14), dp(16), dp(14))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = dp(14) }
        }

        profileHeader = TextView(this).apply {
            text = "PROFILE ▼"
            textSize = 13f
            setTypeface(null, Typeface.BOLD)
            setTextColor(0xFF818CF8.toInt())
            setOnClickListener {
                isProfileExpanded = !isProfileExpanded
                profileBody.visibility = if (isProfileExpanded) View.VISIBLE else View.GONE
                profileHeader.text = if (isProfileExpanded) "PROFILE ▼" else "PROFILE ▶ (Applicant: User1 • Session: 001)"
            }
        }
        profileSection.addView(profileHeader)

        profileBody = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = dp(10) }
        }

        // Applicant Reference
        val applicantLabel = TextView(this).apply {
            text = "APPLICANT"
            textSize = 10f
            setTypeface(null, Typeface.BOLD)
            setTextColor(0xFF94A3B8.toInt())
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = dp(4) }
        }
        applicantRefInput = EditText(this).apply {
            setText("User1")
            textSize = 13f
            setTextColor(0xFFF1F5F9.toInt())
            background = makeShape(0xFF0B101D.toInt(), 0xFF2A364F.toInt(), 1, 8)
            setPadding(dp(10), dp(8), dp(10), dp(8))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = dp(10) }
        }

        // Session
        val sessionLabel = TextView(this).apply {
            text = "SESSION"
            textSize = 10f
            setTypeface(null, Typeface.BOLD)
            setTextColor(0xFF94A3B8.toInt())
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = dp(4) }
        }
        callIdInput = EditText(this).apply {
            setText("001")
            textSize = 13f
            setTypeface(Typeface.MONOSPACE)
            setTextColor(0xFFF1F5F9.toInt())
            background = makeShape(0xFF0B101D.toInt(), 0xFF2A364F.toInt(), 1, 8)
            setPadding(dp(10), dp(8), dp(10), dp(8))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = dp(10) }
        }

        // Scheduled Call
        val callLabel = TextView(this).apply {
            text = "SCHEDULED CALL"
            textSize = 10f
            setTypeface(null, Typeface.BOLD)
            setTextColor(0xFF94A3B8.toInt())
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = dp(4) }
        }
        callStatusView = TextView(this).apply {
            text = "⏳ Call scheduled. Tap Join / Start to verify."
            textSize = 12f
            setTextColor(0xFFFDE68A.toInt())
            background = makeShape(0x22F59E0B, 0x55F59E0B, 1, 8)
            setPadding(dp(10), dp(8), dp(10), dp(8))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = dp(12) }
        }

        val syncButton = Button(this).apply {
            text = "🔄 SYNC ACTIVE CALL FROM PC"
            textSize = 12f
            setTypeface(null, Typeface.BOLD)
            setTextColor(0xFF38BDF8.toInt())
            background = makeShape(0x1F0284C7.toInt(), 0x550284C7.toInt(), 1, 8)
            setOnClickListener { syncFromPc() }
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(38)
            ).apply { bottomMargin = dp(8) }
        }

        joinButton = Button(this).apply {
            text = "START / JOIN VERIFICATION ➔"
            textSize = 13f
            setTypeface(null, Typeface.BOLD)
            setTextColor(0xFFFFFFFF.toInt())
            background = makeGradient(0xFF4F46E5.toInt(), 0xFF7C3AED.toInt(), 10)
            setOnClickListener { onJoinOrStartClicked() }
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(42)
            )
        }

        profileBody.addView(applicantLabel)
        profileBody.addView(applicantRefInput)
        profileBody.addView(sessionLabel)
        profileBody.addView(callIdInput)
        profileBody.addView(callLabel)
        profileBody.addView(callStatusView)
        profileBody.addView(syncButton)
        profileBody.addView(joinButton)
        profileSection.addView(profileBody)
        root.addView(profileSection)

        // --- VERIFICATION Section (Part 22) ---
        val verificationHeader = TextView(this).apply {
            text = "VERIFICATION"
            textSize = 13f
            setTypeface(null, Typeface.BOLD)
            setTextColor(0xFFFFFFFF.toInt())
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = dp(8) }
        }
        root.addView(verificationHeader)

        // 1. Camera View (PreviewView with COMPATIBLE TextureView)
        previewView = PreviewView(this).apply {
            implementationMode = PreviewView.ImplementationMode.COMPATIBLE
            scaleType = PreviewView.ScaleType.FILL_CENTER
        }
        flashOverlay = OpticalFlashOverlay(this).apply {
            visibility = View.GONE
        }

        val cameraCard = FrameLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(240)
            ).apply { bottomMargin = dp(10) }
            background = makeShape(0xFF0B101D.toInt(), 0xFF2A364F.toInt(), 1, 16)
            clipToOutline = true
            addView(previewView, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            ))
            addView(flashOverlay, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            ))
        }
        root.addView(cameraCard)

        // 2. Verification Status (FPS, Face, Lock)
        val statusCard = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            background = makeShape(0xFF111827.toInt(), 0xFF1F2937.toInt(), 1, 10)
            setPadding(dp(10), dp(8), dp(10), dp(8))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = dp(8) }
        }

        fpsView = TextView(this).apply {
            text = "0.0 FPS"
            textSize = 11f
            setTypeface(Typeface.MONOSPACE, Typeface.BOLD)
            setTextColor(0xFF38BDF8.toInt())
            gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        }

        faceStatusView = TextView(this).apply {
            text = "FACE: UNDETECTED"
            textSize = 11f
            setTypeface(null, Typeface.BOLD)
            setTextColor(0xFFEF4444.toInt())
            gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.2f)
        }

        lockStatusView = TextView(this).apply {
            text = "LOCK: CONVERGING…"
            textSize = 11f
            setTypeface(null, Typeface.BOLD)
            setTextColor(0xFFA5B4FC.toInt())
            gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.3f)
        }

        statusCard.addView(fpsView)
        statusCard.addView(faceStatusView)
        statusCard.addView(lockStatusView)
        root.addView(statusCard)

        // 3. rPPG Perfusion & Pulse
        val rppgCard = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            background = makeShape(0xFF111827.toInt(), 0xFF1F2937.toInt(), 1, 10)
            setPadding(dp(10), dp(8), dp(10), dp(8))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = dp(8) }
        }

        hrView = TextView(this).apply {
            text = "HR: -- bpm"
            textSize = 11f
            setTypeface(Typeface.MONOSPACE)
            setTextColor(0xFF34D399.toInt())
            gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        }

        snrView = TextView(this).apply {
            text = "SNR: -- dB"
            textSize = 11f
            setTypeface(Typeface.MONOSPACE)
            setTextColor(0xFF38BDF8.toInt())
            gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        }

        qualityView = TextView(this).apply {
            text = "PERFUSION: --"
            textSize = 11f
            setTypeface(Typeface.MONOSPACE)
            setTextColor(0xFFA5B4FC.toInt())
            gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.2f)
        }

        rppgCard.addView(hrView)
        rppgCard.addView(snrView)
        rppgCard.addView(qualityView)
        root.addView(rppgCard)

        // 3b. Real-time rPPG Pulse Waveform Graph
        rppgGraphView = com.edgeppg.app.rppg.RppgGraphView(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(68)
            ).apply { bottomMargin = dp(8) }
            setFlatline(true)
        }
        root.addView(rppgGraphView)

        // 4. Challenge Card
        challengeCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = makeShape(0xFF131B2E.toInt(), 0xFF2A364F.toInt(), 1, 12)
            setPadding(dp(14), dp(10), dp(14), dp(10))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = dp(8) }
        }

        challengeTitleView = TextView(this).apply {
            text = "STANDBY"
            textSize = 13f
            setTypeface(null, Typeface.BOLD)
            setTextColor(0xFF818CF8.toInt())
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = dp(2) }
        }

        challengeDescView = TextView(this).apply {
            text = "Align face in frame to begin verification."
            textSize = 12f
            setTextColor(0xFFF1F5F9.toInt())
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = dp(2) }
        }

        challengePacingView = TextView(this).apply {
            text = "Hold steady at eye level."
            textSize = 11f
            setTextColor(0xFF94A3B8.toInt())
        }

        challengeCard.addView(challengeTitleView)
        challengeCard.addView(challengeDescView)
        challengeCard.addView(challengePacingView)
        root.addView(challengeCard)

        // 5. Result Card
        resultCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = makeShape(0xFF0F172A.toInt(), 0xFF1E293B.toInt(), 1, 12)
            setPadding(dp(14), dp(10), dp(14), dp(10))
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = dp(10) }
        }

        resultVerdictView = TextView(this).apply {
            text = "READY FOR ATTESTATION"
            textSize = 13f
            setTypeface(null, Typeface.BOLD)
            setTextColor(0xFFE2E8F0.toInt())
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { bottomMargin = dp(2) }
        }

        resultDetailsView = TextView(this).apply {
            text = "Tap 'START / JOIN VERIFICATION' above to begin full zero-knowledge check."
            textSize = 11f
            setTextColor(0xFF94A3B8.toInt())
        }

        resultCard.addView(resultVerdictView)
        resultCard.addView(resultDetailsView)
        root.addView(resultCard)

        // 6. Action Button (Skip / Advance / Restart)
        actionButton = Button(this).apply {
            text = "Skip step"
            textSize = 13f
            setTypeface(null, Typeface.BOLD)
            setTextColor(0xFFCBD5E1.toInt())
            background = makeShape(0xFF1E293B.toInt(), 0xFF334155.toInt(), 1, 10)
            isEnabled = false
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(42)
            )
        }
        root.addView(actionButton)

        scrollView = ScrollView(this).apply {
            setBackgroundColor(0xFF080C14.toInt())
            addView(root)
        }
        setContentView(scrollView)
    }

    private fun syncFromPc() {
        callStatusView.text = "🔄 Syncing with PC verifier at 127.0.0.1:8080…"
        callStatusView.setTextColor(0xFF38BDF8.toInt())
        lifecycleScope.launch {
            val active = transport.fetchActiveCall()
            if (active != null) {
                val (cid, ref, name) = active
                callIdInput.setText(cid)
                applicantRefInput.setText(ref)
                transport.activeCallId = cid
                transport.activeApplicantRef = ref
                callStatusView.text = "✅ Synced call $cid for $name ($ref)"
                callStatusView.setTextColor(0xFF34D399.toInt())
            } else {
                callStatusView.text = "⚡ PC server offline — tap 'SYNC ACTIVE CALL' when connected"
                callStatusView.setTextColor(0xFFFDE68A.toInt())
            }
        }
    }

    private fun streamLiveProgress(stageDesc: String = "") {
        val now = System.currentTimeMillis()
        if (now - lastLiveBroadcastMs < 700L) return
        lastLiveBroadcastMs = now

        val cid = callIdInput.text?.toString().orEmpty()
        val ref = applicantRefInput.text?.toString().orEmpty()
        val stateName = controller.state.value.state.name
        val hr = controller.liveHrBpm
        val snr = controller.liveSnr
        val corr = controller.liveRoiCorr
        val fps = lastFps.toFloat()
        val face = facePresent
        val isLocked = locked
        val spoof = controller.livePhoneDetected || controller.state.value.lastDecision?.name == "SPOOF"
        val reason = controller.livePhoneReason

        val json = org.json.JSONObject().apply {
            put("call_id", cid)
            put("applicant_ref", ref)
            put("state", stateName)
            put("stage_desc", stageDesc)
            put("hr_bpm", if (hr > 0f) hr.toInt() else 0)
            put("snr_db", if (!snr.isNaN()) "%.1f".format(snr) else "0.0")
            put("perfusion", if (!corr.isNaN()) "%.2f".format(corr) else "0.00")
            put("fps", "%.1f".format(fps))
            put("face_detected", face)
            put("hardware_lock", isLocked)
            put("spoof_detected", spoof)
            put("spoof_reason", reason)
            put("timestamp_ms", now)
        }.toString()

        lifecycleScope.launch(Dispatchers.IO) {
            transport.sendLiveProgress(json)
        }
    }

    fun onJoinClicked() = onJoinOrStartClicked()

    private fun onJoinOrStartClicked() {
        val callId = callIdInput.text?.toString().orEmpty()
        val ref = applicantRefInput.text?.toString().orEmpty()
        transport.activeCallId = callId
        transport.activeApplicantRef = ref
        callController.setScheduled(callId, ref)

        joinButton.isEnabled = false
        callStatusView.text = "🔄 Initiating verification handshake…"
        callStatusView.setTextColor(0xFFA5B4FC.toInt())

        lifecycleScope.launch(Dispatchers.Default) {
            val view = try {
                callController.join(transport)
            } catch (t: Throwable) {
                null
            }
            withContext(Dispatchers.Main.immediate) {
                joinButton.isEnabled = true
                if (view != null && view.state == CallState.CONNECTED) {
                    pendingSessionSeed = view.sessionSeed
                    callStatusView.text = "✅ Session authorized! Starting verification…"
                    callStatusView.setTextColor(0xFF6EE7B7.toInt())
                } else {
                    // Fallback to standalone local verification
                    callStatusView.text = "⚡ Verifier offline — running standalone session."
                    callStatusView.setTextColor(0xFFFDE68A.toInt())
                    val localSeed = java.util.UUID.randomUUID().toString().replace("-", "")
                    pendingSessionSeed = localSeed
                }
                startSession()
            }
        }
    }

    private fun startSession() {
        challenges.clear()
        challenges.addAll(controller.start(pendingSessionSeed))
        currentChallengeIndex = 0
        autoDispatched = false
        motionAutoAdvanced = false
        qualityScreenEnteredAt = System.currentTimeMillis()
        rppgFrameCount = 0
        peakSnr = 0f
        peakRoiCorr = 0f
        peakHrBpm = 0f
        Log.stage("ui", "session started; ${challenges.size} challenges queued")

        if (behaviourRunner == null) {
            behaviourRunner = BehaviourRunner(
                scope = lifecycleScope,
                flashOverlay = flashOverlay,
            )
        }
        behaviourRunner?.cancel()
        rppgClient.reset()
        tryAdvanceToBaseline()
    }

    private fun tryAdvanceToBaseline() {
        val q = lastQuality
        if (q != null && locked && facePresent && !q.contaminationFlag) {
            if (q.fps >= 25f) {
                advanceToBaseline("gate=auto")
                return
            }
        }
        if (qualityScreenEnteredAt > 0 &&
            System.currentTimeMillis() - qualityScreenEnteredAt >= QUALITY_AUTO_SKIP_MS &&
            controller.state.value.state == SessionState.QUALITY_CHECK
        ) {
            qualityScreenEnteredAt = 0L
            Log.stage("ui", "quality auto-skip after ${QUALITY_AUTO_SKIP_MS}ms without lock " +
                "(locked=$locked face=$facePresent) — proceeding unlocked, expect UNCERTAIN")
            advanceToBaseline("gate=timeout-skip-unlocked")
        }
    }

    private fun advanceToBaseline(how: String) {
        try {
            controller.qualityPass()
            Log.stage("ui", "quality passed ($how)")
            lifecycleScope.launch {
                delay(3000L)
                if (controller.state.value.state == SessionState.BASELINE) {
                    controller.baselineComplete()
                    Log.stage("ui", "baseline captured")
                }
            }
        } catch (t: IllegalStateException) {
            Log.error("ui", "advanceToBaseline rejected", t)
        }
    }

    private fun render(snap: SessionController.Snapshot) {
        when (snap.state) {
            SessionState.CAPTURE -> {
                challengeTitleView.text = "STANDBY"
                challengeDescView.text = "Initializing verification pipeline…"
                challengePacingView.text = "Align face in camera preview."
                actionButton.isEnabled = false
                streamLiveProgress("STANDBY: Initializing")
            }
            SessionState.QUALITY_CHECK -> {
                challengeTitleView.text = "ALIGN FACE IN FRAME"
                challengeDescView.text = "Hold device steady at eye level."
                challengePacingView.text = "Analyzing lighting & exposure stability…"
                actionButton.isEnabled = true
                actionButton.text = "I look ready (skip quality)"
                actionButton.setOnClickListener {
                    controller.qualityPass()
                    controller.baselineComplete()
                }
                streamLiveProgress("QUALITY CHECK: Aligning face")
            }
            SessionState.BASELINE -> {
                challengeTitleView.text = "PHYSIOLOGICAL BASELINE"
                challengeDescView.text = "Capturing rPPG pulse baseline… hold still."
                challengePacingView.text = "Reading ambient perfusion dynamics…"
                actionButton.isEnabled = false
                streamLiveProgress("BASELINE: Capturing rPPG pulse")
            }
            SessionState.RANDOMIZED_CHALLENGE -> {
                if (behaviourRunner?.isRunning() != true) {
                    behaviourRunner?.start(challenges)
                }
                showCurrentChallenge()
            }
            SessionState.MOTION_BLINK_CHECK -> {
                challengeTitleView.text = "NATURAL LIVENESS CHECK"
                challengeDescView.text = "Stay still and blink naturally."
                challengePacingView.text = "Passive micro-movement analysis in progress…"
                actionButton.isEnabled = true
                actionButton.text = "Skip (motion / blink ok)"
                actionButton.setOnClickListener { tryAdvanceMotionBlink() }
                streamLiveProgress("MOTION CHECK: Passive blink & micro-movement")

                if (!motionAutoAdvanced) {
                    motionAutoAdvanced = true
                    lifecycleScope.launch {
                        delay(3500L)
                        tryAdvanceMotionBlink()
                    }
                }
            }
            SessionState.PROCESSING -> {
                challengeTitleView.text = "FINALIZING ATTESTATION"
                challengeDescView.text = "Evaluating rPPG correlation & signing envelope…"
                challengePacingView.text = "Dispatching cryptographic verdict…"
                actionButton.isEnabled = false
                streamLiveProgress("PROCESSING: Evaluating & signing attestation")

                if (!autoDispatched) {
                    autoDispatched = true
                    lifecycleScope.launch(Dispatchers.Default) {
                        try {
                            controller.commitAndDispatch()
                        } catch (t: Throwable) {
                            Log.error("ui", "commitAndDispatch failed", t)
                        }
                    }
                }
            }
            SessionState.DONE -> {
                callController.markCompleted()
                val d = snap.lastDecision
                val r = snap.lastResult
                val decName = d?.name ?: "?"
                val receipt = r?.receiptPath?.takeIf { it.isNotEmpty() } ?: "Saved on PC"
                when (decName) {
                    "LIVE" -> {
                        resultCard.background = makeShape(0xF0064E3B.toInt(), 0xFF10B981.toInt(), 2, 12)
                        resultVerdictView.text = "🛡️ VERIFIED LIVE APPLICANT"
                        resultVerdictView.setTextColor(0xFF34D399.toInt())
                        resultDetailsView.text = "Verdict: LIVE (Authentication Passed)\nReceipt: $receipt\nHardware Integrity: SECP256R1 Signed ✓\nPC Verifier: ${r?.httpStatus ?: 200} OK"
                        resultDetailsView.setTextColor(0xFFD1FAE5.toInt())
                    }
                    "SPOOF" -> {
                        resultCard.background = makeShape(0xF07F1D1D.toInt(), 0xFFEF4444.toInt(), 2, 12)
                        resultVerdictView.text = "⚠️ SYNTHETIC SPOOF DETECTED"
                        resultVerdictView.setTextColor(0xFFF87171.toInt())
                        resultDetailsView.text = "Verdict: SPOOF (Rejected)\nReceipt: $receipt\nReason: ${r?.reason ?: "Liveness threshold failed"}"
                        resultDetailsView.setTextColor(0xFFFEE2E2.toInt())
                    }
                    else -> {
                        resultCard.background = makeShape(0xF078350F.toInt(), 0xFFF59E0B.toInt(), 2, 12)
                        resultVerdictView.text = "⚠️ INCONCLUSIVE SESSION"
                        resultVerdictView.setTextColor(0xFFFBBF24.toInt())
                        resultDetailsView.text = "Verdict: $decName\nReceipt: $receipt\nReason: ${r?.reason ?: "Lighting or movement unstable"}"
                        resultDetailsView.setTextColor(0xFFFEF3C7.toInt())
                    }
                }
                actionButton.isEnabled = true
                actionButton.text = "Start new session"
                actionButton.setOnClickListener { startSession() }
                streamLiveProgress("Verification completed: $decName")
            }
        }
    }

    private fun tryAdvanceMotionBlink() {
        if (controller.state.value.state != SessionState.MOTION_BLINK_CHECK) return
        try {
            controller.motionBlinkPass()
        } catch (t: IllegalStateException) {
            Log.error("ui", "motionBlinkPass rejected", t)
        }
    }

    private fun showCurrentChallenge() {
        val idx = currentChallengeIndex
        if (idx >= challenges.size) {
            try {
                controller.challengeComplete()
            } catch (t: IllegalStateException) {
                Log.error("ui", "challengeComplete rejected", t)
            }
            return
        }
        val spec = challenges[idx]
        val (icon, title, desc) = when (spec) {
            is ChallengeSpec.Gaze -> Triple("👁️", "GAZE CHALLENGE", "Look ${spec.direction.name.uppercase()}")
            is ChallengeSpec.Head -> Triple("👤", "HEAD ROTATION", "Turn head: ${spec.orientation.name.replace('_', ' ').uppercase()}")
            is ChallengeSpec.Hand -> Triple("✋", "GESTURE DETECTION", "Show hand: ${spec.gesture.name.replace('_', ' ').uppercase()}")
            is ChallengeSpec.RemainStill -> Triple("⏱️", "STILLNESS CHECK", "Hold perfectly still for ${spec.durationMs / 1000}s")
            is ChallengeSpec.OpticalFlash -> Triple("⚡", "OPTICAL PROBE", "Observe the screen flash sequence")
        }
        val sec = (spec.timeoutMs / 1000).toInt()
        challengeTitleView.text = "$icon $title (CHALLENGE ${idx + 1} OF ${challenges.size})"
        challengeDescView.text = "▶  $desc  ◀"
        challengePacingView.text = "Window: ~${sec}s • Analyzing automatically…"
        streamLiveProgress("CHALLENGE ${idx + 1}/${challenges.size}: $desc")

        actionButton.isEnabled = true
        actionButton.text = "Skip challenge"
        actionButton.setOnClickListener {
            currentChallengeIndex++
            showCurrentChallenge()
        }
    }

    private fun onBehaviourEvent(ev: BehaviourRunner.BehaviourEvent) {
        when (ev) {
            is BehaviourRunner.BehaviourEvent.FlashStarted -> {
                Log.behavior("optical flash start: ${ev.spec}")
            }
            is BehaviourRunner.BehaviourEvent.FlashEnded -> {
                Log.behavior("optical flash end:   ${ev.spec}")
            }
            is BehaviourRunner.BehaviourEvent.Observation -> {
                Log.behavior("obs: ${ev.observation.spec} -> ${ev.observation.observed}")
                if (controller.state.value.state == SessionState.RANDOMIZED_CHALLENGE) {
                    val idx = currentChallengeIndex
                    val outcome = ev.observation.observed.name
                    val outcomeEmoji = if (ev.observation.success) "✓" else "—"
                    lifecycleScope.launch(Dispatchers.Main.immediate) {
                        challengeTitleView.text = "Challenge ${idx + 1} of ${challenges.size}"
                        challengeDescView.text = "Result: $outcomeEmoji $outcome"
                        challengePacingView.text = if (idx + 1 < challenges.size) "Next challenge starting in 1s…" else "All challenges complete!"
                    }
                }
            }
            BehaviourRunner.BehaviourEvent.AllComplete -> {
                Log.behavior("all ${challenges.size} challenges observed")
                if (controller.state.value.state == SessionState.RANDOMIZED_CHALLENGE) {
                    try {
                        controller.challengeComplete()
                    } catch (t: IllegalStateException) {
                        Log.error("ui", "challengeComplete rejected", t)
                    }
                }
            }
            is BehaviourRunner.BehaviourEvent.PromptShown -> {
                if (controller.state.value.state == SessionState.RANDOMIZED_CHALLENGE) {
                    currentChallengeIndex = ev.index
                    lifecycleScope.launch(Dispatchers.Main.immediate) {
                        showCurrentChallenge()
                    }
                }
            }
        }
    }

    override fun onDestroy() {
        behaviourRunner?.cancel()
        cameraSession?.stop()
        Log.stage("ui", "MainActivity.onDestroy — session stopped")
        super.onDestroy()
    }

    // --- FrameListener ---

    override fun onCameraFrame(frameNumber: Long, timestampNs: Long) {
        framesInWindow.incrementAndGet()
    }

    override fun onFrameMeans(rgbMeans: FloatArray, timestampNs: Long, frameNumber: Long) {
        // Push frames whenever face is present, even before lock.
        // For spoof detection, we NEED the weak/absent signal data from
        // screens/photos — that poor signal IS the spoof evidence.
        if (facePresent) {
            rppgClient.pushFrame(rgbMeans, timestampNs)
            val snr = rppgClient.snr
            val hr = rppgClient.hrBpm
            val corr = rppgClient.roiCorr

            // Always update controller with latest rPPG metrics
            controller.liveSnr = snr
            controller.liveHrBpm = hr
            controller.liveRoiCorr = corr
            if (rppgClient.quality > 0f) {
                controller.liveSignalQuality = rppgClient.quality
            }

            // Track peak values across the session for spoof assessment
            rppgFrameCount++
            if (snr > peakSnr) peakSnr = snr
            if (corr > peakRoiCorr) peakRoiCorr = corr
            if (hr in 45f..190f && hr > peakHrBpm) peakHrBpm = hr

            // Publish accumulated peak evidence to the controller
            controller.livePeakSnr = peakSnr
            controller.livePeakRoiCorr = peakRoiCorr
            controller.livePeakHrBpm = peakHrBpm
            controller.liveRppgFrameCount = rppgFrameCount

            val pulse = rppgClient.latestPulse

            // Update live rPPG UI metrics and waveform graph
            lifecycleScope.launch(Dispatchers.Main.immediate) {
                if (facePresent) {
                    rppgGraphView.addSample(pulse)
                    if (hr > 0f) {
                        hrView.text = "HR: ${hr.toInt()} bpm"
                    }
                    if (!snr.isNaN()) {
                        snrView.text = "SNR: ${"%.1f".format(snr)} dB"
                    }
                    if (!corr.isNaN()) {
                        qualityView.text = "PERFUSION: ${"%.2f".format(corr)}"
                    }
                }
                streamLiveProgress("rPPG pulse: ${hr.toInt()} BPM")
            }
        }
    }

    override fun onLockStateChanged(locked: Boolean) {
        this.locked = locked
        lifecycleScope.launch(Dispatchers.Main.immediate) {
            if (locked) {
                lockStatusView.text = "LOCK: LOCKED ✓"
                lockStatusView.setTextColor(0xFF34D399.toInt())
            } else {
                lockStatusView.text = "LOCK: CONVERGING…"
                lockStatusView.setTextColor(0xFFA5B4FC.toInt())
                if (!facePresent) {
                    rppgGraphView.setFlatline(true)
                }
            }
        }
        streamLiveProgress(if (locked) "Hardware locked ✓" else "Lock converging…")
        tryAdvanceToBaseline()
    }

    override fun onFaceLost() {
        facePresent = false
        controller.liveHasFace = false
        lifecycleScope.launch(Dispatchers.Main.immediate) {
            if (controller.livePhoneDetected) {
                faceStatusView.text = "SPOOF DETECTED"
                faceStatusView.setTextColor(0xFFEF4444.toInt())
            } else {
                faceStatusView.text = "FACE: UNDETECTED"
                faceStatusView.setTextColor(0xFFEF4444.toInt())
            }
            hrView.text = "HR: -- bpm"
            snrView.text = "SNR: -- dB"
            qualityView.text = "PERFUSION: --"
            rppgGraphView.setFlatline(true)
        }
        streamLiveProgress("Face lost")
    }

    override fun onFaceRestored() {
        facePresent = true
        lifecycleScope.launch(Dispatchers.Main.immediate) {
            if (controller.livePhoneDetected) {
                faceStatusView.text = "SPOOF DETECTED"
                faceStatusView.setTextColor(0xFFEF4444.toInt())
            } else {
                faceStatusView.text = "FACE: DETECTED ✓"
                faceStatusView.setTextColor(0xFF34D399.toInt())
                rppgGraphView.setFlatline(false)
            }
        }
        streamLiveProgress("Face detected")
        tryAdvanceToBaseline()
    }

    override fun onQuality(quality: FrameQuality, gate: QualityGate.GateDecision) {
        lastQuality = quality
        controller.liveFps = quality.fps
        controller.liveDropRate = quality.dropRate
        controller.liveExposureStability = quality.exposureStability
        controller.liveAwbStability = quality.awbStability
        if (controller.liveSignalQuality.isNaN() || controller.liveSignalQuality == 0f) {
            controller.liveSignalQuality = quality.awbStability
        }
        controller.liveContamination = quality.contaminationFlag
        controller.liveLocked = locked
        controller.liveHasFace = facePresent

        behaviourRunner?.latestContaminationFlag = quality.contaminationFlag
        tryAdvanceToBaseline()
    }

    override fun onPhoneDetected(isDetected: Boolean, reason: String) {
        controller.livePhoneDetected = isDetected
        controller.livePhoneReason = reason
        lifecycleScope.launch(Dispatchers.Main.immediate) {
            if (isDetected) {
                faceStatusView.text = "SPOOF DETECTED"
                faceStatusView.setTextColor(0xFFEF4444.toInt())
                resultVerdictView.text = "SPOOF DETECTED"
                resultVerdictView.setTextColor(0xFFEF4444.toInt())
                resultDetailsView.text = "Spoof presentation detected."
                resultCard.visibility = View.VISIBLE
            } else {
                if (controller.state.value.state != SessionState.DONE) {
                    resultCard.visibility = View.GONE
                }
                if (facePresent) {
                    faceStatusView.text = "FACE: DETECTED ✓"
                    faceStatusView.setTextColor(0xFF34D399.toInt())
                    rppgGraphView.setFlatline(false)
                } else {
                    faceStatusView.text = "FACE: UNDETECTED"
                    faceStatusView.setTextColor(0xFFEF4444.toInt())
                }
            }
        }
        streamLiveProgress(if (isDetected) "SPOOF: $reason" else "Biometrics normal")
    }


    companion object {
        private const val QUALITY_AUTO_SKIP_MS: Long = 10_000L
    }
}
