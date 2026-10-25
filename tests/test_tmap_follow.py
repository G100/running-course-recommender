"""우리 모델이 짠 코스를 Tmap 보행자 경로가 그대로 따라가게 한다."""
import pytest

from src.data_collection.scenery import build_indexes
from src.recommend import road_graph as rg
from src.recommend import tmap_follow

LAT, LNG = 35.0, 127.0
D = 0.001  # 위도 약 111m, 경도 약 91m


def _way(wid, coords, **tags):
    return {"type": "way", "id": wid, "geometry": [{"lat": a, "lon": b} for a, b in coords], "tags": tags}


@pytest.fixture
def town():
    """A에서 B로: 곧장 가는 큰길(약 364m)과, 북쪽으로 돌아가는 산책로(약 586m). 우리 코스는 산책로."""
    a, b = (LAT, LNG), (LAT, LNG + 4 * D)
    north = [a] + [(LAT + D, LNG + i * D) for i in range(5)] + [b]
    ways = [_way(1, [a, (LAT, LNG + 2 * D), b], highway="primary"), _way(2, north, highway="footway")]
    graph = rg.RoadGraph(ways, build_indexes({"all": ways}), rg.PRIOR, facts={})
    return graph, north


def _tmap_along(path):
    """Tmap 응답 모양: 주어진 선 그대로, 전부 인도(roadType 21)."""
    from src.data_collection.enrich import haversine_m
    total = sum(haversine_m(p, q) for p, q in zip(path, path[1:]))
    return {"features": [
        {"geometry": {"type": "Point", "coordinates": [path[0][1], path[0][0]]}, "properties": {"totalDistance": round(total)}},
        {"geometry": {"type": "LineString", "coordinates": [[lng, lat] for lat, lng in path]}, "properties": {"roadType": 21}},
        {"geometry": {"type": "Point", "coordinates": [path[-1][1], path[-1][0]]}, "properties": {"description": "도착", "turnType": 201}},
    ]}


class TestWaypoints:
    def test_no_waypoint_when_our_course_is_already_the_shortest(self, town):
        graph, _ = town
        straight = [(LAT, LNG), (LAT, LNG + 2 * D), (LAT, LNG + 4 * D)]
        assert tmap_follow.needed_waypoints(graph, straight) == []

    def test_a_waypoint_keeps_tmap_off_the_shortcut(self, town):
        """최단거리는 큰길인데 우리 코스는 북쪽 산책로 — 산책로 위에 경유지가 있어야 Tmap이 그리로 간다."""
        graph, north = town
        picks = tmap_follow.needed_waypoints(graph, north)
        assert picks and all(p[0] > LAT for p in picks), picks


class TestStitch:
    def test_more_than_five_waypoints_are_asked_in_several_calls(self, monkeypatch):
        asked = []

        def fake(start, end, start_name="", end_name="", waypoints=None):
            asked.append(len(waypoints or []))
            pts = [(start[1], start[0])] + [(lat, lng) for lng, lat in waypoints or []] + [(end[1], end[0])]
            return _tmap_along(pts)

        monkeypatch.setattr(tmap_follow, "get_route", fake)
        start = (LAT, LNG)
        points = [(LAT + D * i, LNG) for i in range(1, 13)]   # 경유지 12개
        route, calls = tmap_follow.stitch(start, start, points)
        assert calls == 3 and max(asked) <= 5
        from src.api_clients.tmap_pedestrian import extract_path
        path, distance = extract_path(route)
        assert distance > 0 and path[0] == [LAT, LNG]


    def test_repeated_points_are_not_sent_twice(self, monkeypatch):
        """코스가 같은 교차로를 두 번 지나면 같은 점이 연달아 찍혔고, Tmap은 400으로 거절했다 (여수)."""
        import requests

        def fake(start, end, start_name="", end_name="", waypoints=None):
            pts = [(start[1], start[0])] + [(lat, lng) for lng, lat in waypoints or []] + [(end[1], end[0])]
            if any(a == b for a, b in zip(pts, pts[1:])):
                raise requests.HTTPError("400 waypoints are too near")
            return _tmap_along(pts)

        monkeypatch.setattr(tmap_follow, "get_route", fake)
        start = (LAT, LNG)
        a, b = (LAT + D, LNG), (LAT + D, LNG + D)
        route, calls = tmap_follow.stitch(start, start, [a, b, b, a, start])
        assert calls == 1


