from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_recommend_with_chosen_scenery():
    payload = {
        "preferred_distance_km": 4,
        "environment_tags": ["바다"],
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


def test_removed_fields_from_older_apps_are_ignored_not_rejected():
    """동반자·목적·숙련도·문장 입력·날씨를 뺐다. 예전 앱이 그 값을 보내도 오류 없이 추천은 나간다."""
    resp = client.post("/recommend", json={"preferred_distance_km": 3, "top_n": 1, "companion": "유아차",
                                           "purpose": "기록 단축", "experience_level": "beginner",
                                           "text": "바다", "use_live_environment": True})
    assert resp.status_code == 200 and resp.json()["results"]
    assert client.get("/onboarding/companions").status_code == 404
    assert client.get("/onboarding/purposes").status_code == 404


def test_time_of_day_is_part_of_the_request_contract():
    ok = client.post("/recommend", json={"time_of_day": "night", "top_n": 1, "use_live_environment": False})
    bad = client.post("/recommend", json={"time_of_day": "midnight", "use_live_environment": False})
    assert ok.status_code == 200
    assert bad.status_code == 422  # 모델에 없는 필드면 조용히 무시돼 422가 나지 않는다


def test_with_a_location_a_live_route_comes_before_saved_courses(monkeypatch):
    """근처에 저장된 코스가 있어도, 현위치가 있으면 그 자리에서 새로 만든 경로를 먼저 준다."""
    from src.api import main

    made = {"id": "generated-live", "name": "지금 만든 코스", "region": "실시간 생성", "distance_km": 4.0,
            "elevation_gain_m": None, "surface": "paved", "safety_score": 0.7, "route_type": "oneway",
            "path": [[34.7393, 127.7359], [34.75, 127.74]], "steps": [], "tags": ["바다뷰"], "source": "live_generated"}
    monkeypatch.setattr(main, "generate_loop_candidates", lambda *a, **k: [dict(made)])
    monkeypatch.setattr(main, "register_in_background", lambda course: None)
    body = client.post("/recommend", json={
        "preferred_distance_km": 4, "environment_tags": ["바다"], "route_type": "oneway", "top_n": 1,
        "current_lat": 34.7393, "current_lng": 127.7359, "max_distance_km": 5,
    }).json()
    assert body["source"] == "generated"
    assert body["results"][0]["course"]["id"] == "generated-live"


def test_without_a_location_saved_courses_are_recommended():
    body = client.post("/recommend", json={"preferred_distance_km": 4, "environment_tags": ["바다"], "top_n": 1}).json()
    assert body["source"] == "db" and body["results"]


def test_scenery_options_list_only_tags_that_have_courses():
    """골라도 결과가 0개인 선택지는 보여주지 않는다."""
    options = client.get("/onboarding/scenery").json()["scenery"]
    assert options, "풍경 선택지가 비어 있다"
    assert all(o["course_count"] >= 1 for o in options)
    assert all(o["hint"] and o["group"] for o in options)
    values = [o["value"] for o in options]
    assert "바다" in values and "강·하천" in values


def test_every_offered_scenery_tag_returns_courses():
    for option in client.get("/onboarding/scenery").json()["scenery"]:
        resp = client.post("/recommend", json={"environment_tags": [option["value"]], "route_type": "oneway",
                                                "use_live_environment": False})
        assert resp.json()["results"], f"{option['value']}을 골랐는데 결과가 없다"


def test_unknown_scenery_tag_is_rejected():
    resp = client.post("/recommend", json={"environment_tags": ["벚꽃길"], "use_live_environment": False})
    assert resp.status_code == 422


def test_nearby_courses_without_the_requested_scenery_fall_through_to_generation(monkeypatch):
    """근처에 저장된 코스가 있어도 요청한 풍경이 없으면 빈 결과(200)가 아니라 그 자리에서 만든다."""
    from src.api import main

    made = {"id": "generated-test", "name": "만든 코스", "region": "실시간 생성", "distance_km": 3.0,
            "elevation_gain_m": 5, "surface": "paved", "safety_score": 0.7, "route_type": "oneway",
            "path": [[34.7393, 127.7359], [34.75, 127.74]], "steps": [], "tags": ["호수"], "source": "live_generated"}
    monkeypatch.setattr(main, "generate_loop_candidates", lambda *a, **k: [dict(made)])
    monkeypatch.setattr(main, "register_in_background", lambda course: None)
    resp = client.post("/recommend", json={
        "preferred_distance_km": 3, "route_type": "oneway", "environment_tags": ["호수"],
        "current_lat": 34.7393, "current_lng": 127.7359, "max_distance_km": 1, "use_live_environment": False,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "generated"
    assert body["results"][0]["course"]["id"] == "generated-test"


def test_results_carry_the_map_data_attribution():
    """OSM 데이터(ODbL)로 만든 결과는 출처를 표시해야 한다. 앱이 그대로 띄울 수 있게 응답에 넣는다."""
    body = client.post("/recommend", json={"preferred_distance_km": 4, "top_n": 1, "use_live_environment": False}).json()
    assert "OpenStreetMap contributors" in body["attribution"]


def test_demo_page_loads_the_tmap_map_only_when_a_key_is_set(monkeypatch):
    """키는 파일에 넣지 않고 페이지를 줄 때 끼운다. 키가 없으면 MapLibre 지도로 그린다."""
    monkeypatch.setenv("TMAP_APP_KEY", "test-key-123")
    page = client.get("/").text
    assert "apis.openapi.sk.com/tmap/vectorjs?version=1&appKey=test-key-123" in page
    monkeypatch.delenv("TMAP_APP_KEY")
    page = client.get("/").text
    assert "vectorjs" not in page and "{{TMAP_MAP_SCRIPT}}" not in page
