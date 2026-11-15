package com.runmate.app

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** GPS 안내: 웹 페이지(startNavigationGPS)와 같은 규칙으로 말하고, 벗어나면 돌아가는 길을 묻고, 도착을 안다. */
class GuideTest {
    private val m = 1 / 111_194.93   // 위도 1m (Geo.meters와 같은 지구 반지름)

    /** 북쪽으로 곧게 1km (10m마다 점). 300m에 직진 안내, 500m에 우회전, 800m에 바퀴 바뀜. */
    private fun straightKm(): Course {
        val path = (0..100).map { LatLng(35.0 + it * 10 * m, 127.0) }
        val steps = listOf(
            Step(LatLng(35.0 + 300 * m, 127.0), "직진하세요", Guide.STRAIGHT, 300.0),
            Step(LatLng(35.0 + 500 * m, 127.0), "오른쪽으로 도세요", 13, 500.0),
            Step(LatLng(35.0 + 800 * m, 127.0), "1바퀴 끝, 2바퀴째입니다", Guide.LAP_TURN, 800.0),
        )
        return Course("c", "곧은 길", path, steps, 1.0, 1, null, true, null, JSONObject())
    }

    private fun at(north: Double, east: Double = 0.0) = LatLng(35.0 + north * m, 127.0 + east * m / 0.8192)

    private fun said(actions: List<GuideAction>) = actions.filterIsInstance<GuideAction.Say>().map { it.text }

    /** 1초에 3m씩 달리며 말한 것을 모은다. */
    private fun run(guide: Guide, fromM: Int, toM: Int, startMs: Long = 0, east: Double = 0.0): List<String> =
        (fromM..toM step 3).flatMapIndexed { i, d -> said(guide.onLocation(at(d.toDouble(), east), startMs + i * 1000L)) }

    @Test fun each_turn_is_said_twice_ahead_and_at_the_corner_and_straight_steps_are_skipped() {
        val guide = Guide(straightKm(), 0)
        val words = run(guide, 0, 520)
        val turn = words.filter { "오른쪽" in it }
        assertEquals(2, turn.size)
        assertTrue(turn[0], turn[0].endsWith("m 후 오른쪽으로 도세요"))
        assertEquals("오른쪽으로 도세요", turn[1])
        assertFalse("직진 안내는 말하지 않는다", words.any { "직진" in it })
    }

    /** 북쪽으로 곧게 1km. 500m에 왼쪽, 그 gap m 뒤에 오른쪽. */
    private fun twoTurns(gap: Double): Course {
        val path = (0..100).map { LatLng(35.0 + it * 10 * m, 127.0) }
        val steps = listOf(
            Step(LatLng(35.0 + 500 * m, 127.0), "왼쪽으로 도세요", 12, 500.0),
            Step(LatLng(35.0 + (500 + gap) * m, 127.0), "오른쪽 용주로로 도세요", 13, 500.0 + gap),
        )
        return Course("c", "곧은 길", path, steps, 1.0, 1, null, true, null, JSONObject())
    }

    @Test fun a_turn_right_after_another_is_said_together_with_it() {
        // 광주 용봉동: '왼쪽으로 도세요'가 20~30m마다 연달아 나왔다. 두 번째는 예고 없이 갑자기 들렸다
        val words = run(Guide(twoTurns(30.0), 0), 0, 560)
        assertTrue(words.toString(), words.any { it.endsWith("m 후 왼쪽으로 도세요. 이어서 바로 오른쪽 용주로로 도세요") })
        assertTrue(words.toString(), "왼쪽으로 도세요. 이어서 바로 오른쪽 용주로로 도세요" in words)
        assertEquals("두 번째 회전은 그 자리에서 다시 말한다", "오른쪽 용주로로 도세요", words.last())
    }

    @Test fun turns_far_apart_are_said_separately() {
        val words = run(Guide(twoTurns(200.0), 0), 0, 720)
        assertFalse(words.toString(), words.any { "이어서" in it })
    }

