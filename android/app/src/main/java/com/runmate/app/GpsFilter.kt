package com.runmate.app

/**
 * 달리는 중 GPS가 튀는 위치를 안내에 넣기 전에 걸러낸다.
 *
 * 빌딩 사이·다리 밑에서는 GPS가 1초 만에 수십 m 옆으로 튀었다 돌아온다. 그대로 넣으면 화살표가 점프하고,
 * 튄 자리가 경로에서 40m 넘게 이어지면 '코스를 벗어났습니다'가 잘못 나온다.
 *
 * - 정확도가 [MAX_ACCURACY_M]보다 나쁜 위치는 버린다. 다만 [POOR_GRACE_MS] 동안 좋은 위치가 하나도 없으면
 *   (빌딩 숲) 멈춰 있는 것보다 나으니 받는다.
 * - 마지막으로 받은 위치에서 사람이 달릴 수 없는 속도로 옮겨 간 위치는 버린다.
 * - 버린 위치끼리 서로 이어지면(새 자리에서 사람 속도로 움직이면) [CONFIRM_FIXES]번째에 그쪽을 믿는다 —
 *   터널을 나와 GPS가 제자리를 찾은 경우를 영영 막지 않게. 이리저리 튀는 위치는 서로 이어지지 않아 계속 버린다.
 *
 * 진짜로 길을 벗어난 러너는 사람 속도로 움직이니 걸러지지 않는다 — 재탐색은 그대로 일어난다.
 */
class GpsFilter {
    private var last: LatLng? = null
    private var lastMs = 0L
    private var pending: LatLng? = null
    private var pendingMs = 0L
    private var pendingCount = 0

    /** 이 위치를 안내에 넣어도 되나. accuracy는 m (모르면 null), nowMs는 안내 시계. */
    fun accept(here: LatLng, accuracy: Float?, nowMs: Long): Boolean {
        val anchor = last
        if (anchor == null) {
            if (accuracy != null && accuracy > MAX_ACCURACY_M) return false
            take(here, nowMs)
            return true
        }
        if (accuracy != null && accuracy > MAX_ACCURACY_M && nowMs - lastMs < POOR_GRACE_MS) return false
        val slack = JUMP_SLACK_M + minOf(accuracy?.toDouble() ?: 0.0, MAX_ACCURACY_M)
        if (reachable(anchor, lastMs, here, nowMs, slack)) {
            take(here, nowMs)
            return true
        }
        // 사람이 달릴 수 없는 점프: 앞서 버린 위치에서 이어지는지 본다
        val before = pending
        pendingCount = if (before != null && reachable(before, pendingMs, here, nowMs, slack)) pendingCount + 1 else 1
        pending = here
        pendingMs = nowMs
        if (pendingCount >= CONFIRM_FIXES) {
            take(here, nowMs)
            return true
        }
        return false
    }

    private fun reachable(from: LatLng, fromMs: Long, to: LatLng, toMs: Long, slack: Double): Boolean {
        val seconds = maxOf(0L, toMs - fromMs) / 1000.0
        return Geo.meters(from, to) <= MAX_SPEED_MPS * seconds + slack
    }

    private fun take(here: LatLng, nowMs: Long) {
        last = here
        lastMs = nowMs
        pending = null
        pendingCount = 0
    }

    companion object {
        const val MAX_ACCURACY_M = 30.0
        const val POOR_GRACE_MS = 10_000L
        /** 사람이 낼 수 있는 가장 빠른 속도 (안내의 '도착' 규칙과 같은 2.5분/km ≈ 6.7m/s) */
        const val MAX_SPEED_MPS = 1000.0 / (Guide.FASTEST_PACE_MIN_PER_KM * 60)
        /** 정확도와 별개로 두는 여유 (GPS 오차는 몇 m씩 늘 흔들린다) */
        const val JUMP_SLACK_M = 15.0
        const val CONFIRM_FIXES = 3
    }
}
