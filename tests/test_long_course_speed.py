"""긴 코스에서도 계산이 오래 걸리지 않는다 — 결과는 예전과 똑같다.

21km 순환 요청 하나에 16분이 걸렸고, 그중 12분이 두 점 사이 거리 계산 2억 1천만 번이었다. 코스의 모든 점을
다른 모든 점과 비교하던 곳이 원인이다(거리가 2배면 계산은 4배). 가까운 칸의 점만 비교하면 결과는 같고
계산은 코스 길이에 비례한다.
"""
import random

import pytest

from src.data_collection.enrich import haversine_m
from src.recommend import generate_live, point_grid, tmap_follow
from src.recommend.point_grid import PointGrid
from src.recommend.step_position import cumulative_distances

LAT0, LNG0 = 35.16, 129.16
M_LAT, M_LNG = 111_320, 111_320 * 0.8176


def at(north_m, east_m):
    return [LAT0 + north_m / M_LAT, LNG0 + east_m / M_LNG]


def wander(seed, steps, step_m=25, spur_every=40):
    """이리저리 꺾이며 가다가 가끔 막다른 길에 들어갔다 그대로 되나오는 경로."""
    rng = random.Random(seed)
    n = e = 0.0
    heading = 0
    path = [at(n, e)]
    for k in range(1, steps + 1):
        if rng.random() < 0.15:
            heading = (heading + rng.choice((90, -90))) % 360
        dn, de = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}[heading]
        n, e = n + dn * step_m, e + de * step_m
        path.append(at(n, e))
        if k % spur_every == 0:   # 옆으로 150m 들어갔다 같은 길로 나온다
            sn, se = de, -dn
            out = [at(n + sn * step_m * i, e + se * step_m * i) for i in range(1, 7)]
            path += out + list(reversed(out[:-1])) + [at(n, e)]
    return path


# ── 예전 방식 (모든 점을 모든 점과 비교). 결과가 같은지 견주는 기준이다 ──

def old_is_out_and_back(segment):
    if len(segment) < 3:
        return False
    far = max(range(len(segment)), key=lambda k: haversine_m(segment[0], segment[k]))
    outbound, inbound = segment[: far + 1], segment[far:]
    if len(inbound) < 2:
        return False
    overlapping = sum(1 for q in inbound if any(haversine_m(q, o) <= generate_live.SPUR_NEAR_M for o in outbound))
    return overlapping / len(inbound) >= generate_live.SPUR_OVERLAP


def old_prune_with_spans(path):
    if len(path) < 4:
        return path, []
    cum = cumulative_distances(path)
    kept, spans, i, last = [path[0]], [], 0, len(path) - 1
    while i < last:
        jump = None
        for j in range(last - 1, i + 1, -1):
            if cum[j] - cum[i] < generate_live.SPUR_MIN_LENGTH_M:
                break
            if haversine_m(path[i], path[j]) <= generate_live.SPUR_NEAR_M and old_is_out_and_back(path[i: j + 1]):
                jump = j
                break
        if jump is not None:
            spans.append((cum[i], cum[jump]))
            i = jump
        else:
            i += 1
        kept.append(path[i])
    return kept, spans


def old_share_near(a, b):
    pts, ref = tmap_follow._dense(a), tmap_follow._dense(b, 10)
    if not pts or not ref:
        return 0.0
    return sum(1 for p in pts if min(haversine_m(p, q) for q in ref) <= tmap_follow.MATCH_M) / len(pts)


# ── 결과는 예전과 같다 ──

def test_grid_finds_exactly_the_points_within_the_radius():
    rng = random.Random(1)
    points = [at(rng.uniform(-400, 400), rng.uniform(-400, 400)) for _ in range(600)]
    grid = PointGrid(points, 15)
    for probe in [at(rng.uniform(-420, 420), rng.uniform(-420, 420)) for _ in range(200)] + points[:50]:
        expected = [i for i, p in enumerate(points) if haversine_m(probe, p) <= 15]
        assert sorted(grid.near(probe)) == expected
        assert grid.any_near(probe) == bool(expected)


def test_grid_with_no_points_finds_nothing():
    assert PointGrid([], 15).near(at(0, 0)) == [] and not PointGrid([], 15).any_near(at(0, 0))


@pytest.mark.parametrize("seed", range(8))
def test_spurs_are_cut_exactly_as_before(seed):
    path = wander(seed, steps=260)
    kept, spans = generate_live._prune_with_spans(path)
    old_kept, old_spans = old_prune_with_spans(path)
    assert spans == old_spans and kept == old_kept
    assert spans, "이 경로에는 잘라낼 가지가 있어야 한다 (없으면 견줄 것이 없다)"


