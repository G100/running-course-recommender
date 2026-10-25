"""추천 결과는 실제로 달릴 Tmap 경로이고, 그 거리가 요청과 5% 안이어야 한다.

우리 설계가 맞아도 Tmap으로 이으면 평균 13% 늘었다(36개 중 5% 안은 12개). 설계 거리만 맞추면
사용자가 실제로 달리는 거리는 틀린다 — 그래서 이은 뒤의 거리로 맞춘다.
"""
import pytest

from src.api import main
from src.data_collection.enrich import haversine_m

TARGET = 5.0


def _straight(km, lat=34.0):
    """북쪽으로 km만큼 가는 경로 (점 여러 개)."""
    n = 20
    return [[lat + km / 111.32 * i / n, 127.0] for i in range(n + 1)]


def _plan(km, route_type="loop"):
    return {"id": f"plan-{km:.3f}", "name": "만든 코스", "distance_km": round(km, 3), "path": _straight(km),
            "route_type": route_type, "steps": [], "tags": []}


def _tmap_follow(stretch):
    """Tmap으로 이으면 우리 설계보다 stretch배 길어진다."""
    calls = []

    def follow(path, target_km=None):
        calls.append(target_km)
        km = haversine_m(path[0], path[-1]) / 1000 * stretch
        tmap_path = _straight(km)
        return {"features": [
            {"geometry": {"type": "Point", "coordinates": [127.0, 34.0]}, "properties": {"totalDistance": km * 1000}},
            {"geometry": {"type": "LineString", "coordinates": [[b, a] for a, b in tmap_path]}, "properties": {"roadType": 21}},
            {"geometry": {"type": "Point", "coordinates": [127.0, tmap_path[-1][0]]}, "properties": {"description": "도착", "turnType": 201}},
        ], "follow": {"ok": True, "distance_km": round(km, 2), "plan_covered": 0.95, "follows_plan": 0.95, "calls": 1}}
    return follow, calls


def test_loop_that_grows_on_tmap_is_resized_until_the_real_route_fits(monkeypatch):
    follow, calls = _tmap_follow(stretch=1.2)
    monkeypatch.setattr(main, "_follow_with_tmap", follow)
    asked = []
    regenerate = lambda km: asked.append(km) or _plan(km)

    course = main._deliver_on_tmap(_plan(TARGET), TARGET, "loop", regenerate)

    assert abs(course["distance_km"] - TARGET) / TARGET <= 0.05, course["distance_km"]
    assert asked and asked[0] == pytest.approx(TARGET / 1.2, rel=0.02), "Tmap이 늘린 만큼 줄여서 다시 짜야 한다"
    assert len(calls) <= main.MAX_TMAP_ROUNDS
    assert course["tmap"]["ok"] and course["plan_path"] != course["path"]


def test_one_way_that_is_too_long_on_tmap_is_cut_at_the_asked_distance(monkeypatch):
    follow, calls = _tmap_follow(stretch=1.3)
    monkeypatch.setattr(main, "_follow_with_tmap", follow)
    course = main._deliver_on_tmap(_plan(TARGET, "oneway"), TARGET, "oneway", lambda km: pytest.fail("다시 짤 필요 없다"))
    assert abs(course["distance_km"] - TARGET) / TARGET <= 0.05, course["distance_km"]
    assert len(calls) == 1


def test_route_already_within_the_limit_is_asked_once(monkeypatch):
    follow, calls = _tmap_follow(stretch=1.03)
    monkeypatch.setattr(main, "_follow_with_tmap", follow)
    course = main._deliver_on_tmap(_plan(TARGET), TARGET, "loop", lambda km: pytest.fail("이미 맞는다"))
    assert len(calls) == 1 and course["distance_km"] == pytest.approx(5.15, abs=0.02)


def test_when_tmap_cannot_be_reached_the_plan_is_given_as_is(monkeypatch):
    def down(path, target_km=None):
        raise RuntimeError("TMAP_APP_KEY 환경변수가 설정되지 않았습니다.")

    monkeypatch.setattr(main, "_follow_with_tmap", down)
    plan = _plan(TARGET)
    assert main._deliver_on_tmap(plan, TARGET, "loop", lambda km: None) is plan
