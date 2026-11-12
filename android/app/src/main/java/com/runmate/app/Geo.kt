package com.runmate.app

import kotlin.math.asin
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

/** 거리·방향 계산 (웹 페이지 navigate.html과 같은 식). */
object Geo {
    private const val R = 6_371_000.0

    fun meters(a: LatLng, b: LatLng): Double {
        val rad = Math.PI / 180
        val dLat = (b.lat - a.lat) * rad
        val dLng = (b.lng - a.lng) * rad
        val h = sin(dLat / 2).let { it * it } + cos(a.lat * rad) * cos(b.lat * rad) * sin(dLng / 2).let { it * it }
        return 2 * R * asin(sqrt(h))
    }

    fun bearing(a: LatLng, b: LatLng): Double {
        val rad = Math.PI / 180
        val y = sin((b.lng - a.lng) * rad) * cos(b.lat * rad)
        val x = cos(a.lat * rad) * sin(b.lat * rad) - sin(a.lat * rad) * cos(b.lat * rad) * cos((b.lng - a.lng) * rad)
        return (Math.toDegrees(atan2(y, x)) + 360) % 360
    }

    /** 경로를 따라 처음부터 각 점까지 온 거리. */
    fun cumulative(path: List<LatLng>): DoubleArray {
        val cum = DoubleArray(path.size)
        for (i in 1 until path.size) cum[i] = cum[i - 1] + meters(path[i - 1], path[i])
        return cum
    }

    /** 경로를 따라 d m 지점. */
    fun pointAt(path: List<LatLng>, cum: DoubleArray, d: Double): LatLng {
        if (path.size < 2) return path.first()
        val target = d.coerceIn(0.0, cum.last())
        var i = 1
        while (i < cum.size - 1 && cum[i] < target) i++
        val seg = (cum[i] - cum[i - 1]).takeIf { it > 0 } ?: 1.0
        val t = ((target - cum[i - 1]) / seg).coerceIn(0.0, 1.0)
        return LatLng(path[i - 1].lat + (path[i].lat - path[i - 1].lat) * t, path[i - 1].lng + (path[i].lng - path[i - 1].lng) * t)
    }

    /** 위치가 경로를 따라 몇 m 지점이고 경로에서 몇 m 떨어져 있나. */
    data class OnPath(val alongM: Double, val offM: Double)

    /**
     * 직전 진행 거리(hint) 근처(뒤로 50m ~ 앞으로 300m)에서만 찾는다. 전체에서 가장 가까운 점을 고르면 순환 코스의
     * 출발점(=도착점)에서 바로 끝으로 잡혀 '도착'이 떴고, 코스가 스스로 가까이 지나는 곳에서는 나중 구간으로 튀었다.
     */
    fun onPath(here: LatLng, path: List<LatLng>, cum: DoubleArray, hint: Double): OnPath {
        var best: OnPath? = null
        val lo = hint - BACK_M
        val hi = hint + AHEAD_M
        for (i in 1 until path.size) {
            if (cum[i] < lo || cum[i - 1] > hi) continue
            val a = path[i - 1]
            val b = path[i]
            val k = cos(Math.toRadians(a.lat))
            val bx = (b.lng - a.lng) * k
            val by = b.lat - a.lat
            val px = (here.lng - a.lng) * k
            val py = here.lat - a.lat
            val len = bx * bx + by * by
            val t = if (len > 0) max(0.0, min(1.0, (px * bx + py * by) / len)) else 0.0
            val q = LatLng(a.lat + (b.lat - a.lat) * t, a.lng + (b.lng - a.lng) * t)
            val off = meters(here, q)
            if (best == null || off < best.offM) best = OnPath(cum[i - 1] + (cum[i] - cum[i - 1]) * t, off)
        }
        return best ?: OnPath(hint, Double.POSITIVE_INFINITY)
    }

    private const val BACK_M = 50.0
    private const val AHEAD_M = 300.0
}
