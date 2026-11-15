package com.runmate.app

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.slideOutVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathMeasure
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.roundToInt
import kotlin.math.sin

/** 시작 화면의 할 일: MainActivity가 받아서 서버에 묻는다. */
class AskActions(
    val find: () -> Unit,
    val searchPlace: (String, (List<Place>) -> Unit) -> Unit,
    val logOut: () -> Unit,
    val openRecords: () -> Unit,
)

/** 한 화면에 질문 하나씩: ① 거리 → ② 모양 → ③ 풍경 → 코스 찾기 (웹 데모의 폰 시작 화면과 같다). */
@Composable
fun AskScreen(state: RunState, actions: AskActions) {
    Column(
        Modifier
            .fillMaxSize()
            .background(Run.bg)
            .windowInsetsPadding(WindowInsets.statusBars)
            .windowInsetsPadding(WindowInsets.navigationBars)
            .imePadding()
            .padding(Run.screenPadding),
    ) {
        TopRow(state, actions)
        var forward by remember { mutableStateOf(true) }
        var shown by remember { mutableIntStateOf(state.step) }
        if (shown != state.step) { forward = state.step > shown; shown = state.step }
        AnimatedContent(
            targetState = state.step,
            transitionSpec = {
                val dir = if (forward) 1 else -1
                (slideInHorizontally(tween(340, easing = FastOutSlowInEasing)) { it / 3 * dir } + fadeIn(tween(260)))
                    .togetherWith(slideOutHorizontally(tween(300)) { -it / 4 * dir } + fadeOut(tween(180)))
            },
            modifier = Modifier.weight(1f),
            label = "step",
        ) { step ->
            Column(Modifier.fillMaxSize()) {
                when (step) {
                    0 -> DistanceStep(state)
                    1 -> ShapeStep(state, actions)
                    else -> SceneryStep(state, actions)
                }
            }
        }
    }
}

@Composable
private fun TopRow(state: RunState, actions: AskActions) {
    Row(Modifier.fillMaxWidth().heightIn(min = 40.dp), verticalAlignment = Alignment.CenterVertically) {
        val backAlpha by animateFloatAsState(if (state.step > 0) 1f else 0f, label = "back")
        Box(
            Modifier.size(40.dp).graphicsLayer { alpha = backAlpha }.clip(CircleShape).background(Run.top)
                .clickable(enabled = state.step > 0) { state.step -= 1 },
            contentAlignment = Alignment.Center,
        ) { Text("←", fontSize = 18.sp, color = Run.ink) }
        Spacer(Modifier.width(10.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            repeat(3) { i ->
                val on = i <= state.step
                val color by animateColorAsState(if (on) Run.accent else Run.line, tween(300), label = "dot")
                val width by animateDpAsState(if (i == state.step) 30.dp else 22.dp, spring(dampingRatio = 0.6f), label = "dotW")
                Box(Modifier.width(width).height(4.dp).clip(RoundedCornerShape(2.dp)).background(color))
            }
        }
        Spacer(Modifier.weight(1f))
        var menu by remember { mutableStateOf(false) }
        Box {
            Text(
                state.placeLabel,
                fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = Run.mute, maxLines = 1, overflow = TextOverflow.Ellipsis,
                modifier = Modifier.widthIn(max = 190.dp).clip(RoundedCornerShape(50)).background(Run.top)
                    .clickable { menu = true }.padding(horizontal = 14.dp, vertical = 6.dp),
            )
            DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                DropdownMenuItem(text = { Text("${state.username} 계정", color = Run.mute) }, onClick = { menu = false }, enabled = false)
                DropdownMenuItem(text = { Text("내 기록 · 즐겨찾기") }, onClick = { menu = false; actions.openRecords() })
                DropdownMenuItem(text = { Text("로그아웃") }, onClick = { menu = false; actions.logOut() })
            }
        }
    }
}

@Composable
private fun Question(title: String, sub: String) {
    Text(title, style = Run.question, modifier = Modifier.padding(top = 40.dp, bottom = 6.dp))
    Text(sub, style = Run.sub, modifier = Modifier.padding(bottom = 28.dp))
}

// ── ① 거리: 다이얼 ──

