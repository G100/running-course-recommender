"""현위치가 있으면 저장된 코스보다 그 자리에서 새로 만든 경로가 먼저다.

저장된 코스는 예전 규칙으로 만든 것일 수 있다(인도 확인·거리 맞추기·풍경 기준이 계속 바뀌었다).
지금 규칙으로 바로 만든 경로를 먼저 주고, 만들 수 없을 때(장애·키 없음)만 저장된 코스로 답한다.
"""
from fastapi import BackgroundTasks

from src.api import main


def _loop(cid, lat, lng, distance_km):
    return {
        "id": cid, "name": cid, "source": "live_generated", "route_type": "loop",
        "path": [[lat, lng], [lat + 0.004, lng + 0.004], [lat, lng]],
        "distance_km": distance_km, "elevation_gain_m": 20, "safety_score": 0.7,
        "traffic_signal_count": 0, "tags": [],
    }


def _request(**kwargs):
    return main.RecommendRequest(
        current_lat=34.0, current_lng=127.0, route_type="loop",
        preferred_distance_km=5.0, use_live_environment=False, **kwargs
    )


def _run(monkeypatch, stored):
    calls = []
    monkeypatch.setattr(main, "load_courses", lambda: stored)
    monkeypatch.setattr(main, "filter_nearby", lambda courses, lat, lng, radius: courses)
    monkeypatch.setattr(main, "generate_loop_candidates",
                        lambda *a, **k: calls.append(a) or [_loop("fresh", 34.0, 127.0, 5.0)])
    response = main.post_recommend(_request(), BackgroundTasks())
    return response, calls


def test_live_route_comes_first_even_when_a_saved_loop_fits(monkeypatch):
    response, calls = _run(monkeypatch, [_loop("cached", 34.0, 127.0, 5.1)])
    assert calls, "저장된 루프를 주고 새로 만들지 않았다"
    assert response["results"][0]["course"]["id"] == "fresh"
    assert response["source"] == "generated"


def test_saved_loop_is_the_fallback_when_making_one_fails(monkeypatch):
    def fail(*a, **k):
        raise ValueError("Tmap 보행자 순환 경로를 찾지 못했습니다.")

    monkeypatch.setattr(main, "load_courses", lambda: [_loop("cached", 34.0, 127.0, 5.1)])
    monkeypatch.setattr(main, "filter_nearby", lambda courses, lat, lng, radius: courses)
    monkeypatch.setattr(main, "generate_loop_candidates", fail)
    response = main.post_recommend(_request(), BackgroundTasks())
    assert response["results"][0]["course"]["id"] == "cached"
    assert response["source"] == "db"


def test_loop_of_a_different_length_is_not_reused(monkeypatch):
    response, calls = _run(monkeypatch, [_loop("too-short", 34.0, 127.0, 2.0)])
    assert calls, "목표 거리와 동떨어진 루프를 재사용했다"
    assert response["results"][0]["course"]["id"] == "fresh"


def test_loop_starting_far_away_is_not_reused(monkeypatch):
    """출발점이 멀면 재사용해도 사용자는 거기까지 걸어가야 한다."""
    response, calls = _run(monkeypatch, [_loop("far", 34.05, 127.05, 5.0)])
    assert calls
    assert response["results"][0]["course"]["id"] == "fresh"


def test_open_db_course_does_not_count_as_a_loop(monkeypatch):
    open_course = {
        "id": "open", "name": "편도", "path": [[34.0, 127.0], [34.02, 127.02]],
        "distance_km": 5.0, "elevation_gain_m": 10, "tags": [],
    }
    _, calls = _run(monkeypatch, [open_course])
    assert calls


def test_cached_loop_without_the_requested_scenery_is_not_reused(monkeypatch):
    """저장된 순환이 요청한 풍경이 아니면 재사용하지 않는다 — 재사용하면 필터에 걸려 결과가 0개가 된다."""
    park_loop = dict(_loop("cached-park", 34.0, 127.0, 5.0), tags=["공원"])
    river_loop = dict(_loop("fresh-river", 34.0, 127.0, 5.0), tags=["강변"])
    calls = []
    monkeypatch.setattr(main, "load_courses", lambda: [park_loop])
    monkeypatch.setattr(main, "filter_nearby", lambda courses, lat, lng, radius: courses)
    monkeypatch.setattr(main, "generate_loop_candidates", lambda *a, **k: calls.append(a) or [river_loop])

    response = main.post_recommend(_request(environment_tags=["강변"]), BackgroundTasks())

    assert calls, "풍경이 안 맞는 순환을 재사용했다"
    assert [r["course"]["id"] for r in response["results"]] == ["fresh-river"]


def _generated(monkeypatch, generate):
    monkeypatch.setattr(main, "load_courses", lambda: [])
    monkeypatch.setattr(main, "filter_nearby", lambda courses, lat, lng, radius: courses)
    monkeypatch.setattr(main, "generate_loop_candidates", generate)


def test_at_night_the_runner_is_asked_before_a_secluded_scenic_path(monkeypatch):
    """밤에 강변을 골랐는데 강변이 인적 드문 길이면, 정하지 않고 사용자에게 묻는다 (위험할 수 있으니)."""
    safe = dict(_loop("safe", 34.0, 127.0, 5.0), tags=["공원"], scenery={"river": 0.1})
    scenic = dict(_loop("riverside", 34.0, 127.0, 5.0), tags=["강변"], scenery={"river": 0.5})
    nights = []

    def generate(lat, lng, km, tags, route_type=None, night=False):
        nights.append(night)
        return [safe] if night else [scenic]

    _generated(monkeypatch, generate)
    first = main.post_recommend(_request(environment_tags=["강변"], time_of_day="night"), BackgroundTasks())
    assert first["results"][0]["course"]["id"] == "safe"
    assert "위험" in first["choice"]["question"]
    go = next(o for o in first["choice"]["options"] if o["set"])

    second = main.post_recommend(_request(environment_tags=["강변"], time_of_day="night", **go["set"]), BackgroundTasks())
    assert second["results"][0]["course"]["id"] == "riverside" and nights[-1] is False
    assert second.get("choice") is None


def test_when_the_scenery_is_out_of_reach_the_runner_chooses_a_longer_run(monkeypatch):
    """요청 거리로는 호수까지 인도로 갈 수 없으면(수원 광교 3km) 풍경 없는 코스를 주고, 늘릴지 묻는다."""
    plain = dict(_loop("plain", 34.0, 127.0, 5.0), tags=["공원"])

    def generate(lat, lng, km, tags, route_type=None, night=False):
        if tags and km < 8:
            raise ValueError("차도를 피해 가는 코스를 만들지 못했습니다.")
        if tags:
            return [dict(_loop("lake", 34.0, 127.0, km), tags=["호수"], scenery={"lake": 0.5})]
        return [plain]

    _generated(monkeypatch, generate)
    first = main.post_recommend(_request(environment_tags=["호수"], time_of_day="morning"), BackgroundTasks())
    assert first["results"][0]["course"]["id"] == "plain"
    assert "호수" in first["notice"]
    longer = next(o for o in first["choice"]["options"] if o["set"])

    second = main.post_recommend(_request(environment_tags=["호수"], time_of_day="morning", **longer["set"]),
                                 BackgroundTasks())
    course = second["results"][0]["course"]
    assert course["id"] == "lake" and course["distance_km"] >= 8
    assert "길" in second["notice"] and second.get("choice") is None
