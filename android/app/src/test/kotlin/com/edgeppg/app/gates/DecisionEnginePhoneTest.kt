package com.edgeppg.app.gates

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DecisionEnginePhoneTest {

    @Test
    fun decide_with_phone_detected_forces_spoof_immediately() {
        val inputs = DecisionEngine.Inputs(
            integrityOk = true,
            hasFace = true,
            lockState = true,
            contaminationFlag = false,
            fps = 30f,
            dropRate = 0f,
            exposureStability = 0.95f,
            awbStability = 0.95f,
            challengeCompleted = true,
            liveProbability = 0.99f, // Even if ML model thinks live, phone presence forces SPOOF
            phoneDetected = true,
            phoneReason = "device-label:mobile phone(0.92)",
        )

        val verdict = DecisionEngine.decide(inputs)
        assertEquals(DecisionEngine.Decision.SPOOF, verdict.decision)
        assertTrue(verdict.reason.startsWith("phone-detected-spoof"))
    }

    @Test
    fun decide_without_phone_and_high_liveP_returns_live() {
        val inputs = DecisionEngine.Inputs(
            integrityOk = true,
            hasFace = true,
            lockState = true,
            contaminationFlag = false,
            fps = 30f,
            dropRate = 0f,
            exposureStability = 0.95f,
            awbStability = 0.95f,
            challengeCompleted = true,
            liveProbability = 0.92f,
            phoneDetected = false,
        )

        val verdict = DecisionEngine.decide(inputs)
        assertEquals(DecisionEngine.Decision.LIVE, verdict.decision)
    }

    @Test
    fun decide_with_phone_detected_overrides_insufficient_quality() {
        // Even if applicant moves or has poor quality, seeing a phone is an immediate SPOOF
        val inputs = DecisionEngine.Inputs(
            integrityOk = true,
            hasFace = false,
            lockState = false,
            contaminationFlag = true,
            fps = 10f,
            dropRate = 0.5f,
            exposureStability = 0.2f,
            awbStability = 0.2f,
            challengeCompleted = false,
            liveProbability = Float.NaN,
            phoneDetected = true,
            phoneReason = "planar-mesh-collapse:score=0.95",
        )

        val verdict = DecisionEngine.decide(inputs)
        assertEquals(DecisionEngine.Decision.SPOOF, verdict.decision)
        assertTrue(verdict.reason.startsWith("phone-detected-spoof"))
    }
}
