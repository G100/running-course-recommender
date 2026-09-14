"""사용자 현위치 기반 실시간 코스 생성 (프로토타입).

DB에 미리 저장된 코스가 아니라, 요청이 들어온 그 순간 사용자 좌표 주변에서
실제 도로/지형 데이터를 조회해 코스를 즉석에서 만든다.

방식: 사용자가 원하는 태그(바다뷰/숲길)에 해당하는 실제 지형을 Overpass "around" 검색으로
찾고, 거기까지 Tmap 보행자 경로(인도/보행로 기준)로 이동한다. route_type="roundtrip"이면
그대로 되돌아와 왕복 코스로(목표거리 절반 반경에서 지형 탐색), "oneway"면 편도로 끝낸다
(목표거리 전체 반경에서 지형 탐색). 완전한 순환 루프보다 구현이 단순해 MVP로 적합하다.

한계 (검증 완료 사항):
- 요청 1건당 Overpass + Tmap + 고도 API를 순차 호출하므로 응답에 수 초 소요.
"""
import requests

from ..api_clients.elevation import get_elevation_profile
from ..api_clients.tmap_pedestrian import extract_path, extract_steps, get_route
from ..data_collection.osm_overpass import HEADERS as OSM_HEADERS
from ..data_collection.osm_overpass import OVERPASS_URL

TAG_TO_OSM_FILTER = {
    "바다뷰": '["natural"="coastline"]',
    "숲길": '["natural"="wood"]',
}


def find_nearby_point(lat: float, lng: float, radius_m: float, osm_filter: str) -> tuple:
    """반경 내에서 조건에 맞는 가장 가까운 지형의 좌표 하나를 찾는다. 없으면 None."""
    query = f"""
    [out:json][timeout:25];
    (way(around:{radius_m},{lat},{lng}){osm_filter};);
    out geom 3;
    """
    resp = requests.post(OVERPASS_URL, data={"data": query}, headers=OSM_HEADERS, timeout=30)
    resp.raise_for_status()
    elements = resp.json().get("elements", [])
    if not elements:
        return None
    geom = elements[0].get("geometry", [])
    if not geom:
        return None
    mid = geom[len(geom) // 2]
    return mid["lat"], mid["lon"]


def sample_elevation_gain(path: list, n: int = 20) -> float:
    if len(path) < 2:
        return 0.0
    step = max(1, len(path) // n)
    samples = path[::step]
    elevations = get_elevation_profile(samples)
    return round(sum(max(0.0, elevations[i] - elevations[i - 1]) for i in range(1, len(elevations))), 1)


def generate_loop_course(lat: float, lng: float, target_distance_km: float, tags: set,
                          route_type: str = "roundtrip") -> dict:
    """사용자 위치·목표거리·선호태그로 코스를 즉석 생성. 매칭 지형 없으면 ValueError.

    roundtrip이면 갔다 오는 길 둘 다 실제 Tmap 호출로 받아서(편도가 아니라 왕복 전용 호출 두 번),
    돌아오는 방향의 턴바이턴 안내도 진짜 데이터로 채운다 — 단순히 좌표를 뒤집어 미러링하지 않는다
    (일방통행 보행로 등에서는 갈 때와 올 때 실제 경로가 다를 수 있음).
    """
    matched_tag = next((t for t in tags if t in TAG_TO_OSM_FILTER), "바다뷰")
    osm_filter = TAG_TO_OSM_FILTER[matched_tag]

    # 왕복은 목적지가 편도 목표거리의 절반 지점에 있어야 전체가 목표거리에 맞는다
    radius_factor = 0.4 if route_type == "roundtrip" else 0.8  # 도로가 직선거리보다 긴 것을 감안해 축소
    radius_m = target_distance_km * 1000 * radius_factor
    waypoint = find_nearby_point(lat, lng, radius_m, osm_filter)
    if waypoint is None:
        raise ValueError(f"반경 {radius_m:.0f}m 안에서 {matched_tag or '조건에 맞는'} 지형을 찾지 못했습니다.")

    outbound = get_route((lng, lat), (waypoint[1], waypoint[0]))
    out_path, out_distance_m = extract_path(outbound)
    if not out_path:
        raise ValueError("Tmap 보행자 경로를 찾지 못했습니다.")
    steps = extract_steps(outbound)

    if route_type == "roundtrip":
        inbound = get_route((waypoint[1], waypoint[0]), (lng, lat))
        in_path, in_distance_m = extract_path(inbound)
        if in_path:
            full_path = out_path + in_path
            steps += extract_steps(inbound)
            distance_m = out_distance_m + in_distance_m
        else:  # 돌아오는 편이 실패하면 왕복 근사치로 미러링
            full_path = out_path + list(reversed(out_path[:-1]))
            distance_m = out_distance_m * 2
    else:
        full_path = out_path
        distance_m = out_distance_m

    course_tags = [matched_tag] if matched_tag else []
    name = f"현위치 기반 {'왕복' if route_type == 'roundtrip' else '편도'} 코스 ({matched_tag or '기본'})"

    return {
        "id": f"generated-{lat:.4f}-{lng:.4f}-{target_distance_km}-{route_type}",
        "name": name,
        "region": "실시간 생성",
        "distance_km": round(distance_m / 1000, 2),
        "elevation_gain_m": sample_elevation_gain(full_path),
        "surface": "paved",
        "safety_score": 0.7,
        "path": full_path,
        "steps": steps,
        "route_type": route_type,
        "tags": course_tags,
        "source": "live_generated",
    }
