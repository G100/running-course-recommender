import pytest

from src.recommend import generate_live


def test_roundtrip_uses_tmap_waypoints_to_close_loop(monkeypatch):
    calls = []

    monkeypatch.setattr(
        generate_live,
        "find_nearby_points",
        lambda lat, lng, radius_m, osm_filter: [(34.001, 127.001), (34.002, 127.002)],
    )
    monkeypatch.setattr(generate_live, "snap_vertices", lambda vertices: vertices)
    monkeypatch.setattr(generate_live, "sample_elevation_gain", lambda path: 10.0)

    def get_route(start, end, start_name="", end_name="", waypoints=None):
        calls.append((start, end, waypoints))
        return {
            "features": [
                {"geometry": {"type": "Point", "coordinates": [127.0, 34.0]},
                 "properties": {"totalDistance": 3000}},
                {"geometry": {"type": "LineString", "coordinates": [
                    [127.0, 34.0], [127.001, 34.001], [127.002, 34.002], [127.0, 34.0],
                ]}},
            ]
        }

    monkeypatch.setattr(generate_live, "get_route", get_route)

    course = generate_live.generate_loop_course(34.0, 127.0, 3.0, {"숲길"})

    assert len(calls) == 1
    assert calls[0][0] == calls[0][1] == (127.0, 34.0)
    assert len(calls[0][2]) == 3
    assert course["path"][0] == course["path"][-1] == [34.0, 127.0]
    assert course["distance_km"] == 3.0


def test_virtual_vertices_use_target_circumference():
    vertices = generate_live.virtual_vertices(34.0, 127.0, 5.0)
    assert len(vertices) == 3
    assert all(abs(point[0] - 34.0) > 0 or abs(point[1] - 127.0) > 0 for point in vertices)


def test_self_intersection_detects_bow_tie_path():
    assert generate_live.has_self_intersection([
        [0.0, 0.0], [1.0, 1.0], [0.0, 1.0], [1.0, 0.0], [0.0, 0.0]
    ])


def test_self_intersection_allows_simple_closed_path():
    assert not generate_live.has_self_intersection([
        [0.0, 0.0], [0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0]
    ])


def test_snap_vertices_falls_back_to_geometry_when_overpass_times_out(monkeypatch, capsys):
    calls = []

    def fail_request(query, timeout):
        calls.append(query)
        raise generate_live.OverpassUnavailable("Overpass timed out")

    monkeypatch.setattr(generate_live, "post_overpass_query", fail_request)
    vertices = [(34.001, 127.001), (34.002, 127.002)]

    assert generate_live.snap_vertices(vertices) == vertices
    assert len(calls) == 1
    assert capsys.readouterr().out == ""


def test_loop_candidate_generator_uses_multiple_orientations_and_snaps_once(monkeypatch):
    calls = []

    def make_course(lat, lng, distance, tags, **kwargs):
        calls.append(kwargs)
        return {"id": f"candidate-{kwargs['angle_offset_deg']}", "distance_km": 5.0}

    monkeypatch.setattr(generate_live, "generate_loop_course", make_course)

    courses = generate_live.generate_loop_candidates(34.0, 127.0, 5.0, set())

    assert [course["id"] for course in courses] == ["candidate-0.0", "candidate-20.0", "candidate--20.0"]
    assert [call["snap_to_osm"] for call in calls] == [True, False, False]
    assert [call["radius_scale"] for call in calls] == list(generate_live.LOOP_RADIUS_SCALES)


def test_short_loops_trigger_one_larger_attempt(monkeypatch):
    """가지를 잘라내면 순환이 짧아진다. 후보가 전부 목표보다 한참 짧으면 반경을 키워 한 번 더 만든다."""
    calls = []

    def make_course(lat, lng, distance, tags, **kwargs):
        calls.append(kwargs["radius_scale"])
        # 반경에 비례해 거리가 나온다고 가정 (반경 1.0이면 목표의 60%)
        return {"id": f"c{len(calls)}", "distance_km": round(distance * 0.6 * kwargs["radius_scale"], 2)}

    monkeypatch.setattr(generate_live, "generate_loop_course", make_course)
    courses = generate_live.generate_loop_candidates(34.0, 127.0, 5.0, set())

    assert len(calls) == 4, "짧은 후보뿐인데 보정 시도를 안 했다"
    assert calls[-1] > max(calls[:3])
    best = min(courses, key=lambda c: abs(c["distance_km"] - 5.0))
    assert abs(best["distance_km"] - 5.0) / 5.0 <= 0.2


