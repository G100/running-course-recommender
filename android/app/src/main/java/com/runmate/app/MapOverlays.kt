package com.runmate.app

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.draw.scale
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.abs
import kotlin.math.roundToInt

/** 지도 위 화면의 할 일 */
class MapActions(
    val pick: (Int) -> Unit,
    val edit: () -> Unit,
    val startGuide: () -> Unit,
    val stopGuide: () -> Unit,
    val toggleVoice: () -> Unit,
    val recenter: () -> Unit,
    val sendRating: () -> Unit,
    val skipRating: () -> Unit,
)

private val floatShape = RoundedCornerShape(32.dp)
private fun Modifier.floating(shape: androidx.compose.ui.graphics.Shape) =
    this.shadow(14.dp, shape, ambientColor = Run.shadow, spotColor = Run.shadow).clip(shape).background(Run.bg)

// ── 코스 확인: 아래에서 올라오는 카드 ──

@Composable
fun BoxScope.CourseSheet(state: RunState, actions: MapActions) {
    AnimatedVisibility(
        visible = state.phase == Phase.Course && state.course != null,
        enter = slideInVertically(spring(dampingRatio = 0.8f, stiffness = 320f)) { it } + fadeIn(),
        exit = slideOutVertically(tween(220)) { it } + fadeOut(),
        modifier = Modifier.align(Alignment.BottomCenter),
    ) {
        val pick = state.pick ?: return@AnimatedVisibility
        val course = pick.course
        // 카드는 지도를 덜 가리게 촘촘하게 둔다. 높이를 알려 주면 지도가 코스를 카드 위쪽 빈 곳에 맞춘다
        Column(
            Modifier.windowInsetsPadding(WindowInsets.navigationBars).padding(8.dp).fillMaxWidth()
                .onGloballyPositioned { state.sheetPx = it.size.height }
                .floating(floatShape)
                .padding(start = 20.dp, end = 20.dp, top = 16.dp, bottom = 16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            if (state.results.size > 1) CourseOptions(state, actions)
            AnimatedContent(course.id, transitionSpec = { fadeIn(tween(250)).togetherWith(fadeOut(tween(150))) }, label = "course") {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Column {
                        Text(course.name, fontSize = 18.sp, fontWeight = FontWeight.Bold, color = Run.ink, lineHeight = 23.sp,
                            maxLines = 1, overflow = TextOverflow.Ellipsis)
                        val reasons = recommendReasons(pick.breakdown)
                        if (reasons.isNotEmpty()) Text(reasons.joinToString(" · "), fontSize = 13.sp, fontWeight = FontWeight.Medium,
                            color = Run.mute, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 2.dp))
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(22.dp)) {
                        Stat(course.distanceKm, if (course.joinedOnTmap) "km" else "km(대략)", decimals = 2, key = course.id)
                        course.signals?.let { Stat(it.toDouble(), "신호등", decimals = 0, key = course.id) }
                        Stat(pick.score * 100, "점수/100", decimals = 0, key = course.id)
                    }
                }
            }
            OffTarget(state, course)
            uncheckedText(course)?.let { Warning(it) }
            listOfNotNull(state.notice, state.attribution).takeIf { it.isNotEmpty() }?.let {
                Text(it.joinToString(" · "), fontSize = 11.sp, color = Run.mute, lineHeight = 14.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("다시 고르기", fontSize = 15.sp, fontWeight = FontWeight.Medium, color = Run.ink, textAlign = TextAlign.Center, maxLines = 1,
                    modifier = Modifier.heightIn(min = 52.dp).clip(RoundedCornerShape(50)).background(Run.top)
                        .clickable(onClick = actions.edit).padding(horizontal = 18.dp, vertical = 14.dp))
                PrimaryButton(if (state.aligning) "길 맞추는 중…" else "안내 시작", modifier = Modifier.weight(1f), radius = 50.dp,
                    enabled = !state.aligning, onClick = actions.startGuide)
            }
        }
    }
}

/** 후보 고르기: 카드 맨 위 알약 줄. 고른 코스만 진한 알약 */
@Composable
private fun CourseOptions(state: RunState, actions: MapActions) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        state.results.forEachIndexed { i, r ->
            val on = i == state.picked
            val bg by animateColorAsState(if (on) Run.ink else Run.top, tween(220), label = "optBg")
            val fg by animateColorAsState(if (on) Run.bg else Run.ink, tween(220), label = "optFg")
            Column(
                Modifier.weight(1f).clip(RoundedCornerShape(14.dp)).background(bg)
                    .clickable(enabled = !state.aligning) { actions.pick(i) }.padding(horizontal = 10.dp, vertical = 7.dp),
            ) {
                Text("코스 ${i + 1}", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = if (on) Run.bg else Run.mute)
                Text((if (r.course.joinedOnTmap) "" else "약 ") + "%.1f".format(r.course.distanceKm),
                    style = TextStyle(fontFamily = Run.num, fontWeight = FontWeight.ExtraBold, fontSize = 20.sp, color = fg))
            }
        }
    }
}

