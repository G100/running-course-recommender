"""코스를 왕복(roundtrip)으로 뛸지 편도(oneway)로 뛸지는 사용자가 고르게 한다.

DB에 저장된 코스는 전부 "랜드마크A ~ 랜드마크B" 편도 경로다. 왕복을 원하면 그대로 되돌아오는
구간을 이어붙여 거리/고도를 두 배로 잡아야 distance_match·truncate_course가 올바르게 동작한다.
"""

from .step_position import assign_positions, cumulative_distances

ROUTE_TYPES = ("roundtrip", "oneway")


def make_roundtrip(course: dict) -> dict:
    """편도 경로에 되돌아오는 구간을 이어붙여 왕복으로 만든다.

    복귀 경로(return_path/return_steps)가 저장돼 있으면 그 실제 경로와 안내를 쓴다.
    갈 때와 올 때는 같은 도로라도 일방통행·횡단보도 때문에 안내가 다르므로, 좌표를 뒤집어
    안내를 지어내지 않는다. 아직 복귀 경로를 받아두지 않은 코스는 반환점 표시만 남긴다.
    """
    path = course.get("path") or []
    if len(path) < 2:
        return dict(course, route_type="roundtrip")

    return_path = course.get("return_path") or list(reversed(path[:-1]))
    full_path = path + return_path

    result = dict(course)
    result["path"] = full_path
    result["distance_km"] = round(course.get("distance_km", 0) * 2, 2)
    # 왕복이면 오르막이 내리막으로도 한 번씩 더 나오므로 편도 상승고도의 약 2배로 근사한다
    # (지형이 완전히 대칭은 아니라 근사치임 — trim.py의 구간비례 방식과 같은 전제).
    result["elevation_gain_m"] = round(course.get("elevation_gain_m", 0) * 2, 1)
    result["route_type"] = "roundtrip"
    result["cum_outbound_m"] = cumulative_distances(path)[-1]

    steps = course.get("steps")
    if steps:
        return_steps = course.get("return_steps")
        if not return_steps:
            return_steps = [{
                "lat": path[-1][0], "lng": path[-1][1],
                "description": "반환점 — 왔던 길로 돌아갑니다",
                "turn_type": None,
            }]
        result["steps"] = assign_positions(steps + return_steps, full_path)
    return result


def mark_oneway(course: dict) -> dict:
    return dict(course, route_type="oneway")


def apply_route_type(course: dict, route_type: str) -> dict:
    if route_type == "roundtrip":
        return make_roundtrip(course)
    return mark_oneway(course)
