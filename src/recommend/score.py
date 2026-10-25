"""규칙 기반 가중치 스코어링으로 사용자 조건에 맞는 코스를 추천한다.

지도학습이 아니므로 라벨링된 학습 데이터셋 없이, 온보딩 입력 자체를 매칭 조건으로 사용한다.
러닝 코스 추천에 직접 필요한 것만 본다: 거리, 고른 풍경, 신호등(멈춤), 안전, 시간대.
"""
import math

from ..data_collection.scenery import THRESHOLDS as SCENERY_THRESHOLDS
from .profile import elevation_target_m, resolve_target_distance_km
from .timeofday import time_fit_match

# 고도는 잠시 끈다. 지금 표고 데이터(SRTM 30m, 건물·나무 높이가 섞인 겉면 높이)로는 평지도
# 25~40m 오르막으로 잰다(여의도 한강공원 1.8km 27m, 상무지구 큰길 1.2km 40m). 맨땅 높이 데이터
# (국토지리정보원 DEM 등)를 쓰게 되면 True로 바꾼다 — 점수·평가 질문·코스의 고도 측정이 같이 켜진다.
ELEVATION_ENABLED = False

DEFAULT_WEIGHTS = {
    "distance": 0.25,
    "tag_match": 0.25,
    "signal_free": 0.2,
    "safety": 0.15,
    "time_fit": 0.15,
}
ELEVATION_WEIGHT = 0.13   # 고도를 켜면 이만큼 주고 나머지를 비율대로 줄인다


def default_weights() -> dict:
    if not ELEVATION_ENABLED:
        return dict(DEFAULT_WEIGHTS)
    rest = 1 - ELEVATION_WEIGHT
    return dict({k: v * rest for k, v in DEFAULT_WEIGHTS.items()}, elevation=ELEVATION_WEIGHT)


def _decay(diff: float, tolerance: float) -> float:
    """차이가 tolerance일 때 약 0.37(1/e)로 떨어지는 완만한 감쇠 함수."""
    if tolerance <= 0:
        return 1.0 if diff == 0 else 0.0
    return math.exp(-(diff / tolerance) ** 2)


def distance_match(course: dict, user: dict) -> float:
    """코스가 선호 거리보다 길어도 감점하지 않는다 — 중간에 끊고 돌아오면 되므로 완전 매칭으로 취급.
    짧은 코스는 더 늘릴 방법이 없으니(도로가 거기서 끝남) 부족한 만큼 감쇠 페널티를 준다."""
    preferred = resolve_target_distance_km(user)
    if not preferred:
        return 0.5
    actual = course.get("distance_km", 0)
    # 순환 코스는 잘라낼 수 없다(자르면 고리가 끊긴다). 길어도 감점해야 목표 길이에 맞는 게 뽑힌다.
    if course.get("route_type") == "loop":
        return _decay(abs(actual - preferred), tolerance=preferred * 0.3 + 0.5)
    if actual >= preferred:
        return 1.0
    return _decay(preferred - actual, tolerance=preferred * 0.3 + 0.5)


def elevation_match(course: dict, user: dict) -> float:
    target = elevation_target_m(user)
    diff = abs((course.get("elevation_gain_m") or 0) - target)
    return _decay(diff, tolerance=target * 0.6 + 10)


def safety_match(course: dict, user: dict) -> float:
    return max(0.0, min(1.0, course.get("safety_score", 0)))


def signal_free_match(course: dict, user: dict) -> float:
    """끊김 정도는 신호등 총 개수가 아니라 km당 밀도로 봐야 한다.

    총 개수로 보면 9km 코스(신호등 30개)가 2km 코스(0개)보다 무조건 불리해지는데,
    실제로 달리면서 체감하는 건 "얼마나 자주 멈추느냐"이지 총 몇 번 멈췄느냐가 아니다.
    """
    tags = set(user.get("environment_tags", []))
    distance_km = max(course.get("distance_km", 0), 0.1)
    density = course.get("traffic_signal_count", 0) / distance_km
    base = 1.0 / (1.0 + density)
    if "차없는길" in tags:
        return base
    return 0.5 + 0.5 * base


def _tag_strength(tag: str, course: dict) -> float:
    """코스가 이 풍경을 얼마나 강하게 갖고 있는가 (0, 또는 0.6~1.0).

    태그는 기준을 넘으면 붙으므로, 붙어 있다는 것만으로 0.6을 주고 기준의 2배에서 만점이 된다.
    바다뷰 태그가 똑같이 붙어 있어도 경로의 100%가 해안인 코스가 41%인 코스보다 앞서야 한다.
    """
    if tag not in course.get("tags", []):
        return 0.0
    rule = SCENERY_THRESHOLDS.get(tag)
    value = (course.get("scenery") or {}).get(rule[0]) if rule else None
    if value is None or not rule[1]:
        return 1.0  # 측정값이 없는 예전 코스나 파생 태그(도심·산길)는 있는 그대로 인정
    return 0.6 + 0.4 * max(0.0, min(1.0, (value - rule[1]) / rule[1]))


def tag_match(course: dict, user: dict) -> float:
    user_tags = set(user.get("environment_tags", []))
    if not user_tags:
        return 0.5
    # 선택지 하나가 태그 여러 개에 대응하면('바다' = 바다뷰 또는 해변) 그중 가장 강한 것으로 친다.
    # 태그마다 평균을 내면 바다뷰만 있는 코스가 '바다'를 절반만 만족한 것처럼 된다.
    groups = user.get("scenery_groups") or [[tag] for tag in user_tags]
    return sum(max(_tag_strength(tag, course) for tag in group) for group in groups) / len(groups)


def component_scores(course: dict, user: dict) -> dict:
    """항목별 적합도(각 0~1). 가중치를 곱하기 전 값이라, 이 코스가 무엇 때문에 추천됐는지
    보여줄 때와 만족도로 사용자 가중치를 학습할 때 쓴다."""
    scores = {
        "distance": distance_match(course, user),
        "safety": safety_match(course, user),
        "signal_free": signal_free_match(course, user),
        "tag_match": tag_match(course, user),
        "time_fit": time_fit_match(course, user),
    }
    if ELEVATION_ENABLED:
        scores["elevation"] = elevation_match(course, user)
    return scores


def score_course(course: dict, user: dict, weights: dict = None) -> float:
    weights = weights or default_weights()
    scores = component_scores(course, user)
    used = {k: w for k, w in weights.items() if k in scores}   # 꺼진 항목(예전 프로필의 날씨·고도)은 빼고
    total = sum(used.values()) or 1.0
    return sum(scores[k] * w for k, w in used.items()) / total


def filter_by_required_tags(courses: list, user: dict) -> list:
    """environment_tags가 있으면, 그중 하나라도 겹치는 코스만 남긴다.

    tag_match는 score_course()의 가중치 중 하나(25%)일 뿐이라, 사용자가 "바다뷰"를 골라도
    바다가 전혀 없는 코스가 다른 점수(거리/안전 등)만으로 순위에 끼어드는 문제가 있었다.
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
