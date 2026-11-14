// 앱 모듈 하나뿐이다. Kotlin은 AGP 9에 들어 있다(2.2.10). 화면은 Compose로 그리므로 같은 버전의 Compose 컴파일러 플러그인만 붙인다.
plugins {
    id("com.android.application") version "9.0.1" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.2.10" apply false
}
