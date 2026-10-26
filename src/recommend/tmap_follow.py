"""우리 모델이 짠 코스를 Tmap 보행자 경로가 그대로 따라가게 한다.

어느 길로 돌지는 우리가 정한다(풍경·거리·취향·밤 안전). Tmap은 그 길을 실제 보행 네트워크(인도·횡단보도)로
이어 주고, 구간마다 길 종류와 회전 안내를 붙여 준다. 사용자는 Tmap이 이어 준 바로 그 경로를 달린다 —
그래서 인도인지는 그 경로에 Tmap이 직접 붙인 길 종류로 확인한다(우리 길과 좌표로 맞춰 볼 필요가 없다).

Tmap은 경유지 사이를 최단거리로 잇는다. 경유지 5개만 주면 그 사이를 지름길로 질러가 우리 코스를 벗어났다
(여의도 강변 5km: 우리 코스의 56%만 따라감). 그래서
  1. 우리 코스를 따라가며, 최단거리로 이으면 코스를 벗어나는 갈림길 바로 앞에만 경유지를 찍는다
     (큰길 한가운데 찍으면 Tmap이 양쪽 인도 중 아무 데나 붙어 길을 건넜다 왔다 해서 교차로에 찍는다)
  2. 경유지가 5개를 넘으면 여러 번 나눠 묻고 이어 붙인다
  3. 받은 경로가 우리 코스와 얼마나 겹치는지 재고, 어긋난 곳에 점을 더 찍어 한 번 더 묻는다
(같은 곳에서 56% → 93%)
"""
import heapq
import os

from ..api_clients.tmap_pedestrian import extract_path, get_route
from ..data_collection.enrich import haversine_m
from . import sidewalk
from .flow import junctions_per_km

MATCH_M = 35        # 이만큼 안이면 같은 길 (넓은 길은 맞은편 인도까지 30m 가까이 된다)
PER_CALL = 5        # Tmap passList 한도
PROBE_M = 40        # 코스를 이 간격으로 짚어 가며 최단거리와 같은지 본다
SAME_RATIO = 0.97   # 우리 길이 최단거리의 이 비율 안이면 Tmap도 그 길로 간다고 본다
FOLLOW_MIN = 0.85   # 우리 코스의 이만큼은 따라가야 통과
MIN_GAP_M = 10      # 연달아 찍는 두 점이 이보다 가까우면 하나만 보낸다


def _shortest_m(graph, a, b, limit_m):
    """길이만 보는 최단거리 (Tmap이 하는 것). 닿지 않으면 None."""
    dist, heap = {a: 0.0}, [(0.0, a)]
    while heap:
        d, node = heapq.heappop(heap)
        if node == b:
            return d
        if d > dist.get(node, float("inf")) or d > limit_m:
            continue
        for nxt, length, way in graph.adjacent[node]:
            if graph.surfaces[way] is None or way in getattr(graph, "avoided", ()):
                continue   # Tmap이 피하는 길로는 Tmap도 가지 않는다
            nd = d + length
            if nd < dist.get(nxt, float("inf")):
                dist[nxt] = nd
                heapq.heappush(heap, (nd, nxt))
    return None


def _is_junction(graph, node) -> bool:
    return len(graph.adjacent.get(node, ())) >= 3


def needed_waypoints(graph, nodes: list) -> list:
    """우리 코스(도로망 노드 목록)를 Tmap이 그대로 따라가게 하는 데 꼭 필요한 경유지만."""
    nodes = [tuple(n) for n in nodes]
    cum = [0.0]
    for a, b in zip(nodes, nodes[1:]):
        cum.append(cum[-1] + haversine_m(a, b))
    picks, i = [], 0
    while True:
        last_ok, j = None, i + 1
        while j < len(nodes):
            if cum[j] - cum[i] >= PROBE_M or j == len(nodes) - 1:
                along = cum[j] - cum[i]
                shortest = _shortest_m(graph, nodes[i], nodes[j], along * 1.2 + 50)
                if shortest is None or shortest < along * SAME_RATIO:
                    break   # 여기까지 최단거리로 이으면 우리 코스를 벗어난다
                last_ok = j
            j += 1
        if j >= len(nodes):
            return picks
        k = last_ok if last_ok is not None else j
        for back in range(k, i, -1):
            if _is_junction(graph, nodes[back]):
                k = back
                break
        picks.append(nodes[k])
        i = k