@pytest.mark.parametrize("seed", range(8))
def test_out_and_back_is_judged_exactly_as_before(seed):
    path = wander(seed, steps=120)
    rng = random.Random(seed)
    for _ in range(60):
        i = rng.randrange(0, len(path) - 3)
        segment = path[i: i + rng.randrange(3, 60)]
        assert generate_live._is_out_and_back(segment) == old_is_out_and_back(segment)


@pytest.mark.parametrize("seed", range(6))
def test_share_of_a_path_near_another_is_measured_exactly_as_before(seed):
    plan = wander(seed, steps=200, spur_every=10_000)
    rng = random.Random(seed)
    # 실제로 달릴 경로: 계획을 조금 비켜 가다가 중간 한 토막은 60m 떨어진 다른 길로 간다
    driven = [[p[0] + (60 / M_LAT if 70 < i < 110 else rng.uniform(-8, 8) / M_LAT), p[1]] for i, p in enumerate(plan)]
    assert tmap_follow._share_near(plan, driven) == old_share_near(plan, driven)
    assert tmap_follow._share_near(driven, plan) == old_share_near(driven, plan)
    assert 0.5 < tmap_follow._share_near(plan, driven) < 1.0


def test_share_near_of_an_empty_path_is_zero():
    assert tmap_follow._share_near([], wander(0, 20)) == 0.0 and tmap_follow._share_near(wander(0, 20), []) == 0.0


# ── 계산은 코스 길이에 비례한다 ──

@pytest.fixture
def distance_calls(monkeypatch):
    """두 점 사이 거리 계산이 몇 번 불렸는지 센다 (시간은 PC마다 달라서 횟수로 본다)."""
    calls = {"n": 0}

    def counted(a, b):
        calls["n"] += 1
        return haversine_m(a, b)

    for module in (generate_live, tmap_follow, point_grid):
        monkeypatch.setattr(module, "haversine_m", counted)
    return calls


def test_cutting_spurs_on_a_marathon_course_does_not_compare_every_point_with_every_other(distance_calls):
    path = wander(3, steps=1700)          # 약 42km, 점 2천 개 남짓
    generate_live._prune_with_spans(path)
    assert distance_calls["n"] < 60 * len(path), f"점 {len(path)}개에 거리 계산 {distance_calls['n']:,}번"


def test_comparing_two_marathon_courses_does_not_compare_every_point_with_every_other(distance_calls):
    plan = wander(4, steps=1700, spur_every=10_000)
    driven = [[p[0] + 5 / M_LAT, p[1]] for p in plan]
    dense = len(tmap_follow._dense(plan))
    distance_calls["n"] = 0
    tmap_follow._share_near(plan, driven)
    assert distance_calls["n"] < 60 * dense, f"점 {dense}개에 거리 계산 {distance_calls['n']:,}번"


def old_retraced_ratio(path):
    if len(path) < 3:
        return 0.0
    cum = cumulative_distances(path)
    total = cum[-1] or 1.0
    retraced = 0.0
    for i in range(1, len(path)):
        if cum[i] > total - 150:
            break
        if any(haversine_m(path[i], path[j]) < generate_live.SPUR_NEAR_M for j in range(i) if cum[i] - cum[j] > 150):
            retraced += cum[i] - cum[i - 1]
    return retraced / total


@pytest.mark.parametrize("seed", range(8))
def test_retraced_share_is_measured_exactly_as_before(seed):
    path = wander(seed, steps=300)
    assert generate_live.retraced_ratio(path) == old_retraced_ratio(path)
    assert generate_live.retraced_ratio(path) > 0, "가지가 있어 되짚는 구간이 있어야 견줄 수 있다"


def test_measuring_retraced_share_on_a_marathon_course_does_not_compare_every_point(distance_calls):
    path = wander(5, steps=1700)
    cumulative_distances(path)
    distance_calls["n"] = 0
    generate_live.retraced_ratio(path)
    assert distance_calls["n"] < 60 * len(path), f"점 {len(path)}개에 거리 계산 {distance_calls['n']:,}번"


# ── 스스로 꼬였는지, 안전 점수도 예전과 같고 코스 길이에 비례한다 ──

def old_has_self_intersection(path):
    if len(path) < 4:
        return False
    points = [tuple(p) for p in path]
    n = len(points) - 1
    for first in range(n):
        for second in range(first + 1, n):
            if second - first <= 1 or (first == 0 and second == n - 1):
                continue
            if generate_live._segments_intersect(points[first], points[first + 1], points[second], points[second + 1]):
                return True
    return False


