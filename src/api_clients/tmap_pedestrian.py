"""Tmap(SK Open API) 보행자 경로 API 클라이언트.

카카오 Directions는 자동차 도로 기준이라 인도/공원 산책로를 반영하지 않는다.
러닝 코스는 실제로 사람이 걸을 수 있는 길이어야 하므로 보행자 전용 경로로 교체.

키 발급: https://openapi.sk.com (무료체험 등급, 경로안내 API그룹 하루 1,000건)
발급 후 환경변수 TMAP_APP_KEY 설정.
"""
import os
import re
import time

import requests

PEDESTRIAN_URL = "https://apis.openapi.sk.com/tmap/routes/pedestrian"
LIMIT_RECHECK_S = 600   # 하루 한도를 넘으면 이만큼은 묻지 않는다. 풀리는 시각을 몰라서 이 간격으로 한 번씩 다시 본다
_limit_hit_at = None    # 한도를 넘었다는 답을 받은 시각 (서버가 떠 있는 동안 기억한다)


class DailyLimitReached(requests.HTTPError):
    """Tmap 하루 호출 한도(무료 1,000건)를 넘었다. 한도가 풀릴 때까지 무엇을 물어도 거절당한다.
    HTTPError이므로 예전처럼 HTTPError로 받는 곳은 그대로 동작한다."""


def _over_daily_limit(resp) -> bool:
    if getattr(resp, "status_code", None) != 429:
        return False
    try:
        return (resp.json().get("error") or {}).get("code") == "QUOTA_EXCEEDED"
    except ValueError:
        return False


def get_route(start: tuple, end: tuple, start_name: str = "", end_name: str = "",
              waypoints: list[tuple] | None = None) -> dict:
    """start/end = (lng, lat), waypoints = [(lng, lat), ...].

    경유지는 Tmap의 passList 형식으로 전달한다. 시작점과 끝점을 같게 하고
    경유지를 넣으면 각 구간을 실제 보행로로 연결한 순환 경로를 받을 수 있다.
    """
    app_key = os.environ.get("TMAP_APP_KEY")
    if not app_key:
        raise RuntimeError("TMAP_APP_KEY 환경변수가 설정되지 않았습니다.")

    global _limit_hit_at
    if _limit_hit_at is not None and time.time() - _limit_hit_at < LIMIT_RECHECK_S:
        raise DailyLimitReached("Tmap 하루 호출 한도를 넘었습니다 (잠시 뒤 다시 확인합니다)")
    headers = {"appKey": app_key, "Content-Type": "application/json", "Accept": "application/json"}
    body = {
        "startX": str(start[0]), "startY": str(start[1]), "startName": start_name or "출발지",
        "endX": str(end[0]), "endY": str(end[1]), "endName": end_name or "도착지",
    }
    if waypoints:
        body["passList"] = "_".join(f"{lng},{lat}" for lng, lat in waypoints)
    resp = requests.post(PEDESTRIAN_URL, params={"version": 1}, headers=headers, json=body, timeout=15)
    if _over_daily_limit(resp):
        _limit_hit_at = time.time()
        raise DailyLimitReached("Tmap 하루 호출 한도를 넘었습니다", response=resp)
    _limit_hit_at = None
    resp.raise_for_status()
    return resp.json()


def extract_path(route_json: dict) -> tuple:
    """(path=[[lat,lng],...], distance_m) 반환. LineString 구간을 순서대로 이어붙인다."""
    features = route_json.get("features", [])
    distance_m = 0
    for f in features:
        if f["geometry"]["type"] == "Point":
            props = f.get("properties", {})
            if "totalDistance" in props:
                distance_m = props["totalDistance"]
                break

    path = []
    for f in features:
        if f["geometry"]["type"] == "LineString":
            for lng, lat in f["geometry"]["coordinates"]:
                path.append([lat, lng])
    return path, distance_m


def extract_steps(route_json: dict) -> list:
    """턴바이턴 안내 목록: [{lat, lng, description, turn_type}, ...].

    Tmap이 각 안내 지점(Point)에 "우회전 후 OO로를 따라 31m 이동" 같은 자연어 설명을
    이미 만들어서 준다 — 직접 좌/우회전을 판정할 필요 없이 그대로 쓰면 된다.
    """
    steps = []
    for f in route_json.get("features", []):
        if f["geometry"]["type"] != "Point":
            continue
        props = f.get("properties", {})
        description = props.get("description")
        if not description:
            continue
        lng, lat = f["geometry"]["coordinates"]
        steps.append({
            "lat": lat, "lng": lng,
            "description": description,
            "turn_type": props.get("turnType"),
            "instruction": runner_instruction(description, props.get("turnType"), props.get("nearPoiName")),
        })
    return steps


# Tmap turnType → 달리는 사람에게 할 말. 무엇을 하면 되는지만, 짧게.
TURN_ACTIONS = {
    11: "쭉 가세요", 12: "왼쪽으로 도세요", 13: "오른쪽으로 도세요", 14: "뒤로 돌아가세요",
    16: "왼쪽 뒤로 크게 꺾으세요", 17: "왼쪽으로 살짝 꺾으세요", 18: "오른쪽으로 살짝 꺾으세요", 19: "오른쪽 뒤로 크게 꺾으세요",
    125: "육교로 건너세요", 126: "지하보도로 건너세요", 127: "계단이 있어요", 128: "경사로를 지나요", 129: "계단과 경사로를 지나요",
    211: "횡단보도를 건너세요", 212: "왼쪽 횡단보도를 건너세요", 213: "오른쪽 횡단보도를 건너세요",
    214: "왼쪽 뒤 횡단보도를 건너세요", 215: "왼쪽 앞 횡단보도를 건너세요", 216: "오른쪽 앞 횡단보도를 건너세요",
    217: "오른쪽 뒤 횡단보도를 건너세요", 218: "엘리베이터를 타세요",
    200: "출발하세요", 201: "도착했어요",
}
# "○○을/를 따라"에서 이름으로 부를 만하지 않은 길
GENERIC_ROADS = {"보행자도로", "도보", "길", "보도", "인도", "산책로"}
_FOLLOW = re.compile(r"(\S+?)(?:을|를) 따라")


def runner_instruction(description: str, turn_type, near_poi: str = None) -> str:
    """Tmap 안내("우회전 후 보행자도로를 따라 125m 이동")를 러너가 듣기 쉬운 말로 바꾼다.
    무엇을 할지 먼저, 근처 가게·건물이 있으면 그 앞에서, 이름 있는 길이면 그 길을 따라.
    거리는 화면·음성이 따로 말하므로 넣지 않는다. 모르는 안내는 Tmap 문구 그대로."""
    action = TURN_ACTIONS.get(turn_type)
    if action is None:
        return description
    if turn_type in (200, 201, 11):
        where = ""
    else:
        where = f"{near_poi.strip()} 앞에서 " if near_poi and near_poi.strip() else ""
    road = _FOLLOW.search(description or "")
    road = road.group(1) if road and road.group(1) not in GENERIC_ROADS else None
    return f"{where}{action}" + (f" · {road} 따라" if road and turn_type not in (201, 11) else "")
