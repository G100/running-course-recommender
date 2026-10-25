"""목적지를 직접 고르는 코스.

"오동도까지 뛰고 싶다"는 거리나 태그로 표현할 수 없는 요구다. 추천이 아니라 지정이므로
점수로 고르지 않고, 준 지점까지 실제 보행 경로를 그대로 만들어 준다.

장소 이름 또는 좌표를 받는다. 이름은 Tmap 장소 검색으로 찾고 현위치에서 가까운 곳을 우선한다
(api_clients/tmap_poi.py). 어느 곳으로 정했는지와 다른 후보를 같이 돌려줘서, 엉뚱한 곳이 잡혔을 때
사용자가 바로 고칠 수 있게 한다. 왕복이면 돌아오는 길도 실제 경로로 붙인다
(일방통행·횡단보도 때문에 갈 때와 올 때 안내가 다르다).
"""
from ..api_clients.tmap_pedestrian import extract_path, extract_steps, get_route
from ..data_collection import area_cache, local_osm, scenery
from ..data_collection.enrich import haversine_m
from ..api_clients.tmap_poi import search_places
from ..data_collection.build_courses_from_landmarks import sample_elevation_gain
from .route_type import attach_actual_return_path, make_roundtrip
from .safety import safety_index, score_components

LOCAL_ROUTE_MAX_M = 8000   # 이보다 먼 목적지는 도로망을 그만큼 넓게 읽어야 해서 Tmap에 맡긴다


SCENIC_DETOUR_MIN = 1.2   # 풍경을 골랐으면 적어도 이만큼은 돌아가도 된다고 본다
ROAD_PER_STRAIGHT = 1.3   # 직선거리 대비 실제 길 길이 (경유지를 고를 때의 추정)
SCENIC_CANDIDATES = 150


def _reachable(graph, start: tuple) -> set:
    """출발점에서 길로 이어진 노드들 (섬·끊긴 길 위의 점은 경유지로 쓸 수 없다)."""
    from .road_graph import BLOCKED

    first = graph.nearest_node(*start)
    if first is None:
        return set()
    seen, stack = {first}, [first]
    while stack:
        node = stack.pop()
        for neighbour, _, way in graph.adjacent[node]:
            if neighbour not in seen and graph.surfaces[way] != BLOCKED:
                seen.add(neighbour)
                stack.append(neighbour)
    return seen