/** 큰 숫자: 코스가 바뀌면 0에서부터 세어 올라간다 */
@Composable
private fun Stat(value: Double, label: String, decimals: Int, key: String) {
    val shown = remember(key) { Animatable(0f) }
    LaunchedEffect(key, value) { shown.animateTo(value.toFloat(), tween(800, easing = FastOutSlowInEasing)) }
    Column {
        Text(if (decimals == 0) shown.value.roundToInt().toString() else "%.${decimals}f".format(shown.value),
            style = TextStyle(fontFamily = Run.num, fontWeight = FontWeight.ExtraBold, fontSize = 42.sp, lineHeight = 40.sp, color = Run.ink))
        Text(label, fontSize = 12.sp, fontWeight = FontWeight.Medium, color = Run.mute, maxLines = 1, modifier = Modifier.padding(top = 2.dp))
    }
}

/** 요청 거리와 5% 넘게 다르면 숨기지 않고 알린다 */
@Composable
private fun OffTarget(state: RunState, course: Course) {
    val want = state.deliverKm ?: state.distanceKm
    val off = (course.distanceKm - want) / want
    if (abs(off) <= 0.05) return
    Warning("요청한 ${Distance.label(state.distanceKm)}보다 ${(abs(off) * 100).roundToInt()}% ${if (off > 0) "길어요" else "짧아요"}. 근처 길로는 더 가깝게 맞추지 못했어요.")
}

@Composable
private fun Warning(text: String) {
    Text(text, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Run.coralInk, lineHeight = 20.sp,
        modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Run.coralSoft).padding(horizontal = 12.dp, vertical = 10.dp))
}

// ── 달리는 중 ──

/** 회전 정도: Tmap 회전 종류 → 화살표 머리 각도 (오른쪽이 +). 웹 데모와 같다 */
private val TURN_ANGLE = mapOf(12 to -90f, 13 to 90f, 14 to -180f, 16 to -135f, 17 to -45f, 18 to 45f, 19 to 135f, 212 to -90f, 213 to 90f)

