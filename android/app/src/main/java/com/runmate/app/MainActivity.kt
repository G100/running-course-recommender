package com.runmate.app

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Build
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.view.WindowManager
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.input.pointer.PointerEventType
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.skt.tmap.TMapPoint
import com.skt.tmap.TMapView
import com.skt.tmap.vsm.camera.CameraPosition
import com.skt.tmap.vsm.camera.CameraUpdateFactory
import com.skt.tmap.vsm.data.VSMMapPoint
import com.skt.tmap.vsm.map.MapEngine
import com.skt.tmap.overlay.TMapMarkerItem
import com.skt.tmap.overlay.TMapPolyLine
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** 런메이트 한 화면: 지도 위에 ① 질문 → ② 코스 카드 → ③ 달리는 중 안내가 차례로 올라온다 (웹 데모의 폰 화면과 같은 디자인). */
class MainActivity : ComponentActivity() {
    private val session by lazy { Session(this) }
    private val api by lazy { ServerApi(BuildConfig.SERVER_URL) { session.current?.token } }
    private lateinit var state: RunState
    private lateinit var map: TMapView
    private var mapReady = false
    private var here: LatLng? = null
    private var guide: Guide? = null
    private var tts: TextToSpeech? = null
    private var gpsListener: LocationListener? = null
    private var lastFixMs = 0L
    private var lastRunner: LatLng? = null
    private var lastNotifiedM = -1
    private var drawJob: Job? = null
    private var lineSeq = 0
    private var shownLine: String? = null
    private var lastStatus: String? = null
    private var messageJob: Job? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // 처음에만 로그인한다. 저장한 토큰이 있으면 바로 들어오고, 서버가 만료됐다고 하면 그때 다시 로그인한다
        val login = session.current ?: return goToLogin(null)
        enableEdgeToEdge()
        state = RunState(login.username)
        api.me { result -> result.exceptionOrNull()?.let { if (needsLoginAgain(it)) goToLogin(getString(R.string.login_again)) } }
        setUpMap()
        tts = TextToSpeech(this) { ok -> if (ok == TextToSpeech.SUCCESS) tts?.language = Locale.KOREAN }