class TestFollow:
    def test_route_that_follows_our_course_passes(self, town, monkeypatch):
        graph, north = town
        monkeypatch.setattr(tmap_follow, "get_route", lambda *a, **k: _tmap_along(north))
        result = tmap_follow.follow(graph, [list(p) for p in north])
        assert result["follow"]["ok"] and result["follow"]["plan_covered"] > 0.95
        assert result["follow"]["road_mix"]["sidewalk"] == 1.0

    def test_when_tmap_will_not_take_our_path_the_course_is_replanned_once(self, town, monkeypatch):
        """Tmap이 어떻게 물어도 산책로로 가지 않으면(그 길이 Tmap 지도에 없다) 그 길을 빼고 다시 짠다 — 한 번만."""
        graph, north = town
        shortcut = [(LAT, LNG), (LAT, LNG + 2 * D), (LAT, LNG + 4 * D)]
        calls = []
        monkeypatch.setattr(tmap_follow, "get_route", lambda *a, **k: calls.append(1) or _tmap_along(shortcut))
        result = tmap_follow.follow(graph, [list(p) for p in north])
        assert result["follow"]["replanned"]
        assert result["follow"]["calls"] == len(calls) == 2


def test_follow_endpoint_returns_the_tmap_route(monkeypatch):
    from fastapi.testclient import TestClient

    from src.api import main

    client = TestClient(main.app)

    route = _tmap_along([(LAT, LNG), (LAT + D, LNG), (LAT, LNG)])
    route["follow"] = {"ok": True, "plan_covered": 0.97, "follows_plan": 0.95, "calls": 1, "waypoints": 2,
                       "road_mix": {"sidewalk": 1.0}, "distance_km": 0.22}
    monkeypatch.setattr(main, "_follow_with_tmap", lambda path, target_km=None: route)
    body = client.post("/courses/follow", json={"path": [[LAT, LNG], [LAT + D, LNG], [LAT, LNG]]}).json()
    assert body["path"][0] == [LAT, LNG] and body["steps"][0]["description"] == "도착"
    assert body["follow"]["ok"] and body["distance_km"] == 0.22


class TestPathsTmapDoesNotHave:
    """우리 지도(OSM)에는 있는데 Tmap 지도에는 없는 길(공원·단지 안 보행로)이 코스에 있으면,
    그 길에 경유지를 찍어 억지로 데려가지 않고(들어갔다 나오느라 0.5~1.3km 늘었다) 그 길을 빼고 다시 짠다."""

    def _towns(self):
        a, b = (LAT, LNG), (LAT, LNG + 6 * D)
        north = [a] + [(LAT + D, LNG + i * D) for i in range(7)] + [b]          # Tmap에 없는 길 (약 770m)
        south = [a] + [(LAT - 1.5 * D, LNG + i * D) for i in range(7)] + [b]    # Tmap에도 있는 길 (약 880m)
        ours = [_way(1, north, highway="footway"), _way(2, south, highway="footway")]
        theirs = [_way(2, south, highway="footway")]
        graph = rg.RoadGraph(ours, build_indexes({"all": ours}), rg.PRIOR, facts={})
        tmap_graph = rg.RoadGraph(theirs, build_indexes({"all": theirs}), rg.PRIOR, facts={})
        return graph, tmap_graph, north, south

    def test_course_is_replanned_around_them_without_more_calls(self, monkeypatch):
        from src.api_clients.tmap_pedestrian import extract_path

        graph, tmap_graph, north, south = self._towns()
        calls = []

        def tmap(start, end, start_name="", end_name="", waypoints=None):
            calls.append(1)
            stops = [(lat, lng) for lng, lat in waypoints or []]
            return rg.route(tmap_graph, (start[1], start[0]), (end[1], end[0]), stops)

        monkeypatch.setattr(tmap_follow, "get_route", tmap)
        result = tmap_follow.follow(graph, [list(p) for p in north])
        follow = result["follow"]
        south_km = extract_path(rg.route(tmap_graph, south[0], south[-1]))[1] / 1000
        assert follow["replanned"] and follow["ok"], follow
        assert abs(follow["distance_km"] - south_km) <= 0.05
        assert follow["calls"] == len(calls) == 2
        assert graph.surfaces[0] == "walkway", "다시 짜려고 막은 길은 원래대로 돌려 놓는다"


