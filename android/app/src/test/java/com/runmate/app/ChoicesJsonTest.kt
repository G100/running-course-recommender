package com.runmate.app

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** 팀원 앱에서 가져온 것들: 풍경 고르기, 목적지 검색, 항목별 평가 질문, 추천 이유, 출처 표기. */
class ChoicesJsonTest {
    @Test fun scenery_choices_are_read_with_how_near_they_are() {
        val body = JSONObject("""{"scenery": [
            {"value": "강·하천", "label": "강·하천", "group": "물가", "hint": "강이나 하천을 따라", "near": "걸어서 6분", "course_count": 6},
            {"value": "숲", "label": "숲", "group": "자연", "near": null, "course_count": 0}], "groups": ["물가", "자연"]}""")
        val options = ChoicesJson.scenery(body)
        assertEquals(listOf("강·하천", "숲"), options.map { it.value })
        assertEquals("걸어서 6분", options[0].near)
        assertNull(options[1].near)
        assertEquals("강·하천 · 걸어서 6분", options[0].chipText)
        assertEquals("숲", options[1].chipText)
    }

    @Test fun places_are_read_for_a_destination() {
        val body = JSONObject("""{"places": [{"name": "오동도", "address": "전남 여수시", "lat": 34.74, "lng": 127.77, "distance_km": 3.2}]}""")
        val place = ChoicesJson.places(body).single()
        assertEquals("오동도", place.name)
        assertEquals(LatLng(34.74, 127.77), place.at)
        assertEquals("오동도 · 3.2km · 전남 여수시", place.listText)
    }

    @Test fun rating_questions_come_from_the_server() {
        val body = JSONObject("""{"questions": [{"key": "stops", "question": "신호등에서 자주 멈췄나요?",
            "options": [{"value": "few", "label": "거의 안 멈췄어요"}, {"value": "many", "label": "자주 멈췄어요"}]}]}""")
        val q = ChoicesJson.questions(body).single()
        assertEquals("stops", q.key)
        assertEquals(listOf("few" to "거의 안 멈췄어요", "many" to "자주 멈췄어요"), q.options)
    }

    @Test fun the_taste_summary_after_rating_is_read() {
        assertEquals(listOf("신호등에 자주 멈추는 걸 불편해하세요"),
            ChoicesJson.summary(JSONObject("""{"summary": ["신호등에 자주 멈추는 걸 불편해하세요"], "n_feedback": 3}""")))
        assertTrue(ChoicesJson.summary(JSONObject("{}")).isEmpty())
    }

    @Test fun reasons_name_the_strongest_score_items() {
        val reasons = recommendReasons(mapOf("distance" to 0.95, "tag_match" to 0.3, "flow" to 0.72, "car_free" to 0.81))
        assertEquals(listOf("거리 95%", "차 없는 길 81%"), reasons)
        assertTrue("60% 아래는 이유로 내세우지 않는다", recommendReasons(mapOf("flow" to 0.4)).isEmpty())
        assertTrue("모르는 항목은 건너뛴다", recommendReasons(mapOf("time_fit" to 0.9)).isEmpty())
    }

    @Test fun the_recommendation_carries_its_score_items_and_the_map_attribution() {
        val found = CourseJson.recommendations(JSONObject("""{"results": [{"score": 0.7, "score_breakdown": {"flow": 0.8},
            "course": {"path": [[1,2],[3,4]]}}], "attribution": "지도 데이터 © OpenStreetMap contributors (ODbL)"}"""))
        assertEquals(mapOf("flow" to 0.8), found.results[0].breakdown)
        assertEquals("지도 데이터 © OpenStreetMap contributors (ODbL)", found.attribution)
    }

    @Test fun a_request_to_a_destination_and_with_scenery_looks_like_the_web_pages() {
        val body = RecommendRequest(5.0, "oneway", LatLng(34.7, 127.6), "android-a", listOf("강·하천"),
            destination = LatLng(34.74, 127.77)).toJson()
        assertEquals("강·하천", body.getJSONArray("environment_tags").getString(0))
        assertEquals(34.74, body.getDouble("destination_lat"), 1e-9)
        assertEquals(127.77, body.getDouble("destination_lng"), 1e-9)
        assertTrue("목적지가 없으면 보내지 않는다",
            !RecommendRequest(5.0, "loop", LatLng(1.0, 2.0), "a").toJson().has("destination_lat"))
    }
}