def test_on_target_loops_are_not_regenerated(monkeypatch):
    calls = []
    monkeypatch.setattr(generate_live, "generate_loop_course",
                        lambda lat, lng, d, tags, **k: calls.append(1) or {"id": f"c{len(calls)}", "distance_km": 5.1})
    generate_live.generate_loop_candidates(34.0, 127.0, 5.0, set())
    assert len(calls) == 3


def _road(lat1, lng1, lat2, lng2):
    return {"geometry": [{"lat": lat1, "lon": lng1}, {"lat": lat2, "lon": lng2}]}


def test_vertices_avoid_directions_with_no_road():
    """해안가에서는 원의 절반이 바다다. 길이 없는 방향에 꼭짓점을 찍으면 코스가 쪼그라든다."""
    # 출발점 북쪽 반원에만 길이 있다 (남쪽은 바다)
    center = (34.0, 127.0)
    ways = [_road(34.0 + 0.002 + i * 0.001, 126.99, 34.0 + 0.002 + i * 0.001, 127.01) for i in range(8)]
    ways += [_road(34.0, 126.99, 34.012, 126.99), _road(34.0, 127.01, 34.012, 127.01)]
    vertices = generate_live.pick_land_vertices(*center, 5.0, ways)
    assert vertices, "길이 있는 방향이 있는데 꼭짓점을 못 골랐다"
    assert all(v[0] >= 34.0 - 1e-9 for v in vertices), "바다 쪽(남쪽)에 꼭짓점을 찍었다"


def test_vertices_are_spread_around_when_roads_are_everywhere():
    center = (34.0, 127.0)
    ways = [_road(34.0 + d, 126.98, 34.0 + d, 127.02) for d in (-0.008, -0.004, 0.0, 0.004, 0.008)]
    ways += [_road(33.98, 127.0 + d, 34.02, 127.0 + d) for d in (-0.008, -0.004, 0.0, 0.004, 0.008)]
    vertices = generate_live.pick_land_vertices(*center, 5.0, ways)
    assert len(vertices) == generate_live.VERTEX_COUNT
    import math
    angles = sorted(math.degrees(math.atan2(v[0] - center[0], v[1] - center[1])) % 360 for v in vertices)
    gaps = [(angles[(i + 1) % len(angles)] - angles[i]) % 360 for i in range(len(angles))]
    assert min(gaps) >= 60, f"꼭짓점이 한쪽에 몰렸다: {angles}"


def test_road_network_is_fetched_once_for_all_candidates(monkeypatch):
    """후보마다 Overpass에 물으면 느리고 속도 제한에 걸린다 — 한 번 받아 모두 쓴다."""
    queries = []

    class Response:
        def json(self):
            return {"elements": []}

    monkeypatch.setattr(generate_live, "post_overpass_query", lambda q, timeout=30: queries.append(q) or Response())
    monkeypatch.setattr(generate_live, "generate_loop_course",
                        lambda lat, lng, d, tags, **k: {"id": f"c{k['angle_offset_deg']}", "distance_km": 5.0})
    generate_live.generate_loop_candidates(34.0, 127.0, 5.0, set())
    assert len(queries) == 1


def test_one_candidate_rejected_by_tmap_does_not_fail_the_request(monkeypatch):
    """후보 하나가 Tmap에서 400을 받아도(경유지가 갈 수 없는 곳 등) 나머지로 답해야 한다."""
    import requests

    def make_course(lat, lng, d, tags, **kwargs):
        if kwargs["angle_offset_deg"] == 0.0:
            raise requests.HTTPError("400 Client Error: Bad Request")
        return {"id": f"c{kwargs['angle_offset_deg']}", "distance_km": 5.0}

    monkeypatch.setattr(generate_live, "generate_loop_course", make_course)
    courses = generate_live.generate_loop_candidates(34.0, 127.0, 5.0, set())
    assert [c["id"] for c in courses] == ["c20.0", "c-20.0"]


