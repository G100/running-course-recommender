package com.runmate.app

import android.Manifest
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Build
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.view.View
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.RatingBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.google.android.material.button.MaterialButton
import com.google.android.material.button.MaterialButtonToggleGroup
import com.skt.tmap.TMapPoint
import com.skt.tmap.TMapView
import com.skt.tmap.overlay.TMapMarkerItem
import com.skt.tmap.overlay.TMapPolyLine
import java.util.Locale
import java.util.UUID

/** 지도 + 아래 카드 하나: 거리·모양을 고르고 코스를 찾으면 지도에 그리고 요약을 보여 준다. */
class MainActivity : AppCompatActivity() {
    private val api by lazy { ServerApi(BuildConfig.SERVER_URL) }
    private lateinit var map: TMapView
    private var mapReady = false
    private var here: LatLng? = null
    private var distanceKm = 5.0
    private var results: List<Recommendation> = emptyList()
    private var deliverKm: Double? = null
    private var picked = 0
    private var guide: Guide? = null
    private var tts: TextToSpeech? = null
    private var gpsListener: LocationListener? = null
    private var lastFixMs = 0L

    private val status by lazy { findViewById<TextView>(R.id.status) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        setUpMap()
        setUpDistance()
        findViewById<MaterialButton>(R.id.findButton).setOnClickListener { find() }
        findViewById<MaterialButton>(R.id.guideButton).setOnClickListener { if (guide == null) startGuide() else stopGuide() }
        tts = TextToSpeech(this) { ok -> if (ok == TextToSpeech.SUCCESS) tts?.language = Locale.KOREAN }
        setUpRating()
        askLocation()
    }

    override fun onDestroy() {
        stopGuide()
        tts?.shutdown()
        super.onDestroy()
    }

    // ── 지도 ──

    private fun setUpMap() {
        map = TMapView(this)
        findViewById<FrameLayout>(R.id.mapHolder).addView(map)
        if (BuildConfig.TMAP_KEY.isBlank()) {
            status.setText(R.string.no_tmap_key)
            return
        }
        map.setSKTMapApiKey(BuildConfig.TMAP_KEY)
        map.setOnMapReadyListener {
            mapReady = true
            map.setZoomLevel(15)
            here?.let { map.setCenterPoint(it.lat, it.lng) }
            currentCourse()?.let { draw(it) }
        }
    }

    private fun draw(course: Course) = drawPath(course.path, fit = true)

    private fun drawPath(path: List<LatLng>, fit: Boolean) {
        if (!mapReady) return
        map.removeAllTMapPolyLine()
        val line = TMapPolyLine().apply {
            setID("course")
            setLineWidth(8f)
            setLineColor(ContextCompat.getColor(this@MainActivity, R.color.course_line))
            setLineAlpha(255)
            path.forEach { addLinePoint(TMapPoint(it.lat, it.lng)) }
        }
        map.addTMapPolyLine(line)
        if (!fit) return
        val view = map.getDisplayTMapInfo(ArrayList(path.map { TMapPoint(it.lat, it.lng) }))
        map.setZoomLevel(view.zoom)
        map.setCenterPoint(view.point.latitude, view.point.longitude)
    }

