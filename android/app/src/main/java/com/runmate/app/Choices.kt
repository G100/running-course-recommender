package com.runmate.app

import org.json.JSONArray
import org.json.JSONObject

/** 풍경 선택지 (GET /onboarding/scenery). 고르면 그 풍경을 지나는 코스를 찾는다. */
data class SceneryOption(val value: String, val group: String?, val near: String?, val courseCount: Int) {
    /** 칩에 쓰는 말: "강·하천 · 걸어서 6분" (얼마나 가까운지 모르면 이름만) */
    val chipText: String get() = if (near != null) "$value · $near" else value
}

/** 목적지 후보 (GET /places). 고르면 그곳까지 가는 코스를 만든다. */
data class Place(val name: String, val address: String?, val at: LatLng, val distanceKm: Double?) {
    val listText: String
        get() = listOfNotNull(name, distanceKm?.let { "%.1fkm".format(it) }, address?.takeIf { it.isNotBlank() }).joinToString(" · ")
}

/** 달린 뒤 항목별 질문 (GET /onboarding/feedback). 답(value)은 POST /feedback의 aspects로 보낸다. */
data class FeedbackQuestion(val key: String, val question: String, val options: List<Pair<String, String>>)

object ChoicesJson {
    fun scenery(body: JSONObject): List<SceneryOption> = objects(body.optJSONArray("scenery")).map {
        SceneryOption(
            value = it.getString("value"),
            group = it.text("group"),
            near = it.text("near"),
            courseCount = it.optInt("course_count", 0),
        )
    }

    fun places(body: JSONObject): List<Place> = objects(body.optJSONArray("places")).map {
        Place(
            name = it.getString("name"),
            address = it.text("address"),
            at = LatLng(it.getDouble("lat"), it.getDouble("lng")),
            distanceKm = it.optDouble("distance_km").takeUnless { d -> d.isNaN() },
        )
    }

    fun questions(body: JSONObject): List<FeedbackQuestion> = objects(body.optJSONArray("questions")).map { q ->
        FeedbackQuestion(
            key = q.getString("key"),
            question = q.getString("question"),
            options = objects(q.optJSONArray("options")).map { it.getString("value") to it.getString("label") },
        )
    }

    /** 평가를 보낸 뒤 서버가 정리해 주는 내 취향 ("신호등에 자주 멈추는 걸 불편해하세요" …) */
    fun summary(body: JSONObject): List<String> =
        (body.optJSONArray("summary") ?: JSONArray()).let { arr -> (0 until arr.length()).map { arr.getString(it) } }

    private fun objects(arr: JSONArray?): List<JSONObject> =
        if (arr == null) emptyList() else (0 until arr.length()).map { arr.getJSONObject(it) }

    private fun JSONObject.text(key: String): String? = optString(key).takeIf { it.isNotBlank() && it != "null" }
}

/** 지금 서버의 점수 항목 (score.py): 거리·풍경·흐름·차 없는 길 */
private val SCORE_LABELS = mapOf("distance" to "거리", "tag_match" to "풍경 일치", "flow" to "흐름", "car_free" to "차 없는 길")

/** 추천 이유: 점수가 높은 항목 둘 ("거리 95%", "차 없는 길 81%"). 60%가 안 되는 항목은 내세우지 않는다. */
fun recommendReasons(breakdown: Map<String, Double>): List<String> =
    breakdown.filterKeys { it in SCORE_LABELS }.filterValues { it >= 0.6 }
        .entries.sortedByDescending { it.value }.take(2)
        .map { "${SCORE_LABELS.getValue(it.key)} ${(it.value * 100).toInt()}%" }
