package com.runmate.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class GpsFilterTest {
    private val start = LatLng(35.1760, 126.9050)

    /** 북쪽으로 m미터 간 자리 (위도 1도 ≈ 111,195m) */
    private fun north(m: Double, from: LatLng = start) = LatLng(from.lat + m / 111_195.0, from.lng)
    private fun east(m: Double, from: LatLng = start) = LatLng(from.lat, from.lng + m / (111_195.0 * Math.cos(Math.toRadians(from.lat))))

    @Test
    fun firstGoodFixIsTaken() {
        val f = GpsFilter()
        assertTrue(f.accept(start, 5f, 0))
    }

    @Test
    fun runningPaceIsTaken() {
        val f = GpsFilter()
        assertTrue(f.accept(start, 5f, 0))
        // 4m/s로 1초마다 (6분대/km 페이스보다 빠른 달리기)
        for (s in 1..20) assertTrue("${s}초", f.accept(north(4.0 * s), 5f, s * 1000L))
    }

    @Test
    fun poorAccuracyIsDropped() {
        val f = GpsFilter()
        assertTrue(f.accept(start, 5f, 0))
        assertFalse(f.accept(north(4.0), 60f, 1000))
        // 다음 좋은 위치는 받는다
        assertTrue(f.accept(north(8.0), 5f, 2000))
    }

    @Test
    fun unknownAccuracyIsNotHeldAgainstTheFix() {
        val f = GpsFilter()
        assertTrue(f.accept(start, null, 0))
        assertTrue(f.accept(north(4.0), null, 1000))
    }

    @Test
    fun onlyPoorFixesForAWhileAreTakenRatherThanFreezing() {
        // 빌딩 숲에서 정확도가 계속 나쁘면 아예 멈추는 것보다 나쁜 위치라도 쓰는 게 낫다
        val f = GpsFilter()
        assertTrue(f.accept(start, 5f, 0))
        var taken = false
        for (s in 1..20) if (f.accept(north(4.0 * s), 50f, s * 1000L)) taken = true
        assertTrue(taken)
    }

    @Test
    fun singleJumpIsDropped() {
        val f = GpsFilter()
        assertTrue(f.accept(start, 5f, 0))
        assertTrue(f.accept(north(4.0), 5f, 1000))
        // 1초 만에 옆으로 80m: 사람이 달릴 수 없다
        assertFalse(f.accept(east(80.0, north(8.0)), 8f, 2000))
        // 튀기 전 자리 근처로 돌아온 다음 위치는 받는다
        assertTrue(f.accept(north(12.0), 5f, 3000))
    }

    @Test
    fun scatteredJumpsNeverWin() {
        // 이리저리 튀는 위치는 서로 이어지지 않으니 계속 버린다
        val f = GpsFilter()
        assertTrue(f.accept(start, 5f, 0))
        assertFalse(f.accept(east(90.0), 10f, 1000))
        assertFalse(f.accept(east(-90.0), 10f, 2000))
        assertFalse(f.accept(north(-100.0), 10f, 3000))
        assertFalse(f.accept(east(95.0), 10f, 4000))
    }

    @Test
    fun consistentNewPlaceIsTakenAfterAFewFixes() {
        // 터널·지하도를 나와 GPS가 제자리를 찾은 경우: 새 자리에서 이어지는 위치가 몇 번 오면 그쪽을 믿는다
        val f = GpsFilter()
        assertTrue(f.accept(start, 5f, 0))
        val far = east(150.0)
        val results = (0 until GpsFilter.CONFIRM_FIXES).map { f.accept(north(4.0 * it, far), 5f, 1000L + it * 1000L) }
        assertFalse(results.first())
        assertTrue(results.last())
        // 그 뒤로는 새 자리 기준으로 받는다
        assertTrue(f.accept(north(4.0 * GpsFilter.CONFIRM_FIXES, far), 5f, 1000L + GpsFilter.CONFIRM_FIXES * 1000L))
    }

    @Test
    fun longGapAllowsLongerMove() {
        // 신호를 30초 잃었다 다시 잡히면 그동안 달린 만큼은 떨어져 있을 수 있다
        val f = GpsFilter()
        assertTrue(f.accept(start, 5f, 0))
        assertTrue(f.accept(north(120.0), 5f, 30_000))
    }

    @Test
    fun realDetourStillReachesTheGuide() {
        // 진짜로 길을 벗어난 러너(옆길로 4m/s)는 걸러지지 않아야 재탐색이 일어난다
        val f = GpsFilter()
        assertTrue(f.accept(start, 5f, 0))
        var taken = 0
        for (s in 1..15) if (f.accept(east(4.0 * s), 5f, s * 1000L)) taken++
        assertEquals(15, taken)
    }
}