    /** 내 위치: 흰 원에 검은 테두리 (코스 선 위에서도 보인다). */
    private val runnerIcon: Bitmap by lazy {
        val size = (26 * resources.displayMetrics.density).toInt()
        Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888).also { bitmap ->
            val canvas = Canvas(bitmap)
            val paint = Paint(Paint.ANTI_ALIAS_FLAG)
            paint.color = Color.WHITE
            canvas.drawCircle(size / 2f, size / 2f, size * 0.42f, paint)
            paint.style = Paint.Style.STROKE
            paint.strokeWidth = size * 0.1f
            paint.color = Color.BLACK
            canvas.drawCircle(size / 2f, size / 2f, size * 0.42f, paint)
        }
    }

    private fun showRunner(at: LatLng) {
        if (!mapReady) return
        map.removeAllTMapMarkerItem()
        map.addTMapMarkerItem(TMapMarkerItem().apply {
            id = "runner"
            icon = runnerIcon
            setTMapPoint(at.lat, at.lng)
        })
        map.setCenterPoint(at.lat, at.lng)
    }

    // ── 거리·모양 ──

    private fun setUpDistance() {
        val shown = findViewById<TextView>(R.id.distance)
        val update = { shown.text = Distance.label(distanceKm) }
        findViewById<MaterialButton>(R.id.distDown).setOnClickListener { distanceKm = Distance.down(distanceKm); update() }
        findViewById<MaterialButton>(R.id.distUp).setOnClickListener { distanceKm = Distance.up(distanceKm); update() }
        val presets = findViewById<LinearLayout>(R.id.presets)
        Distance.PRESETS.forEach { (label, km) ->
            presets.addView(MaterialButton(this, null, com.google.android.material.R.attr.materialButtonOutlinedStyle).apply {
                text = label
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply { marginEnd = 6 }
                setOnClickListener { distanceKm = km; update() }
            })
        }
        update()
    }

    private fun routeType(): String = when (findViewById<MaterialButtonToggleGroup>(R.id.routeType).checkedButtonId) {
        R.id.typeRoundtrip -> "roundtrip"
        R.id.typeOneway -> "oneway"
        else -> "loop"
    }

    // ── 위치 ──

    private fun askLocation() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED) {
            locate()
        } else {
            requestPermissions(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION), REQ_LOCATION)
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != REQ_LOCATION) return
        if (grantResults.any { it == PackageManager.PERMISSION_GRANTED }) locate() else status.setText(R.string.need_location)
    }

    @SuppressLint("MissingPermission")   // 권한을 확인한 뒤에만 부른다
    private fun locate() {
        val manager = getSystemService(LocationManager::class.java)
        val got = { location: Location? ->
            if (location != null) {
                here = LatLng(location.latitude, location.longitude)
                if (mapReady && currentCourse() == null) map.setCenterPoint(location.latitude, location.longitude)
                if (status.text == getString(R.string.locating)) status.text = ""
            }
        }
        val provider = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER).firstOrNull { manager.isProviderEnabled(it) }
            ?: return run { status.setText(R.string.no_location) }
        got(manager.getLastKnownLocation(provider))
        status.setText(R.string.locating)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            manager.getCurrentLocation(provider, null, mainExecutor) { got(it) }
        } else {
            @Suppress("DEPRECATION")
            manager.requestSingleUpdate(provider, { got(it) }, mainLooper)
        }
    }

    // ── 코스 찾기 ──

    private fun find() {
        val start = here ?: return run { status.setText(R.string.no_location); locate() }
        val button = findViewById<MaterialButton>(R.id.findButton)
        button.isEnabled = false
        button.setText(R.string.finding)
        status.text = if (distanceKm > 10) "긴 코스는 그 자리에서 새로 짜느라 1~2분 걸릴 수 있어요." else ""
        val began = System.currentTimeMillis()
        api.recommend(RecommendRequest(distanceKm, routeType(), start, userId())) { result ->
            button.isEnabled = true
            button.setText(R.string.find)
            result.onSuccess { found ->
                if (found.results.isEmpty()) return@onSuccess status.setText(R.string.no_results)
                results = found.results
                deliverKm = found.deliverKm ?: distanceKm
                picked = 0
                status.text = "코스를 만들었어요 · ${"%.1f".format((System.currentTimeMillis() - began) / 1000.0)}초" +
                    (found.notice?.let { " · $it" } ?: "")
                showCandidates()
                show(results[0].course, results[0].score)
            }.onFailure { status.text = "코스를 찾지 못했어요: ${it.message}" }
        }
    }

    private fun showCandidates() {
        val group = findViewById<MaterialButtonToggleGroup>(R.id.candidates)
        group.removeAllViews()
        group.clearOnButtonCheckedListeners()
        group.visibility = if (results.size > 1) View.VISIBLE else View.GONE
        results.forEachIndexed { i, r ->
            group.addView(MaterialButton(this, null, com.google.android.material.R.attr.materialButtonOutlinedStyle).apply {
                id = View.generateViewId()
                text = "코스 ${i + 1} · ${if (r.course.joinedOnTmap) "" else "약 "}${"%.1f".format(r.course.distanceKm)}km"
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                isCheckable = true
                isChecked = i == picked
                tag = i
            })
        }
        group.addOnButtonCheckedListener { _, checkedId, isChecked ->
            if (isChecked) pick(group.findViewById<View>(checkedId).tag as Int)
        }
    }

    /** 다른 후보를 고르면 실제로 달릴 Tmap 경로로 맞춘다 (1등은 이미 맞춰져 온다). */
    private fun pick(index: Int) {
        if (index == picked) return
        picked = index
        val chosen = results[index]
        if (chosen.course.joinedOnTmap || chosen.course.uncheckedReason != null) return show(chosen.course, chosen.score)
        status.text = "코스 ${index + 1}을(를) 실제로 달릴 길로 맞추는 중…"
        api.deliver(chosen.course, deliverKm ?: distanceKm, routeType()) { result ->
            result.onSuccess { delivered ->
                results = results.toMutableList().also { it[index] = Recommendation(delivered, chosen.score) }
                status.text = ""
            }.onFailure { status.text = "실제 길로 맞추지 못해 설계한 코스를 보여 드려요: ${it.message}" }
            if (picked == index) show(results[index].course, chosen.score)
            showCandidates()
        }
    }

    private fun currentCourse(): Course? = results.getOrNull(picked)?.course

    private fun show(course: Course, score: Double) {
        findViewById<View>(R.id.resultBox).visibility = View.VISIBLE
        findViewById<TextView>(R.id.courseName).text = course.name
        val laps = if (course.laps > 1) " · ${course.laps}바퀴" else ""
        findViewById<TextView>(R.id.courseStats).text =
            "${if (course.joinedOnTmap) "" else "약 "}${"%.2f".format(course.distanceKm)}km$laps · " +
                "신호등 ${course.signals ?: "—"}개 · 코스 점수 ${(score * 100).toInt()}"
        val note = findViewById<TextView>(R.id.uncheckedNote)
        val unchecked = uncheckedText(course)
        note.visibility = if (unchecked == null) View.GONE else View.VISIBLE
        note.text = unchecked
        draw(course)
    }

    // ── 안내 (GPS · 음성) ──

    @SuppressLint("MissingPermission")   // 권한을 확인한 뒤에만 부른다
    private fun startGuide() {
        val course = currentCourse() ?: return
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            return askLocation()
        }
        val running = Guide(course, System.currentTimeMillis())
        guide = running
        // 달리는 동안 화면이 꺼지면 안내가 멈춘다 (화면이 꺼져도 도는 안내는 다음 단계)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        findViewById<View>(R.id.askBox).visibility = View.GONE
        findViewById<View>(R.id.candidates).visibility = View.GONE
        findViewById<MaterialButton>(R.id.guideButton).setText(R.string.guide_stop)
        status.setText(R.string.waiting_gps)
        if (mapReady) map.setZoomLevel(17)
        if (uncheckedText(course) != null) say("Tmap으로 길을 확인하지 못한 코스입니다. 달리면서 길을 살펴 주세요.", false)
        val listener = LocationListener { location ->
            if (guide !== running) return@LocationListener
            lastFixMs = System.currentTimeMillis()
            val here = LatLng(location.latitude, location.longitude)
            showRunner(here)
            handle(running, running.onLocation(here, lastFixMs))
        }
        gpsListener = listener
        getSystemService(LocationManager::class.java).requestLocationUpdates(LocationManager.GPS_PROVIDER, GPS_EVERY_MS, 0f, listener)
        // 달리다 신호를 잠깐 잃는 건 흔하다(다리 밑·건물 사이) — 안내를 끄지 않고 다시 잡힐 때까지 기다린다
        status.postDelayed(object : Runnable {
            override fun run() {
                if (guide !== running || running.done) return
                if (lastFixMs > 0 && System.currentTimeMillis() - lastFixMs > GPS_LOST_MS) status.setText(R.string.gps_lost)
                status.postDelayed(this, GPS_LOST_MS)
            }
        }, GPS_LOST_MS)
    }

    private fun handle(running: Guide, actions: List<GuideAction>) {
        for (action in actions) when (action) {
            is GuideAction.Say -> say(action.text, action.interrupt)
            is GuideAction.Status -> status.text = action.text
            is GuideAction.Banner -> showBanner(action)
            is GuideAction.Reroute -> askWayBack(running, action)
            GuideAction.Arrived -> {
                status.setText(R.string.arrived)
                endGps()
                askRating()
            }
        }
    }

    private fun askWayBack(running: Guide, action: GuideAction.Reroute) {
        api.reroute(action.position, running.currentPath(), running.currentSteps(), action.progressM) { result ->
            if (guide !== running) return@reroute
            result.onSuccess { (back, extraM) ->
                handle(running, running.onRerouted(back, extraM))
                drawPath(running.currentPath(), fit = false)
            }.onFailure { handle(running, running.onRerouteFailed(System.currentTimeMillis())) }
        }
    }

    private fun showBanner(banner: GuideAction.Banner) {
        val box = findViewById<View>(R.id.turnBanner)
        val next = banner.next ?: return run { box.visibility = View.GONE }
        box.visibility = View.VISIBLE
        findViewById<TextView>(R.id.turnDistance).text = Guide.distanceText(banner.remainingM)
        findViewById<TextView>(R.id.turnText).text = next.instruction
        findViewById<TextView>(R.id.turnAfter).text = banner.after?.let { "그다음 ${it.instruction}" } ?: ""
    }

    private fun say(text: String, interrupt: Boolean) {
        tts?.speak(text, if (interrupt) TextToSpeech.QUEUE_FLUSH else TextToSpeech.QUEUE_ADD, null, text)
    }

    private fun endGps() {
        gpsListener?.let { getSystemService(LocationManager::class.java).removeUpdates(it) }
        gpsListener = null
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }

    private fun stopGuide() {
        if (guide == null) return
        endGps()
        guide = null
        lastFixMs = 0
        findViewById<View>(R.id.turnBanner).visibility = View.GONE
        findViewById<View>(R.id.rateBox).visibility = View.GONE
        findViewById<View>(R.id.resultBox).visibility = View.VISIBLE
        findViewById<View>(R.id.askBox).visibility = View.VISIBLE
        findViewById<View>(R.id.candidates).visibility = if (results.size > 1) View.VISIBLE else View.GONE
        findViewById<MaterialButton>(R.id.guideButton).setText(R.string.guide_start)
        if (mapReady) map.removeAllTMapMarkerItem()
        currentCourse()?.let { draw(it) }
        status.text = ""
    }

    // ── 평가 (달린 뒤에만 받는다 — 시뮬레이션이나 중간에 끝낸 안내는 달린 것이 아니다) ──

    private fun setUpRating() {
        val stars = findViewById<RatingBar>(R.id.stars)
        val send = findViewById<MaterialButton>(R.id.rateSend)
        stars.setOnRatingBarChangeListener { _, rating, _ -> send.isEnabled = rating >= 1 }
        send.setOnClickListener {
            val course = currentCourse() ?: return@setOnClickListener
            send.isEnabled = false
            api.feedback(userId(), course.id, stars.rating.toInt()) { result ->
                result.onSuccess {
                    findViewById<View>(R.id.rateBox).visibility = View.GONE
                    status.setText(R.string.rate_sent)
                }.onFailure {
                    send.isEnabled = true
                    status.text = "평가를 보내지 못했어요: ${it.message}"
                }
            }
        }
    }

    private fun askRating() {
        findViewById<RatingBar>(R.id.stars).rating = 0f
        findViewById<MaterialButton>(R.id.rateSend).isEnabled = false
        findViewById<View>(R.id.rateBox).visibility = View.VISIBLE
        findViewById<View>(R.id.resultBox).visibility = View.GONE
    }

    /** 평가·학습에 쓰는 이 폰의 이름 (로그인은 아직 없다). 처음 한 번 만들어 둔다. */
    private fun userId(): String {
        val prefs = getSharedPreferences("runmate", MODE_PRIVATE)
        return prefs.getString("user_id", null) ?: ("android-" + UUID.randomUUID().toString().take(8)).also {
            prefs.edit().putString("user_id", it).apply()
        }
    }

    companion object {
        private const val REQ_LOCATION = 1
        private const val GPS_EVERY_MS = 1_000L
        private const val GPS_LOST_MS = 10_000L
    }
}