class TestLearningWhatTmapUses:
    """Tmap에 물을 때마다 우리 길 중 Tmap이 탄 길과 피한 길을 적어 둔다. 다음부터는 피한 길로 짜지 않아서
    처음 한 번에 맞는다 (다시 묻는 호출이 줄고, 다시 짜느라 거리가 늘어나는 일도 줄어든다)."""

    def test_avoided_path_is_remembered_and_avoided_next_time(self, monkeypatch):
        graph, tmap_graph, north, south = TestPathsTmapDoesNotHave()._towns()

        def tmap(start, end, start_name="", end_name="", waypoints=None):
            stops = [(lat, lng) for lng, lat in waypoints or []]
            return rg.route(tmap_graph, (start[1], start[0]), (end[1], end[0]), stops)

        monkeypatch.setattr(tmap_follow, "get_route", tmap)
        tmap_follow.follow(graph, [list(p) for p in north])

        assert tmap_follow.way_id(north) in tmap_follow.tmap_avoided()
        assert tmap_follow.way_id(south) not in tmap_follow.tmap_avoided()

        # 새로 읽은 도로망(다음 요청)은 그 길로 짜지 않는다 — 조금 더 길어도 Tmap이 다니는 길로
        fresh = rg.RoadGraph(graph_ways(north, south), build_indexes({"all": graph_ways(north, south)}), rg.PRIOR, facts={})
        from src.api_clients.tmap_pedestrian import extract_path
        path, _ = extract_path(rg.route(fresh, north[0], north[-1]))
        assert all(p[0] <= LAT for p in path), "Tmap이 안 다니는 길로 또 짰다"

    def test_a_path_tmap_has_ridden_is_never_marked_avoided(self, monkeypatch):
        graph, tmap_graph, north, south = TestPathsTmapDoesNotHave()._towns()
        key = tmap_follow.way_id(north)
        tmap_follow.remember_ways({key: True})      # 전에 Tmap이 탔다
        tmap_follow.remember_ways({key: False})     # 이번엔 피했다 — 다른 길이 더 짧았을 수도 있다
        assert key not in tmap_follow.tmap_avoided()


def graph_ways(north, south):
    return [_way(1, north, highway="footway"), _way(2, south, highway="footway")]


def test_answer_within_the_distance_limit_is_chosen_first():
    """두 번 물은 결과 중에서는 요청 거리와 5% 안인 쪽이 먼저다 (우리 코스를 더 따라갔어도 거리가 틀리면 안 된다)."""
    close = {"ok": False, "distance_km": 3.05, "plan_covered": 0.7}
    far = {"ok": True, "distance_km": 5.2, "plan_covered": 0.97}
    assert tmap_follow._better(close, far, 3.0)
    assert not tmap_follow._better(far, close, 3.0)


