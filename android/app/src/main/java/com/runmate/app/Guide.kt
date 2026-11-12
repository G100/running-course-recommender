package com.runmate.app

import kotlin.math.abs
import kotlin.math.roundToInt

/** 안내가 화면·음성·서버에 시키는 일. */
sealed class GuideAction {
    data class Say(val text: String, val interrupt: Boolean = false) : GuideAction()
    /** 다음에 할 일과 남은 거리, 그다음 할 일 (화면 위 안내 띠). next가 null이면 띠를 숨긴다. */
    data class Banner(val next: Step?, val remainingM: Double, val after: Step?) : GuideAction()
    data class Status(val text: String) : GuideAction()
    /** 코스를 벗어났다 — 서버에 돌아가는 길을 묻는다 (POST /courses/reroute). */
    data class Reroute(val position: LatLng, val progressM: Double) : GuideAction()
    object Arrived : GuideAction()
}

/**
 * GPS 안내 (웹 페이지 startNavigationGPS와 같은 규칙). 위치를 넣으면 할 일을 돌려준다 — 화면·음성·네트워크는 부르는 쪽이 한다.
 *
 * - 회전 안내는 두 번만 말한다: 180m 앞에서 예고("120m 앞에서 오른쪽으로 도세요"), 30m 앞에서 실행.
 *   '직진' 안내(Tmap이 건널목마다 넣는다)는 건너뛴다. 바퀴가 바뀌는 안내는 지나갈 때 한 번, 거리 없이.
 * - 경로에서 40m 넘게 8초 동안 벗어나면 돌아가는 길을 묻는다. 못 찾으면 30초 뒤에 다시 묻는다.
 * - 도착: 경로를 따라 끝점 20m 안까지 왔고, 사람이 그 거리를 달릴 수 있는 시간이 지났을 때만.
 */
class Guide(course: Course, private val startedAtMs: Long) {
    private var path = course.path
    private var cum = Geo.cumulative(path)
    private var steps = locate(course.steps, path, cum)
    private var total = cum.last()
    private val requiredMs = (total / 1000 * FASTEST_PACE_MIN_PER_KM * 60_000).toLong()

    /** 경로를 따라 지금까지 온 거리 (뒤로는 가지 않는다). */
    var progressM = 0.0
        private set
    var done = false
        private set

    private var spokenKey: String? = null
    private var offSince: Long? = null
    private var rerouting = false
    private var retryAt = 0L
    private var toldFailure = false
    private var note = ""

    fun onLocation(here: LatLng, nowMs: Long): List<GuideAction> {
        if (done) return emptyList()
        val actions = mutableListOf<GuideAction>()
        val at = Geo.onPath(here, path, cum, progressM)
        // 경로에서 멀리 벗어난 위치로는 진행 거리를 옮기지 않는다 (엉뚱한 구간으로 건너뛰지 않게)
        if (at.offM <= OFF_COURSE_M) progressM = maxOf(progressM, at.alongM)

        if (at.offM > OFF_COURSE_M) {
            val since = offSince ?: nowMs.also { offSince = it }
            if (!rerouting && nowMs - since >= OFF_COURSE_HOLD_MS && nowMs >= retryAt) {
                rerouting = true
                // 못 찾아서 다시 찾는 중에는 같은 말을 되풀이하지 않는다
                if (!toldFailure) actions += GuideAction.Say("코스를 벗어났습니다. 경로를 재탐색합니다.", interrupt = true)
                actions += GuideAction.Reroute(here, progressM)
            }
        } else {
            offSince = null
            toldFailure = false
            retryAt = 0
        }

        // 아직 달릴 시간이 안 됐으면 끝 직전으로 친다 (GPS가 튀어 앞쪽 구간에 잡혀도 도착으로 치지 않게)
        val ranLongEnough = nowMs - startedAtMs >= requiredMs
        val counted = if (ranLongEnough) progressM else minOf(progressM, total - ARRIVE_M - 1)
        if (counted >= total - ARRIVE_M) {
            done = true
            actions += GuideAction.Banner(null, 0.0, null)
            actions += GuideAction.Say("목적지에 도착했습니다. 수고하셨습니다.", interrupt = true)
            actions += GuideAction.Arrived
            return actions
        }
        val (shown, say) = nextTurn()
        actions += shown
        say?.let { actions += it }
        actions += GuideAction.Status(
            if (at.offM > OFF_COURSE_M) {
                when {
                    rerouting -> "코스를 벗어났어요 · 돌아가는 길을 찾는 중"
                    toldFailure -> "돌아가는 길을 찾지 못했어요 · 경로에서 약 ${at.offM.roundToInt()}m · 곧 다시 찾아요"
                    else -> "경로에서 약 ${at.offM.roundToInt()}m 떨어져 있어요"
                }
            } else "안내 중$note"
        )
        return actions
    }