def test_loop_is_not_routed_through_the_sea_when_roads_are_known(monkeypatch):
    """주변 길을 받았는데 길 있는 방향이 부족하면, 바다일 수 있는 계산 좌표로 억지로 요청하지 않는다."""
    monkeypatch.setattr(generate_live, "get_route", lambda *a, **k: pytest.fail("길 없는 좌표로 Tmap을 불렀다"))
    far_road = [{"geometry": [{"lat": 40.0, "lon": 130.0}, {"lat": 40.001, "lon": 130.0}]}]
    with pytest.raises(ValueError):
        generate_live.generate_loop_course(34.0, 127.0, 5.0, set(), route_type="loop",
                                           angle_offset_deg=0.0, ways=far_road)


def _square_loop(lat, lng, size, n=8):
    d = size
    pts = [[lat, lng + d * i / n] for i in range(n)]
    pts += [[lat + d * i / n, lng + d] for i in range(n)]
    pts += [[lat + d, lng + d - d * i / n] for i in range(n)]
    pts += [[lat + d - d * i / n, lng] for i in range(n)]
    return pts + [[lat, lng]]


def test_useless_candidates_are_dropped(monkeypatch):
    """막다른 길 왕복을 걷어내고 나면 거의 안 남는 후보(0.04km 등)는 코스가 아니다."""
    loops = {
        0.0: {"id": "good", "distance_km": 4.9, "path": _square_loop(34.0, 127.0, 0.011)},
        20.0: {"id": "tiny", "distance_km": 0.04, "path": _square_loop(34.0, 127.0, 0.0001)},
        -20.0: {"id": "ok", "distance_km": 4.2, "path": _square_loop(34.0, 127.0, 0.0095)[::-1]},
    }
    monkeypatch.setattr(generate_live, "generate_loop_course",
                        lambda lat, lng, d, tags, **k: loops[k["angle_offset_deg"]])
    ids = [c["id"] for c in generate_live.generate_loop_candidates(34.0, 127.0, 5.0, set())]
    assert "tiny" not in ids
    assert "good" in ids


def test_all_useless_candidates_is_a_failure_not_an_empty_answer(monkeypatch):
    monkeypatch.setattr(generate_live, "generate_loop_course",
                        lambda lat, lng, d, tags, **k: {"id": "tiny", "distance_km": 0.05,
                                                        "path": _square_loop(34.0, 127.0, 0.0001)})
    with pytest.raises(ValueError):
        generate_live.generate_loop_candidates(34.0, 127.0, 5.0, set())


def test_near_duplicate_candidates_are_collapsed(monkeypatch):
    """사실상 같은 길이면 하나만 남긴다 — 목표 거리에 더 가까운 쪽을."""
    same = _square_loop(34.0, 127.0, 0.011)
    loops = {
        0.0: {"id": "a", "distance_km": 4.6, "path": same},
        20.0: {"id": "b", "distance_km": 4.9, "path": same},
        -20.0: {"id": "c", "distance_km": 5.1, "path": _square_loop(34.02, 127.02, 0.011)},
    }
    monkeypatch.setattr(generate_live, "generate_loop_course",
                        lambda lat, lng, d, tags, **k: loops[k["angle_offset_deg"]])
    ids = [c["id"] for c in generate_live.generate_loop_candidates(34.0, 127.0, 5.0, set())]
    assert "a" not in ids and "b" in ids and "c" in ids


def test_smaller_loop_radius_scales_waypoints_inward():
    full_radius = generate_live.virtual_vertices(34.0, 127.0, 5.0, radius_scale=1.0)
    reduced_radius = generate_live.virtual_vertices(34.0, 127.0, 5.0, radius_scale=0.7)

    full_delta = abs(full_radius[0][1] - 127.0)
    reduced_delta = abs(reduced_radius[0][1] - 127.0)
    assert reduced_delta == pytest.approx(full_delta * 0.7)