class TestSpikes:
    """경유지가 옆길(막다른 곳)에 찍히면 Tmap이 거기까지 들어갔다가 그대로 되나온다 — 굳이 들를 필요 없는
    '삐죽' 구간이다 (상무 순환 138m, 대구 왕복 145·125·52m). 그 경유지를 빼고 다시 묻는다."""

    def test_waypoint_that_makes_tmap_poke_into_a_side_street_is_dropped(self, monkeypatch):
        from src.api_clients.tmap_pedestrian import extract_path
        from src.recommend.generate_live import _prune_with_spans

        a, b = (LAT, LNG), (LAT, LNG + 8 * D)
        main_road = [(LAT, LNG + i * D) for i in range(9)]
        side = [(LAT, LNG + 4 * D), (LAT - 0.0012, LNG + 4 * D)]       # 가운데에서 남쪽으로 133m 막다른 길
        ways = [_way(1, main_road, highway="footway"), _way(2, side, highway="footway")]
        graph = rg.RoadGraph(ways, build_indexes({"all": ways}), rg.PRIOR, facts={}, avoided=set())
        calls = []

        def tmap(start, end, start_name="", end_name="", waypoints=None):
            calls.append(len(waypoints or []))
            stops = [(lat, lng) for lng, lat in waypoints or []]
            return rg.route(graph, (start[1], start[0]), (end[1], end[0]), stops)

        monkeypatch.setattr(tmap_follow, "get_route", tmap)
        route, used, more = tmap_follow.remove_spikes(graph, a, b, [side[-1]], *tmap_follow.stitch(a, b, [side[-1]]))
        path, _ = extract_path(route)
        assert not [s for s in _prune_with_spans(path)[1] if s[1] - s[0] <= tmap_follow.SPIKE_MAX_M], "삐죽 구간이 남았다"
        assert side[-1] not in used and len(calls) == 2


def test_joined_directions_have_no_waypoint_or_midway_arrival_messages(monkeypatch):
    """경로를 여러 번 나눠 물어 이으면 Tmap의 '경유지 후 125m 이동', 중간 '도착' 안내가 그대로 섞였다.
    러너에게는 경유지가 없다 — 출발 하나, 도착 하나만 남긴다."""
    from src.api_clients.tmap_pedestrian import extract_steps

    def piece(start, end, start_name="", end_name="", waypoints=None):
        pts = [(start[1], start[0])] + [(lat, lng) for lng, lat in waypoints or []] + [(end[1], end[0])]
        feats = [{"geometry": {"type": "Point", "coordinates": [pts[0][1], pts[0][0]]},
                  "properties": {"totalDistance": 100, "description": "보행자도로를 따라 50m 이동", "turnType": 200}},
                 {"geometry": {"type": "LineString", "coordinates": [[b, a] for a, b in pts]}, "properties": {"roadType": 21}}]
        for lat, lng in pts[1:-1]:
            feats.append({"geometry": {"type": "Point", "coordinates": [lng, lat]},
                          "properties": {"description": "경유지 후 47m 이동", "turnType": 185}})
        feats.append({"geometry": {"type": "Point", "coordinates": [pts[-1][1], pts[-1][0]]},
                      "properties": {"description": "우회전 후 30m 이동", "turnType": 13}})
        feats.append({"geometry": {"type": "Point", "coordinates": [pts[-1][1], pts[-1][0]]},
                      "properties": {"description": "도착", "turnType": 201}})
        return {"features": feats}

    monkeypatch.setattr(tmap_follow, "get_route", piece)
    points = [(LAT + D * i, LNG) for i in range(1, 9)]          # 8개 → 두 번에 나눠 묻는다
    route, calls = tmap_follow.stitch((LAT, LNG), (LAT, LNG + D), points)
    steps = extract_steps(route)
    assert calls == 2
    assert not [s for s in steps if "경유지" in s["description"]]
    assert [s["turn_type"] for s in steps].count(201) == 1 and steps[-1]["turn_type"] == 201
    assert [s["turn_type"] for s in steps].count(200) == 1 and steps[0]["turn_type"] == 200
    assert sum(1 for s in steps if s["turn_type"] == 13) == 2, "진짜 회전 안내는 그대로 남아야 한다"


def test_waypoint_messages_are_dropped_whatever_code_tmap_gives_them():
    """Tmap이 경유지 안내에 경유지 코드(184~189) 대신 0을 줄 때도 있었다 ("경유지 후 동백로를 따라 10m 이동")."""
    point = {"geometry": {"type": "Point", "coordinates": [127.0, 34.0]},
             "properties": {"description": "경유지 후 동백로를 따라 10m 이동", "turnType": 0}}
    assert tmap_follow._runner_facing(point, first=False, last=False) is None
