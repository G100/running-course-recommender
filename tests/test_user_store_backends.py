"""사용자 DB는 개발·테스트에서는 SQLite 파일, 운영에서는 PostgreSQL(DATABASE_URL)에 둔다 — 같은 코드로.

앱을 쓰는 사람들의 계정·취향·평가는 서버를 다시 올려도 남아야 한다. 그래서 운영 DB는 서버 밖의 관리형
PostgreSQL이다. 두 DB에서 다 도는 SQL만 쓰므로(INSERT … ON CONFLICT 등), 아래 시험은 SQLite에서 돌고,
TEST_DATABASE_URL을 주면 같은 시험을 PostgreSQL에서도 돌린다.
"""
import os
import uuid

import pytest

from src.recommend import user_store


def run_everything(prefix: str):
    """계정·로그인·취향·평가·즐겨찾기·손님 데이터 옮기기·지우기를 한 번씩."""
    guest, account = f"{prefix}-guest", f"{prefix}-acct"
    name = f"Runner_{prefix}"
    assert user_store.add_account(account, name, "salt", "hash")
    assert not user_store.add_account(f"{prefix}-other", name.lower(), "s", "h"), "아이디는 대소문자를 가리지 않고 하나만"
    assert user_store.account_by_username(name.upper())["user_id"] == account, "대소문자를 바꿔 써도 로그인된다"
    assert user_store.is_account(account) and not user_store.is_account(guest)

    user_store.add_session("tok", account, 4_000_000_000)
    assert user_store.session_user("tok", 1.0) == account
    assert user_store.remove_session("tok") and user_store.session_user("tok", 1.0) is None

    user_store.put_profile({"user_id": guest, "weights": {"flow": 0.3}})
    user_store.put_profile({"user_id": guest, "weights": {"flow": 0.4}})   # 고쳐 쓴다
    assert user_store.get_profile(guest)["weights"] == {"flow": 0.4}

    user_store.save_review(account, "c1", 2, "계정으로 남긴 후기")
    user_store.save_review(guest, "c1", 5, "손님으로 남긴 후기")
    user_store.save_review(guest, "c2", 4)
    user_store.add_favorite(guest, {"id": "c1", "name": "강변"})
    user_store.add_favorite(guest, {"id": "c1", "name": "강변 (고침)"})   # 고쳐 쓴다
    user_store.log_feedback(guest, "c1", 5, measures={"km": 5.0})
    assert user_store.ratings(["c1", "c2"])["c1"] == {"average": 3.5, "count": 2}
    assert user_store.reviews_for("c2")["average"] == 4.0

    user_store.move_user_data(guest, account)   # 가입하면 손님 데이터가 계정으로
    assert user_store.get_profile(account)["weights"] == {"flow": 0.4} and user_store.get_profile(guest) is None
    mine = {r["user_id"]: r["rating"] for r in user_store.reviews_for("c1")["reviews"]}
    assert mine == {account: 5}, "같은 코스에 둘 다 있으면 손님 때 것이 이긴다"
    assert [f["course"]["name"] for f in user_store.favorites(account)] == ["강변 (고침)"]
    assert user_store.favorite_ids(account) == {"c1"}
    assert [h["rating"] for h in user_store.feedback_history(account)] == [5]
    assert user_store.usernames([account]) == {account: name}

    removed = user_store.delete_user(account)
    assert removed["accounts"] == 1 and removed["reviews"] == 2 and user_store.get_profile(account) is None


def test_everything_works_on_the_sqlite_file(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    run_everything("lite")


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL(PostgreSQL)이 없다")
def test_everything_works_on_postgres(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    prefix = "pg-" + uuid.uuid4().hex[:8]   # 다른 시험과 겹치지 않는 이름
    try:
        run_everything(prefix)
    finally:   # 중간에 실패해도 실제 DB에 시험 기록을 남기지 않는다
        for user_id in (f"{prefix}-guest", f"{prefix}-acct", f"{prefix}-other"):
            user_store.delete_user(user_id)


def test_without_a_database_url_the_sqlite_file_is_used(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    user_store.put_profile({"user_id": "where", "weights": {}})
    assert os.path.exists(user_store.DB_PATH)


def test_postgres_gets_its_own_placeholders():
    """PostgreSQL 드라이버는 ? 대신 %s 를 쓴다 — 같은 SQL을 넘겨도 바꿔서 보낸다."""
    sent = []

    class Cursor:
        def execute(self, sql, params):
            sent.append((sql, params))

    class Conn:
        def cursor(self):
            return Cursor()

    user_store._Postgres(Conn()).execute("SELECT body FROM profiles WHERE user_id = ? AND x IN (?,?)", ["a", 1, 2])
    assert sent == [("SELECT body FROM profiles WHERE user_id = %s AND x IN (%s,%s)", ("a", 1, 2))]


def test_no_sqlite_only_sql_is_left():
    """INSERT OR REPLACE · UPDATE OR REPLACE는 PostgreSQL에 없다."""
    code = open(user_store.__file__, encoding="utf-8").read()
    statements = [line for line in code.splitlines() if not line.strip().startswith("#")]
    assert not any("OR REPLACE" in line and ('"' in line or "'" in line) for line in statements)
