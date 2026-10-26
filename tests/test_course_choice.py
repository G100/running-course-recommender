"""러너가 코스를 고른다: 후보를 여러 개 보여주고, 고른 코스만 실제로 달릴 Tmap 경로로 맞춘다.

후보를 전부 미리 Tmap으로 이으면 호출이 3배가 된다. 그래서 1등만 미리 잇고, 다른 후보는 고를 때 잇는다.
고른 코스의 크기를 고칠 때는 같은 방향·모양으로 다시 짠다 — 다른 코스로 바뀌면 안 된다.
"""
import pytest
from fastapi.testclient import TestClient

from src.api import main
from src.recommend import generate_live
from tests.test_delivery import _plan, _straight, _tmap_follow

client = TestClient(main.app)
TARGET = 5.0


def _north(km, lat=34.0, lng=127.0):
    return [[lat + km / 111.32 * i / 20, lng] for i in range(21)]


def _east(km, lat=34.0, lng=127.0):
    return [[lat, lng + km / 92.4 * i / 20] for i in range(21)]


# ── 편도·왕복도 후보를 여러 방향으로 만든다 ──
def test_one_way_candidates_head_in_different_directions(monkeypatch):
    calls = []

    def make(lat, lng, km, tags, **kwargs):
        calls.append(kwargs["angle_offset_deg"])
        path = {0.0: _north(km), 120.0: _east(km), 240.0: _north(-km)}[kwargs["angle_offset_deg"]]
        return {"id": f"c{kwargs['angle_offset_deg']}", "distance_km": km, "path": path, "route_type": "oneway"}

    monkeypatch.setattr(generate_live, "generate_loop_course", make)
    monkeypatch.setattr(generate_live.area_cache, "load_area", lambda *a, **k: None)
    courses = generate_live.generate_loop_candidates(34.0, 127.0, TARGET, set(), route_type="oneway")

    assert sorted(calls) == [0.0, 120.0, 240.0]
    assert len(courses) == 3
    assert courses[0]["id"] == "c0.0", "예전 첫 후보(정면)가 그대로 1순위 후보다"


def test_one_way_candidates_that_end_up_on_the_same_road_are_shown_once(monkeypatch):
    def make(lat, lng, km, tags, **kwargs):
        return {"id": f"c{kwargs['angle_offset_deg']}", "distance_km": km, "path": _north(km), "route_type": "oneway"}

    monkeypatch.setattr(generate_live, "generate_loop_course", make)
    monkeypatch.setattr(generate_live.area_cache, "load_area", lambda *a, **k: None)
    courses = generate_live.generate_loop_candidates(34.0, 127.0, TARGET, set(), route_type="oneway")
    assert len(courses) == 1


def test_candidates_remember_how_they_were_made(monkeypatch):
    """고른 뒤 크기를 고쳐 다시 짤 때, 같은 자리·방향·모양·풍경으로 짜려면 그 값을 알아야 한다."""
    monkeypatch.setattr(generate_live, "generate_loop_course",
                        lambda lat, lng, km, tags, **k: {"id": f"c{k['angle_offset_deg']}", "distance_km": km,
                                                          "path": _north(km) if k["angle_offset_deg"] == 0 else _east(km)})
    courses = generate_live.generate_loop_candidates(34.0, 127.0, TARGET, {"강변"}, route_type="loop", night=True)
    shape = courses[0]["shape"]
    assert shape == {"lat": 34.0, "lng": 127.0, "route_type": "loop", "angle": 0.0,
                     "radius_scale": generate_live.LOOP_RADIUS_SCALES[0], "tags": ["강변"], "night": True}


def test_one_way_candidates_in_other_directions_get_their_own_id(monkeypatch):
    """같은 id면 저장할 때 서로 덮어쓰고, 즐겨찾기·평가가 엉뚱한 코스에 붙는다."""
    monkeypatch.setattr(generate_live, "_fit_one_way_end", lambda *a, **k: (34.03, 127.0))
    monkeypatch.setattr(generate_live, "_route", lambda *a, **k: None)
    ids = set()
    for offset in (0.0, 120.0):
        monkeypatch.setattr(generate_live, "_route", lambda area, start, end, waypoints=None, night=False: {
            "features": [{"geometry": {"type": "LineString", "coordinates": [[127.0, 34.0], [127.0, 34.03]]},
                          "properties": {"roadType": 21}}]})
        course = generate_live.generate_loop_course(34.0, 127.0, 3.0, set(), route_type="oneway", angle_offset_deg=offset)
        ids.add(course["id"])
    assert len(ids) == 2