        val ask = AskActions(find = ::find, searchPlace = ::searchPlace, logOut = ::logOut, openRecords = ::openRecords)
        val records = RecordsActions(close = { state.showRecords = false }, run = ::runFavorite, remove = ::removeFavorite,
                                     deleteAll = ::deleteMyData)
        val onMap = MapActions(
            pick = ::pick, edit = ::edit, startGuide = ::startGuide, stopGuide = ::stopGuide,
            toggleVoice = { state.voiceOn = !state.voiceOn; if (!state.voiceOn) tts?.stop() },
            recenter = {
                state.following = true
                val running = guide
                val at = lastRunner ?: here
                if (running != null && at != null) followRunner(at, running, ms = 600)
            },
            sendRating = ::sendRating, skipRating = { state.rating = null; stopGuide() },
            toggleFavorite = ::toggleFavorite,
        )
        setContent {
            Box(Modifier.fillMaxSize().background(Run.bg)) {
                AndroidView(
                    factory = { map },
                    modifier = Modifier.fillMaxSize().pointerInput(Unit) {
                        // 안내 중 지도를 직접 끌면 따라가기를 멈춘다 ('내 위치' 버튼으로 다시)
                        awaitPointerEventScope {
                            while (true) {
                                val event = awaitPointerEvent(PointerEventPass.Initial)
                                if (event.type == PointerEventType.Move && state.phase == Phase.Guiding) state.following = false
                            }
                        }
                    },
                )
                CourseSheet(state, onMap)
                GuideOverlays(state, onMap)
                AnimatedVisibility(
                    state.phase == Phase.Ask,
                    enter = fadeIn(tween(250)) + slideInVertically(tween(320)) { it / 12 },
                    exit = fadeOut(tween(300)) + slideOutVertically(tween(320)) { -it / 12 },
                ) { AskScreen(state, ask) }
                // 내 기록: 오른쪽에서 밀려 들어온다
                AnimatedVisibility(
                    state.showRecords,
                    enter = slideInHorizontally(tween(320)) { it } + fadeIn(tween(200)),
                    exit = slideOutHorizontally(tween(280)) { it } + fadeOut(tween(200)),
                ) { RecordsScreen(state, records) }
            }
            BackHandler(enabled = state.showRecords || state.phase != Phase.Ask || state.step > 0) {
                if (state.showRecords) return@BackHandler run { state.showRecords = false }
                when (state.phase) {
                    Phase.Ask -> state.step -= 1
                    Phase.Course -> edit()
                    Phase.Guiding -> show("안내를 끝내려면 아래 ✕를 눌러 주세요.")
                }
            }
        }
        askLocation()
        // 코스 카드가 올라와 높이가 정해지면(또는 바뀌면) 코스를 그 위쪽에 다시 맞춘다
        lifecycleScope.launch {
            snapshotFlow { state.sheetPx }.collect { if (state.phase == Phase.Course) state.course?.let { fitAboveSheet(it.path) } }
        }
    }

    override fun onDestroy() {
        stopGuide()
        tts?.shutdown()
        super.onDestroy()
    }

    /** 화면 위쪽에 잠깐 보이는 알림 */
    private fun show(text: String, forMs: Long = 4_000) {
        state.message = text
        messageJob?.cancel()
        messageJob = lifecycleScope.launch { delay(forMs); state.message = null }
    }

    // ── 지도 ──

    private fun setUpMap() {
        map = TMapView(this)
        if (BuildConfig.TMAP_KEY.isBlank()) return show(getString(R.string.no_tmap_key), 60_000)
        map.setSKTMapApiKey(BuildConfig.TMAP_KEY)
        map.setOnMapReadyListener {
            mapReady = true
            map.setZoomLevel(15)
            here?.let { map.setCenterPoint(it.lat, it.lng) }
            state.course?.let { drawCourse(it) }
        }
    }

    /** 코스 선을 출발점부터 끝까지 이어 그린다 (약 1초). 카드가 아래를 덮으니 코스는 위쪽에 보이게 맞춘다 */
    private fun drawCourse(course: Course) {
        if (!mapReady) return
        fitAboveSheet(course.path)
        drawJob?.cancel()
        drawJob = lifecycleScope.launch {
            val frames = 28
            for (i in 1..frames) {
                drawPath(course.path.take(maxOf(2, course.path.size * i / frames)))
                delay(32)
            }
            drawPath(course.path)
        }
    }

    /**
     * 선을 매번 새 이름으로 넣고, 넣은 뒤에 이전 선만 지운다. 같은 이름으로 지우고 바로 다시 넣으면
     * 지도 SDK가 지우기를 늦게 처리하면서 새 선을 버려서, 코스가 그리다 만 모양(끝이 안 닫힌 순환)으로 남았다.
     */
    private fun drawPath(path: List<LatLng>) {
        if (!mapReady) return
        val id = "course-${++lineSeq}"
        map.addTMapPolyLine(TMapPolyLine().apply {
            setID(id)
            setLineWidth(8f)
            setLineColor(ContextCompat.getColor(this@MainActivity, R.color.course_line))
            setLineAlpha(255)
            path.forEach { addLinePoint(TMapPoint(it.lat, it.lng)) }
        })
        shownLine?.let { map.removeTMapPolyLine(it) }
        shownLine = id
    }

    private fun clearPath() {
        drawJob?.cancel()
        if (mapReady) map.removeAllTMapPolyLine()
        shownLine = null
    }

    /**
     * 코스 전체가 위쪽(상태 표시줄 아래)부터 코스 카드 바로 위까지의 빈 곳에 들어오게 맞춘다.
     * 지도 SDK의 fitBounds는 이 폰에서 아무것도 바꾸지 않아서(확대 단계·범위 그대로), 지금 보이는 범위로
     * 한 화소가 몇 도인지 재고, 확대 단계가 하나 내려갈 때마다 두 배가 되는 것으로 맞는 단계와 중심을 계산한다.
     */
    private fun fitAboveSheet(path: List<LatLng>) {
        if (path.size < 2 || map.width == 0 || map.height == 0) return
        val dp = resources.displayMetrics.density
        val top = 64 * dp
        val bottom = state.sheetPx + 24 * dp
        val side = 28 * dp
        val freeW = map.width - side * 2
        val freeH = map.height - top - bottom
        if (freeW <= 0 || freeH <= 0) return
        val lt = map.leftTopPoint
        val rb = map.rightBottomPoint
        val zoomNow = map.zoomLevel
        val lngPerPx = (rb.longitude - lt.longitude) / map.width
        val latPerPx = (lt.latitude - rb.latitude) / map.height
        if (lngPerPx <= 0 || latPerPx <= 0) return
        val minLat = path.minOf { it.lat }
        val maxLat = path.maxOf { it.lat }
        val minLng = path.minOf { it.lng }
        val maxLng = path.maxOf { it.lng }
        // 이 단계에서 코스가 빈 곳에 들어가려면 화소당 몇 배가 더 넓어야 하나 → 그만큼 단계를 내린다
        val need = maxOf((maxLng - minLng) / lngPerPx / freeW, (maxLat - minLat) / latPerPx / freeH)
        val zoom = (zoomNow - Math.ceil(Math.log(maxOf(need, 1e-9)) / Math.log(2.0)).toInt()).coerceIn(7, 18)
        val scale = Math.pow(2.0, (zoomNow - zoom).toDouble())
        // 빈 곳의 가운데에 코스 가운데가 오게: 화면 가운데보다 (위 여백 - 아래 여백)/2 만큼 위
        val shiftPx = (bottom - top) / 2
        val centerLat = (minLat + maxLat) / 2 - shiftPx * latPerPx * scale
        map.setZoomLevel(zoom)
        map.setCenterPoint(centerLat, (minLng + maxLng) / 2)
    }


    /** 달리는 중의 내 위치: 내비게이션 화살표 (지도가 진행 방향을 위로 돌리므로 화살표는 늘 위를 본다) */
    private val navIcon: Bitmap by lazy {
        val d = resources.displayMetrics.density
        val size = (52 * d).toInt()
        Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888).also { bitmap ->
            val canvas = Canvas(bitmap)
            val c = size / 2f
            val paint = Paint(Paint.ANTI_ALIAS_FLAG)
            paint.color = 0x332F6BFF
            canvas.drawCircle(c, c, size * 0.5f, paint)   // 옅은 파란 후광
            val arrow = android.graphics.Path().apply {
                moveTo(c, size * 0.14f)                    // 머리
                lineTo(size * 0.80f, size * 0.80f)
                lineTo(c, size * 0.64f)                    // 오목한 꼬리
                lineTo(size * 0.20f, size * 0.80f)
                close()
            }
            paint.setShadowLayer(3 * d, 0f, 1.5f * d, 0x55000000)
            paint.color = android.graphics.Color.WHITE
            paint.style = Paint.Style.STROKE
            paint.strokeWidth = 3.5f * d
            paint.strokeJoin = Paint.Join.ROUND
            canvas.drawPath(arrow, paint)
            paint.clearShadowLayer()
            paint.style = Paint.Style.FILL
            paint.color = ContextCompat.getColor(this, R.color.course_line)
            canvas.drawPath(arrow, paint)
        }
    }

    // ── 내비게이션 카메라: 기울인 3D 지도 + 진행 방향이 위 + 내 위치는 화면 아래쪽 ──

    /** 지도 SDK 안의 3D 지도 엔진. TMapView가 바깥으로 내주지 않아서 꺼내 쓴다 (못 꺼내면 평면 지도로 안내한다) */
    private fun engine(): MapEngine? = runCatching {
        TMapView::class.java.declaredFields.first { MapEngine::class.java.isAssignableFrom(it.type) }
            .apply { isAccessible = true }.get(map) as MapEngine?
    }.getOrNull()

    /** 엔진 좌표는 (경도, 위도) 순서인지 실행할 때 확인한다 */
    private fun vsmPoint(at: LatLng): VSMMapPoint =
        VSMMapPoint(at.lng, at.lat).takeIf { Math.abs(it.longitude - at.lng) < 1e-9 } ?: VSMMapPoint(at.lat, at.lng)

    private var navCum: Pair<List<LatLng>, DoubleArray>? = null
    private var navBearing = 0f          // 앞길 방향 (목표)
    private var shownAt: LatLng? = null  // 지금 화면에 그려 둔 화살표 위치
    private var shownBearing = 0f        // 지금 화면의 지도 방향
    private var shownTilt = NAV_TILT     // 지금 화면의 기울기 (안내를 시작할 때만 0에서 기울어진다)
    private var runnerMarker: TMapMarkerItem? = null
    private var glideJob: Job? = null

    private fun resetRunner() {
        glideJob?.cancel()
        runnerMarker = null
        shownAt = null
        shownBearing = 0f
        navCum = null
    }

    /**
     * 위치가 새로 오면 화살표와 카메라를 지금 그려 둔 곳에서 새 위치까지 매 화면(약 1/60초) 조금씩 옮긴다.
     * 다음 위치가 올 즈음(GPS 1초) 도착하게 해서 멈췄다 움직였다 하지 않고 이어진다. 지도 방향도 같이 천천히 돈다.
     * (예전에는 1초마다 카메라 애니메이션을 새로 걸고 화살표를 지웠다 다시 그려서, 화면이 덜컹이고 화살표가 순간이동했다)
     */
    private fun followRunner(at: LatLng, running: Guide, ms: Long = GPS_EVERY_MS) {
        if (!mapReady) return
        val path = running.currentPath()
        val cum = navCum?.takeIf { it.first === path }?.second ?: Geo.cumulative(path).also { navCum = path to it }
        val onPath = Geo.pointAt(path, cum, running.progressM)
        val ahead = Geo.pointAt(path, cum, running.progressM + 30)
        if (Geo.meters(onPath, ahead) > 3) navBearing = Geo.bearing(onPath, ahead).toFloat()
        val from = shownAt ?: at
        val fromBearing = shownBearing
        val fromTilt = shownTilt
        // 돌 각도는 가까운 쪽으로 (350° → 10° 는 20°만 돈다)
        val turn = ((navBearing - fromBearing + 540f) % 360f) - 180f
        val engine = engine()
        glideJob?.cancel()
        glideJob = lifecycleScope.launch {
            val start = android.os.SystemClock.uptimeMillis()
            while (true) {
                val t = ((android.os.SystemClock.uptimeMillis() - start).toFloat() / ms).coerceIn(0f, 1f)
                val p = LatLng(from.lat + (at.lat - from.lat) * t, from.lng + (at.lng - from.lng) * t)
                val b = (fromBearing + turn * t + 360f) % 360f
                val tilt = fromTilt + (NAV_TILT - fromTilt) * t
                shownAt = p
                shownBearing = b
                shownTilt = tilt
                placeRunner(p)
                if (state.following) {
                    if (engine != null) engine.moveCamera(CameraUpdateFactory.newCameraPosition(CameraPosition(vsmPoint(p), NAV_ZOOM, tilt, b)))
                    else map.setCenterPoint(p.lat, p.lng)
                }
                if (t >= 1f) break
                delay(16)
            }
            if (BuildConfig.DEBUG) engine?.cameraPosition?.let { android.util.Log.d("RunNav", "tilt=${it.tilt} bearing=${it.bearing} zoom=${it.zoom}") }
        }
    }

    /** 화살표는 한 번만 올리고, 그다음부터는 위치만 옮긴다 (지웠다 다시 그리면 깜빡인다) */
    private fun placeRunner(at: LatLng) {
        val marker = runnerMarker
        if (marker == null) {
            map.removeAllTMapMarkerItem()
            runnerMarker = TMapMarkerItem().apply {
                id = "runner"
                icon = navIcon
                setPosition(0.5f, 0.5f)
                setTMapPoint(at.lat, at.lng)
            }.also { map.addTMapMarkerItem(it) }
        } else {
            marker.setTMapPoint(at.lat, at.lng)
            map.updateTMapMarkerItem(marker)
        }
    }

    /** 안내를 시작하면 화면 초점을 아래쪽으로 내려 앞길이 넓게 보이게, 끝내면 원래대로(가운데·평면·북쪽 위) */
    private fun navView(on: Boolean) {
        val engine = engine() ?: return
        engine.setScreenCenter(android.graphics.Point(map.width / 2, if (on) (map.height * NAV_FOCUS_Y).toInt() else map.height / 2))
        if (!on) {
            val pos = engine.cameraPosition
            engine.moveCamera(CameraUpdateFactory.newCameraPosition(CameraPosition(pos.target, pos.zoom, 0f, 0f)))
        }
    }

    // ── 위치 ──

    private fun askLocation() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED) {
            locate()
        } else {
            requestPermissions(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION), REQ_LOCATION)
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != REQ_LOCATION) return
        if (grantResults.any { it == PackageManager.PERMISSION_GRANTED }) locate() else {
            state.placeLabel = "위치 권한 필요"
            show(getString(R.string.need_location), 8_000)
        }
    }

    @SuppressLint("MissingPermission")   // 권한을 확인한 뒤에만 부른다
    private fun locate() {
        val manager = getSystemService(LocationManager::class.java)
        val got = { location: Location? ->
            if (location != null) {
                val first = here == null
                here = LatLng(location.latitude, location.longitude)
                state.hasLocation = true
                state.placeLabel = "📍 현재 위치"
                if (first) loadScenery()
                if (mapReady && state.course == null) map.setCenterPoint(location.latitude, location.longitude)
            }
        }
        // GPS만 기다리면 실내에서는 끝내 위치가 안 잡힌다 — 켜져 있는 위치 공급자(통합·GPS·와이파이/기지국)에 다 묻고 먼저 온 것을 쓴다
        val providers = locationProviders().filter { it in manager.allProviders && manager.isProviderEnabled(it) }
        if (providers.isEmpty()) {
            state.placeLabel = "위치가 꺼져 있어요"
            return show("휴대폰 위치(GPS)를 켜 주세요.", 8_000)
        }
        state.placeLabel = "현재 위치 확인 중"
        providers.mapNotNull { manager.getLastKnownLocation(it) }.maxByOrNull { it.time }?.let(got)
        var waiting = providers.size
        val answered = { location: Location? ->
            got(location)
            waiting -= 1
            if (waiting == 0 && here == null) state.placeLabel = "위치를 못 받았어요"
        }
        for (provider in providers) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                manager.getCurrentLocation(provider, null, mainExecutor) { answered(it) }
            } else {
                @Suppress("DEPRECATION")
                manager.requestSingleUpdate(provider, { answered(it) }, mainLooper)
            }
        }
    }

    private fun locationProviders(): List<String> = buildList {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) add(LocationManager.FUSED_PROVIDER)
        add(LocationManager.GPS_PROVIDER)
        add(LocationManager.NETWORK_PROVIDER)
    }

    // ── 풍경 · 목적지 ──

    private fun loadScenery() {
        api.scenery(here) { result ->
            val options = result.getOrNull() ?: return@scenery
            state.chosen.retainAll(options.map { it.value }.toSet())
            state.scenery = options
        }
    }

    private fun searchPlace(query: String, done: (List<Place>) -> Unit) {
        api.places(query, here) { result ->
            result.onSuccess { if (it.isEmpty()) show(getString(R.string.dest_none)); done(it) }
                .onFailure { show("장소를 찾지 못했어요: ${it.message}"); done(emptyList()) }
        }
    }

    // ── 코스 찾기 ──

    private fun find() {
        val start = here ?: return run { show(getString(R.string.no_location)); locate() }
        state.finding = true
        state.findStartedMs = System.currentTimeMillis()
        val dest = state.destination.takeIf { state.routeType == "oneway" }
        val request = RecommendRequest(state.distanceKm, state.routeType, start, userId(), state.chosen.toList(), dest?.at)
        api.recommend(request) { result ->
            state.finding = false
            result.onSuccess { found ->
                if (found.results.isEmpty()) return@onSuccess show(getString(R.string.no_results))
                state.results = found.results
                found.results.forEach { r -> if (r.favorite && r.course.id !in state.savedIds) state.savedIds += r.course.id }
                state.deliverKm = found.deliverKm ?: state.distanceKm
                state.notice = found.notice
                state.attribution = found.attribution
                state.picked = 0
                state.phase = Phase.Course
                drawCourse(found.results[0].course)
            }.onFailure {
                if (needsLoginAgain(it)) return@onFailure goToLogin(getString(R.string.login_again))
                show("코스를 찾지 못했어요: ${(it as? ServerError)?.detail ?: it.message}", 6_000)
            }
        }
    }

    /** 다른 후보를 고르면 실제로 달릴 Tmap 경로로 맞춘다 (1등은 이미 맞춰져 온다). */
    private fun pick(index: Int) {
        if (index == state.picked) return
        state.picked = index
        val chosen = state.results[index]
        drawCourse(chosen.course)
        if (chosen.course.joinedOnTmap || chosen.course.uncheckedReason != null) return
        state.aligning = true
        api.deliver(chosen.course, state.deliverKm ?: state.distanceKm, state.routeType) { result ->
            state.aligning = false
            result.onSuccess { delivered ->
                state.results = state.results.toMutableList().also { it[index] = chosen.copy(course = delivered) }
                if (state.picked == index) drawCourse(delivered)
            }.onFailure { show("실제 길로 맞추지 못해 설계한 코스를 보여 드려요: ${it.message}") }
        }
    }

    // ── 즐겨찾기 · 내 기록 ──

    /** 코스 카드의 별: 바로 바꿔 보여 주고, 서버가 거절하면 되돌린다 */
    private fun toggleFavorite() {
        val course = state.course ?: return
        val saved = course.id in state.savedIds
        if (saved) state.savedIds -= course.id else state.savedIds += course.id
        val done: (Result<Unit>) -> Unit = { result ->
            result.onSuccess { show(if (saved) "즐겨찾기에서 뺐어요" else "즐겨찾기에 담았어요. 메뉴의 '내 기록'에서 다시 달릴 수 있어요", 2_500) }
                .onFailure {
                    if (saved) state.savedIds += course.id else state.savedIds -= course.id
                    if (needsLoginAgain(it)) return@onFailure goToLogin(getString(R.string.login_again))
                    show("즐겨찾기를 바꾸지 못했어요: ${(it as? ServerError)?.detail ?: it.message}")
                }
        }
        if (saved) api.unfavorite(userId(), course.id, done) else api.favorite(userId(), course, done)
    }

    private fun openRecords() {
        state.showRecords = true
        state.records = null
        state.favorites = null
        state.recordsError = null
        api.taste(userId()) { result ->
            result.onSuccess { state.records = it }.onFailure { state.recordsError = "기록을 불러오지 못했어요: ${it.message}" }
        }
        api.favorites(userId()) { result ->
            result.onSuccess { list ->
                state.favorites = list
                list.forEach { f -> if (f.course.id !in state.savedIds) state.savedIds += f.course.id }
            }.onFailure { state.favorites = emptyList(); state.recordsError = "즐겨찾기를 불러오지 못했어요: ${it.message}" }
        }
    }

    /** 즐겨찾기한 코스를 그대로 띄운다 (저장할 때의 실제 경로 그대로 — 바로 안내를 시작할 수 있다) */
    private fun runFavorite(fav: Favorite) {
        state.results = listOf(Recommendation(fav.course, score = -1.0, favorite = true))
        state.picked = 0
        state.deliverKm = fav.course.distanceKm
        state.notice = null
        state.showRecords = false
        state.phase = Phase.Course
        drawCourse(fav.course)
    }

    /** 내 계정과 기록을 모두 지우고 로그인 화면으로 (확인 창에서 '모두 지우기'를 눌렀을 때만 온다) */
    private fun deleteMyData() {
        api.deleteMyData(userId()) { result ->
            result.onSuccess { goToLogin("내 데이터를 모두 지웠어요.") }
                .onFailure {
                    if (needsLoginAgain(it)) return@onFailure goToLogin(getString(R.string.login_again))
                    show("지우지 못했어요: ${(it as? ServerError)?.detail ?: it.message}")
                }
        }
    }

    private fun removeFavorite(fav: Favorite) {
        state.favorites = state.favorites?.filterNot { it.course.id == fav.course.id }
        state.savedIds -= fav.course.id
        api.unfavorite(userId(), fav.course.id) { result ->
            result.onFailure {
                state.favorites = (state.favorites ?: emptyList()) + fav
                state.savedIds += fav.course.id
                show("즐겨찾기에서 빼지 못했어요: ${(it as? ServerError)?.detail ?: it.message}")
            }
        }
    }

    private fun edit() {
        clearPath()
        state.phase = Phase.Ask
        state.step = 2
    }

    // ── 안내 (GPS · 음성) ──

    @SuppressLint("MissingPermission")   // 권한을 확인한 뒤에만 부른다
    private fun startGuide() {
        val course = state.course ?: return
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            return askLocation()
        }
        val running = Guide(course, System.currentTimeMillis())
        guide = running
        // 개발용 빌드에서만: 안내하는 코스 좌표를 기록에 남긴다 (PC에서 가짜 GPS로 이 코스를 따라 달려 보는 시험용)
        if (BuildConfig.DEBUG) course.path.chunked(40).forEachIndexed { i, part ->
            android.util.Log.d("RunPath", "$i/${(course.path.size + 39) / 40} " + part.joinToString(";") { "%.7f,%.7f".format(it.lat, it.lng) })
        }
        // 화면은 켜 두되, 잠가도 안내가 이어지게 포그라운드 서비스를 띄운다 (알림창에 "길안내 중")
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQ_NOTIFY)   // 거절해도 안내는 된다 (알림만 안 보인다)
        }
        GuideService.start(this)
        lastNotifiedM = -1
        lastStatus = null
        state.phase = Phase.Guiding
        state.arrived = false
        state.banner = null
        state.eta = null
        state.following = true
        drawJob?.cancel()
        drawPath(course.path)
        // 내비게이션 화면으로: 지도를 기울이고 진행 방향을 위로. GPS가 처음 잡히기 전에도 빈 지도를 보이지 않게
        // 마지막으로 안 내 위치(없으면 출발점)에 화살표를 두고 그곳에서 출발 방향을 비춘다
        if (mapReady) {
            navView(true)
            // 평면·북쪽 위에서 출발 방향으로 돌며 기울어지는 첫 장면 (1.2초)
            resetRunner()
            shownTilt = 0f
            (here ?: course.path.firstOrNull())?.let { followRunner(it, running, ms = 1200) }
        }
        if (uncheckedText(course) != null) say("Tmap으로 길을 확인하지 못한 코스입니다. 달리면서 길을 살펴 주세요.", false)
        // 튀는 위치는 안내·화살표에 넣지 않는다 (속도는 안내 시계로 잰다 — 개발용 빨리 감기에서도 같은 기준이 되게)
        val filter = GpsFilter()
        val listener = LocationListener { location ->
            if (guide !== running) return@LocationListener
            lastFixMs = System.currentTimeMillis()   // 신호는 있다 (걸러 낸 위치여도 'GPS 신호 없음'은 아니다)
            val at = LatLng(location.latitude, location.longitude)
            val now = guideClock(running.startedAt)
            if (!filter.accept(at, if (location.hasAccuracy()) location.accuracy else null, now)) {
                if (BuildConfig.DEBUG) android.util.Log.d("RunGps", "버림 ${at.lat},${at.lng} 정확도 ${location.accuracy}")
                return@LocationListener
            }
            lastRunner = at
            handle(running, running.onLocation(at, now))
            followRunner(at, running)   // 진행 거리가 갱신된 뒤에 앞길 방향을 잡는다
        }
        gpsListener = listener
        getSystemService(LocationManager::class.java).requestLocationUpdates(LocationManager.GPS_PROVIDER, GPS_EVERY_MS, 0f, listener)
        // 달리다 신호를 잠깐 잃는 건 흔하다(다리 밑·건물 사이) — 안내를 끄지 않고 다시 잡힐 때까지 기다린다
        lifecycleScope.launch {
            while (guide === running && !running.done) {
                delay(GPS_LOST_MS)
                if (lastFixMs > 0 && System.currentTimeMillis() - lastFixMs > GPS_LOST_MS) show(getString(R.string.gps_lost))
            }
        }
    }

    /**
     * 안내 규칙이 보는 시각. 배포용은 실제 시각 그대로다. 개발용 빌드에서만, 폰에
     * `adb shell setprop debug.runmate.timescale 10` 처럼 배수를 걸어 두면 안내 시작부터 그 배로 빨리 흐른다
     * (가짜 GPS로 코스를 빨리 감아 달릴 때 '그 거리를 달릴 수 있는 시간이 지나야 도착' 규칙도 같이 빨리 감기게).
     */
    private fun guideClock(startedAt: Long): Long {
        val now = System.currentTimeMillis()
        if (!BuildConfig.DEBUG) return now
        val scale = runCatching {
            Class.forName("android.os.SystemProperties").getMethod("get", String::class.java)
                .invoke(null, "debug.runmate.timescale") as String
        }.getOrNull()?.toDoubleOrNull()?.takeIf { it > 1 } ?: return now
        return startedAt + ((now - startedAt) * scale).toLong()
    }

    private fun handle(running: Guide, actions: List<GuideAction>) {
        for (action in actions) when (action) {
            is GuideAction.Say -> say(action.text, action.interrupt)
            // 그냥 "안내 중"은 위 회전 카드·아래 막대로 이미 보인다 — 코스를 벗어났거나 돌아가는 길로 바뀌었을 때처럼
            // 알릴 일이 생겼을 때, 그것도 말이 바뀔 때만 띄운다 (매초 같은 알림이 지도를 가리지 않게)
            is GuideAction.Status -> if (action.text != lastStatus) {
                lastStatus = action.text
                if (action.text.isNotBlank() && action.text != "안내 중") show(action.text)
            }
            is GuideAction.Banner -> state.banner = action
            is GuideAction.Reroute -> askWayBack(running, action)
            is GuideAction.Remaining -> showRemaining(action.meters)
            is GuideAction.Arrived -> {
                endGps()
                state.arrived = true
                if (action.completed) lifecycleScope.launch { delay(1_800); askRating() }
                else show("도착했어요. 코스를 80% 넘게 달린 뒤에 평가할 수 있어요.", 8_000)
            }
        }
    }

    private fun askWayBack(running: Guide, action: GuideAction.Reroute) {
        api.reroute(action.position, running.currentPath(), running.currentSteps(), action.progressM) { result ->
            if (guide !== running) return@reroute
            result.onSuccess { (back, extraM) ->
                handle(running, running.onRerouted(back, extraM))
                drawPath(running.currentPath())
            }.onFailure { handle(running, running.onRerouteFailed(System.currentTimeMillis())) }
        }
    }

    /** 아래 막대: 도착 예정 시각 · 남은 거리 · 남은 시간 (6분/km로 잡는다) */
    private fun showRemaining(meters: Double) {
        val minutes = Math.ceil(meters / 1000 * PACE_MIN_PER_KM).toInt()
        val at = Date(System.currentTimeMillis() + minutes * 60_000L)
        state.eta = Eta(SimpleDateFormat("H:mm", Locale.KOREAN).format(at), Guide.distanceText(meters), minutes)
        // 알림 문구는 100m마다만 고친다 (매초 고칠 일은 아니다)
        val step = (meters / 100).toInt()
        if (step != lastNotifiedM) {
            lastNotifiedM = step
            GuideService.update(this, "${SimpleDateFormat("a h:mm", Locale.KOREAN).format(at)} 도착 · ${Guide.distanceText(meters)} · ${minutes}분 남음")
        }
    }

    private fun say(text: String, interrupt: Boolean) {
        if (!state.voiceOn) return
        tts?.speak(text, if (interrupt) TextToSpeech.QUEUE_FLUSH else TextToSpeech.QUEUE_ADD, null, text)
    }

    private fun endGps() {
        gpsListener?.let { getSystemService(LocationManager::class.java).removeUpdates(it) }
        gpsListener = null
        GuideService.stop(this)
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }

    private fun stopGuide() {
        if (guide == null) return
        endGps()
        guide = null
        lastFixMs = 0
        state.banner = null
        state.eta = null
        state.arrived = false
        state.rating = null
        state.phase = Phase.Course
        if (mapReady) {
            resetRunner()
            map.removeAllTMapMarkerItem()
            navView(false)   // 평면·북쪽 위·가운데 초점으로 돌린 뒤에 코스 전체를 맞춘다
        }
        state.course?.let { drawCourse(it) }
    }

    // ── 평가 (달린 뒤에만 받는다 — 중간에 끝낸 안내는 달린 것이 아니다) ──

    private fun askRating() {
        // 항목별 질문은 서버가 정한다 (못 받으면 별점만 받는다)
        api.feedbackQuestions { result -> if (guide != null) state.rating = Rating(result.getOrNull() ?: emptyList()) }
    }

    private fun sendRating() {
        val rating = state.rating ?: return
        val course = state.course ?: return
        if (rating.stars == 0) return
        rating.sending = true
        api.feedback(userId(), course.id, rating.stars, rating.answers.toMap(), rating.comment) { result ->
            rating.sending = false
            result.onSuccess { taste ->
                state.rating = null
                show(if (taste.isEmpty()) getString(R.string.rate_sent) else "고마워요! 지금까지 본 내 취향\n" + taste.joinToString("\n") { "· $it" }, 8_000)
                stopGuide()
            }.onFailure {
                if (needsLoginAgain(it)) return@onFailure goToLogin(getString(R.string.login_again))
                show("평가를 보내지 못했어요: ${it.message}")
            }
        }
    }

    /** 로그인한 계정 (추천·평가·학습이 이 계정에 쌓인다) */
    private fun userId(): String = session.current?.userId ?: ""

    private fun goToLogin(message: String?) {
        session.clear()
        message?.let { Toast.makeText(this, it, Toast.LENGTH_LONG).show() }
        startActivity(Intent(this, LoginActivity::class.java))
        finish()
    }

    private fun logOut() {
        if (guide != null) return   // 달리는 중에는 로그아웃하지 않는다
        api.logOut { }               // 서버의 토큰도 지운다 (못 지워도 이 폰에서는 지운다)
        goToLogin(null)
    }

    companion object {
        private const val REQ_LOCATION = 1
        private const val REQ_NOTIFY = 2
        private const val GPS_EVERY_MS = 1_000L
        private const val GPS_LOST_MS = 10_000L
        private const val PACE_MIN_PER_KM = 6.0   // 도착 예정 시각 계산용
        private const val NAV_ZOOM = 17.5          // 달리는 중 확대 (골목 하나하나가 보이는 정도)
        private const val NAV_TILT = 55f           // 달리는 중 지도 기울기 (도) — 앞길이 멀리까지 입체로 보인다
        private const val NAV_FOCUS_Y = 0.68f      // 달리는 중 내 위치를 화면 위에서 이만큼 내려온 곳에 둔다
    }
}
