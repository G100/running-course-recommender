"""코스 점수 (100점): 거리 30 · 풍경 25 · 흐름 25 · 차 없는 길 20.

먼저 걸러낸다(점수 이전의 필수 조건): 거리 ±5% 안, 차도 0%, 고른 풍경이 기준 이상.
남은 코스끼리 아래 네 항목으로 순위를 매긴다. 각 항목은 0~1이고, 기준점은 임의로 정하지 않고
실제 코스 53개에서 잰 분포의 상위 10%(만점)·하위 10%(0점)로 잡았다.

  거리       1 − 0.5 × (오차 ÷ 5%)                 5% 오차에 0.5점, 10%면 0점
  풍경       고른 풍경 비율 ÷ (기준 × 2)            기준을 겨우 넘으면 0.5점, 2배면 만점
             (안 골랐으면 녹지·물가 비율: 11.7% → 0점, 89% → 만점)
  흐름       신호등·꺾기·갈림길(km당) 세 값의 평균   멈추지 않고 쭉 이어지는 길
  차 없는 길  차가 다니지 않는 길(공원 산책로·자전거길·보행자 전용길)의 비율

근거: 러너 설문 N=1,228(녹지 77%, 가장 큰 걱정은 운전자 61%), 러닝 환경 연구 정리
(Tegart 외 2025, 논문 102편 — 녹지·물가, 끊기지 않는 길, 차와 떨어진 길).
"""
import math

from ..data_collection.scenery import THRESHOLDS as SCENERY_THRESHOLDS
from .flow import turns_per_km
from .profile import elevation_target_m, resolve_target_distance_km

# 고도는 잠시 끈다. 지금 표고 데이터(SRTM 30m, 건물·나무 높이가 섞인 겉면 높이)로는 평지도
# 25~40m 오르막으로 잰다(여의도 한강공원 1.8km 27m, 상무지구 큰길 1.2km 40m). 맨땅 높이 데이터
# (국토지리정보원 DEM 등)를 쓰게 되면 True로 바꾼다 — 점수·평가 질문·코스의 고도 측정이 같이 켜진다.
ELEVATION_ENABLED = False

DEFAULT_WEIGHTS = {
    "distance": 0.30,
    "tag_match": 0.25,
    "flow": 0.25,
    "car_free": 0.20,
}
ELEVATION_WEIGHT = 0.13   # 고도를 켜면 이만큼 주고 나머지를 비율대로 줄인다

DISTANCE_OK = 0.05        # 이 오차에서 거리 점수가 절반이 된다

# 풍경을 고르지 않았을 때 보는 녹지·물가 비율 (실제 코스의 하위 10% → 0점, 상위 10% → 만점)
GREEN_BLUE = ("park", "forest", "river", "lake", "coast")
GREEN_BLUE_RANGE = (0.117, 0.89)

# 흐름: km당 값이 이 범위의 앞쪽이면 만점, 뒤쪽이면 0점 (실제 코스 53개의 상위·하위 10%)
STOPS_RANGE = (0.0, 2.7)        # 신호등
TURNS_RANGE = (1.5, 6.5)        # 35° 넘게 꺾는 곳
JUNCTIONS_RANGE = (2.7, 13.9)   # 세 갈래 이상 갈림길


def default_weights() -> dict:
    if not ELEVATION_ENABLED:
        return dict(DEFAULT_WEIGHTS)
    rest = 1 - ELEVATION_WEIGHT
    return dict({k: v * rest for k, v in DEFAULT_WEIGHTS.items()}, elevation=ELEVATION_WEIGHT)


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _scale(value: float, good: float, bad: float) -> float:
    """good이면 1, bad이면 0, 그 사이는 직선."""
    return _clamp((value - bad) / (good - bad))


def distance_match(course: dict, user: dict) -> float:
    target = resolve_target_distance_km(user)
    if not target:
        return 0.5
    actual = course.get("distance_km", 0)
    # 편도·왕복은 목표 거리에서 잘라 준다 — 길어도 실제로 달리는 건 목표 거리다.
    # 순환은 자르면 고리가 끊기니 길어도 그대로 오차다.
    if course.get("route_type") != "loop" and actual > target:
        actual = target
    error = abs(actual - target) / target
    return _clamp(1 - 0.5 * error / DISTANCE_OK)


def elevation_match(course: dict, user: dict) -> float:
    target = elevation_target_m(user)
    diff = abs((course.get("elevation_gain_m") or 0) - target)
    tolerance = target * 0.6 + 10
    return math.exp(-(diff / tolerance) ** 2)


def _tag_strength(tag: str, course: dict) -> float:
    """코스가 이 풍경을 얼마나 지나는가: 측정 비율 ÷ (기준 × 2). 태그가 없으면 0."""
    if tag not in course.get("tags", []):
        return 0.0
    rule = SCENERY_THRESHOLDS.get(tag)
    value = (course.get("scenery") or {}).get(rule[0]) if rule else None
    if value is None or not rule[1]:
        return 1.0  # 측정값이 없는 예전 코스나 파생 태그(도심·산길)는 있는 그대로 인정
    return _clamp(value / (rule[1] * 2))