    /** 서버가 돌아가는 길을 줬다: 지금 자리에서 코스로 돌아가 남은 코스를 잇는 경로. */
    fun onRerouted(back: Course, extraM: Double): List<GuideAction> {
        rerouting = false
        if (offSince == null) return emptyList()   // 그사이 스스로 코스로 돌아왔다 — 원래 안내를 계속한다
        path = back.path
        cum = Geo.cumulative(path)
        steps = locate(back.steps, path, cum)
        total = cum.last()
        progressM = 0.0
        spokenKey = null
        offSince = null
        toldFailure = false
        retryAt = 0
        val change = distanceChange(extraM)
        note = " · 코스로 돌아가는 길${change.second}"
        return listOf(GuideAction.Say("새 경로로 안내합니다.${change.first}", interrupt = true))
    }

    fun onRerouteFailed(nowMs: Long): List<GuideAction> {
        rerouting = false
        retryAt = nowMs + REROUTE_RETRY_MS
        if (offSince != null && !toldFailure) {
            toldFailure = true
            return listOf(GuideAction.Say("경로를 찾지 못했습니다. 원래 코스로 돌아가 주세요.", interrupt = true))
        }
        return emptyList()
    }

    /** 지금 안내 중인 경로 (재탐색하면 돌아가는 길로 바뀐다). */
    fun currentPath(): List<LatLng> = path

    /** 재탐색을 물을 때 보내는 남은 안내 (서버가 새 경로에 이어 붙인다). */
    fun currentSteps(): List<Step> = steps

    /** 화면 위 안내 띠와, 지금 말할 안내(있으면). */
    private fun nextTurn(): Pair<GuideAction.Banner, GuideAction.Say?> {
        val ahead = steps.filter { (it.cumM ?: 0.0) > progressM + 0.5 && it.turnType != STRAIGHT }
        val next = ahead.firstOrNull() ?: return GuideAction.Banner(null, 0.0, null) to null
        val remaining = (next.cumM ?: 0.0) - progressM
        return GuideAction.Banner(next, remaining, ahead.getOrNull(1)) to announce(next, remaining)
    }

    /** 회전 안내를 말할 때인가 (예고·실행 두 번만). */
    private fun announce(step: Step, remainingM: Double): GuideAction.Say? {
        val stage = when {
            remainingM <= NOW_M -> "now"
            remainingM <= SOON_M -> "soon"
            else -> return null
        }
        if (step.turnType == LAP_TURN) {
            if (stage != "now") return null   // 바퀴가 바뀌는 건 미리 알릴 일이 아니다
            val key = "${step.cumM}|lap"
            if (key == spokenKey) return null
            spokenKey = key
            return GuideAction.Say(step.instruction)
        }
        val key = "${step.cumM}|$stage"
        if (key == spokenKey) return null
        spokenKey = key
        return GuideAction.Say(if (stage == "now") step.instruction else "${distanceText(remainingM)} 앞에서 ${step.instruction}")
    }

    companion object {
        const val OFF_COURSE_M = 40.0
        const val OFF_COURSE_HOLD_MS = 8_000L
        const val REROUTE_RETRY_MS = 30_000L
        const val ARRIVE_M = 20.0
        const val FASTEST_PACE_MIN_PER_KM = 2.5   // 사람이 이보다 빨리 달릴 수는 없다 (마라톤 세계 기록 약 2.9분/km)
        const val SOON_M = 180.0
        const val NOW_M = 30.0
        const val STRAIGHT = 11
        const val LAP_TURN = 300   // 여러 바퀴 코스에서 바퀴가 바뀌는 안내 (서버 laps.py와 같은 번호)
        const val SAY_CHANGE_FROM_M = 50.0

        fun distanceText(m: Double): String = if (m >= 1000) "%.1fkm".format(m / 1000) else "${m.roundToInt()}m"

        /** 재탐색으로 전체 거리가 얼마나 달라지는지: (음성, 화면). 50m 안이면 말하지 않는다. */
        fun distanceChange(extraM: Double): Pair<String, String> {
            val m = abs(extraM)
            if (m < SAY_CHANGE_FROM_M) return "" to ""
            val rounded = (m / 10).roundToInt() * 10.0
            val spoken = if (m >= 1000) "%.1f킬로미터".format(m / 1000) else "${rounded.toInt()}미터"
            val more = extraM > 0
            return " 전체 거리가 약 $spoken ${if (more) "늘어납니다" else "줄어듭니다"}." to
                " · 전체 거리 약 ${distanceText(rounded)} ${if (more) "늘어남" else "줄어듦"}"
        }

        /** 안내마다 경로 위 위치. 서버가 준 cum_m을 쓴다 (왕복은 갈 때·올 때 좌표가 같아 가까운 점으로 찾으면 틀린다). */
        fun locate(steps: List<Step>, path: List<LatLng>, cum: DoubleArray): List<Step> = steps.map { s ->
            if (s.cumM != null) s else {
                val nearest = path.indices.minByOrNull { Geo.meters(s.at, path[it]) } ?: 0
                s.copy(cumM = cum[nearest])
            }
        }.sortedBy { it.cumM }
    }
}
