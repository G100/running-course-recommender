package com.runmate.app

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** '내 기록' 화면의 할 일 */
class RecordsActions(
    val close: () -> Unit,
    val run: (Favorite) -> Unit,
    val remove: (Favorite) -> Unit,
    val deleteAll: () -> Unit,
)

/** 내 기록: 평가 숫자, 서버가 정리한 취향, 좋아한 풍경, 즐겨찾기(눌러서 바로 달리기), 내가 한 평가. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun RecordsScreen(state: RunState, actions: RecordsActions) {
    Column(
        Modifier.fillMaxSize().background(Run.bg).windowInsetsPadding(WindowInsets.statusBars)
            .windowInsetsPadding(WindowInsets.navigationBars).verticalScroll(rememberScrollState())
            .padding(Run.screenPadding),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(40.dp).clip(CircleShape).background(Run.top).clickable(onClick = actions.close),
                contentAlignment = Alignment.Center) { Text("←", fontSize = 18.sp, color = Run.ink) }
            Spacer(Modifier.width(12.dp))
            Text("${state.username}님의 기록", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = Run.mute)
        }
        Text("내 기록", style = Run.question, modifier = Modifier.padding(top = 16.dp))

        state.recordsError?.let { Text(it, fontSize = 14.sp, color = Run.coralInk) }
        val taste = state.records
        if (taste == null && state.recordsError == null) Text("불러오는 중…", style = Run.sub)

        if (taste != null) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Number("${taste.feedbackCount}", "평가", Modifier.weight(1f))
                Number(taste.averageRating?.let { "%.1f".format(it) } ?: "—", "평균 ★", Modifier.weight(1f))
                Number("${state.favorites?.size ?: taste.favoriteCount}", "즐겨찾기", Modifier.weight(1f))
            }
            if (taste.summary.isNotEmpty()) {
                Section("내 취향")
                taste.summary.forEachIndexed { i, line ->
                    Appear(i) {
                        Text(line, fontSize = 15.sp, color = Run.ink, lineHeight = 21.sp,
                            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Run.top)
                                .padding(horizontal = 16.dp, vertical = 12.dp))
                    }
                }
            } else if (taste.feedbackCount == 0) {
                Text("코스를 달리고 별점을 남기면 여기에 내 취향이 정리돼요. 평가할수록 다음 추천이 내게 맞춰집니다.", style = Run.sub)
            }
            if (taste.likedScenery.isNotEmpty()) {
                Section("좋게 평가한 코스의 풍경")
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    taste.likedScenery.forEach { (label, count) ->
                        Text("$label · ${count}번", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Run.ink,
                            modifier = Modifier.clip(RoundedCornerShape(50)).background(Run.accentSoft).padding(horizontal = 14.dp, vertical = 8.dp))
                    }
                }
            }
        }

        Section("즐겨찾기")
        val favorites = state.favorites
        when {
            favorites == null -> if (state.recordsError == null) Text("불러오는 중…", style = Run.sub)
            favorites.isEmpty() -> Text("코스 카드의 ☆를 누르면 여기에 모여요. 눌러서 바로 달릴 수 있어요.", style = Run.sub)
            else -> favorites.forEachIndexed { i, fav -> Appear(i) { FavoriteRow(fav, actions) } }
        }

        if (taste != null && taste.history.isNotEmpty()) {
            Section("내가 한 평가")
            taste.history.forEachIndexed { i, run -> Appear(i, stagger = 40) { RunRow(run) } }
        }
        // 내 데이터 모두 지우기 — 되돌릴 수 없어서 확인 창을 거친다
        var asking by remember { mutableStateOf(false) }
        Text("내 데이터 모두 지우기", fontSize = 15.sp, fontWeight = FontWeight.Medium, color = Run.coralInk,
            modifier = Modifier.padding(top = 28.dp).clip(RoundedCornerShape(50)).border(1.dp, Run.coralSoft, RoundedCornerShape(50))
                .clickable { asking = true }.padding(horizontal = 18.dp, vertical = 12.dp))
        if (asking) AlertDialog(
            onDismissRequest = { asking = false },
            title = { Text("내 데이터를 모두 지울까요?") },
            text = { Text("계정과 취향·평가·즐겨찾기를 모두 지웁니다. 되돌릴 수 없어요.") },
            confirmButton = { TextButton(onClick = { asking = false; actions.deleteAll() }) { Text("모두 지우기", color = Run.coralInk) } },
            dismissButton = { TextButton(onClick = { asking = false }) { Text("취소", color = Run.ink) } },
            containerColor = Run.bg, titleContentColor = Run.ink, textContentColor = Run.mute,
        )
        Spacer(Modifier.height(24.dp))
    }
}

@Composable
private fun Section(title: String) {
    Text(title, fontSize = 18.sp, fontWeight = FontWeight.Bold, color = Run.ink, modifier = Modifier.padding(top = 14.dp))
}

@Composable
private fun Number(value: String, label: String, modifier: Modifier) {
    Column(modifier.clip(RoundedCornerShape(18.dp)).background(Run.top).padding(horizontal = 14.dp, vertical = 12.dp)) {
        RollingNumber(value, TextStyle(fontFamily = Run.num, fontWeight = FontWeight.ExtraBold, fontSize = 36.sp, lineHeight = 36.sp, color = Run.ink))
        Text(label, fontSize = 12.sp, fontWeight = FontWeight.Medium, color = Run.mute, maxLines = 1)
    }
}

@Composable
private fun FavoriteRow(fav: Favorite, actions: RecordsActions) {
    val course = fav.course
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(Run.top).clickable { actions.run(fav) }
            .padding(start = 16.dp, end = 8.dp, top = 12.dp, bottom = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(course.name, fontSize = 16.sp, fontWeight = FontWeight.Bold, color = Run.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
            val rating = fav.average?.let { " · ★ ${"%.1f".format(it)} (${fav.ratingCount})" } ?: ""
            Text("${"%.2f".format(course.distanceKm)}km$rating · 눌러서 달리기", fontSize = 13.sp, color = Run.mute)
        }
        Text("빼기", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = Run.mute,
            modifier = Modifier.clip(RoundedCornerShape(50)).clickable { actions.remove(fav) }.padding(horizontal = 10.dp, vertical = 8.dp))
    }
}

@Composable
private fun RunRow(run: RatedRun) {
    Column(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("★".repeat(run.rating.coerceIn(0, 5)) + "☆".repeat((5 - run.rating).coerceIn(0, 5)),
                fontSize = 15.sp, color = Run.coral)
            Spacer(Modifier.width(8.dp))
            Text(run.courseName, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = Run.ink, maxLines = 1,
                overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
            Text(day(run.atSec), fontSize = 12.sp, color = Run.mute)
        }
        val details = (run.answers + listOfNotNull(run.comment?.let { "“$it”" })).joinToString(" · ")
        if (details.isNotEmpty()) Text(details, fontSize = 13.sp, color = Run.mute, lineHeight = 18.sp, modifier = Modifier.padding(top = 2.dp))
        Box(Modifier.fillMaxWidth().padding(top = 10.dp).height(1.dp).background(Run.line))
    }
}

private fun day(sec: Long): String =
    if (sec <= 0) "" else SimpleDateFormat("M월 d일", Locale.KOREAN).format(Date(sec * 1000))

