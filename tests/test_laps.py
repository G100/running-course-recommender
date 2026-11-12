"""한 바퀴로 요청 거리의 순환을 못 만들면, 짧은 순환을 여러 바퀴 도는 코스를 만들어 두고 러너에게 묻는다.

산길을 빼면 산을 낀 동네에서는 긴 순환이 아예 나오지 않았다(해운대 21·42km). 그래도 코스는 반드시 준다 —
같은 길을 되도록 적게 반복하도록 2바퀴부터 시도하고, 러너는 그대로 달리거나 왕복·편도로 바꿀 수 있다.
"""
import pytest
from fastapi.testclient import TestClient

from src.api import main
from src.data_collection.enrich import haversine_m
from src.recommend import laps
from src.recommend.step_position import assign_positions, cumulative_distances

LAT0, LNG0 = 35.0, 127.0
M_LAT, M_LNG = 111_320, 111_320 * 0.8192


def at(north_m, east_m):
    return [LAT0 + north_m / M_LAT, LNG0 + east_m / M_LNG]


def square(side_m):
    """한 변이 side_m인 사각형 순환 (출발점 = 도착점). 50m마다 점."""
    corners = [(0, 0), (side_m, 0), (side_m, side_m), (0, side_m), (0, 0)]
    path = [at(0, 0)]
    for (n0, e0), (n1, e1) in zip(corners, corners[1:]):
        pieces = max(1, round((abs(n1 - n0) + abs(e1 - e0)) / 50))
        path += [at(n0 + (n1 - n0) * i / pieces, e0 + (e1 - e0) * i / pieces) for i in range(1, pieces + 1)]
    return path


def loop_course(km, cid="loop"):
    side = km * 1000 / 4
    path = square(side)
    return {"id": cid, "name": "북쪽 순환 코스", "region": "실시간 생성", "distance_km": round(km, 3), "route_type": "loop",
            "path": path, "tags": [], "source": "live_generated", "surface": "paved", "safety_score": 0.7,
            "elevation_gain_m": None,
            # 안내 위치(cum_m)는 경로를 따라 잰 값이다
            "steps": assign_positions([
                {"lat": path[0][0], "lng": path[0][1], "description": "출발", "turn_type": 200, "instruction": "출발하세요"},
                {"lat": at(side, 0)[0], "lng": at(side, 0)[1], "description": "우회전", "turn_type": 13, "instruction": "오른쪽으로 도세요"},
                {"lat": path[-1][0], "lng": path[-1][1], "description": "도착", "turn_type": 201, "instruction": "도착했어요"}], path)}


# ── 바퀴 이어 붙이기 ──

def test_laps_repeat_the_course_and_add_up_the_distance():
    one = loop_course(7.0)
    three = laps.repeat(one, 3)
    lap_m = cumulative_distances(one["path"])[-1]
    assert cumulative_distances(three["path"])[-1] == pytest.approx(3 * lap_m, rel=1e-6)
    assert len(three["path"]) == 3 * (len(one["path"]) - 1) + 1, "바퀴가 만나는 점을 두 번 넣지 않는다"
    assert three["distance_km"] == pytest.approx(21.0, abs=0.01)
    assert three["laps"] == 3 and three["lap_km"] == pytest.approx(7.0)
    assert three["name"] == "북쪽 순환 코스 · 3바퀴"
    assert three["id"] == one["id"], "평가·즐겨찾기가 맞으려면 같은 코스로 남아야 한다"


def test_each_lap_has_its_turns_and_the_runner_hears_when_a_lap_ends():
    one = loop_course(4.0)
    steps = laps.repeat(one, 3)["steps"]
    assert [s["turn_type"] for s in steps] == [200, 13, laps.LAP_TURN, 13, laps.LAP_TURN, 13, 201], \
        "출발은 처음에 한 번, 도착은 끝에 한 번"
    assert [s["instruction"] for s in steps if s["turn_type"] == laps.LAP_TURN] == \
        ["1바퀴 끝, 2바퀴째입니다", "2바퀴 끝, 마지막 바퀴입니다"]
    positions = [s["cum_m"] for s in steps]
    lap = cumulative_distances(one["path"])[-1]   # 약 4km (사각형을 실제로 잰 길이)
    turn = one["steps"][1]["cum_m"]              # 첫 모서리, 약 1km
    assert positions == sorted(positions)
    assert positions == pytest.approx([0, turn, lap, lap + turn, 2 * lap, 2 * lap + turn, 3 * lap], abs=1)


def test_steps_without_positions_are_placed_on_the_lap_first():
    one = loop_course(4.0)
    for s in one["steps"]:
        del s["cum_m"]
    turns = [s for s in laps.repeat(one, 2)["steps"] if s["turn_type"] == 13]
    lap, turn = cumulative_distances(one["path"])[-1], loop_course(4.0)["steps"][1]["cum_m"]
    assert [s["cum_m"] for s in turns] == pytest.approx([turn, lap + turn], abs=1)


def test_one_lap_gives_back_the_lap_to_run_on_tmap():
    one = loop_course(7.0)
    lap = laps.one_lap(laps.repeat(one, 3))
    assert lap["path"] == one["path"] and lap["distance_km"] == pytest.approx(7.0)
    assert "laps" not in lap and lap["name"] == "북쪽 순환 코스"


def test_one_lap_course_is_left_as_it_is():
    one = loop_course(5.0)
    assert laps.repeat(one, 1) is one and laps.one_lap(one) is one


