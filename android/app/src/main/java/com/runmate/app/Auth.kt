package com.runmate.app

import android.content.Context
import org.json.JSONObject

/** 로그인한 계정. token은 이후 요청의 Authorization: Bearer 로 보낸다 (서버가 30일 동안 받아 준다). */
data class Login(val userId: String, val username: String, val token: String)

object AuthJson {
    fun login(body: JSONObject) = Login(body.getString("user_id"), body.getString("username"), body.getString("token"))
}

fun authHeaders(token: String?): Map<String, String> =
    if (token.isNullOrBlank()) emptyMap() else mapOf("Authorization" to "Bearer $token")

/** 서버에 묻기 전에 걸러 낸다 (서버 auth.py와 같은 규칙). 문제가 없으면 null. */
fun credentialProblem(username: String, password: String): String? = when {
    !Regex("^[A-Za-z0-9_가-힣]{2,20}$").matches(username) -> "아이디는 2~20자의 한글·영문·숫자·밑줄만 쓸 수 있어요."
    password.length < 8 -> "비밀번호는 8자 이상이어야 해요."
    else -> null
}

/** 토큰이 만료됐거나 모르는 토큰일 때만 다시 로그인한다. 서버에 닿지 않는 것은 로그인 문제가 아니다. */
fun needsLoginAgain(error: Throwable): Boolean = error is ServerError && error.status == 401

/**
 * 이 폰에 남기는 것은 로그인 토큰과 계정 이름뿐이다. 취향·평가·즐겨찾기는 모두 서버의 계정에 있다.
 * 처음에 로그인하면 저장해 두고, 다음부터는 이것으로 자동 로그인한다.
 */
class Session(context: Context) {
    private val prefs = context.getSharedPreferences("runmate_session", Context.MODE_PRIVATE)

    val current: Login?
        get() {
            val id = prefs.getString("user_id", null) ?: return null
            val token = prefs.getString("token", null) ?: return null
            return Login(id, prefs.getString("username", null) ?: "", token)
        }

    fun save(login: Login) = prefs.edit()
        .putString("user_id", login.userId).putString("username", login.username).putString("token", login.token).apply()

    fun clear() = prefs.edit().clear().apply()
}
