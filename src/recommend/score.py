"""규칙 기반 가중치 스코어링으로 사용자 조건에 맞는 코스를 추천한다.

지도학습이 아니므로 라벨링된 학습 데이터셋 없이, 온보딩 입력 자체를 매칭 조건으로 사용한다.
"""
import math

from .vectorize import ELEVATION_PREFERENCE_TARGET_M

DEFAULT_WEIGHTS = {
    "distance": 0.25,
    "elevation": 0.15,
    "safety": 0.15,
    "signal_free": 0.20,
    "tag_match": 0.25,
}

DEFAULT_WEIGHTS_WITH_ENV = {
    "distance": 0.20,
    "elevation": 0.10,
    "safety": 0.15,
    "signal_free": 0.15,
    "tag_match": 0.20,
    "environment": 0.20,
}


def _decay(diff: float, tolerance: float) -> float:
    """차이가 tolerance일 때 약 0.37(1/e)로 떨어지는 완만한 감쇠 함수."""
    if tolerance <= 0:
        return 1.0 if diff == 0 else 0.0
    return math.exp(-(diff / tolerance) ** 2)


def distance_match(course: dict, user: dict) -> float:
    """코스가 선호 거리보다 길어도 감점하지 않는다 — 중간에 끊고 돌아오면 되므로 완전 매칭으로 취급.
    짧은 코스는 더 늘릴 방법이 없으니(도로가 거기서 끝남) 부족한 만큼 감쇠 페널티를 준다."""
    preferred = user.get("preferred_distance_km")
    if not preferred:
        return 0.5
    actual = course.get("distance_km", 0)
    if actual >= preferred:
        return 1.0
    return _decay(preferred - actual, tolerance=preferred * 0.3 + 0.5)


def elevation_match(course: dict, user: dict) -> float:
    pref = user.get("elevation_preference", "medium")
    target = ELEVATION_PREFERENCE_TARGET_M.get(pref, ELEVATION_PREFERENCE_TARGET_M["medium"])
    diff = abs(course.get("elevation_gain_m", 0) - target)
    return _decay(diff, tolerance=target * 0.6 + 10)


def safety_match(course: dict, user: dict) -> float:
    return max(0.0, min(1.0, course.get("safety_score", 0)))


def signal_free_match(course: dict, user: dict) -> float:
    tags = set(user.get("environment_tags", []))
    signal_count = course.get("traffic_signal_count", 0)
    base = 1.0 / (1.0 + signal_count)
    if "차없는길" in tags:
        return base
    return 0.5 + 0.5 * base


def tag_match(course: dict, user: dict) -> float:
    user_tags = set(user.get("environment_tags", []))
    course_tags = set(course.get("tags", []))
    if not user_tags:
        return 0.5
    overlap = user_tags & course_tags
    return len(overlap) / len(user_tags)


def score_course(course: dict, user: dict, weights: dict = None, env_context: dict = None) -> float:
    if weights is None:
        weights = DEFAULT_WEIGHTS_WITH_ENV if env_context is not None else DEFAULT_WEIGHTS

    scores = {
        "distance": distance_match(course, user),
        "elevation": elevation_match(course, user),
        "safety": safety_match(course, user),
        "signal_free": signal_free_match(course, user),
        "tag_match": tag_match(course, user),
    }
    if "environment" in weights:
        from .environment import environment_score
        scores["environment"] = environment_score(env_context or {})

    return sum(scores[k] * weights[k] for k in weights)


def filter_by_required_tags(courses: list, user: dict) -> list:
    """environment_tags가 있으면, 그중 하나라도 겹치는 코스만 남긴다.

    tag_match는 score_course()의 가중치 중 하나(25%)일 뿐이라, 사용자가 "바다뷰"를 골라도
    바다가 전혀 없는 코스가 다른 점수(거리/고도/안전)만으로 순위에 끼어드는 문제가 있었다.
    명시적으로 고른 태그는 소프트 가중치가 아니라 필수 조건으로 다뤄야 실사용에 맞다.
    """
    user_tags = set(user.get("environment_tags", []))
    if not user_tags:
        return courses
    return [c for c in courses if user_tags & set(c.get("tags", []))]


def recommend(courses: list, user: dict, top_n: int = 5, weights: dict = None, env_context_map: dict = None) -> list:
    """(course, score) 튜플 리스트를 점수 내림차순으로 반환.

    사용자가 environment_tags를 지정하면 그 태그를 하나도 안 가진 코스는 결과에서 제외한다
    (예: "바다뷰"를 골랐는데 내륙 코스가 뜨는 것을 방지). 남는 후보끼리는 기존 가중치 점수로 정렬.
    env_context_map: {course_id: environment_context} 를 주면 실시간 날씨/대기질을 점수에 반영.
    """
    candidates = filter_by_required_tags(courses, user)
    scored = [
        (c, score_course(c, user, weights, env_context=(env_context_map or {}).get(c["id"]) if env_context_map else None))
        for c in candidates
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:top_n]