# ── 몇 바퀴로 만들까 ──

def fake_generate(longest_loop_km, made):
    """longest_loop_km보다 긴 순환은 못 만든다. 만들 수 있으면 정확히 그 거리로 만든다."""
    def generate(km, wanted):
        made.append(round(km, 3))
        if km > longest_loop_km:
            raise ValueError("차도를 피해 가는 코스를 만들지 못했습니다.")
        return [loop_course(km, cid=f"loop-{km:.2f}")]
    return generate


def test_a_loop_that_can_be_made_in_one_lap_stays_one_lap():
    asked = []
    found, count = main._loop_or_laps(fake_generate(30, asked), 21.1, set())
    assert count == 1 and asked == [21.1]


def test_fewest_laps_that_work_are_used():
    asked = []
    found, count = main._loop_or_laps(fake_generate(8, asked), 21.0, set())
    assert count == 3 and asked == [21.0, 10.5, 7.0], "2바퀴(10.5km)가 안 되면 3바퀴(7km)"
    assert found[0]["distance_km"] == pytest.approx(7.0)


def test_a_one_lap_loop_far_from_the_asked_distance_counts_as_not_made():
    asked = []

    def generate(km, wanted):
        asked.append(round(km, 3))
        return [loop_course(km * 0.7 if km > 12 else km)]   # 긴 순환은 30% 짧게만 나온다

    found, count = main._loop_or_laps(generate, 21.0, set())
    assert count == 2 and asked == [21.0, 10.5]


def test_when_no_number_of_laps_works_the_one_lap_attempt_is_kept():
    def generate(km, wanted):
        return [loop_course(km * 0.7)]   # 몇 km든 30% 짧게 나온다

    found, count = main._loop_or_laps(generate, 21.0, set())
    assert count == 1 and found[0]["distance_km"] == pytest.approx(14.7)


def test_when_nothing_can_be_made_the_reason_is_passed_on():
    with pytest.raises(ValueError, match="차도"):
        main._loop_or_laps(fake_generate(0.5, []), 21.0, set())


# ── 추천 응답과 고른 후보 맞추기 ──

client = TestClient(main.app)


@pytest.fixture
def only_short_loops(monkeypatch):
    def candidates(lat, lng, km, wanted, route_type="loop", night=False):
        if km > 8:
            raise ValueError("차도를 피해 가는 코스를 만들지 못했습니다.")
        return [loop_course(km, cid="loop-a"), loop_course(km, cid="loop-b")]

    delivered = []

    def deliver(plan, target_km, route_type, regenerate):
        delivered.append((plan["id"], round(plan["distance_km"], 2), round(target_km, 2), route_type))
        return dict(plan, tmap={"ok": True, "distance_km": plan["distance_km"]})

    monkeypatch.setattr(main, "generate_loop_candidates", candidates)
    monkeypatch.setattr(main, "register_in_background", lambda course: None)
    monkeypatch.setattr(main, "_deliver_on_tmap", deliver)
    return delivered


def test_long_loop_comes_back_as_laps_and_the_runner_is_asked(only_short_loops):
    body = client.post("/recommend", json={"preferred_distance_km": 21.0, "route_type": "loop", "top_n": 3,
                                           "current_lat": LAT0, "current_lng": LNG0}).json()
    first = body["results"][0]["course"]
    assert first["laps"] == 3 and first["distance_km"] == pytest.approx(21.0, abs=0.05)
    assert only_short_loops == [("loop-a", 7.0, 7.0, "loop")] or only_short_loops[0][2] == 7.0, \
        "Tmap으로는 한 바퀴만 잇는다"
    assert all(r["course"]["laps"] == 3 for r in body["results"]), "다른 후보도 3바퀴 거리로 보여야 고를 수 있다"
    assert "3바퀴" in body["notice"] and "7.0km" in body["notice"]
    sets = [o["set"] for o in body["choice"]["options"]]
    assert {} in sets and {"route_type": "roundtrip"} in sets and {"route_type": "oneway"} in sets
    assert body["deliver_km"] == pytest.approx(21.0)


def test_picking_another_lap_course_runs_one_lap_on_tmap_and_repeats_it(only_short_loops):
    body = client.post("/recommend", json={"preferred_distance_km": 21.0, "route_type": "loop", "top_n": 3,
                                           "current_lat": LAT0, "current_lng": LNG0}).json()
    other = body["results"][1]["course"]
    only_short_loops.clear()
    picked = client.post("/courses/deliver", json={"course": other, "target_km": body["deliver_km"],
                                                     "route_type": "loop"}).json()["course"]
    assert only_short_loops == [("loop-b", 7.0, 7.0, "loop")]
    assert picked["laps"] == 3 and picked["distance_km"] == pytest.approx(21.0, abs=0.05) and picked["tmap"]["ok"]
    start, end = picked["path"][0], picked["path"][-1]
    assert haversine_m(start, end) < 1


def test_a_loop_that_fits_in_one_lap_is_not_split(monkeypatch, only_short_loops):
    body = client.post("/recommend", json={"preferred_distance_km": 6.0, "route_type": "loop", "top_n": 1,
                                           "current_lat": LAT0, "current_lng": LNG0}).json()
    course = body["results"][0]["course"]
    assert course.get("laps", 1) == 1 and body.get("choice") is None and not (body.get("notice") or "").count("바퀴")