def scribble(seed, steps, step_m=40):
    """방향을 자주 바꾸며 가는 경로 — 가끔 자기 길을 가로지른다."""
    rng = random.Random(seed)
    n = e = 0.0
    path = [at(0, 0)]
    for _ in range(steps):
        heading = rng.uniform(0, 6.283)
        import math
        n, e = n + math.cos(heading) * step_m, e + math.sin(heading) * step_m * 0.3 + step_m * 0.2
        path.append(at(n, e))
    return path


def loop_of(path):
    """같은 곳으로 돌아오는 고리 (닫는 선분 둘은 검사에서 빠진다)."""
    return path + [path[0]]


@pytest.mark.parametrize("seed", range(12))
def test_self_crossing_is_judged_exactly_as_before(seed):
    for path in (scribble(seed, 30), scribble(seed, 300), loop_of(wander(seed, 200, spur_every=10_000)),
                 loop_of(scribble(seed, 8)), wander(seed, 120)):
        assert generate_live.has_self_intersection(path) == old_has_self_intersection(path)


def test_self_crossing_cases_both_ways_are_covered():
    results = {old_has_self_intersection(scribble(seed, 30)) for seed in range(12)}
    assert results == {True, False}, "꼬인 경로와 안 꼬인 경로가 둘 다 있어야 견줄 수 있다"


def test_a_crossing_at_a_cell_corner_is_still_found():
    """칸 경계에 걸친 교차도 찾는다 — 두 선분이 서로 다른 칸에 담겨도 교차점이 있는 칸은 함께 갖는다."""
    square = [at(0, 0), at(0, 400), at(400, 400), at(400, 200), at(-100, 200), at(-100, 300)]   # 넷째 선분이 첫째를 가로지른다
    assert generate_live.has_self_intersection(square) and old_has_self_intersection(square)


def test_checking_a_marathon_loop_for_crossings_does_not_compare_every_segment(monkeypatch):
    path = loop_of(wander(6, steps=1700, spur_every=10_000))
    calls = {"n": 0}
    real = generate_live._segments_intersect

    def counted(*a):
        calls["n"] += 1
        return real(*a)

    monkeypatch.setattr(generate_live, "_segments_intersect", counted)
    generate_live.has_self_intersection(path)
    assert calls["n"] < 60 * len(path), f"선분 {len(path)}개에 교차 검사 {calls['n']:,}번"


def facilities(seed, count, spread_m=1500):
    rng = random.Random(seed)
    return [dict(zip(("lat", "lng"), at(rng.uniform(-spread_m, spread_m), rng.uniform(-spread_m, spread_m))))
            for _ in range(count)]


def old_count_near_path(points, path, radius_m=150):
    return sum(1 for p in points if any(haversine_m((p["lat"], p["lng"]), (q[0], q[1])) <= radius_m for q in path))


@pytest.mark.parametrize("seed", range(6))
def test_safety_counts_are_exactly_as_before(seed):
    from src.recommend import safety
    path = wander(seed, steps=200)
    for count in (0, 5, 300):
        points = facilities(seed, count)
        assert safety._count_near_path(points, path) == old_count_near_path(points, path)
    assert 0 < safety._count_near_path(facilities(seed, 300), path) < 300, "가까운 시설과 먼 시설이 섞여야 견줄 수 있다"


def test_safety_on_a_marathon_course_does_not_compare_every_point_with_every_facility(distance_calls, monkeypatch):
    from src.recommend import safety
    monkeypatch.setattr(safety, "haversine_m", point_grid.haversine_m)   # 같은 세는 함수를 쓴다
    path = wander(7, steps=1700)
    points = facilities(7, 2000, spread_m=6000)
    distance_calls["n"] = 0
    safety._count_near_path(points, path)
    assert distance_calls["n"] < 60 * (len(path) + len(points)), f"거리 계산 {distance_calls['n']:,}번"


# ── 길 찾기: 목표 쪽을 먼저 본다 (가장 좋은 길은 예전과 같다) ──

