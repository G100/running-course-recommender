package com.runmate.app

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableDoubleStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/** 화면이 지금 어디에 있는지: 질문(거리·모양·풍경) → 코스 확인 → 달리는 중 */
enum class Phase { Ask, Course, Guiding }

/** 아래 막대: 도착 예정 시각 · 남은 거리 · 남은 시간 */
data class Eta(val clock: String, val distance: String, val minutes: Int)

/** 달린 뒤 평가 카드 */
class Rating(val questions: List<FeedbackQuestion>) {
    var stars by mutableIntStateOf(0)
    val answers = mutableStateMapOf<String, String>()
    var comment by mutableStateOf("")
    var sending by mutableStateOf(false)
}

/** 화면이 그리는 값 전부. MainActivity가 고치고, Compose가 바뀐 곳만 다시 그린다. */
class RunState(val username: String) {
    // 질문
    var step by mutableIntStateOf(0)
    var distanceKm by mutableDoubleStateOf(5.0)
    var routeType by mutableStateOf("loop")            // loop · roundtrip · oneway
    var scenery by mutableStateOf<List<SceneryOption>>(emptyList())
    val chosen = mutableStateListOf<String>()
    var destination by mutableStateOf<Place?>(null)
    var placeLabel by mutableStateOf("현재 위치 확인 중")
    var hasLocation by mutableStateOf(false)
    var finding by mutableStateOf(false)
    var findStartedMs by mutableStateOf(0L)

    // 코스
    var phase by mutableStateOf(Phase.Ask)
    var results by mutableStateOf<List<Recommendation>>(emptyList())
    var picked by mutableIntStateOf(0)
    var aligning by mutableStateOf(false)
    var deliverKm by mutableStateOf<Double?>(null)
    var notice by mutableStateOf<String?>(null)
    var attribution by mutableStateOf<String?>(null)
    var sheetPx by mutableIntStateOf(0)                 // 코스 카드 높이 (지도가 코스를 그 위쪽에 맞춘다)

    // 짧은 알림 (오류·진행 상황). 화면 위쪽 알약으로 잠깐 보인다
    var message by mutableStateOf<String?>(null)

    // 달리는 중
    var banner by mutableStateOf<GuideAction.Banner?>(null)
    var eta by mutableStateOf<Eta?>(null)
    var voiceOn by mutableStateOf(true)
    var following by mutableStateOf(true)
    var arrived by mutableStateOf(false)
    var finishKm by mutableStateOf<Double?>(null)        // 도착 판에 보일 실제로 나아간 거리·걸린 시간
    var finishSeconds by mutableStateOf(0L)
    var rating by mutableStateOf<Rating?>(null)
    var taste by mutableStateOf<List<String>>(emptyList())

    // 즐겨찾기 · 내 기록
    val savedIds = mutableStateListOf<String>()          // 내가 즐겨찾기한 코스 id (코스 카드의 별)
    var showRecords by mutableStateOf(false)
    var records by mutableStateOf<MyTaste?>(null)        // null = 불러오는 중
    var favorites by mutableStateOf<List<Favorite>?>(null)
    var recordsError by mutableStateOf<String?>(null)

    val course: Course? get() = results.getOrNull(picked)?.course
    val pick: Recommendation? get() = results.getOrNull(picked)
}