/** 다이얼: 왼쪽 아래(1km)에서 시계 방향으로 270° 돌면 오른쪽 아래(42.195km). 1~10km가 55%를 쓴다 (웹과 같은 눈금). */
object Dial {
    const val FROM = 135f
    const val SWEEP = 270f
    private const val MID_SHARE = 0.55

    fun share(km: Double): Float = (if (km <= Distance.MID) (km - Distance.MIN) / (Distance.MID - Distance.MIN) * MID_SHARE
    else MID_SHARE + (km - Distance.MID) / (Distance.MAX - Distance.MID) * (1 - MID_SHARE)).toFloat()

    fun km(share: Double): Double = if (share <= MID_SHARE) Distance.MIN + share / MID_SHARE * (Distance.MID - Distance.MIN)
    else Distance.MID + (share - MID_SHARE) / (1 - MID_SHARE) * (Distance.MAX - Distance.MID)

    /** 다이얼로 고를 수 있는 값: 10km까지 0.5km씩, 그 위는 1km씩, 맨 끝은 풀코스 */
    fun snap(km: Double): Double {
        if (km >= Distance.MAX - 0.5) return Distance.MAX
        val v = if (km <= Distance.MID) (km * 2).roundToInt() / 2.0 else km.roundToInt().toDouble()
        return v.coerceIn(Distance.MIN, Distance.MAX)
    }

    val TICKS = listOf(1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 15.0, 20.0, Distance.HALF, 25.0, 30.0, 35.0, 40.0, Distance.MAX)
    val LABELS = mapOf(1.0 to "1", 5.0 to "5", 10.0 to "10", Distance.HALF to "21", Distance.MAX to "42")

    fun bigNumber(km: Double): String = if (km == Distance.MAX) "42.195" else "%.1f".format(km)
    fun unit(km: Double): String = when (km) { Distance.HALF -> "km · 하프"; Distance.MAX -> "km · 풀코스"; else -> "km" }
}

@Composable
private fun ColumnScope.DistanceStep(state: RunState) {
    Question("얼마나\n달릴까요?", "다이얼을 돌려 정하세요. 실제로 달릴 길로 ±5% 안에 맞춰 드려요.")
    DistanceDial(state.distanceKm, onChange = { state.distanceKm = it })
    Row(Modifier.fillMaxWidth().padding(top = 14.dp), horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally)) {
        Distance.PRESETS.forEach { (label, km) ->
            val on = state.distanceKm == km
            val bg by animateColorAsState(if (on) Run.coral else Run.top, tween(220), label = "preset")
            val fg by animateColorAsState(if (on) Color.White else Run.ink, tween(220), label = "presetText")
            val pop by animateFloatAsState(if (on) 1.06f else 1f, spring(dampingRatio = 0.45f, stiffness = 500f), label = "presetPop")
            Text(
                label, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = fg, textAlign = TextAlign.Center, maxLines = 1,
                // 넷이 같은 너비로 한 줄을 나눠 쓴다 (폰 글씨를 크게 해 둬도 '풀코스'가 잘리지 않게)
                modifier = Modifier.weight(1f).scale(pop).clip(RoundedCornerShape(50)).background(bg)
                    .clickable { state.distanceKm = km }.padding(horizontal = 2.dp, vertical = 10.dp),
            )
        }
    }
    Spacer(Modifier.weight(1f))
    PrimaryButton("다음") { state.step = 1 }
}

