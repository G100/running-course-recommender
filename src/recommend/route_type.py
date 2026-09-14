"""코스를 왕복(roundtrip)으로 뛸지 편도(oneway)로 뛸지는 사용자가 고르게 한다.

DB에 저장된 코스는 전부 "랜드마크A ~ 랜드마크B" 편도 경로다. 왕복을 원하면 그대로 되돌아오는
구간을 이어붙여 거리/고도를 두 배로 잡아야 distance_match·truncate_course가 올바르게 동작한다.
"""

ROUTE_TYPES = ("roundtrip", "oneway")


def make_roundtrip(course: dict) -> dict:
    """편도 경로에 되돌아오는 구간을 이어붙여 왕복으로 만든다."""
    path = course.get("path") or []
    if len(path) < 2:
        return dict(course, route_type="roundtrip")

    result = dict(course)
    result["path"] = path + list(reversed(path[:-1]))
    result["distance_km"] = round(course.get("distance_km", 0) * 2, 2)
    # 왕복이면 오르막이 내리막으로도 한 번씩 더 나오므로 편도 상승고도의 약 2배로 근사한다
    # (지형이 완전히 대칭은 아니라 근사치임 — trim.py의 구간비례 방식과 같은 전제).
    result["elevation_gain_m"] = round(course.get("elevation_gain_m", 0) * 2, 1)
    result["route_type"] = "roundtrip"

    # 돌아오는 방향의 실제 턴바이턴은 다시 Tmap을 불러야 나오므로(저장된 건 편도 안내뿐),
    # 가짜 좌/우회전을 지어내는 대신 반환점 표시만 남긴다 — 없는 데이터를 있는 척하지 않는다.
    steps = course.get("steps")
    if steps:
        result["steps"] = steps + [{
            "lat": path[-1][0], "lng": path[-1][1],
            "description": "반환점 — 왔던 길로 돌아갑니다",
            "turn_type": None,
        }]
    return result


def mark_oneway(course: dict) -> dict:
    return dict(course, route_type="oneway")


def apply_route_type(course: dict, route_type: str) -> dict:
    if route_type == "roundtrip":
        return make_roundtrip(course)
    return mark_oneway(course)
