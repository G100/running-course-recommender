"""평가할 때 그 코스의 측정값을 같이 남긴다 — 나중에 '어떤 길일 때 별점이 높았나'로 점수식을 새로 찾으려면 필요하다.

예전 기록(feedback_log)에는 별점·답·그때의 배점만 남았다. 추천할 때 기억해 둔 항목별 점수는 배점을 고치는 데
쓰고 버려져서, 평가가 쌓여도 새 식을 찾을 재료가 없었다. 위치나 경로는 남기지 않고 숫자만 남긴다.
"""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from src.api import main
from src.recommend import score, user_store

client = TestClient(main.app)

QUIET = {"id": "quiet", "name": "한적한 길", "region": "여수", "path": [[34.0, 127.0], [34.03, 127.0]],
         "distance_km": 5.2, "elevation_gain_m": 150, "tags": [], "traffic_signal_count": 2,
         "turns_per_km": 1.8, "junctions_per_km": 3.1, "route_type": "oneway",
         "road_mix": {"sidewalk": 0.7, "car_free": 0.3}, "scenery": {"river": 0.41, "park": 0.05, "coast": 0.0}}
BUSY = {**QUIET, "id": "busy", "name": "번화한 길", "traffic_signal_count": 9, "road_mix": {"sidewalk": 0.0, "car_free": 1.0}}


@pytest.fixture
def two_courses(monkeypatch):
    monkeypatch.setattr(main, "load_courses", lambda: [QUIET, BUSY])


def _recommend(user_id):
    return client.post("/recommend", json={"user_id": user_id, "preferred_distance_km": 5, "route_type": "oneway", "top_n": 2,
                                           "use_live_environment": False, "time_of_day": "morning"})


def _logged():
    with sqlite3.connect(user_store.DB_PATH) as db:
        return [json.loads(row[0]) if row[0] else None for row in db.execute("SELECT measures FROM feedback_log ORDER BY id")]


def test_measured_values_of_a_course_are_numbers_only():
    m = score.measures(QUIET, {"preferred_distance_km": 5, "environment_tags": ["강변"]})
    assert m["asked_km"] == 5 and m["km"] == 5.2 and m["route_type"] == "oneway" and m["laps"] == 1
    assert m["signals_per_km"] == pytest.approx(2 / 5.2, abs=0.01)
    assert m["turns_per_km"] == pytest.approx(1.8) and m["junctions_per_km"] == pytest.approx(3.1)
    assert m["road_mix"] == {"sidewalk": 0.7, "car_free": 0.3}
    assert m["scenery"]["river"] == pytest.approx(0.41) and m["chosen_scenery"] == ["강변"]
    assert "path" not in json.dumps(m) and "34.0" not in json.dumps(m), "위치는 남기지 않는다"


def test_rating_after_a_recommendation_keeps_what_the_course_measured(two_courses):
    shown = {r["course"]["id"]: r for r in _recommend("runner-m").json()["results"]}
    assert client.post("/feedback", json={"user_id": "runner-m", "course_id": "quiet", "rating": 4}).status_code == 200
    kept, = _logged()
    assert set(kept) == {"scores", "baseline", "measures"}
    assert kept["scores"] == pytest.approx(shown["quiet"]["score_breakdown"], abs=1e-3), "추천할 때 보여 준 항목별 점수"
    assert kept["baseline"] is not None, "같이 보여 준 다른 후보와 비교한 기준도 남는다"
    course = shown["quiet"]["course"]   # 요청 거리(5km)로 잘라서 추천된 코스 — 그 코스의 값이 남아야 한다
    assert kept["measures"]["km"] == course["distance_km"]
    assert kept["measures"]["signals_per_km"] == pytest.approx(score.flow_parts(course)["stops"]["per_km"])
    assert kept["measures"]["road_mix"]["car_free"] == pytest.approx(0.3)


def test_review_without_a_recommendation_keeps_no_measures(two_courses):
    client.post("/favorites", json={"user_id": "runner-r", "course_id": "quiet"})
    client.post("/reviews", json={"user_id": "runner-r", "course_id": "quiet", "rating": 5})
    assert _logged() == [None]


def test_an_older_log_file_gets_the_new_column(tmp_path, monkeypatch):
    old = tmp_path / "old.sqlite"
    with sqlite3.connect(old) as db:
        db.execute("CREATE TABLE feedback_log (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, course_id TEXT NOT NULL, "
                   "course_name TEXT, labels TEXT, rating INTEGER NOT NULL, aspects TEXT, comment TEXT, weights TEXT, created_at REAL NOT NULL)")
        db.execute("INSERT INTO feedback_log (user_id, course_id, rating, created_at) VALUES ('a', 'c', 3, 0)")
    monkeypatch.setattr(user_store, "DB_PATH", str(old))
    user_store.log_feedback("a", "c", 4, measures={"scores": {"flow": 0.5}})
    assert [row["rating"] for row in user_store.feedback_history("a")] == [4, 3]
    assert _logged() == [None, {"scores": {"flow": 0.5}}]