    @Test fun a_lap_change_is_said_once_when_passing_without_a_distance() {
        val guide = Guide(straightKm(), 0)
        val words = run(guide, 0, 820).filter { "바퀴" in it }
        assertEquals(listOf("1바퀴 끝, 2바퀴째입니다"), words)
    }

    @Test fun the_banner_shows_the_next_turn_and_the_one_after() {
        val guide = Guide(straightKm(), 0)
        val banner = guide.onLocation(at(100.0), 0).filterIsInstance<GuideAction.Banner>().single()
        assertEquals(13, banner.next!!.turnType)
        assertEquals(400.0, banner.remainingM, 1.0)
        assertEquals(Guide.LAP_TURN, banner.after!!.turnType)
    }

    @Test fun leaving_the_course_for_eight_seconds_asks_for_the_way_back_once() {
        val guide = Guide(straightKm(), 0)
        guide.onLocation(at(100.0), 0)
        val early = (1..7).flatMap { guide.onLocation(at(100.0, 60.0), it * 1000L) }
        assertTrue("8초가 안 됐다", early.none { it is GuideAction.Reroute })
        val now = guide.onLocation(at(100.0, 60.0), 9_000)
        assertTrue(now.any { it is GuideAction.Reroute })
        assertEquals(listOf("코스를 벗어났습니다. 경로를 재탐색합니다."), said(now))
        val waiting = guide.onLocation(at(100.0, 60.0), 10_000)
        assertTrue("묻는 중에는 다시 묻지 않는다", waiting.none { it is GuideAction.Reroute })
    }

    @Test fun a_failed_search_is_said_once_and_tried_again_after_thirty_seconds_without_repeating() {
        val guide = Guide(straightKm(), 0)
        guide.onLocation(at(100.0), 0)
        guide.onLocation(at(100.0, 60.0), 1_000)
        guide.onLocation(at(100.0, 60.0), 9_000)
        assertEquals(listOf("경로를 찾지 못했습니다. 원래 코스로 돌아가 주세요."), said(guide.onRerouteFailed(9_500)))
        assertTrue(guide.onLocation(at(100.0, 60.0), 20_000).none { it is GuideAction.Reroute })
        val again = guide.onLocation(at(100.0, 60.0), 40_000)
        assertTrue(again.any { it is GuideAction.Reroute })
        assertTrue("다시 찾을 때는 같은 말을 되풀이하지 않는다", said(again).isEmpty())
        assertTrue(said(guide.onRerouteFailed(40_500)).isEmpty())
    }

    @Test fun coming_back_by_yourself_cancels_the_way_back() {
        val guide = Guide(straightKm(), 0)
        guide.onLocation(at(100.0), 0)
        guide.onLocation(at(100.0, 60.0), 1_000)
        guide.onLocation(at(100.0, 60.0), 9_000)
        guide.onLocation(at(103.0), 10_000)   // 돌아왔다
        val back = Course("b", "", listOf(at(103.0, 60.0), at(103.0)), emptyList(), 0.1, 1, null, true, null, JSONObject())
        assertTrue(guide.onRerouted(back, 120.0).isEmpty())
        assertEquals(straightKm().path, guide.currentPath())
    }

    @Test fun the_way_back_replaces_the_route_and_says_how_much_longer_it_is() {
        val guide = Guide(straightKm(), 0)
        guide.onLocation(at(100.0), 0)
        guide.onLocation(at(100.0, 60.0), 1_000)
        guide.onLocation(at(100.0, 60.0), 9_000)
        val back = Course("b", "", listOf(at(100.0, 60.0), at(110.0)) + straightKm().path.drop(11), emptyList(), 1.0, 1, null, true, null, JSONObject())
        assertEquals(listOf("새 경로로 안내합니다. 전체 거리가 약 120미터 늘어납니다."), said(guide.onRerouted(back, 118.0)))
        assertEquals(back.path, guide.currentPath())
    }