@Composable
private fun DistanceDial(km: Double, onChange: (Double) -> Unit) {
    // 처음 보일 때 0에서 돌아 올라오고, 값을 바꾸면 스프링으로 따라간다
    val share = remember { Animatable(0f) }
    LaunchedEffect(km) { share.animateTo(Dial.share(km), spring(dampingRatio = 0.75f, stiffness = 260f)) }
    BoxWithConstraints(Modifier.fillMaxWidth().padding(top = 4.dp), contentAlignment = Alignment.Center) {
        val side = minOf(maxWidth, 250.dp)
        Box(Modifier.size(side).aspectRatio(1f)) {
            fun kmAt(pos: Offset, size: Float): Double {
                val c = size / 2
                var rel = ((Math.toDegrees(atan2((pos.y - c).toDouble(), (pos.x - c).toDouble())) - Dial.FROM) + 720) % 360
                if (rel > Dial.SWEEP) rel = if (rel > Dial.SWEEP + (360 - Dial.SWEEP) / 2) 0.0 else Dial.SWEEP.toDouble()   // 아래 트인 곳은 가까운 끝으로
                return Dial.km(rel / Dial.SWEEP)
            }
            Canvas(
                Modifier.fillMaxSize()
                    .pointerInput(Unit) { detectTapGestures { onChange(Dial.snap(kmAt(it, size.width.toFloat()))) } }
                    .pointerInput(Unit) {
                        detectDragGestures(onDragStart = { onChange(Dial.snap(kmAt(it, size.width.toFloat()))) }) { change, _ ->
                            onChange(Dial.snap(kmAt(change.position, size.width.toFloat())))
                        }
                    },
            ) { drawDial(share.value) }
            Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
                RollingNumber(Dial.bigNumber(km), TextStyle(fontFamily = Run.num, fontWeight = FontWeight.Black,
                    fontSize = if (km == Distance.MAX) 54.sp else 76.sp, color = Run.ink, lineHeight = 70.sp))
                Text(Dial.unit(km), fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = Run.mute)
            }
            Row(Modifier.align(Alignment.BottomCenter).offset(y = 4.dp), horizontalArrangement = Arrangement.spacedBy(44.dp)) {
                RoundIcon("−") { onChange(Distance.down(km)) }
                RoundIcon("+") { onChange(Distance.up(km)) }
            }
        }
    }
}

/** 웹 다이얼과 같은 비율(가로세로 260 기준): 반지름 104, 굵기 18, 눈금은 안쪽, 숫자는 바깥쪽 */
private fun DrawScope.drawDial(share: Float) {
    val k = size.width / 260f
    val r = 104f * k
    val c = Offset(size.width / 2, size.height / 2)
    fun at(deg: Float, radius: Float) = Offset(c.x + radius * cos(Math.toRadians(deg.toDouble())).toFloat(), c.y + radius * sin(Math.toRadians(deg.toDouble())).toFloat())
    val arcTopLeft = Offset(c.x - r, c.y - r)
    val arcSize = Size(r * 2, r * 2)
    drawArc(Run.line, Dial.FROM, Dial.SWEEP, false, arcTopLeft, arcSize, style = Stroke(18f * k, cap = StrokeCap.Round))
    for (km in Dial.TICKS) {
        val deg = Dial.FROM + Dial.share(km) * Dial.SWEEP
        val major = km in Dial.LABELS
        drawLine(if (major) Run.mute else Run.line, at(deg, r - 18f * k), at(deg, r - 26f * k), 2f * k, StrokeCap.Round)
    }
    val deg = Dial.FROM + share * Dial.SWEEP
    drawArc(Run.accent, Dial.FROM, maxOf(0.01f, share * Dial.SWEEP), false, arcTopLeft, arcSize, style = Stroke(18f * k, cap = StrokeCap.Round))
    val knob = at(deg, r)
    drawCircle(Run.shadow, 17f * k, knob + Offset(0f, 2f * k))
    drawCircle(Color.White, 15f * k, knob)
    drawCircle(Run.accent, 15f * k, knob, style = Stroke(5f * k))
    // 눈금 숫자 (1·5·10·21·42)
    val paint = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply {
        color = android.graphics.Color.rgb(0x5B, 0x64, 0x78)
        textSize = 13f * k
        textAlign = android.graphics.Paint.Align.CENTER
        typeface = android.graphics.Typeface.create("sans-serif-condensed", android.graphics.Typeface.BOLD)
    }
    for ((km, label) in Dial.LABELS) {
        val p = at(Dial.FROM + Dial.share(km) * Dial.SWEEP, r + 22f * k)
        drawContext.canvas.nativeCanvas.drawText(label, p.x, p.y + 4.5f * k, paint)
    }
}