@Composable
fun BoxScope.GuideOverlays(state: RunState, actions: MapActions) {
    val guiding = state.phase == Phase.Guiding
    Column(
        Modifier.align(Alignment.TopCenter).windowInsetsPadding(WindowInsets.statusBars).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        AnimatedVisibility(guiding && state.banner?.next != null && !state.arrived,
            enter = slideInVertically(spring(dampingRatio = 0.8f)) { -it } + fadeIn(), exit = slideOutVertically { -it } + fadeOut()) {
            state.banner?.let { TurnCard(it) }
        }
        AnimatedVisibility(guiding && state.banner?.after != null && !state.arrived, enter = fadeIn() + slideInVertically { -it / 2 }, exit = fadeOut()) {
            state.banner?.after?.let { after ->
                Row(
                    Modifier.padding(horizontal = 12.dp).fillMaxWidth().clip(RoundedCornerShape(50)).background(Run.top)
                        .padding(start = 18.dp, end = 18.dp, top = 8.dp, bottom = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    TurnArrow(after, Modifier.size(18.dp), stroke = 8f)
                    Spacer(Modifier.width(10.dp))
                    Text("그다음 ${after.instruction}", fontSize = 14.sp, fontWeight = FontWeight.Medium, color = Run.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
        }
        // 짧은 알림 (GPS를 잃음 · 길을 벗어남 · 오류)
        AnimatedVisibility(state.message != null, enter = fadeIn() + scaleIn(initialScale = 0.9f), exit = fadeOut()) {
            Text(state.message ?: "", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Color.White, lineHeight = 19.sp,
                modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(Run.ink.copy(alpha = 0.88f)).padding(horizontal = 16.dp, vertical = 10.dp))
        }
    }

    // 오른쪽 아래 둥근 버튼: 내 위치로
    AnimatedVisibility(guiding && !state.following, enter = scaleIn() + fadeIn(), exit = scaleOut() + fadeOut(),
        modifier = Modifier.align(Alignment.BottomEnd).windowInsetsPadding(WindowInsets.navigationBars).padding(end = 16.dp, bottom = 96.dp)) {
        Box(Modifier.size(44.dp).floating(CircleShape).clickable(onClick = actions.recenter), contentAlignment = Alignment.Center) {
            Canvas(Modifier.size(20.dp)) {
                scale(size.width / 24f, pivot = Offset.Zero) {
                    drawCircle(Run.ink, 7f, Offset(12f, 12f), style = androidx.compose.ui.graphics.drawscope.Stroke(1.8f))
                    drawCircle(Run.ink, 2.5f, Offset(12f, 12f), style = androidx.compose.ui.graphics.drawscope.Stroke(1.8f))
                    listOf(Offset(12f, 2f) to Offset(12f, 5f), Offset(12f, 19f) to Offset(12f, 22f), Offset(2f, 12f) to Offset(5f, 12f), Offset(19f, 12f) to Offset(22f, 12f))
                        .forEach { (a, b) -> drawLine(Run.ink, a, b, 1.8f, StrokeCap.Round) }
                }
            }
        }
    }

    // 아래 막대: 소리 · 도착 예정 · 끝내기
    AnimatedVisibility(guiding, enter = slideInVertically(spring(dampingRatio = 0.8f)) { it } + fadeIn(), exit = slideOutVertically { it } + fadeOut(),
        modifier = Modifier.align(Alignment.BottomCenter)) {
        Row(
            Modifier.windowInsetsPadding(WindowInsets.navigationBars).padding(12.dp).fillMaxWidth().floating(RoundedCornerShape(50))
                .padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            BarButton(if (state.voiceOn) "🔊" else "🔇", actions.toggleVoice)
            Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                val eta = state.eta
                Text(if (state.arrived) "도착" else eta?.clock ?: "—",
                    style = TextStyle(fontFamily = Run.num, fontWeight = FontWeight.ExtraBold, fontSize = 32.sp, lineHeight = 32.sp, color = Run.ink))
                Text(if (state.arrived) "수고하셨어요" else eta?.let { "도착 예정 · ${it.distance} · ${it.minutes}분" } ?: "GPS 위치를 기다리는 중",
                    fontSize = 12.sp, fontWeight = FontWeight.Medium, color = Run.mute)
            }
            BarButton("✕", actions.stopGuide)
        }
    }

    // 도착: 가운데 파란 판이 튀어나온다
    AnimatedVisibility(guiding && state.arrived && state.rating == null,
        enter = scaleIn(spring(dampingRatio = 0.45f, stiffness = 300f), initialScale = 0.6f) + fadeIn(),
        exit = scaleOut(targetScale = 0.9f) + fadeOut(), modifier = Modifier.align(Alignment.Center).padding(horizontal = 24.dp)) {
        Text("도착했어요", textAlign = TextAlign.Center,
            style = TextStyle(fontFamily = Run.num, fontWeight = FontWeight.ExtraBold, fontSize = 56.sp, lineHeight = 56.sp, color = Color.White),
            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(24.dp)).background(Run.accent).padding(28.dp))
    }

    // 평가
    AnimatedVisibility(state.rating != null, enter = slideInVertically(spring(dampingRatio = 0.8f)) { it } + fadeIn(), exit = slideOutVertically { it } + fadeOut(),
        modifier = Modifier.align(Alignment.BottomCenter)) {
        state.rating?.let { RateCard(it, actions) }
    }
}

@Composable
private fun TurnCard(banner: GuideAction.Banner) {
    val next = banner.next ?: return
    Box(Modifier.fillMaxWidth().floating(RoundedCornerShape(24.dp)).padding(start = 20.dp, end = 20.dp, top = 30.dp, bottom = 16.dp)) {
        Text("달리기", fontSize = 11.sp, fontWeight = FontWeight.SemiBold, color = Run.mute, modifier = Modifier.padding(top = 0.dp).align(Alignment.TopStart).padding(bottom = 0.dp))
        Row(Modifier.padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            TurnArrow(next, Modifier.size(56.dp), stroke = 6f)
            Spacer(Modifier.width(16.dp))
            Column {
                RollingNumber(Guide.distanceText(banner.remainingM),
                    TextStyle(fontFamily = Run.num, fontWeight = FontWeight.ExtraBold, fontSize = 60.sp, lineHeight = 56.sp, color = Run.accent))
                Text(next.instruction, fontSize = 16.sp, fontWeight = FontWeight.Medium, color = Run.ink, maxLines = 1, overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.padding(top = 6.dp))
            }
        }
    }
}

/** 안내 화살표: 줄기는 그대로, 머리만 꺾이는 만큼 돌아간다 (다음 안내로 바뀌면 부드럽게 돈다). 도착은 깃발 */
@Composable
private fun TurnArrow(step: Step, modifier: Modifier, stroke: Float) {
    if (step.turnType == 201) {
        Box(modifier, contentAlignment = Alignment.Center) { Text("🏁", fontSize = 30.sp) }
        return
    }
    val angle by animateFloatAsState(TURN_ANGLE[step.turnType] ?: 0f, spring(dampingRatio = 0.6f, stiffness = 200f), label = "turn")
    Canvas(modifier) {
        scale(size.width / 56f, pivot = Offset.Zero) {
            drawLine(Run.accent, Offset(28f, 52f), Offset(28f, 31f), stroke, StrokeCap.Round)
            rotate(angle, Offset(28f, 31f)) {
                drawLine(Run.accent, Offset(28f, 31f), Offset(28f, 10f), stroke, StrokeCap.Round)
                drawLine(Run.accent, Offset(19f, 19f), Offset(28f, 9f), stroke, StrokeCap.Round)
                drawLine(Run.accent, Offset(28f, 9f), Offset(37f, 19f), stroke, StrokeCap.Round)
            }
        }
    }
}

@Composable
private fun BarButton(symbol: String, onClick: () -> Unit) {
    Box(Modifier.size(44.dp).clip(CircleShape).background(Run.top).clickable(onClick = onClick), contentAlignment = Alignment.Center) {
        Text(symbol, fontSize = 17.sp, color = Run.ink)
    }
}

// ── 달린 뒤 평가 ──

@Composable
private fun RateCard(rating: Rating, actions: MapActions) {
    Column(
        Modifier.windowInsetsPadding(WindowInsets.navigationBars).imePadding().padding(8.dp).fillMaxWidth()
            .heightIn(max = 560.dp).floating(floatShape).verticalScroll(rememberScrollState())
            .padding(horizontal = 22.dp, vertical = 26.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("이 코스 어땠나요?", fontSize = 24.sp, fontWeight = FontWeight.Bold, color = Run.ink, modifier = Modifier.padding(bottom = 8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            (1..5).forEach { n ->
                val on = n <= rating.stars
                val color by animateColorAsState(if (on) Run.coral else Run.line, tween(160, delayMillis = n * 30), label = "star")
                val pop by animateFloatAsState(if (on) 1.15f else 1f, spring(dampingRatio = 0.35f, stiffness = 500f), label = "starPop")
                Text("★", fontSize = 34.sp, color = color, modifier = Modifier.scale(pop).clickable { rating.stars = n }.padding(4.dp))
            }
        }
        AnimatedVisibility(rating.stars > 0) {
            Column(Modifier.padding(top = 12.dp)) {
                Text("더 알려주시면 다음 추천이 정확해져요 (건너뛰어도 됩니다)", fontSize = 13.sp, color = Run.mute, textAlign = TextAlign.Center,
                    modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))
                rating.questions.forEach { q ->
                    Column(Modifier.fillMaxWidth().padding(vertical = 12.dp)) {
                        Text(q.question, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = Run.ink, modifier = Modifier.padding(bottom = 8.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            q.options.forEach { (value, label) ->
                                val on = rating.answers[q.key] == value
                                val bg by animateColorAsState(if (on) Run.accent else Run.top, label = "opt")
                                Text(label, fontSize = 12.sp, lineHeight = 15.sp, fontWeight = FontWeight.Medium, color = if (on) Color.White else Run.ink, textAlign = TextAlign.Center,
                                    modifier = Modifier.weight(1f).heightIn(min = 40.dp).clip(RoundedCornerShape(50)).background(bg)
                                        .clickable { if (on) rating.answers.remove(q.key) else rating.answers[q.key] = value }
                                        .padding(horizontal = 4.dp, vertical = 11.dp))
                            }
                        }
                    }
                }
                Box(Modifier.fillMaxWidth().padding(top = 12.dp).clip(RoundedCornerShape(8.dp)).background(Run.top).padding(horizontal = 14.dp, vertical = 12.dp)) {
                    if (rating.comment.isEmpty()) Text("한마디 남기기 (선택)", fontSize = 14.sp, color = Run.mute)
                    BasicTextField(rating.comment, { if (it.length <= 500) rating.comment = it }, textStyle = TextStyle(fontSize = 14.sp, color = Run.ink),
                        modifier = Modifier.fillMaxWidth())
                }
                Spacer(Modifier.size(12.dp))
                PrimaryButton(if (rating.sending) "보내는 중…" else "평가 보내기", radius = 50.dp, enabled = !rating.sending, onClick = actions.sendRating)
            }
        }
        Text("평가할수록 다음 추천이 내 취향에 맞춰집니다", fontSize = 13.sp, color = Run.mute, modifier = Modifier.padding(top = 8.dp))
        Text("나중에 하기", fontSize = 14.sp, fontWeight = FontWeight.Medium, color = Run.mute,
            modifier = Modifier.padding(top = 6.dp).clickable(onClick = actions.skipRating).padding(8.dp))
    }
}
