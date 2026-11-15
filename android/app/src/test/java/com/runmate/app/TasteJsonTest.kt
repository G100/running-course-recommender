package com.runmate.app

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** '내 기록' 화면: 서버의 내 취향(GET /users/{id}/taste)과 즐겨찾기(GET /favorites/{id}) 응답을 읽는다. */
class TasteJsonTest {
    @Test fun my_taste_is_read_with_stats_and_history() {
        val taste = TasteJson.taste(JSONObject("""{
            "summary": ["신호등에 자주 멈추는 걸 불편해하세요"],
            "stats": {"feedback_count": 2, "average_rating": 4.5, "favorite_count": 1,
                      "liked_scenery": [{"label": "강·하천", "count": 2}]},
            "history": [{"created_at": 1763190000, "course_id": "c1", "course_name": "강변 순환",
                         "scenery_labels": ["강·하천"], "rating": 5, "answers": ["거의 안 멈췄어요"], "comment": null}]
        }"""))
        assertEquals(listOf("신호등에 자주 멈추는 걸 불편해하세요"), taste.summary)
        assertEquals(2, taste.feedbackCount)
        assertEquals(4.5, taste.averageRating!!, 0.0)
        assertEquals(listOf("강·하천" to 2), taste.likedScenery)
        val run = taste.history.single()
        assertEquals("강변 순환", run.courseName)
        assertEquals(5, run.rating)
        assertEquals(listOf("거의 안 멈췄어요"), run.answers)
        assertNull("후기가 없으면 null (문자열 'null'이 아니라)", run.comment)
    }

    @Test fun no_ratings_yet_reads_as_empty() {
        val taste = TasteJson.taste(JSONObject("""{"summary": [], "stats": {"feedback_count": 0, "average_rating": null}}"""))
        assertEquals(0, taste.feedbackCount)
        assertNull(taste.averageRating)
        assertTrue(taste.history.isEmpty())
    }

    @Test fun saved_courses_come_back_as_courses_that_can_be_run() {
        val favorites = TasteJson.favorites(JSONObject("""{"favorites": [
            {"course": {"id": "c1", "name": "강변 순환", "distance_km": 5.02, "path": [[35.0, 127.0], [35.01, 127.0]],
                        "tmap": {"ok": true}}, "saved_at": 1763190000, "rating": {"average": 4.0, "count": 3}},
            {"course": {"id": "broken"}, "saved_at": 1763190000}
        ]}"""))
        val saved = favorites.single()
        assertEquals("c1", saved.course.id)
        assertTrue(saved.course.joinedOnTmap)
        assertEquals(4.0, saved.average!!, 0.0)
        assertEquals(3, saved.ratingCount)
    }

    @Test fun the_recommendation_says_whether_i_saved_the_course() {
        val body = JSONObject("""{"results": [
            {"course": {"id": "a", "path": [[35.0, 127.0], [35.01, 127.0]]}, "score": 0.8, "favorite": true},
            {"course": {"id": "b", "path": [[35.0, 127.0], [35.01, 127.0]]}, "score": 0.7}
        ]}""")
        val results = CourseJson.recommendations(body).results
        assertTrue(results[0].favorite)
        assertTrue(!results[1].favorite)
    }
}
