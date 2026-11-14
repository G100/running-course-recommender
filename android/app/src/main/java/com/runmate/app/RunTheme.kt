package com.runmate.app

import android.graphics.Typeface
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * 웹 데모(src/api/static/navigate.html)의 폰 화면과 같은 색·글씨.
 * 흰 바탕 + 일렉트릭 블루(주색) + 코랄(고른 것·강조), 글씨는 남색.
 */
object Run {
    val bg = Color(0xFFFFFFFF)
    val top = Color(0xFFF2F5FF)        // 옅은 파랑 판 (버튼 바탕)
    val line = Color(0xFFDCE3F5)       // 다이얼 트랙·눈금·구분선
    val ink = Color(0xFF10142A)
    val mute = Color(0xFF5B6478)
    val accent = Color(0xFF2F6BFF)
    val accentSoft = Color(0x1A2F6BFF)
    val coral = Color(0xFFFF6B4A)
    val coralInk = Color(0xFFB83A1F)
    val coralSoft = Color(0x1FFF6B4A)
    val shadow = Color(0x2410142A)

    /** 큰 숫자: 웹은 Big Shoulders Display. 폰에는 같은 결의 좁고 굵은 글꼴(sans-serif-condensed)을 쓴다 */
    val num = FontFamily(Typeface.create("sans-serif-condensed", Typeface.BOLD))

    val question = TextStyle(fontSize = 34.sp, fontWeight = FontWeight.ExtraBold, lineHeight = 39.sp, letterSpacing = (-0.8).sp, color = ink)
    val sub = TextStyle(fontSize = 14.sp, color = mute, lineHeight = 20.sp)
    val button = TextStyle(fontSize = 18.sp, fontWeight = FontWeight.Bold)

    val screenPadding = PaddingValues(start = 24.dp, end = 24.dp, top = 20.dp, bottom = 24.dp)
}
