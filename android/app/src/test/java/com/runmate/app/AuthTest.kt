package com.runmate.app

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** 처음에만 로그인하고, 다음부터는 저장한 토큰으로 자동 로그인한다. 취향·평가는 서버의 계정에 쌓인다. */
class AuthTest {
    @Test fun a_login_answer_gives_the_account_and_its_token() {
        val login = AuthJson.login(JSONObject("""{"user_id": "u_1a2b", "username": "러너", "token": "t0k"}"""))
        assertEquals(Login("u_1a2b", "러너", "t0k"), login)
    }

    @Test fun requests_carry_the_token_only_when_logged_in() {
        assertEquals(mapOf("Authorization" to "Bearer t0k"), authHeaders("t0k"))
        assertTrue(authHeaders(null).isEmpty())
        assertTrue(authHeaders("").isEmpty())
    }

    @Test fun ids_and_passwords_are_checked_before_asking_the_server() {
        // 서버(auth.py)와 같은 규칙: 아이디 2~20자 한글·영문·숫자·밑줄, 비밀번호 8자 이상
        assertNull(credentialProblem("러너_01", "password1"))
        assertEquals("아이디는 2~20자의 한글·영문·숫자·밑줄만 쓸 수 있어요.", credentialProblem("a", "password1"))
        assertEquals("아이디는 2~20자의 한글·영문·숫자·밑줄만 쓸 수 있어요.", credentialProblem("run mate", "password1"))
        assertEquals("비밀번호는 8자 이상이어야 해요.", credentialProblem("runner", "short"))
    }

    @Test fun only_an_expired_or_unknown_token_sends_the_runner_back_to_login() {
        assertTrue(needsLoginAgain(ServerError(401, "로그인이 필요합니다.")))
        assertFalse("서버에 닿지 않을 때는 저장한 토큰으로 그냥 들어간다", needsLoginAgain(java.io.IOException("timeout")))
        assertFalse(needsLoginAgain(ServerError(500, "오류")))
    }
}