def scenic_waypoints(area, tags, start: tuple, end: tuple, want_km: float = None) -> list:
    """목적지 가는 길에 고른 풍경을 지나게 할 경유지. 풍경 위 두 점을 골라 그 사이를 풍경을 따라 달리게 한다.

    목적지만 주면 곧장 가서 고른 풍경을 지나지 않았다(여수: 바다를 골랐는데 1.3km 시내 직행).
    길이는 원하는 거리에 맞추고, 원하는 거리가 직선보다 짧으면 조금만 돌아간다. 풍경이 근처에 없으면 [].
    """
    from .generate_live import _steerable

    names = _steerable(set(tags or ()))
    if not names or area is None or area.graph is None:
        return []
    feature, near_m = area.indexes[names[0]], scenery.MEASURE_RADIUS[names[0]]
    if not feature.size:
        return []
    direct = haversine_m(start, end)
    budget = max((want_km or 0) * 1000, direct * SCENIC_DETOUR_MIN) / ROAD_PER_STRAIGHT
    nodes = list(_reachable(area.graph, start))
    step = max(1, len(nodes) // 6000)
    scenic = [n for n in nodes[::step]
              if haversine_m(start, n) + haversine_m(n, end) <= budget and feature.near(n[0], n[1], near_m)]
    if not scenic:
        return []
    # 고르게 솎는다 (약 100m 칸마다 하나)
    cells = {}
    for n in scenic:
        cells.setdefault((round(n[0] / 0.001), round(n[1] / 0.001)), n)
    pool = list(cells.values())[::max(1, len(cells) // SCENIC_CANDIDATES)]

    d = haversine_m
    best, best_cost = [], float("inf")
    for p in pool:
        one = d(start, p) + d(p, end)
        cost = abs(one - budget) / budget
        if cost < best_cost:
            best, best_cost = [p], cost
        for q in pool:
            if q is p:
                continue
            est = d(start, p) + d(p, q) + d(q, end)
            if est > budget * 1.15:
                continue
            # 길이가 맞고, 풍경 위 두 점 사이(= 풍경을 따라 달리는 구간)가 길수록 좋다
            cost = abs(est - budget) / budget - 0.5 * d(p, q) / est
            if cost < best_cost:
                best, best_cost = [p, q], cost
    return best


FIT_ROUNDS = 4
FIT_TOLERANCE = 0.1


def _fit_scenic(area, tags, start, end, want_km, night):
    """풍경 경유지로 짠 경로를 원하는 거리에 맞춘다. 직선거리로 고른 경유지는 해안처럼 구불구불한 길에서
    실제로 훨씬 길어진다(여수 5km 요청에 8.2km). 짜 본 거리를 보고 범위를 줄이거나 늘려 다시 고른다. (경유지, 경로)."""
    from . import road_graph

    if not tags or area is None or area.graph is None:
        return [], None
    best, best_gap, mult = ([], None), float("inf"), 1.0
    for _ in range(FIT_ROUNDS):
        waypoints = scenic_waypoints(area, tags, start, end, (want_km or 0) * mult)
        if not waypoints:
            break
        route = road_graph.route(area.graph, start, end, waypoints, night=night)
        if route is None:
            break
        actual_km = extract_path(route)[1] / 1000
        if not want_km:
            return waypoints, route
        gap = abs(actual_km - want_km) / want_km
        if gap < best_gap:
            best, best_gap = (waypoints, route), gap
        if gap <= FIT_TOLERANCE or actual_km <= 0:
            break
        mult = min(max(mult * want_km / actual_km, 0.3), 2.0)
    return best


def _own_route(lat, lng, dest_lat, dest_lng, night: bool, tags=None, want_km: float = None):
    """받아 둔 도로망에서 직접 짠 경로 (인도 없는 차도를 피하고, 밤에는 사람 있는 길로, 고른 풍경을 지나게).
    못 짜면 (None, None)."""
    from . import road_graph, sidewalk

    straight_m = haversine_m((lat, lng), (dest_lat, dest_lng))
    if not local_osm.available() or straight_m > LOCAL_ROUTE_MAX_M:
        return None, None
    reach_m = max(straight_m, (want_km or 0) * 500 if tags else 0)
    area = area_cache.load_area(lat, lng, radius_m=reach_m + 500)
    if area is None or area.graph is None or not area.covers(dest_lat, dest_lng):
        return None, None
    start, end = (lat, lng), (dest_lat, dest_lng)
    waypoints, route = _fit_scenic(area, tags, start, end, want_km, night)
    plan = lambda: road_graph.route(area.graph, start, end, waypoints, night=night)
    if route is None:
        waypoints = []   # 고른 풍경이 없거나 그쪽으로 길이 이어지지 않는다 → 곧장 간다
        route = plan()
    if route is not None:
        route = sidewalk.confirm(area.graph, start, end, waypoints, route, plan)
    if route is None or route.get("no_car_lanes") is False:
        return None, area   # 차도를 피해 갈 길이 없다 → Tmap 경로를 쓰되 확인되지 않았다고 표시한다
    return route, area
from .step_position import assign_positions


def _elevation_on() -> bool:
    from .score import ELEVATION_ENABLED
    return ELEVATION_ENABLED


def course_to_destination(lat: float, lng: float, place: str = None,
                          dest_lat: float = None, dest_lng: float = None,
                          route_type: str = "oneway", night: bool = False,
                          tags=None, want_km: float = None) -> dict:
    """현위치에서 목적지까지의 코스. 장소 이름이나 좌표 중 하나는 있어야 한다.

    tags(고른 풍경)를 주면 그 풍경을 지나 목적지로 간다. 길이는 want_km에 맞춘다."""
    found, others = None, []
    if dest_lat is None or dest_lng is None:
        if not place:
            raise ValueError("목적지를 장소 이름이나 좌표로 지정해주세요.")
        candidates = search_places(place, lat, lng)
        if not candidates:
            raise ValueError(f"'{place}'을(를) 찾지 못했습니다. 다른 이름으로 검색해 보세요.")
        found, others = candidates[0], candidates[1:]
        dest_lat, dest_lng = found["lat"], found["lng"]
        place = found["name"]   # 사용자가 친 말이 아니라 실제 장소 이름으로 보여준다

    # 추천 코스와 같은 규칙으로 간다: 인도 없는 차도는 지나지 않고, 밤에는 사람 있는 길로.
    # 도로망이 없거나 그렇게 갈 길이 없으면 Tmap 보행자 경로(최단 거리)를 쓴다.
    route, area = _own_route(lat, lng, dest_lat, dest_lng, night, tags, want_km)
    own = route is not None
    if not own:
        route = get_route((lng, lat), (dest_lng, dest_lat), start_name="현위치", end_name=place or "목적지")
    path, distance_m = extract_path(route)
    if not path:
        raise ValueError("목적지까지 걸어갈 수 있는 경로를 찾지 못했습니다.")

    label = place or f"{dest_lat:.4f},{dest_lng:.4f}"
    course = {
        "id": f"destination-{lat:.4f}-{lng:.4f}-{dest_lat:.4f}-{dest_lng:.4f}-{route_type}",
        "name": f"{label}까지",
        "region": "실시간 생성",
        "distance_km": round(distance_m / 1000, 2),
        # 고도는 지금 꺼져 있다 (score.ELEVATION_ENABLED) — 꺼져 있으면 표고 API를 부르지 않는다
        "elevation_gain_m": sample_elevation_gain(path) if _elevation_on() else None,
        "surface": "paved",
        "safety_score": 0.7,
        "path": path,
        "steps": assign_positions(extract_steps(route), path),
        "route_type": "oneway",
        "tags": [],
        "source": "live_generated",
    }
    if own:
        course.update(router=route["router"], road_mix=route["road_mix"], road_score=route["road_score"],
                      no_car_lanes=route["no_car_lanes"], sidewalk_only=route["sidewalk_only"],
                      lively_ratio=route["lively_ratio"], secluded_ratio=route["secluded_ratio"],
                      planned_for_night=night)
    else:
        course["no_car_lanes"] = None   # Tmap 최단 경로라 인도 여부를 확인하지 못했다
    if area is not None:
        points = area.safety_points
        course["safety_breakdown"] = score_components(path, points["cctv"], points["convenience"], points["police"])
        course["safety_score"] = safety_index(path, points["cctv"], points["convenience"], points["police"])
    if found is not None:
        # 어디로 정했는지, 그리고 그곳이 아닐 때 고를 수 있는 다른 후보
        course["destination"] = found
        course["destination_alternatives"] = others

    measured = scenery.tags_for_path(path, course)  # 지형 데이터가 있는 지역이면 실제 풍경을 잰다
    if measured is None:
        course["scenery_pending"] = True
    else:
        course["scenery"], course["tags"] = measured

    if route_type == "roundtrip":
        course = make_roundtrip(attach_actual_return_path(course))
        course["name"] = f"{label} 왕복"
    return course
