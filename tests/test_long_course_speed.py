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
