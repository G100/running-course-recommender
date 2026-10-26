"""끊기지 않는 길인가: 경로에서 꺾는 횟수와 지나는 갈림길 수를 잰다 (각각 km당).

러너 설문(N=1,228)과 연구 정리(Tegart 외 2025, 논문 102편)에서 러너가 좋아하는 길은 멈추지 않고
쭉 이어지는 길이다. 멈춤(신호등)만으로는 부족하다 — 신호가 없어도 골목을 이리저리 꺾거나 갈림길마다
차·사람을 살펴야 하면 흐름이 끊긴다. 둘 다 경로 모양과 도로망에서 바로 셀 수 있는 객관적인 값이다.
"""
import math

from ..data_collection.enrich import haversine_m
from ..data_collection.scenery import resample

TURN_STEP_M = 20         # 20m 간격으로 다시 찍고
TURN_WINDOW = 2          # 앞뒤 40m의 방향을 비교해
TURN_MIN_DEG = 35        # 35° 넘게 바뀌면 꺾은 것 (보도 따라 살짝 휘는 건 세지 않는다)
JUNCTION_NEAR_M = 8      # 경로 8m 안에 있는
JUNCTION_MIN_ROADS = 3   # 세 갈래 이상 갈림길을
JUNCTION_MERGE_M = 30    # 30m 안에 몰린 노드는 교차로 하나로 쳐서 센다


def _km(path: list) -> float:
    return sum(haversine_m(a, b) for a, b in zip(path, path[1:])) / 1000


def _bearing(a, b) -> float:
    dy = b[0] - a[0]
    dx = (b[1] - a[1]) * math.cos(math.radians(a[0]))
    return math.degrees(math.atan2(dx, dy)) % 360


def turns_per_km(path: list) -> float:
    km = _km(path)
    if km <= 0:
        return 0.0
    pts = resample(path, TURN_STEP_M)
    w, n, i = TURN_WINDOW, 0, TURN_WINDOW
    while i < len(pts) - w:
        before, after = _bearing(pts[i - w], pts[i]), _bearing(pts[i], pts[i + w])
        if abs((after - before + 540) % 360 - 180) >= TURN_MIN_DEG:
            n += 1
            i += w + 1       # 한 번 꺾은 곳을 여러 번 세지 않게 건너뛴다
        else:
            i += 1
    return round(n / km, 2)


def junctions_per_km(path: list, graph) -> float:
    km = _km(path)
    if km <= 0:
        return 0.0
    counted = []
    for p in resample(path, 10):
        r, c = graph._cell(tuple(p))
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                for node in graph._grid.get((r + dr, c + dc), ()):
                    if len({nb for nb, *_ in graph.adjacent[node]}) < JUNCTION_MIN_ROADS:
                        continue
                    if haversine_m(p, node) > JUNCTION_NEAR_M:
                        continue
                    if counted and haversine_m(counted[-1], node) <= JUNCTION_MERGE_M:
                        continue
                    counted.append(node)
    return round(len(counted) / km, 2)
