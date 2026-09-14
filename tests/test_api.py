from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_recommend_with_free_text():
    payload = {
        "preferred_distance_km": 4,
        "elevation_preference": "low",
        "text": "바다가 보이는 코스 추천해줘",
        "top_n": 1,
        "use_live_environment": False,
    }
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    results = body["results"]
    assert body["source"] == "db"
    assert len(results) == 1
    # 실제 코스 DB는 라이브 데이터로 계속 갱신되므로 특정 id 대신 태그로 검증
    assert "바다뷰" in results[0]["course"]["tags"]


def test_recommend_with_nearby_location_uses_db():
    payload = {
        "preferred_distance_km": 4,
        "text": "바다가 보이는 코스",
        "top_n": 1,
        "use_live_environment": False,
        "current_lat": 34.7393,
        "current_lng": 127.7359,
        "max_distance_km": 5,
    }
    resp = client.post("/recommend", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "db"
    assert len(body["results"]) == 1