# ── 고른 코스를 실제로 달릴 경로로 맞춘다 ──
def _shaped(km, angle=20.0, scale=0.9):
    return dict(_plan(km), shape={"lat": 34.0, "lng": 127.0, "route_type": "loop", "angle": angle,
                                  "radius_scale": scale, "tags": ["강변"], "night": False})


def test_chosen_course_is_resized_in_the_same_shape(monkeypatch):
    follow, calls = _tmap_follow(stretch=1.2)
    monkeypatch.setattr(main, "_follow_with_tmap", follow)
    remade = []

    def regenerate(lat, lng, km, tags, **kwargs):
        remade.append((km, tags, kwargs["angle_offset_deg"], kwargs["radius_scale"]))
        return _plan(km)

    monkeypatch.setattr(main, "generate_loop_course", regenerate)
    monkeypatch.setattr(main.area_cache, "load_area", lambda *a, **k: None)

    resp = client.post("/courses/deliver", json={"course": _shaped(TARGET), "target_km": TARGET, "route_type": "loop"})
    assert resp.status_code == 200, resp.text
    course = resp.json()["course"]
    assert abs(course["distance_km"] - TARGET) / TARGET <= 0.05
    assert remade and remade[0][1:] == ({"강변"}, 20.0, 0.9), "고른 코스와 같은 방향·모양·풍경으로 다시 짜야 한다"
    assert course["tmap"]["ok"] and course["id"] == _shaped(TARGET)["id"], "고른 코스로 남아야 평가·즐겨찾기가 맞는다"


def test_course_without_shape_is_joined_once_and_cut_if_one_way(monkeypatch):
    """저장된 코스는 다시 짤 방법이 없다. 이어 보고, 편도면 요청 거리에서 끝낸다."""
    follow, calls = _tmap_follow(stretch=1.3)
    monkeypatch.setattr(main, "_follow_with_tmap", follow)
    resp = client.post("/courses/deliver", json={"course": _plan(TARGET, "oneway"), "target_km": TARGET,
                                                 "route_type": "oneway"})
    course = resp.json()["course"]
    assert len(calls) == 1
    assert abs(course["distance_km"] - TARGET) / TARGET <= 0.05


def test_recommend_gives_several_courses_and_joins_only_the_first(monkeypatch):
    plans = [dict(_plan(TARGET), id=f"loop-{i}", path=p) for i, p in enumerate([_north(TARGET), _east(TARGET)])]
    monkeypatch.setattr(main, "generate_loop_candidates", lambda *a, **k: [dict(p) for p in plans])
    monkeypatch.setattr(main, "register_in_background", lambda course: None)
    follow, calls = _tmap_follow(stretch=1.02)
    monkeypatch.setattr(main, "_follow_with_tmap", follow)

    body = client.post("/recommend", json={"preferred_distance_km": TARGET, "route_type": "loop", "top_n": 3,
                                           "current_lat": 34.0, "current_lng": 127.0}).json()
    results = body["results"]
    assert len(results) == 2
    assert "tmap" in results[0]["course"] and "tmap" not in results[1]["course"]
    assert len(calls) == 1
    assert body["deliver_km"] == TARGET, "다른 후보를 고를 때 맞출 거리를 알려줘야 한다"


def test_first_course_is_resized_in_its_own_shape_not_swapped_for_another(monkeypatch):
    """크기를 고칠 때마다 새로 후보를 만들어 1등을 고르면 매번 다른 코스가 되고, 코스마다 Tmap이 늘리는
    비율이 달라 거리가 수렴하지 않았다(해운대 바다 5km: 3.26 → 5.42 → 5.98km, 5% 밖)."""
    made = []
    monkeypatch.setattr(main, "generate_loop_candidates",
                        lambda *a, **k: made.append("candidates") or [_shaped(TARGET)])
    remade = []
    monkeypatch.setattr(main, "generate_loop_course",
                        lambda lat, lng, km, tags, **k: remade.append((k["angle_offset_deg"], k["radius_scale"])) or _plan(km))
    monkeypatch.setattr(main.area_cache, "load_area", lambda *a, **k: None)
    monkeypatch.setattr(main, "register_in_background", lambda course: None)
    follow, calls = _tmap_follow(stretch=1.2)
    monkeypatch.setattr(main, "_follow_with_tmap", follow)

    body = client.post("/recommend", json={"preferred_distance_km": TARGET, "route_type": "loop", "top_n": 3,
                                           "current_lat": 34.0, "current_lng": 127.0}).json()
    course = body["results"][0]["course"]
    assert made == ["candidates"], "크기를 고칠 때 후보를 새로 만들지 않는다"
    assert remade and set(remade) == {(20.0, 0.9)}, "1등 코스와 같은 방향·모양으로 다시 짠다"
    assert abs(course["distance_km"] - TARGET) / TARGET <= 0.05