def test_snap_projects_vertex_to_middle_of_nearby_road_segment(monkeypatch):
    queries = []

    class Response:
        def json(self):
            return {"elements": [{"geometry": [
                {"lat": 34.0, "lon": 127.0},
                {"lat": 34.0, "lon": 127.002},
            ]}]}

    def post_query(query, timeout):
        queries.append(query)
        return Response()

    monkeypatch.setattr(generate_live, "post_overpass_query", post_query)

    snapped = generate_live.snap_to_runnable_point(34.0005, 127.001)

    assert snapped[0] == pytest.approx(34.0, abs=1e-7)
    assert snapped[1] == pytest.approx(127.001, abs=1e-7)
    assert f"around:{generate_live.SNAP_RADIUS_M}" in queries[0]
    assert '["highway"~' in queries[0]
    assert '["leisure"="park"]' not in queries[0]


def test_snap_rejects_nearest_road_outside_200_meter_radius(monkeypatch):
    class Response:
        def json(self):
            return {"elements": [{"geometry": [
                {"lat": 34.003, "lon": 127.0},
                {"lat": 34.003, "lon": 127.002},
            ]}]}

    monkeypatch.setattr(generate_live, "post_overpass_query", lambda query, timeout: Response())

    assert generate_live.snap_to_runnable_point(34.0, 127.001) is None