def old_shortest(graph, start, goal, used=None, max_m=30000, night=False):
    """예전 길 찾기 (목표 방향을 모르고 사방으로 넓혀 간다)."""
    import heapq
    from src.recommend import road_graph as rg
    used = used or set()
    best, came, heap = {start: 0.0}, {}, [(0.0, 0.0, start)]
    while heap:
        cost, length, node = heapq.heappop(heap)
        if node == goal:
            break
        if cost > best.get(node, float("inf")) or length > max_m:
            continue
        for neighbour, edge_m, way in graph.adjacent[node]:
            if graph.surfaces[way] == rg.BLOCKED:
                continue
            new_cost = cost + edge_m * edge_factor(graph, node, neighbour, way, used, night)
            if new_cost < best.get(neighbour, float("inf")):
                best[neighbour] = new_cost
                came[neighbour] = (node, way)
                heapq.heappush(heap, (new_cost, length + edge_m, neighbour))
    if goal not in came and goal != start:
        return None
    hops, node = [(goal, None)], goal
    while node != start:
        node, way = came[node]
        hops.append((node, way))
    return hops[::-1]


def edge_factor(graph, node, neighbour, way, used, night):
    from src.recommend import road_graph as rg
    factor = (1 + rg.DETOUR_FOR_BAD_ROAD * (1 - graph.way_score(way))) * rg.SURFACE_PENALTY[graph.surfaces[way]]
    if night:
        factor *= rg.NIGHT_PENALTY[graph.night_kind(way)]
    if (node, neighbour) in used or (neighbour, node) in used:
        factor *= rg.REUSE_PENALTY
    if way in graph.avoided:
        factor *= rg.TMAP_AVOIDED_PENALTY
    return factor


def hops_cost(graph, hops, used=frozenset(), night=False):
    return sum(haversine_m(a, b) * edge_factor(graph, a, b, way, used, night)
               for (a, way), (b, _) in zip(hops, hops[1:]))


def street_grid(seed, size=24, block_m=80):
    """바둑판 동네: 길마다 종류가 제각각이고, 몇몇 길은 막혀 있다."""
    from src.data_collection.scenery import build_indexes
    from src.recommend import road_graph as rg
    rng = random.Random(seed)
    kinds = ["footway", "residential", "primary", "service", "steps", "secondary", "living_street"]
    ways, wid = [], 1
    for i in range(size):
        for j in range(size):
            for di, dj in ((1, 0), (0, 1)):
                if i + di < size and j + dj < size and rng.random() > 0.12:
                    a, b = at(i * block_m, j * block_m), at((i + di) * block_m, (j + dj) * block_m)
                    mid = at((i + di / 2) * block_m + rng.uniform(-15, 15), (j + dj / 2) * block_m + rng.uniform(-15, 15))
                    tags = {"highway": rng.choice(kinds)}
                    if tags["highway"] in ("primary", "secondary") and rng.random() < 0.5:
                        tags["sidewalk"] = "both"
                    ways.append({"type": "way", "id": wid, "geometry": [{"lat": p[0], "lon": p[1]} for p in (a, mid, b)],
                                 "tags": tags})
                    wid += 1
    graph = rg.RoadGraph(ways, build_indexes({"all": ways}), rg.PRIOR)
    nodes = list(graph.adjacent)
    for way in rng.sample(range(len(graph.surfaces)), 8):
        graph.avoided.add(way)
    return graph, nodes, rng


@pytest.mark.parametrize("seed", range(6))
def test_the_best_path_is_as_good_as_before(seed):
    graph, nodes, rng = street_grid(seed)
    same = 0
    for k in range(25):
        start, goal = rng.sample(nodes, 2)
        night = k % 3 == 0
        old = old_shortest(graph, start, goal, night=night)
        used = set()
        if old and k % 2 == 0:
            used = {(a, b) for (a, _), (b, _) in zip(old[: len(old) // 2], old[1: len(old) // 2 + 1])}
            old = old_shortest(graph, start, goal, used=used, night=night)
        new = graph.shortest(start, goal, used=used, night=night)
        assert (old is None) == (new is None)
        if old is None:
            continue
        assert hops_cost(graph, new, used, night) == pytest.approx(hops_cost(graph, old, used, night), rel=1e-9)
        same += new == old
    assert same >= 20, "점수가 똑같은 길이 둘일 때만 다른 길을 고를 수 있다"


def test_finding_a_path_looks_at_fewer_places(monkeypatch):
    """목표 쪽을 먼저 보면 둘러보는 곳이 준다."""
    graph, nodes, rng = street_grid(9, size=40)
    start, goal = tuple(at(0, 0)), tuple(at(20 * 80, 20 * 80))
    scores = {"n": 0}
    real = graph.way_score

    def counted(way):
        scores["n"] += 1
        return real(way)

    monkeypatch.setattr(graph, "way_score", counted)
    old_shortest(graph, start, goal)
    before, scores["n"] = scores["n"], 0
    graph.shortest(start, goal)
    assert scores["n"] < before, (scores["n"], before)