def tag_match(course: dict, user: dict) -> float:
    user_tags = set(user.get("environment_tags", []))
    if not user_tags:
        scenery = course.get("scenery")
        if not scenery:
            return 0.5
        return _scale(max(scenery.get(k) or 0 for k in GREEN_BLUE), GREEN_BLUE_RANGE[1], GREEN_BLUE_RANGE[0])
    # 선택지 하나가 태그 여러 개에 대응하면('바다' = 바다뷰 또는 해변) 그중 가장 강한 것으로 친다.
    groups = user.get("scenery_groups") or [[tag] for tag in user_tags]
    return sum(max(_tag_strength(tag, course) for tag in group) for group in groups) / len(groups)


def flow_parts(course: dict) -> dict:
    """흐름의 세 값(km당)과 각각의 점수. 잴 수 없는 값은 빠진다."""
    km = max(course.get("distance_km") or 0, 0.1)
    measured = {}
    if course.get("traffic_signal_count") is not None:
        measured["stops"] = course["traffic_signal_count"] / km
    if course.get("turns_per_km") is not None:
        measured["turns"] = course["turns_per_km"]
    elif len(course.get("path") or []) > 2:
        measured["turns"] = turns_per_km(course["path"])
    if course.get("junctions_per_km") is not None:
        measured["junctions"] = course["junctions_per_km"]
    ranges = {"stops": STOPS_RANGE, "turns": TURNS_RANGE, "junctions": JUNCTIONS_RANGE}
    return {k: {"per_km": round(v, 2), "score": round(_scale(v, *ranges[k]), 3)} for k, v in measured.items()}


def flow_match(course: dict, user: dict) -> float:
    parts = flow_parts(course)
    if not parts:
        return 0.5
    return sum(p["score"] for p in parts.values()) / len(parts)


def car_free_match(course: dict, user: dict) -> float:
    mix = course.get("road_mix")
    if mix and mix.get("car_free") is not None:
        return _clamp(mix["car_free"])
    measured = (course.get("scenery") or {}).get("carfree")
    if measured is not None:
        return _clamp(measured)
    return 0.5


def component_scores(course: dict, user: dict) -> dict:
    """항목별 점수(각 0~1). 가중치를 곱하기 전 값이라, 이 코스가 무엇 때문에 추천됐는지
    보여줄 때와 만족도로 사용자 가중치를 학습할 때 쓴다."""
    scores = {
        "distance": distance_match(course, user),
        "tag_match": tag_match(course, user),
        "flow": flow_match(course, user),
        "car_free": car_free_match(course, user),
    }
    if ELEVATION_ENABLED:
        scores["elevation"] = elevation_match(course, user)
    return scores


def score_course(course: dict, user: dict, weights: dict = None) -> float:
    weights = weights or default_weights()
    scores = component_scores(course, user)
    used = {k: w for k, w in weights.items() if k in scores}   # 꺼진 항목(고도)은 빼고
    total = sum(used.values()) or 1.0
    return sum(scores[k] * w for k, w in used.items()) / total


def filter_by_required_tags(courses: list, user: dict) -> list:
    """environment_tags가 있으면, 그중 하나라도 겹치는 코스만 남긴다.

    tag_match는 score_course()의 가중치 중 하나(25%)일 뿐이라, 사용자가 "바다뷰"를 골라도
    바다가 전혀 없는 코스가 다른 점수(거리/흐름 등)만으로 순위에 끼어드는 문제가 있었다.
    명시적으로 고른 태그는 소프트 가중치가 아니라 필수 조건으로 다뤄야 실사용에 맞다.
    """
    user_tags = set(user.get("environment_tags", []))
    if not user_tags:
        return courses
    # 지형 데이터가 없는 곳에서 만든 코스(scenery_pending)는 풍경을 확인할 수 없다. 태그가 없다고
    # 버리면 그 지역에선 추천이 0개가 되므로 남겨 두되, tag_match가 0이라 확인된 코스보다 뒤로 간다.
    return [c for c in courses if c.get("scenery_pending") or user_tags & set(c.get("tags", []))]


def recommend(courses: list, user: dict, top_n: int = 5, weights: dict = None) -> list:
    """(course, score) 튜플 리스트를 점수 내림차순으로 반환.

    사용자가 environment_tags를 지정하면 그 태그를 하나도 안 가진 코스는 결과에서 제외한다
    (예: "바다뷰"를 골랐는데 내륙 코스가 뜨는 것을 방지). 남는 후보끼리는 가중치 점수로 정렬.
    """
    candidates = filter_by_required_tags(courses, user)
    scored = [(c, score_course(c, user, weights)) for c in candidates]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:top_n]