def stitch(start: tuple, end: tuple, points: list) -> tuple:
    """start → points → end 를 경유지 PER_CALL개씩 끊어 Tmap에 묻고 이어 붙인다. (경로, 호출 수)."""
    stops = [tuple(start)]
    for p in [tuple(p) for p in points] + [tuple(end)]:
        # 같은 자리를 연달아 주면 Tmap이 400으로 거절한다 ("waypoints are too near"). 20m 떨어지면 받는다
        if haversine_m(stops[-1], p) >= MIN_GAP_M or p == tuple(end) and len(stops) == 1:
            stops.append(p)
        elif p == tuple(end):
            stops[-1] = p
    features, total, calls, i = [], 0, 0, 0
    while i < len(stops) - 1:
        chunk = stops[i:i + PER_CALL + 2]
        res = get_route((chunk[0][1], chunk[0][0]), (chunk[-1][1], chunk[-1][0]), start_name="출발지", end_name="도착지",
                        waypoints=[(lng, lat) for lat, lng in chunk[1:-1]])
        calls += 1
        _, distance = extract_path(res)
        total += distance
        first, last = i == 0, i + len(chunk) - 1 >= len(stops) - 1
        features += [f for f in (_runner_facing(f, first, last) for f in res.get("features", [])) if f]
        i += len(chunk) - 1
    head = {"geometry": {"type": "Point", "coordinates": [start[1], start[0]]}, "properties": {"totalDistance": total}}
    return {"features": [head] + features}, calls


WAYPOINT_TURNS = {184, 185, 186, 187, 188, 189}   # Tmap의 '경유지' 안내
START_TURN, ARRIVE_TURN = 200, 201


def _runner_facing(feature: dict, first: bool, last: bool):
    """나눠 물은 Tmap 응답을 이을 때, 러너에게 의미 없는 안내를 뺀다: 경유지 안내("경유지 후 47m 이동"),
    중간 조각의 '도착'과 '출발'. 러너에게 경유지는 없다 — 출발 하나, 도착 하나만 남긴다. 진짜 회전 안내는 그대로."""
    if feature["geometry"]["type"] != "Point":
        return feature
    props = feature.get("properties", {})
    turn = props.get("turnType")
    if "totalDistance" in props:            # 조각마다 있는 첫 점(전체 거리 포함) — 거리는 이은 쪽이 새로 센다
        if not first:
            return None
        props = {k: v for k, v in props.items() if k != "totalDistance"}
        return dict(feature, properties=props)
    if (turn in WAYPOINT_TURNS or str(props.get("description", "")).startswith("경유지")
            or (turn == ARRIVE_TURN and not last) or (turn == START_TURN and not first)):
        return None
    return feature


