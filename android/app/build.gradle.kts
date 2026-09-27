plugins {
    id("com.android.application")
    // No explicit Kotlin plugin: AGP 9.0+ provides built-in Kotlin
    // support enabled by default. See:
    // https://blog.jetbrains.com/kotlin/2026/01/update-your-projects-for-agp9/
}

android {
    namespace = "com.edgeppg.app"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.edgeppg.app"
        minSdk = 26
        targetSdk = 37
        versionCode = 1
        versionName = "0.1"

        // Stage 1: only arm64 is in scope for the iQOO 15 target. Camera2 interop +
        // any future NDK DSP (Stage 4) will only ship for this ABI.
        ndk {
            abiFilters += listOf("arm64-v8a")
        }
    }

    buildTypes {
        debug {
            // EDGEPPG_DEV_MODE controls on-device diagnostics surfacing.
            // Kept off by default in release; debug flips it on for engineering.
            buildConfigField("boolean", "EDGEPPG_DEV_MODE", "true")
        }
        release {
            isMinifyEnabled = false
            buildConfigField("boolean", "EDGEPPG_DEV_MODE", "false")
        }
    }

    buildFeatures {
        // Stage 1: keep this minimal. View binding is only enabled if/when
        // we add XML layouts beyond the manifest. Left off for the placeholder
        // stage to avoid pulling extra code-gen for an unused feature.
        buildConfig = true
    }

    compileOptions {
        // CameraX requires API 26+ (already minSdk). Source/target compat
        // are kept at 17 to match the rest of the verified toolchain.
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

// (Empty — see comment below for the platform-jar workaround.)

dependencies {
    // ---- Stage 1: Android foundation ----
    // AndroidX core / lifecycle for ComponentActivity and LifecycleOwner.
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-ktx:1.9.3")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-viewmodel-ktx:2.8.7")

    // Coroutines for structured concurrency on the lifecycle scope. Used by
    // the heartbeat in MainActivity (Stage 1) and by every per-session
    // coroutine in later stages.
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")

    // ---- Stage 2: CameraX (camera-core, camera2 interop, lifecycle, view) ----
    // Per TechStack §8: CameraX is the documented candidate. The camera-camera2
    // interop artifact is required for AE/AWB lock control used in
    // ConvergenceLockController.
    val cameraxVersion = "1.4.1"
    implementation("androidx.camera:camera-core:$cameraxVersion")
    implementation("androidx.camera:camera-camera2:$cameraxVersion")
    implementation("androidx.camera:camera-lifecycle:$cameraxVersion")
    implementation("androidx.camera:camera-view:$cameraxVersion")

    // Stage 2: ML Kit Face Mesh (468-point). Bundled (~6.4 MB) per Google's
    // docs — added here, only here, not earlier. Architecture §4.1 / §4.5
    // require 468-point landmarks; bounding-box-only would not suffice.
    implementation("com.google.mlkit:face-mesh-detection:16.0.0-beta1")

    // ---- Stage 13: Transport (Wi-Fi primary, QR fallback) ----
    // OkHttp 4.12.0 is the last 4.x line. JDK 8+, Android minSdk 21+,
    // which is well below our minSdk = 26. The OkHttp 5.x line requires
    // JDK 11+; we are JDK 25.0.3 per ANDROID_ENVIRONMENT.md, so either
    // would build, but 4.12.0 is the conservative choice that has been
    // on Maven Central since long before AGP 9.4.1 and is known to
    // work under Gradle 9.6.0 / AGP 9.4.1.
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    // ---- Stage 13: QR fallback transport ----
    // ZXing core 3.5.4 is the current stable. Only `core` is needed;
    // `android` brings in Android-specific code we don't use. The
    // transport emits a QR code the user scans / pastes into the
    // verifier dashboard (Architecture §10 fallback).
    implementation("com.google.zxing:core:3.5.4")

    // ---- Stage 15 Task 6: JVM unit tests ----
    // JUnit 4 is the smallest-machinery test framework that pairs with
    // AGP 9.4.1's built-in-Kotlin JVM test source set. We only test
    // the pure-Kotlin modules (no Android imports) in `src/test/` —
    // anything that pulls in `android.security.keystore.*` is out
    // of scope for a JVM unit test.
    testImplementation("junit:junit:4.13.2")
    // Real org.json for JVM unit tests: android.jar stubs throw
    // "not mocked", so tests that parse JSON use this JVM library.
    // Test-only; the app itself keeps using Android's org.json.
    testImplementation("org.json:json:20231013")
}

// AGP 9.4.1 with built-in Kotlin does not always surface the
// androidx AARs' `classes.jar` to the Kotlin task's classpath the
// way the Java compile does. The result on this project is
// `Unresolved reference: addSessionCaptureCallback` in
// `capture/CameraSession.kt:191` and
// `capture/ConvergenceLockController.kt:44`, plus `gains.size` and
// `gains[i]` in `CameraSession.kt:204-207` (where `R<FloatArray>`
// is the camera2 AWB-gain type, requiring `.toFloatArray()` first).
// The fix: take the standard compile classpath's resolved component
// files (which AGP populates with the AAR-expanded classes.jar
// entries) and add them to the Kotlin task's `libraries`. We force
// configuration-time resolution via `.resolve()` on a lazy copy of
// the classpath, then call `.libraries.from(...)` on the Kotlin task.
androidComponents {
    onVariants(selector().all()) { variant ->
        val capName = variant.name.replaceFirstChar { it.titlecase() }
        val kotlinTaskName = "compile" + capName + "Kotlin"
        val compileConfigName = "${variant.name}CompileClasspath"
        afterEvaluate {
            val cc = configurations.findByName(compileConfigName)
            if (cc != null) {
                val resolved: org.gradle.api.file.FileCollection =
                    project.files(cc.resolve())
                tasks.withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompile>().configureEach {
                    if (name == kotlinTaskName) {
                        this.libraries.from(resolved)
                    }
                }
            }
        }
    }
}
