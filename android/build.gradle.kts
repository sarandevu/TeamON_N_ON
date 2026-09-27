plugins {
    id("com.android.application") version "9.4.1" apply false
    // AGP 9.0+ has built-in Kotlin support enabled by default. The
    // explicit KGP 2.2.10 declared by the verified env (per
    // ANDROID_ENVIRONMENT.md) is incompatible with Gradle 9.6.0:
    // KGP 2.2.10 has no `gradle9` variant in its .module file
    // (variants go up to gradle81* only). The two opt-out paths per
    // https://blog.jetbrains.com/kotlin/2026/01/update-your-projects-for-agp9/
    // are (a) keep the explicit KGP and hope for a future version, or
    // (b) remove the explicit KGP and rely on built-in Kotlin (AGP 9
    // default). We take (b) here because (a) does not work today and
    // the built-in Kotlin path is the one Google and JetBrains now
    // recommend for AGP 9.x.
}
