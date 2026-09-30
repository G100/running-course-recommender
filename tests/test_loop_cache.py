"""같은 자리에서 같은 거리를 다시 요청하면 루프를 새로 만들지 않는다.

실시간 루프 생성은 요청 1건에 Tmap 3건 + 13초가 든다. Tmap 무료 한도가 하루 1,000건이라
매번 새로 만들면 하루 333회로 팀 전체가 막힌다. 한 번 만든 루프는 DB에 쌓이므로,
그 자리에 맞는 게 이미 있으면 그걸 쓰고 없을 때만 만든다.
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


def test_existing_loop_at_the_same_spot_is_reused(monkeypatch):
    response, calls = _run(monkeypatch, [_loop("cached", 34.0, 127.0, 5.1)])
    assert not calls, "맞는 루프가 이미 있는데 Tmap을 다시 불렀다"
    assert response["results"][0]["course"]["id"] == "cached"


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
