package com.runmate.app

/** 고를 수 있는 거리 (웹 페이지의 다이얼과 같다): 10km까지 0.5km씩, 그 위는 1km씩, 맨 끝은 풀코스. */
object Distance {
    const val MIN = 1.0
    const val MID = 10.0
    const val MAX = 42.195
    const val HALF = 21.0975

    /** 바로 고르는 버튼: 5km · 10km · 하프 · 풀코스 */
    val PRESETS = listOf("5km" to 5.0, "10km" to 10.0, "하프" to HALF, "풀코스" to MAX)

    fun up(km: Double): Double {
        val next = if (km < MID) km + 0.5 else Math.floor(km) + 1
        return if (next > MAX - 0.5) MAX else next   // 42 다음은 풀코스
    }

    fun down(km: Double): Double = maxOf(MIN, if (km <= MID) km - 0.5 else Math.ceil(km) - 1)

    fun label(km: Double): String = when (km) {
        MAX -> "풀코스 42.195km"
        HALF -> "하프 21.1km"
        else -> if (km % 1.0 == 0.0) "${km.toInt()}km" else "${km}km"
    }
}
