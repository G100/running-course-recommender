import java.util.Properties

plugins {
    id("com.android.application")
}

// 내 PC에만 있는 값: Tmap 키와 서버 주소 (android/local.properties, git에 올리지 않는다)
//   tmap.key=...                       Tmap 앱 키 (서버의 TMAP_APP_KEY와 같은 키)
//   runmate.server=http://192.168.0.10:8000   폰에서 닿는 서버 주소 (같은 와이파이의 PC 주소)
val local = Properties().apply {
    val file = rootProject.file("local.properties")
    if (file.exists()) file.inputStream().use { load(it) }
}

android {
    namespace = "com.runmate.app"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.runmate.app"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1"
        buildConfigField("String", "TMAP_KEY", "\"${local.getProperty("tmap.key", "")}\"")
        buildConfigField("String", "SERVER_URL", "\"${local.getProperty("runmate.server", "http://10.0.2.2:8000")}\"")
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    // Tmap 벡터 지도 SDK (Tmap 개발자 사이트에서 받아 app/libs에 둔다). 지도 SDK가 flatbuffers를 쓴다
    implementation(files("libs/vsm-tmap-sdk-v2-eaa-2.0.14.aar"))
    implementation(files("libs/tmap-sdk-3.8.aar"))
    implementation("com.google.flatbuffers:flatbuffers-java:24.3.25")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")   // 단위 테스트에서는 안드로이드의 org.json이 없다
}
