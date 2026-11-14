package com.runmate.app

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** 처음에만 보이는 로그인·가입 화면. 성공하면 토큰을 저장하고 지도 화면으로 간다 (다음부터는 바로 지도 화면). */
class LoginActivity : ComponentActivity() {
    private val api by lazy { ServerApi(BuildConfig.SERVER_URL) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { LoginScreen(::submit) }
    }

    private fun submit(username: String, password: String, signUp: Boolean, done: (String?) -> Unit) {
        credentialProblem(username, password)?.let { return done(it) }
        val finished: (Result<Login>) -> Unit = { result ->
            result.onSuccess { login ->
                Session(this).save(login)
                startActivity(Intent(this, MainActivity::class.java))
                finish()
            }.onFailure { done((it as? ServerError)?.detail ?: "서버에 연결하지 못했어요: ${it.message}") }
        }
        if (signUp) api.signUp(username, password, finished) else api.logIn(username, password, finished)
    }
}

@Composable
private fun LoginScreen(submit: (String, String, Boolean, (String?) -> Unit) -> Unit) {
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val go = { signUp: Boolean ->
        busy = true
        error = null
        submit(username.trim(), password, signUp) { problem -> busy = false; error = problem }
    }
    Column(
        Modifier.fillMaxSize().background(Run.bg).windowInsetsPadding(WindowInsets.statusBars)
            .windowInsetsPadding(WindowInsets.navigationBars).imePadding().verticalScroll(rememberScrollState())
            .padding(horizontal = 24.dp, vertical = 24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Spacer(Modifier.height(12.dp))
        LoopMark()
        Text("런메이트", style = Run.question.copy(fontSize = 40.sp, lineHeight = 44.sp), modifier = Modifier.padding(top = 16.dp))
        Text("처음 한 번만 로그인하면 다음부터는 바로 들어가요. 내 취향과 평가는 서버의 내 계정에 저장돼요.",
            style = Run.sub, modifier = Modifier.padding(bottom = 12.dp))
        Field(username, { username = it }, "아이디", "2~20자 한글·영문·숫자")
        Field(password, { password = it }, "비밀번호", "8자 이상", secret = true)
        AnimatedVisibility(error != null, enter = expandVertically() + fadeIn()) {
            Text(error ?: "", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Run.coralInk, lineHeight = 20.sp,
                modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Run.coralSoft).padding(horizontal = 12.dp, vertical = 10.dp))
        }
        Spacer(Modifier.height(8.dp))
        PrimaryButton(if (busy) "확인하는 중…" else "로그인", enabled = !busy) { go(false) }
        Text("처음이에요 · 가입하기", fontSize = 16.sp, fontWeight = FontWeight.SemiBold, color = Run.ink, textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp).clip(RoundedCornerShape(16.dp)).background(Run.top)
                .clickable(enabled = !busy) { go(true) }.padding(vertical = 17.dp))
    }
}

@Composable
private fun Field(value: String, onChange: (String) -> Unit, label: String, hint: String, secret: Boolean = false) {
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(Run.top).padding(horizontal = 18.dp, vertical = 12.dp)) {
        Text(label, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Run.mute)
        Box(Modifier.padding(top = 4.dp)) {
            if (value.isEmpty()) Text(hint, fontSize = 17.sp, color = Run.mute.copy(alpha = 0.6f), maxLines = 1, overflow = TextOverflow.Ellipsis)
            BasicTextField(
                value, onChange, singleLine = true,
                textStyle = TextStyle(fontSize = 17.sp, color = Run.ink, fontWeight = FontWeight.Medium),
                visualTransformation = if (secret) PasswordVisualTransformation() else VisualTransformation.None,
                keyboardOptions = KeyboardOptions(keyboardType = if (secret) KeyboardType.Password else KeyboardType.Text),
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

/** 표지: 한 바퀴 도는 순환 코스 선이 그려지고 출발점 점이 찍힌다 */
@Composable
private fun LoopMark() {
    val p = remember { Animatable(0f) }
    LaunchedEffect(Unit) { p.animateTo(1f, tween(1100, easing = FastOutSlowInEasing)) }
    Canvas(Modifier.size(64.dp)) {
        val stroke = size.width * 0.11f
        drawArc(Run.line, 0f, 360f, false, Offset(stroke, stroke), Size(size.width - stroke * 2, size.height - stroke * 2), style = Stroke(stroke))
        drawArc(Run.accent, -90f, 340f * p.value, false, Offset(stroke, stroke), Size(size.width - stroke * 2, size.height - stroke * 2),
            style = Stroke(stroke, cap = StrokeCap.Round))
        drawCircle(Run.coral, stroke * 0.9f * p.value, Offset(size.width / 2, stroke))
    }
}