    @Test fun reaching_the_end_too_soon_is_not_arrival() {
        val guide = Guide(straightKm(), 0)
        // 1km를 1분 만에 따라왔다 — 2.5분보다 빨리 달릴 수는 없으니 GPS가 튄 것이다
        val quick = (0..995 step 5).flatMapIndexed { i, d -> guide.onLocation(at(d.toDouble()), i * 300L) }
        assertTrue(quick.none { it is GuideAction.Arrived })
        assertTrue(guide.onLocation(at(995.0), 60_000).none { it is GuideAction.Arrived })
        val arrived = guide.onLocation(at(995.0), 151_000)
        assertTrue(arrived.any { it is GuideAction.Arrived })
        assertTrue(guide.done)
        assertTrue("도착한 뒤에는 더 안내하지 않는다", guide.onLocation(at(995.0), 160_000).isEmpty())
    }

    @Test fun on_a_loop_the_start_is_not_taken_for_the_end() {
        val square = listOf(at(0.0), at(250.0), at(250.0, 250.0), at(0.0, 250.0), at(0.0)).let { corners ->
            corners.zipWithNext { a, b -> (0 until 25).map { k -> LatLng(a.lat + (b.lat - a.lat) * k / 25, a.lng + (b.lng - a.lng) * k / 25) } }.flatten() + corners.last()
        }
        val loop = Course("l", "", square, emptyList(), 1.0, 1, null, true, null, JSONObject())
        val guide = Guide(loop, 0)
        val first = guide.onLocation(at(0.0), 10_000_000)
        assertTrue("출발점에 서 있는데 도착이라고 하면 안 된다", first.none { it is GuideAction.Arrived })
        assertTrue(guide.progressM < 50)
    }

    @Test fun distance_changes_are_said_in_plain_words() {
        assertEquals("" to "", Guide.distanceChange(30.0))
        assertEquals(" 전체 거리가 약 300미터 줄어듭니다." to " · 전체 거리 약 300m 줄어듦", Guide.distanceChange(-304.0))
        assertEquals(" 전체 거리가 약 1.2킬로미터 늘어납니다." to " · 전체 거리 약 1.2km 늘어남", Guide.distanceChange(1240.0))
    }

    @Test fun steps_without_a_position_are_placed_at_the_nearest_point() {
        val path = straightKm().path
        val placed = Guide.locate(listOf(Step(LatLng(35.0 + 205 * m, 127.0), "왼쪽", 12, null)), path, Geo.cumulative(path))
        assertEquals("가장 가까운 점(200m 또는 210m)", 205.0, placed.single().cumM!!, 5.5)
    }

    // ── 팀원 앱에서 가져온 것 ──

    @Test fun guidance_says_it_has_started_once() {
        val guide = Guide(straightKm(), 0)
        assertEquals(listOf("길안내를 시작합니다"), said(guide.onLocation(at(0.0), 0)).filter { "시작" in it })
        assertTrue(said(guide.onLocation(at(3.0), 1000)).none { "시작" in it })
    }

    @Test fun the_finish_point_is_said_as_the_finish_not_as_a_turn() {
        val path = straightKm().path
        val finish = Step(path.last(), "도착", 201, 1000.0)
        val guide = Guide(straightKm().copy(steps = listOf(finish)), 0)
        val words = run(guide, 0, 990, startMs = 0)
        assertTrue(words.toString(), words.any { it.endsWith("m 앞이 도착 지점입니다") })
        assertTrue("도착 안내를 회전처럼 말하지 않는다", words.none { it == "도착" || it.endsWith("후 도착") || it.endsWith("앞에서 도착") })
    }

