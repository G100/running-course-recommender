package com.runmate.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import kotlin.math.abs

/** 달리는 중 지도 방향: 모퉁이에 닿기 전에는 돌지 않고, 모퉁이를 지나며 돈다. */
class NavHeadingTest {
    private val start = LatLng(35.1760, 126.9050)
    private fun east(m: Double, from: LatLng) = LatLng(from.lat, from.lng + m / (111_195.0 * Math.cos(Math.toRadians(from.lat))))
    private fun north(m: Double, from: LatLng) = LatLng(from.lat + m / 111_195.0, from.lng)

    // 동쪽으로 100m 간 뒤 왼쪽(북쪽)으로 100m
    private val corner = east(100.0, start)
    private val path = listOf(start, corner, north(100.0, corner))
    private val cum = Geo.cumulative(path)

    private fun close(expected: Double, actual: Double?, tol: Double = 3.0) {
        requireNotNull(actual)
        val diff = abs(((actual - expected + 540) % 360) - 180)
        assert(diff <= tol) { "기대 $expected°, 실제 $actual°" }
    }

    @Test
    fun beforeTheCornerItStillFacesTheCurrentRoad() {
        close(90.0, Geo.headingAt(path, cum, 50.0))
        close(90.0, Geo.headingAt(path, cum, 90.0))
        // 모퉁이 5m 앞: 예전 방식(30m 앞을 봄)은 이미 북쪽으로 80° 가까이 돌아 있었다
        close(90.0, Geo.headingAt(path, cum, 95.0))
    }

    @Test
    fun itTurnsWhileGoingRoundTheCorner() {
        val at = Geo.headingAt(path, cum, 102.0)!!
        assert(at < 85 && at > 5) { "모퉁이를 도는 중이면 동쪽과 북쪽 사이: $at" }
    }

    @Test
    fun afterTheCornerItFacesTheNewRoad() {
        close(0.0, Geo.headingAt(path, cum, 112.0))
        close(0.0, Geo.headingAt(path, cum, 150.0))
    }

    @Test
    fun atTheVeryStartItFacesTheFirstRoad() {
        close(90.0, Geo.headingAt(path, cum, 0.0))
    }

    @Test
    fun aPathWithNoLengthHasNoHeading() {
        assertNull(Geo.headingAt(listOf(start, start), doubleArrayOf(0.0, 0.0), 0.0))
    }

    @Test
    fun turnTakesTheShortWayRound() {
        assertEquals(20.0, Geo.turnDegrees(350.0, 10.0), 1e-9)
        assertEquals(-20.0, Geo.turnDegrees(10.0, 350.0), 1e-9)
        assertEquals(90.0, Geo.turnDegrees(0.0, 90.0), 1e-9)
    }
}
