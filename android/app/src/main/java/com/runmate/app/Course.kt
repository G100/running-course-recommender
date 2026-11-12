package com.runmate.app

import org.json.JSONArray
import org.json.JSONObject

/** 위도·경도 한 점. */
data class LatLng(val lat: Double, val lng: Double)

/** 회전 안내 하나: 어디서(경로를 따라 몇 m 지점), 무엇을 하라고 말하는지. */
data class Step(val at: LatLng, val instruction: String, val turnType: Int, val cumM: Double?)

/** 서버가 준 코스 (POST /recommend 응답의 results[].course). 화면과 안내에 쓰는 것만 꺼낸다. */
data class Course(
    val id: String,
    val name: String,
    val path: List<LatLng>,
    val steps: List<Step>,
    val distanceKm: Double,
    val laps: Int,
    val signals: Int?,
    /** 서버가 실제로 달릴 Tmap 경로로 맞춰 준 코스인가. 아니면 거리를 '약'으로 보여 준다. */
    val joinedOnTmap: Boolean,
    /** Tmap으로 길을 확인하지 못한 이유: daily_limit(하루 한도) · unavailable(연결 안 됨) · null(확인함 또는 해당 없음) */
    val uncheckedReason: String?,
    /** 서버에 그대로 돌려보낼 원본 (다른 후보를 고를 때 POST /courses/deliver에 보낸다) */
    val raw: JSONObject,
)

/** 추천 한 건: 코스와 점수(0~1). */
data class Recommendation(val course: Course, val score: Double)

/** POST /recommend 응답. */
data class Recommendations(
    val results: List<Recommendation>,
    /** 다른 후보를 고르면 이 거리로 맞춘다 (요청 거리, 풍경까지 늘리기로 했으면 늘린 거리) */
    val deliverKm: Double?,
    val notice: String?,
)

object CourseJson {
    fun recommendations(body: JSONObject): Recommendations {
        val results = body.optJSONArray("results") ?: JSONArray()
        return Recommendations(
            results = (0 until results.length()).map { i ->
                val item = results.getJSONObject(i)
                Recommendation(course(item.getJSONObject("course")), item.optDouble("score", 0.0))
            },
            deliverKm = body.optDouble("deliver_km").takeUnless { it.isNaN() },
            notice = body.optString("notice").takeIf { it.isNotBlank() && it != "null" },
        )
    }

    fun course(c: JSONObject): Course {
        val path = c.getJSONArray("path").let { arr -> (0 until arr.length()).map { point(arr.getJSONArray(it)) } }
        val steps = (c.optJSONArray("steps") ?: JSONArray()).let { arr ->
            (0 until arr.length()).map { i ->
                val s = arr.getJSONObject(i)
                Step(
                    at = LatLng(s.getDouble("lat"), s.getDouble("lng")),
                    instruction = s.optString("instruction").ifBlank { s.optString("description") },
                    turnType = s.optInt("turn_type", 0),
                    cumM = s.optDouble("cum_m").takeUnless { it.isNaN() },
                )
            }
        }
        return Course(
            id = c.optString("id"),
            name = c.optString("name", "코스"),
            path = path,
            steps = steps,
            distanceKm = c.optDouble("distance_km", 0.0),
            laps = c.optInt("laps", 1).coerceAtLeast(1),
            signals = if (c.isNull("traffic_signal_count") || !c.has("traffic_signal_count")) null else c.getInt("traffic_signal_count"),
            joinedOnTmap = c.has("tmap") && !c.isNull("tmap"),
            uncheckedReason = c.optString("tmap_unchecked").takeIf { it.isNotBlank() && it != "null" },
            raw = c,
        )
    }

    private fun point(p: JSONArray) = LatLng(p.getDouble(0), p.getDouble(1))
}

/** 코스 카드에 띄울 'Tmap으로 확인하지 못했다'는 말 (웹 페이지와 같은 문구). 확인했으면 null. */
fun uncheckedText(course: Course): String? {
    if (course.joinedOnTmap) return null
    val why = when (course.uncheckedReason) {
        "daily_limit" -> "오늘 Tmap 길 확인 횟수를 다 써서"
        "unavailable" -> "지금 Tmap에 연결되지 않아"
        else -> return null
    }
    return "$why 이 코스는 Tmap으로 길을 확인하지 못했어요. 거리는 맞췄지만 인도·횡단보도 안내가 틀릴 수 있으니 달리면서 길을 살펴 주세요."
}

/** 추천 요청 (웹 페이지가 보내는 것과 같은 모양). */
data class RecommendRequest(
    val distanceKm: Double,
    val routeType: String,      // loop · roundtrip · oneway
    val here: LatLng,
    val userId: String,
    val tags: List<String> = emptyList(),
) {
    fun toJson(): JSONObject = JSONObject().apply {
        put("preferred_distance_km", distanceKm)
        put("route_type", routeType)
        put("environment_tags", JSONArray(tags))
        put("current_lat", here.lat)
        put("current_lng", here.lng)
        put("user_id", userId)
        put("max_distance_km", 5)
        put("top_n", 3)   // 후보를 여럿 받아 러너가 고른다 (1등만 미리 Tmap으로 맞춰져 온다)
    }
}