    @Test fun the_remaining_distance_is_given_each_time() {
        val guide = Guide(straightKm(), 0)
        val left = guide.onLocation(at(250.0), 0).filterIsInstance<GuideAction.Remaining>().single()
        assertEquals(750.0, left.meters, 3.0)
    }

    @Test fun arriving_after_running_most_of_the_course_counts_as_a_completed_run() {
        val guide = Guide(straightKm(), 0)
        val all = (0..995 step 5).flatMapIndexed { i, d -> guide.onLocation(at(d.toDouble()), i * 2_000L) }
        assertEquals(true, all.filterIsInstance<GuideAction.Arrived>().single().completed)
    }

    @Test fun a_way_back_that_skips_most_of_the_course_is_not_a_completed_run() {
        // ㄷ자 코스: 북쪽 500m → 동쪽 20m → 남쪽 500m (끝이 출발점 옆). 50m에서 서쪽으로 벗어났더니
        // 서버가 끝으로 바로 가는 길(약 115m)을 줬다 — 코스 대부분을 달리지 않았다
        val corners = listOf(at(0.0), at(500.0), at(500.0, 20.0), at(0.0, 20.0))
        val uPath = corners.zipWithNext { a, b ->
            (0 until 50).map { k -> LatLng(a.lat + (b.lat - a.lat) * k / 50, a.lng + (b.lng - a.lng) * k / 50) }
        }.flatten() + corners.last()
        val guide = Guide(Course("u", "", uPath, emptyList(), 1.02, 1, null, true, null, JSONObject()), 0)
        (0..50 step 5).forEachIndexed { i, d -> guide.onLocation(at(d.toDouble()), i * 2_000L) }
        guide.onLocation(at(50.0, -45.0), 30_000)
        assertTrue(guide.onLocation(at(50.0, -45.0), 39_000).any { it is GuideAction.Reroute })
        val back = listOf(at(50.0, -45.0), at(0.0, -45.0), at(0.0, 20.0))
        guide.onRerouted(Course("b", "", back, emptyList(), 0.12, 1, null, true, null, JSONObject()), -800.0)
        val along = back.zipWithNext { a, b ->
            val n = (Geo.meters(a, b) / 5).toInt().coerceAtLeast(1)
            (0 until n).map { k -> LatLng(a.lat + (b.lat - a.lat) * k / n, a.lng + (b.lng - a.lng) * k / n) }
        }.flatten() + back.last()
        val arrived = along.flatMapIndexed { k, p -> guide.onLocation(p, 1_000_000L + k * 2_000L) }
            .filterIsInstance<GuideAction.Arrived>().single()
        assertEquals("165m만 달렸다 (1,020m 코스의 80%가 안 된다)", false, arrived.completed)
    }

    @Test fun running_a_long_way_back_still_counts_the_distance_run() {
        // 벗어났다가 돌아가는 길이 길면, 그 길도 실제로 달린 거리다
        val guide = Guide(straightKm(), 0)
        (0..100 step 5).forEachIndexed { i, d -> guide.onLocation(at(d.toDouble()), i * 2_000L) }
        guide.onLocation(at(100.0, 60.0), 50_000)
        guide.onLocation(at(100.0, 60.0), 59_000)
        val back = listOf(at(100.0, 60.0), at(990.0, 60.0), at(1000.0))
        guide.onRerouted(Course("b", "", back, emptyList(), 0.95, 1, null, true, null, JSONObject()), -50.0)
        val along = back.zipWithNext { a, b ->
            val n = (Geo.meters(a, b) / 5).toInt().coerceAtLeast(1)
            (0 until n).map { k -> LatLng(a.lat + (b.lat - a.lat) * k / n, a.lng + (b.lng - a.lng) * k / n) }
        }.flatten() + back.last()
        val arrived = along.flatMapIndexed { k, p -> guide.onLocation(p, 1_000_000L + k * 2_000L) }
            .filterIsInstance<GuideAction.Arrived>().single()
        assertEquals(true, arrived.completed)
    }
}