def _dense(path: list, every: float = 15) -> list:
    out = []
    for a, b in zip(path, path[1:]):
        n = max(1, int(haversine_m(a, b) // every))
        out += [(a[0] + (b[0] - a[0]) * t / n, a[1] + (b[1] - a[1]) * t / n) for t in range(n)]
    return out + [tuple(path[-1])] if path else out


def _share_near(a: list, b: list) -> float:
    """a의 몇 %(길이 기준)가 b에서 MATCH_M 안에 있나."""
    pts, ref = _dense(a), _dense(b, 10)
    if not pts or not ref:
        return 0.0
    return sum(1 for p in pts if min(haversine_m(p, q) for q in ref) <= MATCH_M) / len(pts)


def check(route_json: dict, plan_path: list, graph=None) -> dict:
    path, distance = extract_path(route_json)
    road_mix = sidewalk.mix_of(sidewalk.resolve(route_json, graph))
    covered, follows = _share_near(plan_path, path), _share_near(path, plan_path)
    return {"ok": covered >= FOLLOW_MIN and follows >= FOLLOW_MIN and not road_mix.get("car_lane"),
            "plan_covered": round(covered, 3), "follows_plan": round(follows, 3),
            "distance_km": round(distance / 1000, 2), "road_mix": road_mix}


def _off_course(graph, tmap_path: list, nodes: list) -> list:
    """우리 코스 중 Tmap 경로에서 벗어난 구간마다 하나씩, 가운데에 가까운 교차로 노드."""
    ref = _dense(tmap_path, 10)
    off = [min(haversine_m(n, q) for q in ref) > MATCH_M for n in nodes]
    spots, k = [], 0
    while k < len(off):
        if off[k]:
            s = k
            while k < len(off) and off[k]:
                k += 1
            mid = (s + k) // 2
            near = [n for n in range(max(0, s - 3), min(len(nodes), k + 3)) if _is_junction(graph, nodes[n])]
            spots.append(nodes[min(near, key=lambda n: abs(n - mid))] if near else nodes[mid])
        k += 1
    return spots


def _nodes(graph, plan_path: list) -> list:
    nodes = []
    for lat, lng in plan_path:
        node = (lat, lng) if (lat, lng) in graph.adjacent else graph.nearest_node(lat, lng)
        if node is not None and (not nodes or nodes[-1] != node):
            nodes.append(node)
    return nodes


ANCHOR_M = 300   # 다시 짤 때 우리 코스의 모양을 지키려고 이 간격으로 붙잡는 점
SPIKE_MAX_M = 400   # 들어갔다 나오는 길이(왕복 합)가 이 이하면 '삐죽' 구간이다. 더 길면 코스 모양 자체다(왕복 코스)
SPIKE_TIP_M = 40    # 삐죽 구간 끝에서 이만큼 안의 경유지가 Tmap을 그리로 끌고 간 것이다


def _spike_tips(path: list) -> list:
    """경로에서 짧게 들어갔다가 같은 길로 되나오는 구간들의 끝점."""
    from .generate_live import _prune_with_spans
    from .step_position import cumulative_distances

    spans = [span for span in _prune_with_spans(path)[1] if span[1] - span[0] <= SPIKE_MAX_M]
    if not spans:
        return []
    cum = cumulative_distances(path)
    tips = []
    for begin, finish in spans:
        inside = [i for i, c in enumerate(cum) if begin <= c <= finish]
        if inside:
            origin = path[inside[0]]
            tips.append(tuple(max((path[i] for i in inside), key=lambda q: haversine_m(origin, q))))
    return tips


def _spike_m(path: list) -> float:
    from .generate_live import _prune_with_spans
    return sum(b - a for a, b in _prune_with_spans(path)[1] if b - a <= SPIKE_MAX_M)


def remove_spikes(graph, start: tuple, end: tuple, points: list, route: dict, calls: int) -> tuple:
    """Tmap 경로의 '삐죽' 구간(경유지가 옆길·맞은편에 찍혀 거기까지 들어갔다 되나오는 곳)을 없앤다.
    그 끝에 있는 경유지를 빼고 다시 묻는다. 다시 물은 게 더 나으면 그것을 쓴다. (경로, 경유지, 호출 수)"""
    path = extract_path(route)[0]
    tips = _spike_tips(path)
    bad = {p for p in points if any(haversine_m(p, tip) <= SPIKE_TIP_M for tip in tips)}
    if not bad:
        return route, points, calls
    kept = [p for p in points if p not in bad]
    again, more = stitch(start, end, kept)
    if _spike_m(extract_path(again)[0]) < _spike_m(path):
        return again, kept, calls + more
    return route, points, calls + more


def _skipped_ways(graph, nodes: list, tmap_path: list) -> set:
    """우리 코스 중 Tmap이 타지 않은 구간 밑의 길들 — 대개 Tmap 지도에 없는 공원·단지 안 보행로다."""
    ref = _dense(tmap_path, 10)
    skipped = set()
    for a, b in zip(nodes, nodes[1:]):
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if min(haversine_m(mid, q) for q in ref) > MATCH_M:
            skipped.update(way for neighbour, _, way in graph.adjacent.get(a, ()) if neighbour == b)
    return skipped


def _replan_around(graph, nodes: list, skipped: set):
    """Tmap이 타지 않은 길을 빼고, 나머지 코스 모양은 지키며 다시 짠다. (새 코스, Tmap에 줄 경유지) 또는 None."""
    from .road_graph import BLOCKED, route

    saved = {way: graph.surfaces[way] for way in skipped}
    for way in skipped:
        graph.surfaces[way] = BLOCKED
    try:
        usable = lambda n: any(graph.surfaces[way] != BLOCKED for _, _, way in graph.adjacent.get(n, ()))
        anchors, last = [], nodes[0]
        for node in nodes[1:-1]:
            if haversine_m(last, node) >= ANCHOR_M and usable(node):
                anchors.append(node)
                last = node
        replanned = route(graph, nodes[0], nodes[-1], anchors)
        if replanned is None:
            return None
        new_nodes = _nodes(graph, extract_path(replanned)[0])
        # 경유지도 막아 둔 채로 고른다 — Tmap 지도처럼 그 길이 없다고 보고 지름길이 생기는 곳을 찾는다
        return replanned, needed_waypoints(graph, new_nodes)
    finally:
        for way, kind in saved.items():
            graph.surfaces[way] = kind


DISTANCE_OK = 0.05   # 요청 거리와 이 비율 안이어야 한다


def _better(a: dict, b: dict, target_km: float) -> bool:
    """a가 b보다 나은가: 요청 거리와 5% 안인 것이 먼저(거리가 틀리면 안 된다), 그다음 검사 통과,
    그다음 거리가 더 가까운 것, 그다음 우리 설계를 더 따라간 것."""
    gap = lambda r: abs(r["distance_km"] - target_km) / target_km if target_km else 0
    rank = lambda r: (gap(r) > DISTANCE_OK, not r["ok"], gap(r), -r["plan_covered"])
    return rank(a) < rank(b)


# ── Tmap이 탄 길·피한 길을 쌓는다 ──

RIDDEN_SHARE, AVOIDED_SHARE, MIN_WAY_M = 0.8, 0.2, 40


def way_id(points: list) -> str:
    """길 식별자: 양 끝과 가운데 꼭짓점. 양 끝만 보면 같은 두 교차로를 잇는 다른 길(공원 안 길과 바깥 길)이
    같은 길로 섞여, Tmap이 한쪽은 타고 한쪽은 피했다는 기록이 서로 지워졌다."""
    a, m, b = points[0], points[len(points) // 2], points[-1]
    return f"{a[0]:.6f},{a[1]:.6f},{m[0]:.6f},{m[1]:.6f},{b[0]:.6f},{b[1]:.6f}"


def _ride_votes(graph, nodes: list, tmap_path: list) -> dict:
    """우리 코스 밑의 길마다: Tmap 경로가 그 길 대부분을 탔으면 True, 거의 안 탔으면 False."""
    ref = _dense(tmap_path, 10)
    near, total = {}, {}
    for a, b in zip(nodes, nodes[1:]):
        ways = [way for neighbour, _, way in graph.adjacent.get(a, ()) if neighbour == b]
        if not ways:
            continue
        length = haversine_m(a, b)
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        on = min(haversine_m(mid, q) for q in ref) <= MATCH_M
        for way in ways:
            total[way] = total.get(way, 0) + length
            near[way] = near.get(way, 0) + (length if on else 0)
    votes = {}
    for way, length in total.items():
        share = near[way] / length
        if share >= RIDDEN_SHARE:
            votes[way] = True
        elif share <= AVOIDED_SHARE and length >= MIN_WAY_M:
            votes[way] = False
    return votes


def remember_ways(facts: dict) -> None:
    """{길 키: True(Tmap이 탔다) / False(피했다)}를 쌓는다."""
    if not facts:
        return
    with sidewalk._open() as db:
        for key, ridden in facts.items():
            db.execute("INSERT OR IGNORE INTO tmap_ways (way) VALUES (?)", (key,))
            column = "ridden" if ridden else "avoided"
            db.execute(f"UPDATE tmap_ways SET {column} = {column} + 1 WHERE way = ?", (key,))


def tmap_avoided() -> set:
    """Tmap이 피했고 한 번도 탄 적 없는 길들. 한 번이라도 탔으면 Tmap 지도에 있는 길이다 —
    피한 건 그때 다른 길이 더 짧았을 뿐이다."""
    if not os.path.exists(sidewalk.FACTS_PATH):
        return set()
    with sidewalk._open() as db:
        return {way for way, in db.execute("SELECT way FROM tmap_ways WHERE avoided > 0 AND ridden = 0")}


def _learn(graph, nodes: list, tmap_path: list) -> None:
    votes = _ride_votes(graph, nodes, tmap_path)
    remember_ways({way_id(graph.ways[way][1]): ridden for way, ridden in votes.items()})
    if hasattr(graph, "avoided"):
        for way, ridden in votes.items():
            if ridden:
                graph.avoided.discard(way)
            else:
                graph.avoided.add(way)   # 이 서버가 떠 있는 동안 바로 반영한다


def follow(graph, plan_path: list, start: tuple = None, end: tuple = None, target_km: float = None) -> dict:
    """우리 코스를 Tmap 경로로 잇는다. 반환은 Tmap 응답 모양 + follow(검사 결과, 호출 수, 경유지 수).

    한 번에 안 맞으면 한 번 더 묻는다(호출은 최대 두 번 분량). Tmap이 우리 코스의 일부를 타지 않았다면
    대개 그 길이 Tmap 지도에 없는 것이다 — 그 길에 경유지를 찍어 억지로 데려가면 들어갔다 나오느라 크게
    늘어났다(수원 광교 3km → 5.45km). 그래서 그 길을 빼고 다시 짠 코스로 묻는다. 두 번 중 나은 쪽을 쓴다 —
    요청 거리(target_km, 없으면 우리 설계 거리)와 5% 안인 쪽이 먼저다.
    물을 때마다 Tmap이 탄 길과 피한 길을 적어 둔다(다음 코스부터 피한 길로 짜지 않는다).
    """
    start = tuple(start or plan_path[0])
    end = tuple(end or plan_path[-1])
    nodes = _nodes(graph, plan_path)
    plan_km = _dense_km(plan_path)
    points = needed_waypoints(graph, nodes)
    route, calls = stitch(start, end, points)
    _learn(graph, nodes, extract_path(route)[0])
    result = dict(check(route, plan_path, graph), replanned=False)
    used_plan = plan_path
    target = target_km or plan_km
    if not result["ok"] or abs(result["distance_km"] - target) > target * DISTANCE_OK:
        skipped = _skipped_ways(graph, nodes, extract_path(route)[0])
        again = _replan_around(graph, nodes, skipped) if skipped else None
        if again is not None:
            new_plan, new_points = again
            new_path = extract_path(new_plan)[0]
            second, more = stitch(start, end, new_points)
            _learn(graph, _nodes(graph, new_path), extract_path(second)[0])
            second_result = dict(check(second, new_path, graph), replanned=True)
        else:
            extra = [p for p in _off_course(graph, extract_path(route)[0], nodes) if p not in points]
            if not extra:
                second = None
            else:
                order = {n: i for i, n in enumerate(nodes)}
                new_points = sorted(set(points) | set(extra), key=lambda n: order.get(n, 0))
                second, more = stitch(start, end, new_points)
                second_result = dict(check(second, plan_path, graph), replanned=False)
        if second is not None:
            calls += more
            if _better(second_result, result, target):
                route, result, points = second, second_result, new_points
                used_plan = new_path if second_result["replanned"] else plan_path
    cleaned, points, calls = remove_spikes(graph, start, end, points, route, calls)
    if cleaned is not route:
        route = cleaned
        result = dict(check(route, used_plan, graph), replanned=result["replanned"])
    result.update(calls=calls, waypoints=len(points),
                  junctions_per_km=junctions_per_km(extract_path(route)[0], graph))   # 실제로 달리는 길의 갈림길
    return dict(route, follow=result)


def _dense_km(path: list) -> float:
    return sum(haversine_m(a, b) for a, b in zip(path, path[1:])) / 1000
