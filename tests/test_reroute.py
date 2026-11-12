"""달리다 코스를 벗어나면 원래 코스로 돌아가는 길을 준다.

돌아갈 곳은 아직 달리지 않은 코스 중 지금 위치에서 가장 가까운 지점이다(되돌아가지 않는다).
순환 코스는 출발점과 도착점이 같아서, 그대로 찾으면 출발 직후에 벗어난 러너를 도착점으로 보내
코스 전체를 건너뛴다 — 그래서 코스를 따라 1km 앞까지만 찾는다.
"""
import pytest
import requests
from fastapi.testclient import TestClient

from src.api import main
from src.data_collection.enrich import haversine_m
from src.recommend import reroute
from src.recommend.step_position import cumulative_distances

LAT0, LNG0 = 35.0, 127.0
M_PER_LAT = 111_320
M_PER_LNG = 111_320 * 0.8192   # cos(35°)


def at(north_m, east_m):
    return [LAT0 + north_m / M_PER_LAT, LNG0 + east_m / M_PER_LNG]


def line(*corners, step_m=50):
    """모서리(북쪽 m, 동쪽 m)를 차례로 잇는 경로. 50m마다 점을 찍는다."""
    path = [at(*corners[0])]
    for (n0, e0), (n1, e1) in zip(corners, corners[1:]):
        pieces = max(1, round((abs(n1 - n0) + abs(e1 - e0)) / step_m))
        path += [at(n0 + (n1 - n0) * i / pieces, e0 + (e1 - e0) * i / pieces) for i in range(1, pieces + 1)]
    return path


STRAIGHT = line((0, 0), (3000, 0))                                   # 북쪽으로 3km
SQUARE = line((0, 0), (1000, 0), (1000, 1000), (0, 1000), (0, 0))    # 한 변 1km인 순환 4km
HAIRPIN = line((0, 0), (1500, 0), (1500, 100), (0, 100))             # 1.5km 갔다가 100m 옆으로 돌아오는 길


def test_runner_is_sent_to_the_nearest_part_of_the_course_not_yet_run():
    cum_m, point = reroute.rejoin_point(at(800, 60), STRAIGHT, progress_m=500)
    assert cum_m == pytest.approx(800, abs=5)
    assert haversine_m(point, at(800, 0)) < 5


def test_runner_is_never_sent_back_to_a_part_already_run():
    cum_m, _ = reroute.rejoin_point(at(200, 60), STRAIGHT, progress_m=500)
    assert cum_m == pytest.approx(500, abs=5), "지나온 200m 지점이 더 가깝지만 되돌아가지 않는다"


def test_leaving_a_loop_right_after_the_start_does_not_skip_to_the_finish():
    # 출발 100m 뒤에 서쪽으로 벗어났다. 도착점(=출발점)이 가깝지만 그리로 보내면 4km를 다 건너뛴다
    cum_m, _ = reroute.rejoin_point(at(100, -60), SQUARE, progress_m=100)
    assert cum_m < 1100, cum_m


def test_rejoin_is_searched_only_one_km_ahead_along_the_course():
    # 돌아오는 길(코스 2.9km 지점)이 바로 옆 40m에 있어도, 거기로 가면 2.7km를 건너뛴다
    cum_m, _ = reroute.rejoin_point(at(200, 60), HAIRPIN, progress_m=200)
    assert 200 <= cum_m <= 1200, cum_m


def test_rejoin_reach_can_be_changed():
    cum_m, _ = reroute.rejoin_point(at(200, 60), HAIRPIN, progress_m=200, ahead_m=3000)
    assert cum_m == pytest.approx(2900, abs=10)


def _tmap_answer(points, turn_at):
    """Tmap 보행자 경로 응답 모양: 출발 안내, 중간에 우회전 하나, 도착 안내."""
    coords = [[lng, lat] for lat, lng in points]
    metres = cumulative_distances(points)[-1]
    point = lambda p, **props: {"geometry": {"type": "Point", "coordinates": [p[1], p[0]]}, "properties": props}
    return {"features": [
        point(points[0], totalDistance=metres, description="출발", turnType=200),
        {"geometry": {"type": "LineString", "coordinates": coords}, "properties": {}},
        point(turn_at, description="우회전 후 보행자도로를 따라 60m 이동", turnType=13),
        point(points[-1], description="도착", turnType=201),
    ]}


def test_new_route_goes_to_the_rejoin_point_and_then_follows_the_rest_of_the_course():
    position = at(800, 60)
    steps = [{"lat": at(300, 0)[0], "lng": at(300, 0)[1], "description": "지나간 안내", "turn_type": 12, "instruction": "왼쪽", "cum_m": 300.0},
             {"lat": at(2000, 0)[0], "lng": at(2000, 0)[1], "description": "남은 안내", "turn_type": 13, "instruction": "오른쪽", "cum_m": 2000.0},
             {"lat": at(3000, 0)[0], "lng": at(3000, 0)[1], "description": "도착", "turn_type": 201, "instruction": "도착했어요", "cum_m": 3000.0}]
    asked = []

    def get_route(start, end):
        asked.append((start, end))
        return _tmap_answer(line((800, 60), (800, 0), step_m=20), turn_at=at(800, 30))

    made = reroute.back_to_course(position, STRAIGHT, steps, progress_m=500, get_route=get_route)

    (start, end), = asked
    assert start == (position[1], position[0]), "Tmap은 (경도, 위도) 순서로 받는다"
    assert haversine_m((end[1], end[0]), at(800, 0)) < 5
    assert haversine_m(made["path"][0], position) < 1 and haversine_m(made["path"][-1], STRAIGHT[-1]) < 1
    assert cumulative_distances(made["path"])[-1] == pytest.approx(60 + 2200, abs=15)
    assert [s["description"] for s in made["steps"]] == ["우회전 후 보행자도로를 따라 60m 이동", "남은 안내", "도착"], \
        "돌아가는 길의 출발·도착 안내와 이미 지나간 안내는 빠진다"
    positions = [s["cum_m"] for s in made["steps"]]
    assert positions == sorted(positions) and positions[1] == pytest.approx(60 + 1200, abs=15)
    assert made["distance_km"] == pytest.approx(2.26, abs=0.02)
    assert made["rejoin_m"] == pytest.approx(60, abs=5) and made["skipped_m"] == pytest.approx(300, abs=5)


