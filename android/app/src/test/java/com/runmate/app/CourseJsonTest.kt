package com.runmate.app

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** 서버 응답(POST /recommend)을 앱의 코스로 읽는다 — 웹 페이지가 받는 것과 같은 응답이다. */
class CourseJsonTest {
    private val joined = """
        {"results": [
          {"score": 0.71, "course": {"id": "generated-1", "name": "북쪽 순환 코스 · 공원", "distance_km": 7.02,
            "path": [[35.1468, 126.9195], [35.1500, 126.9250], [35.1468, 126.9195]],
            "steps": [{"lat": 35.15, "lng": 126.925, "description": "우회전", "instruction": "오른쪽으로 도세요",
                       "turn_type": 13, "cum_m": 520.5}],
            "traffic_signal_count": 4, "tmap": {"ok": true, "distance_km": 7.02}}},
          {"score": 0.65, "course": {"id": "generated-2", "name": "남쪽 순환 코스", "distance_km": 6.7,
            "path": [[35.1468, 126.9195], [35.14, 126.91]], "steps": [], "traffic_signal_count": null}}
        ], "source": "generated", "deliver_km": 7.0, "notice": null}
    """.trimIndent()

    @Test fun the_first_course_comes_joined_on_tmap_and_others_do_not() {
        val found = CourseJson.recommendations(JSONObject(joined))
        assertEquals(2, found.results.size)
        val first = found.results[0].course
        assertTrue(first.joinedOnTmap)
        assertEquals(7.02, first.distanceKm, 1e-9)
        assertEquals(3, first.path.size)
        assertEquals(LatLng(35.1468, 126.9195), first.path[0])
        assertEquals(4, first.signals)
        assertEquals("오른쪽으로 도세요", first.steps[0].instruction)
        assertEquals(520.5, first.steps[0].cumM!!, 1e-9)
        assertFalse(found.results[1].course.joinedOnTmap)
        assertNull("값이 null이면 모르는 것이다", found.results[1].course.signals)
        assertEquals(7.0, found.deliverKm!!, 1e-9)
        assertNull(found.notice)
    }

    @Test fun a_step_without_its_own_words_uses_the_description() {
        val c = CourseJson.course(JSONObject("""{"path": [[1,2],[3,4]], "steps": [{"lat": 1, "lng": 2, "description": "횡단보도"}]}"""))
        assertEquals("횡단보도", c.steps[0].instruction)
        assertNull(c.steps[0].cumM)
        assertEquals(1, c.laps)
    }

    @Test fun a_course_tmap_could_not_check_says_why() {
        val limit = CourseJson.course(JSONObject("""{"path": [[1,2],[3,4]], "distance_km": 6.99, "tmap_unchecked": "daily_limit"}"""))
        assertTrue(uncheckedText(limit)!!.startsWith("오늘 Tmap 길 확인 횟수를 다 써서"))
        val down = CourseJson.course(JSONObject("""{"path": [[1,2],[3,4]], "tmap_unchecked": "unavailable"}"""))
        assertTrue(uncheckedText(down)!!.startsWith("지금 Tmap에 연결되지 않아"))
        val joinedCourse = CourseJson.recommendations(JSONObject(joined)).results[0].course
        assertNull(uncheckedText(joinedCourse))
        val notYetJoined = CourseJson.recommendations(JSONObject(joined)).results[1].course
        assertNull("다른 후보는 고를 때 맞추므로 경고하지 않는다", uncheckedText(notYetJoined))
    }

    @Test fun laps_are_read() {
        val c = CourseJson.course(JSONObject("""{"path": [[1,2],[3,4]], "laps": 2, "distance_km": 21.14}"""))
        assertEquals(2, c.laps)
    }

    @Test fun the_request_looks_like_the_web_pages() {
        val body = RecommendRequest(10.0, "loop", LatLng(36.35, 127.38), "android-abc").toJson()
        assertEquals(10.0, body.getDouble("preferred_distance_km"), 1e-9)
        assertEquals("loop", body.getString("route_type"))
        assertEquals(36.35, body.getDouble("current_lat"), 1e-9)
        assertEquals(127.38, body.getDouble("current_lng"), 1e-9)
        assertEquals("android-abc", body.getString("user_id"))
        assertEquals(3, body.getInt("top_n"))
        assertEquals(0, body.getJSONArray("environment_tags").length())
    }
}
