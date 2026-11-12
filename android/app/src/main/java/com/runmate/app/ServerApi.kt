package com.runmate.app

import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/** 우리 서버(FastAPI)에 묻는다. 네트워크는 작업 스레드에서, 결과는 화면 스레드로 돌려준다. */
class ServerApi(private val baseUrl: String) {
    private val worker = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())

    fun recommend(request: RecommendRequest, done: (Result<Recommendations>) -> Unit) =
        post("/recommend", request.toJson(), READ_LONG_MS) { CourseJson.recommendations(it) }.let { call(it, done) }

    /** 다른 후보를 고르면 실제로 달릴 Tmap 경로로 맞춘다 (1등은 이미 맞춰져 온다). */
    fun deliver(course: Course, targetKm: Double, routeType: String, done: (Result<Course>) -> Unit) {
        val body = JSONObject().put("course", course.raw).put("target_km", targetKm).put("route_type", routeType)
        call(post("/courses/deliver", body, READ_LONG_MS) { CourseJson.course(it.getJSONObject("course")) }, done)
    }

    /** 코스를 벗어난 러너에게 원래 코스로 돌아가는 길 (경로, 전체 거리가 늘어나는 m). */
    fun reroute(position: LatLng, path: List<LatLng>, steps: List<Step>, progressM: Double, done: (Result<Pair<Course, Double>>) -> Unit) {
        val body = JSONObject()
            .put("position", org.json.JSONArray(listOf(position.lat, position.lng)))
            .put("path", org.json.JSONArray(path.map { org.json.JSONArray(listOf(it.lat, it.lng)) }))
            .put("steps", org.json.JSONArray(steps.map {
                JSONObject().put("lat", it.at.lat).put("lng", it.at.lng).put("instruction", it.instruction)
                    .put("description", it.instruction).put("turn_type", it.turnType).put("cum_m", it.cumM)
            }))
            .put("progress_m", progressM)
        call(post("/courses/reroute", body, READ_SHORT_MS) { CourseJson.course(it) to it.optDouble("extra_m", 0.0) }, done)
    }

    /** 달린 뒤 별점 (1~5). 추천받은 코스여야 서버가 받는다 — 무엇 때문에 추천했는지 서버가 기억해 두었다가 학습한다. */
    fun feedback(userId: String, courseId: String, rating: Int, done: (Result<Unit>) -> Unit) {
        val body = JSONObject().put("user_id", userId).put("course_id", courseId).put("rating", rating)
        call(post("/feedback", body, READ_SHORT_MS) { }, done)
    }

    private fun <T> call(task: () -> T, done: (Result<T>) -> Unit) {
        worker.execute {
            val result = runCatching(task)
            main.post { done(result) }
        }
    }

    private fun <T> post(path: String, body: JSONObject, readMs: Int, parse: (JSONObject) -> T): () -> T = {
        val connection = (URL(baseUrl.trimEnd('/') + path).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = CONNECT_MS
            readTimeout = readMs
            doOutput = true
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
        }
        try {
            connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            val ok = connection.responseCode in 200..299
            val text = (if (ok) connection.inputStream else connection.errorStream)?.bufferedReader(Charsets.UTF_8)?.readText().orEmpty()
            if (!ok) throw ServerError(connection.responseCode, detail(text))
            parse(JSONObject(text))
        } finally {
            connection.disconnect()
        }
    }

    private fun detail(text: String): String =
        runCatching { JSONObject(text).optString("detail") }.getOrNull()?.takeIf { it.isNotBlank() } ?: text.take(200)

    companion object {
        const val CONNECT_MS = 10_000
        // 처음 가는 동네의 긴 코스는 서버가 그 자리에서 새로 짜느라 1분 넘게 걸릴 수 있다
        const val READ_LONG_MS = 180_000
        // 달리는 중에 묻는 것은 오래 기다리지 않는다 (못 받으면 30초 뒤 다시 묻는다)
        const val READ_SHORT_MS = 20_000
    }
}

class ServerError(val status: Int, val detail: String) : IOException("서버 응답 $status: $detail")