def test_runner_already_back_on_the_course_gets_the_rest_of_it_without_asking_tmap():
    # 안내받은 길 대신 곧장 코스로 돌아와 있다. Tmap은 출발과 도착이 같은 길을 주지 못한다(실제로 502가 났다)
    steps = [{"lat": at(2000, 0)[0], "lng": at(2000, 0)[1], "description": "남은 안내", "turn_type": 13, "instruction": "오른쪽", "cum_m": 2000.0}]
    made = reroute.back_to_course(at(800, 3), STRAIGHT, steps, progress_m=500,
                                  get_route=lambda start, end: pytest.fail("이미 코스 위다 — Tmap에 물을 길이 없다"))
    assert haversine_m(made["path"][0], at(800, 3)) < 1 and haversine_m(made["path"][-1], STRAIGHT[-1]) < 1
    assert cumulative_distances(made["path"])[-1] == pytest.approx(2200, abs=10)
    assert [round(s["cum_m"], -1) for s in made["steps"]] == [1200]
    assert made["skipped_m"] == pytest.approx(300, abs=5)


def test_new_route_starts_where_the_runner_stands_even_when_tmap_starts_from_the_nearest_road():
    # 광장·해변처럼 길이 없는 곳에 서 있으면 Tmap은 가까운 길에서 출발한다(실제로 50m 떨어져 있었다).
    # 그 길에서 시작하는 경로를 주면 받자마자 다시 '벗어남'이 되어 재탐색이 되풀이된다
    position = at(800, 110)
    get_route = lambda start, end: _tmap_answer(line((800, 60), (800, 0), step_m=20), turn_at=at(800, 30))
    made = reroute.back_to_course(position, STRAIGHT, [], progress_m=500, get_route=get_route)
    assert haversine_m(made["path"][0], position) < 1
    assert made["rejoin_m"] == pytest.approx(110, abs=5), "길까지 가는 50m도 돌아가는 거리다"
    assert made["steps"][0]["cum_m"] == pytest.approx(80, abs=12), "안내 위치도 선 자리부터 잰다 (경로의 점은 20m 간격)"


def test_change_in_total_distance_counts_what_was_run_off_course():
    # 500m 지점에서 벗어나 60m 옆으로 갔다가, 60m를 걸어 500m 지점으로 돌아온다 → 120m 늘어난다
    get_route = lambda start, end: _tmap_answer(line((500, 60), (500, 0), step_m=20), turn_at=at(500, 30))
    made = reroute.back_to_course(at(500, 60), STRAIGHT, [], progress_m=500, get_route=get_route)
    assert made["extra_m"] == pytest.approx(120, abs=10)


def test_cutting_a_corner_makes_the_run_shorter():
    # 순환의 첫 모서리(1km 지점)를 가로질러 갔다: 600m 지점에서 벗어나 1.4km 지점 쪽으로
    position = at(940, 300)
    get_route = lambda start, end: _tmap_answer(line((940, 300), (1000, 300), step_m=20), turn_at=at(970, 300))
    made = reroute.back_to_course(position, SQUARE, [], progress_m=600, get_route=get_route)
    assert made["skipped_m"] == pytest.approx(700, abs=10)
    assert made["extra_m"] < -100, made["extra_m"]


client = TestClient(main.app)
BODY = {"position": at(800, 60), "path": STRAIGHT, "steps": [], "progress_m": 500}


def test_reroute_endpoint_returns_the_new_route(monkeypatch):
    monkeypatch.setattr(reroute.tmap, "get_route",
                        lambda start, end: _tmap_answer(line((800, 60), (800, 0), step_m=20), turn_at=at(800, 30)))
    response = client.post("/courses/reroute", json=BODY)
    assert response.status_code == 200, response.text
    body = response.json()
    assert haversine_m(body["path"][0], BODY["position"]) < 1 and body["steps"] and "extra_m" in body


def test_reroute_endpoint_says_so_when_tmap_cannot_be_reached(monkeypatch):
    def down(start, end):
        raise requests.ConnectionError("끊김")
    monkeypatch.setattr(reroute.tmap, "get_route", down)
    response = client.post("/courses/reroute", json=BODY)
    assert response.status_code == 502 and "Tmap" in response.json()["detail"]


def test_reroute_endpoint_says_so_when_tmap_gives_no_route(monkeypatch):
    monkeypatch.setattr(reroute.tmap, "get_route", lambda start, end: {"features": []})
    assert client.post("/courses/reroute", json=BODY).status_code == 502
