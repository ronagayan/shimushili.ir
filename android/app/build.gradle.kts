plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.shimushili.ir"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.shimushili.ir"
        minSdk = 26
        targetSdk = 34
        versionCode = (System.getenv("GITHUB_RUN_NUMBER") ?: "1").toInt()
        versionName = "0.1." + (System.getenv("GITHUB_RUN_NUMBER") ?: "0")
    }

    // Same key on every build, so new versions install over old ones.
    // keystore/dev.jks is for testing; before selling, set ANDROID_KEYSTORE_* to a private key.
    signingConfigs {
        create("app") {
            storeFile = file(System.getenv("ANDROID_KEYSTORE_FILE") ?: "../keystore/dev.jks")
            storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD") ?: "shimushili-dev"
            keyAlias = System.getenv("ANDROID_KEY_ALIAS") ?: "dev"
            keyPassword = System.getenv("ANDROID_KEYSTORE_PASSWORD") ?: "shimushili-dev"
        }
    }
    buildTypes {
        debug { signingConfig = signingConfigs.getByName("app") }
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("app")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true }
}

dependencies {
    val bom = platform("androidx.compose:compose-bom:2024.09.03")
    implementation(bom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-core")
    implementation("androidx.activity:activity-compose:1.9.2")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
}
