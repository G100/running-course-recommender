package com.runmate.app

import org.json.JSONArray
import org.json.JSONObject

/** 즐겨찾기한 코스 하나 (GET /favorites/{user_id}). 저장할 때의 코스를 통째로 돌려준다. */
data class Favorite(val course: Course, val savedAtSec: Long?, val average: Double?, val ratingCount: Int)

/** 내가 한 평가 하나 (GET /users/{user_id}/taste 의 history). */
data class RatedRun(val atSec: Long, val courseName: String, val rating: Int, val answers: List<String>,
                    val comment: String?, val scenery: List<String>)

/** '내 기록' 화면에 그리는 것 전부 (GET /users/{user_id}/taste). */
data class MyTaste(
    val summary: List<String>,          // 서버가 정리한 취향 문장
    val feedbackCount: Int,
    val averageRating: Double?,
    val favoriteCount: Int,
    val likedScenery: List<Pair<String, Int>>,   // 4점 이상 준 코스들이 지나던 풍경 (많은 순)
    val history: List<RatedRun>,
) {
    companion object {
        /** 아직 평가한 적이 없을 때 (서버가 404를 준다) */
        val EMPTY = MyTaste(emptyList(), 0, null, 0, emptyList(), emptyList())
    }
}

object TasteJson {
    fun taste(body: JSONObject): MyTaste {
        val stats = body.optJSONObject("stats") ?: JSONObject()
        return MyTaste(
            summary = strings(body.optJSONArray("summary")),
            feedbackCount = stats.optInt("feedback_count", 0),
            averageRating = stats.optDouble("average_rating").takeUnless { it.isNaN() },
            favoriteCount = stats.optInt("favorite_count", 0),
            likedScenery = objects(stats.optJSONArray("liked_scenery")).map { it.optString("label") to it.optInt("count") },
            history = objects(body.optJSONArray("history")).map {
                RatedRun(
                    atSec = it.optLong("created_at"),
                    courseName = it.optString("course_name").takeIf { n -> n.isNotBlank() && n != "null" } ?: "코스",
                    rating = it.optInt("rating"),
                    answers = strings(it.optJSONArray("answers")),
                    comment = it.optString("comment").takeIf { c -> c.isNotBlank() && c != "null" },
                    scenery = strings(it.optJSONArray("scenery_labels")),
                )
            },
        )
    }

    fun favorites(body: JSONObject): List<Favorite> = objects(body.optJSONArray("favorites")).mapNotNull { item ->
        val course = item.optJSONObject("course") ?: return@mapNotNull null
        if (course.optJSONArray("path") == null) return@mapNotNull null
        val rating = item.optJSONObject("rating")
        Favorite(
            course = CourseJson.course(course),
            savedAtSec = item.optLong("saved_at").takeIf { it > 0 },
            average = rating?.optDouble("average")?.takeUnless { it.isNaN() },
            ratingCount = rating?.optInt("count", 0) ?: 0,
        )
    }

    private fun objects(arr: JSONArray?): List<JSONObject> =
        if (arr == null) emptyList() else (0 until arr.length()).mapNotNull { arr.optJSONObject(it) }

    private fun strings(arr: JSONArray?): List<String> =
        if (arr == null) emptyList() else (0 until arr.length()).map { arr.optString(it) }.filter { it.isNotBlank() }
}