/** 숫자가 바뀌면 위·아래로 굴러 바뀐다 (늘면 위로, 줄면 아래로) */
@Composable
fun RollingNumber(text: String, style: TextStyle, modifier: Modifier = Modifier) {
    var previous by remember { mutableStateOf(text) }
    val up = (text.toDoubleOrNull() ?: 0.0) >= (previous.toDoubleOrNull() ?: 0.0)
    LaunchedEffect(text) { previous = text }
    AnimatedContent(
        targetState = text,
        transitionSpec = {
            val d = if (up) 1 else -1
            (slideInVertically(tween(220)) { it / 2 * d } + fadeIn(tween(180)))
                .togetherWith(slideOutVertically(tween(200)) { -it / 2 * d } + fadeOut(tween(140)))
        },
        modifier = modifier,
        label = "number",
    ) { Text(it, style = style, maxLines = 1) }
}

@Composable
private fun RoundIcon(symbol: String, onClick: () -> Unit) {
    val source = remember { MutableInteractionSource() }
    val pressed by source.collectIsPressedAsState()
    val s by animateFloatAsState(if (pressed) 0.9f else 1f, spring(stiffness = 700f), label = "press")
    Box(
        Modifier.size(40.dp).scale(s).clip(CircleShape).background(Run.top).clickable(source, null, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) { Text(symbol, fontSize = 22.sp, color = Run.ink) }
}

// ── ② 모양: 큰 카드 셋, 모양을 선으로 그린다 (고르면 선이 다시 그려진다) ──

private val SHAPES = listOf(
    Triple("roundtrip", "왕복", "갔던 길로 되돌아와요"),
    Triple("loop", "순환", "한 바퀴 돌아 제자리로 와요"),
    Triple("oneway", "편도", "한 방향으로 쭉 가요"),
)

@Composable
private fun ColumnScope.ShapeStep(state: RunState, actions: AskActions) {
    Question("코스는\n어떻게 짤까요?", "다 달리고 어디로 올지 골라 주세요.")
    Column(Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SHAPES.forEachIndexed { i, (value, title, sub) ->
            val on = state.routeType == value
            Appear(i) {
                val bg by animateColorAsState(if (on) Run.accentSoft else Run.top, tween(240), label = "segBg")
                val border by animateColorAsState(if (on) Run.accent else Color.Transparent, tween(240), label = "segBorder")
                Row(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(bg)
                        .border(2.dp, border, RoundedCornerShape(18.dp))
                        .clickable { state.routeType = value; if (value != "oneway") state.destination = null }
                        .padding(horizontal = 18.dp, vertical = 16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    ShapeIcon(value, on)
                    Spacer(Modifier.width(16.dp))
                    Column {
                        Text(title, fontSize = 18.sp, fontWeight = FontWeight.Bold, color = Run.ink)
                        Text(sub, fontSize = 13.sp, color = Run.mute)
                    }
                }
            }
        }
        AnimatedVisibility(state.routeType == "oneway", enter = expandVertically() + fadeIn(), exit = shrinkVertically() + fadeOut()) {
            DestinationBox(state, actions)
        }
    }
    Spacer(Modifier.height(12.dp))
    PrimaryButton("다음") { state.step = 2 }
}

/** 웹의 SVG(46×46)와 같은 선. on이 되면 처음부터 다시 그려진다 */
@Composable
private fun ShapeIcon(kind: String, on: Boolean) {
    val progress = remember { Animatable(1f) }
    LaunchedEffect(on) { if (on) { progress.snapTo(0f); progress.animateTo(1f, tween(700, easing = FastOutSlowInEasing)) } }
    val color by animateColorAsState(if (on) Run.accent else Run.mute, label = "icon")
    Canvas(Modifier.size(46.dp)) {
        scale(size.width / 46f, pivot = Offset.Zero) {
            val stroke = Stroke(3f, cap = StrokeCap.Round, join = StrokeJoin.Round)
            for (path in shapePaths(kind)) {
                val measure = PathMeasure().apply { setPath(path, false) }
                val part = Path()
                measure.getSegment(0f, measure.length * progress.value, part, true)
                drawPath(part, color, style = stroke)
            }
        }
    }
}

private fun shapePaths(kind: String): List<Path> = when (kind) {
    "roundtrip" -> listOf(
        Path().apply { moveTo(8f, 30f); lineTo(34f, 30f) },
        Path().apply { moveTo(28f, 24f); lineTo(34f, 30f); lineTo(28f, 36f) },
        Path().apply { moveTo(38f, 16f); lineTo(12f, 16f) },
        Path().apply { moveTo(18f, 10f); lineTo(12f, 16f); lineTo(18f, 22f) },
    )
    "loop" -> listOf(
        Path().apply {
            moveTo(23f, 8f); cubicTo(34f, 8f, 38f, 16f, 38f, 23f); cubicTo(38f, 32f, 31f, 38f, 23f, 38f)
            cubicTo(14f, 38f, 8f, 31f, 8f, 23f); cubicTo(8f, 16f, 13f, 10f, 20f, 8.5f)
        },
        Path().apply { moveTo(16f, 5f); lineTo(21f, 8.6f); lineTo(17f, 13f) },
    )
    else -> listOf(
        Path().apply { addOval(androidx.compose.ui.geometry.Rect(6f, 31f, 12f, 37f)) },
        Path().apply { moveTo(12f, 32f); cubicTo(20f, 26f, 22f, 18f, 30f, 14f); lineTo(38f, 10f) },
        Path().apply { moveTo(31f, 8f); lineTo(38f, 10f); lineTo(35f, 17f) },
    )
}

/** 편도일 때만: 목적지를 검색해서 고르면 그곳까지 가는 코스 (안 고르면 한 방향으로 쭉) */
@Composable
private fun DestinationBox(state: RunState, actions: AskActions) {
    var query by remember { mutableStateOf("") }
    var found by remember { mutableStateOf<List<Place>>(emptyList()) }
    var searching by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().padding(top = 4.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        val chosen = state.destination
        if (chosen != null) {
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Run.accentSoft).padding(horizontal = 16.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text("목적지", fontSize = 12.sp, color = Run.mute)
                    Text(chosen.name, fontSize = 16.sp, fontWeight = FontWeight.Bold, color = Run.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                Text("지우기", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Run.accent,
                    modifier = Modifier.clickable { state.destination = null }.padding(6.dp))
            }
            return@Column
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val search = {
                if (query.isNotBlank()) {
                    searching = true
                    actions.searchPlace(query.trim()) { found = it; searching = false }
                }
            }
            Box(Modifier.weight(1f).clip(RoundedCornerShape(14.dp)).background(Run.top).padding(horizontal = 16.dp, vertical = 14.dp)) {
                if (query.isEmpty()) Text("목적지 검색 (선택)", fontSize = 15.sp, color = Run.mute, maxLines = 1)
                BasicTextField(
                    query, { query = it }, singleLine = true,
                    textStyle = TextStyle(fontSize = 15.sp, color = Run.ink),
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                    keyboardActions = KeyboardActions(onSearch = { search() }),
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            Text(if (searching) "…" else "검색", fontSize = 15.sp, fontWeight = FontWeight.Bold, color = Color.White,
                modifier = Modifier.clip(RoundedCornerShape(14.dp)).background(Run.accent).clickable { search() }.padding(horizontal = 18.dp, vertical = 14.dp))
        }
        found.take(5).forEachIndexed { i, place ->
            Appear(i) {
                Column(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Run.top)
                        .clickable { state.destination = place; found = emptyList(); query = "" }
                        .padding(horizontal = 16.dp, vertical = 10.dp),
                ) {
                    Text(place.name, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = Run.ink)
                    Text(listOfNotNull(place.distanceKm?.let { "%.1fkm".format(it) }, place.address).joinToString(" · "),
                        fontSize = 12.sp, color = Run.mute, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
        }
    }
}

// ── ③ 풍경: 근처에 실제로 있는 것만, 여러 개 고를 수 있다 ──

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ColumnScope.SceneryStep(state: RunState, actions: AskActions) {
    Question("어디를\n지나고 싶어요?", "근처에 실제로 있는 풍경만 보여드려요. 안 골라도 돼요.")
    Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
        if (state.scenery.isEmpty()) {
            Text(if (state.hasLocation) "근처 풍경을 불러오는 중…" else "현재 위치를 확인하면 근처 풍경을 보여드려요.", style = Run.sub)
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            state.scenery.forEachIndexed { i, option ->
                val on = option.value in state.chosen
                Appear(i, stagger = 35) {
                    val bg by animateColorAsState(if (on) Run.accentSoft else Run.top, tween(200), label = "chipBg")
                    val border by animateColorAsState(if (on) Run.accent else Color.Transparent, tween(200), label = "chipBorder")
                    val pop by animateFloatAsState(if (on) 1.05f else 1f, spring(dampingRatio = 0.4f, stiffness = 600f), label = "chipPop")
                    Row(
                        Modifier.scale(pop).heightIn(min = 44.dp).clip(RoundedCornerShape(50)).background(bg)
                            .border(2.dp, border, RoundedCornerShape(50))
                            .clickable { if (on) state.chosen.remove(option.value) else state.chosen.add(option.value) }
                            .padding(horizontal = 16.dp, vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(option.value, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, color = Run.ink)
                        option.near?.let { Text("  $it", fontSize = 12.sp, color = if (on) Run.ink else Run.mute) }
                    }
                }
            }
        }
        if (state.scenery.isNotEmpty()) Text("고른 풍경을 지나는 코스를 먼저 찾아요.", fontSize = 13.sp, color = Run.mute, modifier = Modifier.padding(top = 12.dp))
    }
    Spacer(Modifier.height(12.dp))
    val shape = SHAPES.first { it.first == state.routeType }.second
    val picked = if (state.chosen.isEmpty()) "풍경 상관없음" else "풍경 ${state.chosen.size}개"
    Text("${Distance.label(state.distanceKm)} · $shape · $picked", fontSize = 13.sp, color = Run.mute, textAlign = TextAlign.Center,
        modifier = Modifier.fillMaxWidth().padding(bottom = 10.dp))
    FindButton(state, actions.find)
}

/** 코스 찾기: 찾는 동안 버튼 위로 빛줄기가 흐르고 걸린 초를 센다 (긴 코스는 1~2분 걸린다) */
@Composable
private fun FindButton(state: RunState, onClick: () -> Unit) {
    if (!state.finding) return PrimaryButton("코스 찾기", onClick = onClick)
    var seconds by remember { mutableIntStateOf(0) }
    LaunchedEffect(state.findStartedMs) {
        while (true) { seconds = ((System.currentTimeMillis() - state.findStartedMs) / 1000).toInt(); delay(250) }
    }
    val shine = rememberInfiniteTransition(label = "shine")
    val x by shine.animateFloat(-0.4f, 1.4f, infiniteRepeatable(tween(1300, easing = LinearEasing), RepeatMode.Restart), label = "x")
    BoxWithConstraints(Modifier.fillMaxWidth().height(56.dp).clip(RoundedCornerShape(16.dp)).background(Run.accent)) {
        val w = constraints.maxWidth.toFloat()
        Box(Modifier.fillMaxSize().background(Brush.horizontalGradient(
            listOf(Color.Transparent, Color.White.copy(alpha = 0.28f), Color.Transparent),
            startX = w * (x - 0.3f), endX = w * (x + 0.3f),
        )))
        val text = if (state.distanceKm > 10) "긴 코스를 만드는 중 · ${seconds}초" else "코스를 만드는 중 · ${seconds}초"
        Text(text, style = Run.button, color = Color.White, modifier = Modifier.align(Alignment.Center))
    }
}

// ── 공통 ──

@Composable
fun PrimaryButton(text: String, modifier: Modifier = Modifier, radius: Dp = 16.dp, enabled: Boolean = true, onClick: () -> Unit) {
    val source = remember { MutableInteractionSource() }
    val pressed by source.collectIsPressedAsState()
    val s by animateFloatAsState(if (pressed) 0.97f else 1f, spring(stiffness = Spring.StiffnessHigh), label = "press")
    Box(
        modifier.fillMaxWidth().height(56.dp).scale(s).clip(RoundedCornerShape(radius))
            .background(if (enabled) Run.accent else Run.top)
            .clickable(source, null, enabled = enabled, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) { Text(text, style = Run.button, color = if (enabled) Color.White else Run.mute) }
}

/** 목록이 처음 보일 때 하나씩 아래에서 떠오른다 */
@Composable
fun Appear(index: Int, stagger: Int = 60, content: @Composable () -> Unit) {
    val p = remember { Animatable(0f) }
    LaunchedEffect(Unit) { delay(index * stagger.toLong()); p.animateTo(1f, tween(320, easing = FastOutSlowInEasing)) }
    Box(Modifier.graphicsLayer { alpha = p.value; translationY = (1 - p.value) * 24.dp.toPx() }) { content() }
}