class TestDistanceFit:
    """요청 거리와 5% 안: 맞추는 건 나가는 코스 그대로의 길이로 한다 (Tmap 호출 없이)."""

    def _square_with_spur(self, side_m, spur_m=300):
        from src.recommend.generate_live import _offset

        lat, lng = 34.0, 127.0
        def walk(start, bearing, length):
            n = max(1, int(length // 25))
            return [_offset(start[0], start[1], bearing, length * k / n) for k in range(1, n + 1)]
        start = (lat, lng)
        up = walk(start, 0, spur_m)                      # 막다른 길로 들어갔다가
        path = [start] + up + list(reversed(up[:-1])) + [start]   # 같은 길로 되나온다
        for bearing in (90, 180, 270, 0):                # 그리고 한 바퀴
            path += walk(path[-1], bearing, side_m)
        return path

    def test_fit_counts_the_length_left_after_dead_end_spurs_are_cut(self, monkeypatch):
        """막다른 가지는 맞춘 뒤에 잘려 나가서 코스가 짧아졌다 (대전 3km → 2.12km)."""
        from types import SimpleNamespace

        from src.api_clients.tmap_pedestrian import extract_path
        from src.recommend import generate_live as gl

        def route(graph, start, end, waypoints, night=False):
            path = self._square_with_spur(700 * waypoints[0][0])
            total = sum(gl.haversine_m(a, b) for a, b in zip(path, path[1:]))
            return {"features": [{"geometry": {"type": "Point", "coordinates": [127.0, 34.0]}, "properties": {"totalDistance": total}},
                                 {"geometry": {"type": "LineString", "coordinates": [[b, a] for a, b in path]}}]}

        monkeypatch.setattr(gl.road_graph, "route", route)
        area = SimpleNamespace(graph=object())
        chosen = gl._fit_length(area, 34.0, 127.0, 3.0, [(1.0, 0.0)], lambda mult: [(mult, 0.0)], False)
        delivered = gl.prune_spurs(extract_path(route(None, None, None, chosen))[0])
        km = gl.cumulative_distances(delivered)[-1] / 1000
        assert abs(km - 3.0) / 3.0 <= 0.03, km


def test_loops_far_from_the_asked_distance_are_dropped_when_a_close_one_exists():
    from src.recommend.generate_live import keep_useful_loops

    def loop(cid, km, lat):
        return {"id": cid, "distance_km": km, "path": [[lat, 127.0], [lat + 0.01, 127.01], [lat, 127.0]]}

    kept = keep_useful_loops([loop("short", 4.07, 34.0), loop("long", 6.0, 35.0), loop("close", 5.1, 36.0)], 5.0)
    assert [c["id"] for c in kept] == ["close"]


def test_loops_within_ten_percent_stay_as_choices():
    """러너가 고를 수 있게 10% 안의 후보는 남긴다. 고른 코스는 Tmap으로 이을 때 같은 모양으로 5% 안에 맞춘다
    (해운대 바다 5km 순환: 4.68·5.43·4.83km 중 4.83km 하나만 남아 고를 게 없었다)."""
    from src.recommend.generate_live import keep_useful_loops

    def loop(cid, km, lat):
        return {"id": cid, "distance_km": km, "path": [[lat, 127.0], [lat + 0.01, 127.01], [lat, 127.0]]}

    kept = keep_useful_loops([loop("a", 4.68, 34.0), loop("b", 5.43, 35.0), loop("c", 4.83, 36.0)], 5.0)
    assert [c["id"] for c in kept] == ["c", "a", "b"], "목표에 가까운 순서로"


class TestOneWayDistanceFit:
    """편도·왕복도 요청 거리와 5% 안이어야 한다 (해운대 3km 왕복이 2.24km로 나왔다)."""

    def _stub(self, monkeypatch, detour):
        from types import SimpleNamespace

        from src.recommend import generate_live as gl

        # 실제 길은 직선보다 detour배 길다 — 추정(ONE_WAY_DETOUR)과 다르면 처음 잡은 끝점은 빗나간다
        def end(lat, lng, km, route_type, tags, area, offset, scale=1.0):
            leg = km / 2 if route_type == "roundtrip" else km
            return gl._offset(lat, lng, 90, leg * 1000 / gl.ONE_WAY_DETOUR * scale)

        def route(graph, start, goal, waypoints=None, night=False):
            km = gl.haversine_m(start, goal) * detour
            return {"features": [{"geometry": {"type": "Point", "coordinates": [start[1], start[0]]}, "properties": {"totalDistance": km}},
                                 {"geometry": {"type": "LineString", "coordinates": [[start[1], start[0]], [goal[1], goal[0]]]}}]}

        monkeypatch.setattr(gl, "_one_way_end", end)
        monkeypatch.setattr(gl.road_graph, "route", route)
        return gl, SimpleNamespace(graph=object())

    @pytest.mark.parametrize("route_type", ["oneway", "roundtrip"])
    def test_end_point_is_moved_until_the_distance_fits(self, monkeypatch, route_type):
        gl, area = self._stub(monkeypatch, detour=1.75)
        goal = gl._fit_one_way_end(34.0, 127.0, 3.0, route_type, set(), area, 0, False)
        leg_m = gl.haversine_m((34.0, 127.0), goal) * 1.75
        total_km = leg_m * (2 if route_type == "roundtrip" else 1) / 1000
        assert abs(total_km - 3.0) / 3.0 <= 0.03, total_km


def test_one_way_end_on_an_island_crosses_the_bridge():
    """여의도처럼 섬에서 출발하면 직선으로 2km를 그으면 전부 강을 건너 도착점을 못 찾았다.
    도착점은 실제 길로 걸어서 그 거리만큼 가는 곳에서 고른다 — 다리도 길이다."""
    from types import SimpleNamespace

    from src.api_clients.tmap_pedestrian import extract_path
    from src.recommend import generate_live as gl, road_graph as rg

    def way(wid, pts, **tags):
        return {"type": "way", "id": wid, "geometry": [{"lat": a, "lon": b} for a, b in pts], "tags": tags}

    lat, lng = 34.0, 127.0
    island = [(lat, lng + 0.001 * i) for i in range(4)]                         # 섬 안 길 약 270m
    bridge = [island[-1], (lat + 0.006, lng + 0.003)]                            # 다리 약 670m
    land = [bridge[-1]] + [(lat + 0.006, lng + 0.003 + 0.002 * i) for i in range(1, 12)]   # 건너편 길 약 2km
    ways = [way(1, island, highway="footway"), way(2, bridge, highway="footway", bridge="yes"), way(3, land, highway="footway")]
    graph = rg.RoadGraph(ways, {}, rg.PRIOR, facts={}, avoided=set())
    area = SimpleNamespace(graph=graph, roads=ways, indexes={}, covers=lambda *a: True)

    end = gl._fit_one_way_end(lat, lng, 2.5, "oneway", set(), area, 0, False)
    assert end is not None, "섬에서 도착점을 못 찾았다"
    km = extract_path(rg.route(graph, (lat, lng), end))[1] / 1000
    assert abs(km - 2.5) / 2.5 <= 0.05, km


class TestRefitAfterSidewalkCheck:
    """인도 확인이 길을 바꾸면 거리를 다시 맞춘다. 맞춘 설계(6.85km)에서 인도가 확인되지 않은 큰길을 빼고
    다시 짰더니 6.36km(-9%)가 됐다 (광주 7km 순환). 여수는 7.37km가 12.53km가 됐다."""

    def _square(self, km):
        from src.recommend.generate_live import _offset
        side = km * 1000 / 4
        path = [(34.0, 127.0)]
        for bearing in (90, 180, 270, 0):
            n = int(side // 25)
            start = path[-1]
            path += [_offset(start[0], start[1], bearing, side * k / n) for k in range(1, n + 1)]
        return {"router": "local", "no_car_lanes": True,
                "features": [{"geometry": {"type": "LineString", "coordinates": [[b, a] for a, b in path]}}]}

    def _stub(self, monkeypatch, lengths):
        """_route가 차례로 lengths 길이의 코스를 준다. 다시 맞춘 횟수를 센다."""
        from src.recommend import generate_live as gl
        asked, refits = list(lengths), []
        monkeypatch.setattr(gl, "_route", lambda area, start, end, waypoints, night=False: self._square(asked.pop(0)))
        monkeypatch.setattr(gl, "_fit", lambda area, lat, lng, km, wps, rebuild, night, mult=1.0: (refits.append(wps) or [(100 + len(refits), 0)], mult))   # 매번 다른 경유지
        return gl, refits

    def _km(self, gl, route):
        from src.api_clients.tmap_pedestrian import extract_path
        return gl._delivered(extract_path(route)[0])[0]

    def test_a_course_the_sidewalk_check_made_short_is_fitted_again(self, monkeypatch):
        gl, refits = self._stub(monkeypatch, [6.36, 7.05])
        route = gl._routed_to_length(object(), 34.0, 127.0, 7.0, [(1, 1)], lambda m: [(m, m)], False)
        assert len(refits) == 1 and self._km(gl, route) == pytest.approx(7.05, abs=0.02)

    def test_a_course_still_on_length_is_not_fitted_again(self, monkeypatch):
        gl, refits = self._stub(monkeypatch, [7.1])
        route = gl._routed_to_length(object(), 34.0, 127.0, 7.0, [(1, 1)], lambda m: [(m, m)], False)
        assert refits == [] and self._km(gl, route) == pytest.approx(7.1, abs=0.02)

    def test_the_closest_try_is_kept_when_fitting_again_does_not_help(self, monkeypatch):
        gl, refits = self._stub(monkeypatch, [6.6, 8.4, 9.0])
        route = gl._routed_to_length(object(), 34.0, 127.0, 7.0, [(1, 1)], lambda m: [(m, m)], False)
        assert len(refits) == gl.REFIT_ROUNDS and self._km(gl, route) == pytest.approx(6.6, abs=0.02)

    def test_without_a_way_to_rebuild_the_course_is_used_as_it_is(self, monkeypatch):
        gl, refits = self._stub(monkeypatch, [6.36])
        route = gl._routed_to_length(object(), 34.0, 127.0, 7.0, [(1, 1)], None, False)
        assert refits == [] and self._km(gl, route) == pytest.approx(6.36, abs=0.02)

    def test_a_course_on_car_roads_is_not_fitted_again(self, monkeypatch):
        """차도를 지나는 코스는 어차피 버린다 — 다시 맞출 필요가 없다."""
        gl, refits = self._stub(monkeypatch, [6.0])
        real = gl._route
        monkeypatch.setattr(gl, "_route", lambda *a, **k: dict(real(*a, **k), no_car_lanes=False))
        route = gl._routed_to_length(object(), 34.0, 127.0, 7.0, [(1, 1)], lambda m: [(m, m)], False)
        assert refits == [] and route["no_car_lanes"] is False


class TestFitAcrossAJump:
    """거리는 경유지 범위(배율)에 매끄럽게 따라오지 않는다 — 막다른 가지 하나, 다리 하나로 1km씩 뛴다
    (광주 7km: 0.97배 6.07km, 1.12배 8.22km). '목표/실제' 비율로만 고치면 두 값 사이를 오가기만 했다."""

    def _stub(self, monkeypatch, km_at):
        from types import SimpleNamespace

        from src.recommend import generate_live as gl
        tried = []

        def route(graph, start, end, waypoints, night=False):
            mult = waypoints[0][0]
            tried.append(mult)
            return TestRefitAfterSidewalkCheck()._square(km_at(mult))
        monkeypatch.setattr(gl.road_graph, "route", route)
        return gl, SimpleNamespace(graph=object()), tried

    def _km(self, gl, km_at, waypoints):
        return km_at(waypoints[0][0])

    def test_a_length_just_below_the_jump_is_found(self, monkeypatch):
        km_at = lambda m: 7.6 * m if m < 0.9 else 9.5 * m      # 0.894~0.9배에서만 3% 안 (6.79~6.84km)
        gl, area, tried = self._stub(monkeypatch, km_at)
        chosen = gl._fit_length(area, 34.0, 127.0, 7.0, [(1.0, 0.0)], lambda m: [(m, 0.0)], False)
        assert abs(km_at(chosen[0][0]) - 7.0) / 7.0 <= gl.FIT_TOLERANCE, (tried, km_at(chosen[0][0]))

    def test_the_last_waypoints_made_are_also_tried(self, monkeypatch):
        """마지막 판에 만든 경유지를 재 보지도 않고 버렸다 (광주: 버려진 것이 6.88km, 고른 것은 6.36km)."""
        gl, area, tried = self._stub(monkeypatch, lambda m: 7.6 * m if m < 0.9 else 9.5 * m)
        made = []
        gl._fit_length(area, 34.0, 127.0, 7.0, [(1.0, 0.0)], lambda m: made.append(m) or [(m, 0.0)], False)
        assert set(made) <= set(tried), "만든 경유지는 모두 짜 본다"


def test_fitting_again_stops_when_it_gives_the_same_waypoints(monkeypatch):
    """도로망이 그대로면 거리 맞추기는 같은 경유지를 준다 — 같은 길을 다시 짤 필요가 없다."""
    t = TestRefitAfterSidewalkCheck()
    from src.recommend import generate_live as gl
    lengths, refits = [6.36, 6.5, 6.6], []
    monkeypatch.setattr(gl, "_route", lambda area, start, end, waypoints, night=False: t._square(lengths.pop(0)))
    monkeypatch.setattr(gl, "_fit", lambda area, lat, lng, km, wps, rebuild, night, mult=1.0: (refits.append(wps) or [(9, 9)], mult))
    gl._routed_to_length(object(), 34.0, 127.0, 7.0, [(1, 1)], lambda m: [(m, m)], False)
    assert len(refits) == 2 and lengths == [6.6], "두 번째로 맞춘 경유지가 첫 번째와 같으면 짜지 않는다"


def test_fitting_again_starts_from_the_scale_the_waypoints_were_made_at(monkeypatch):
    """처음 맞출 때 1.28배로 만든 경유지를 다시 맞출 때 1배로 알았다 — 0.94~1배만 뒤지다 끝났다 (수원 광교 7km)."""
    t = TestRefitAfterSidewalkCheck()
    from types import SimpleNamespace
    from src.recommend import generate_live as gl
    made = []
    km_at = lambda m: 5.82 * m          # 인도 확인이 큰길을 빼서 도로망에서도 1.28배가 7.45km가 됐다 (1.2배쯤에서 7km)
    monkeypatch.setattr(gl.road_graph, "route", lambda graph, s, e, wps, night=False: t._square(km_at(wps[0][0])))
    lengths = [7.45]                    # 인도 확인이 1.28배 경유지로 짠 7.0km를 7.45km로 바꿨다
    monkeypatch.setattr(gl, "_route", lambda area, s, e, wps, night=False:
                        t._square(lengths.pop(0) if lengths else km_at(wps[0][0])))
    rebuild = lambda m: made.append(m) or [(m, 0.0)]
    gl._routed_to_length(SimpleNamespace(graph=object()), 34.0, 127.0, 7.0, [(1.28, 0.0)], rebuild, False, 1.28)
    assert made and min(made) > 1.1, f"1.28배 근처를 뒤져야 한다: {made}"
    assert km_at(made[-1]) == pytest.approx(7.0, rel=gl.FIT_TOLERANCE)
