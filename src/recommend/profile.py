"""사용자가 고른 거리·시간을 추천 파라미터로 바꾼다.

- 거리: 고른 그대로가 목표 거리다.
- 시간: "30분 뛸래"는 기본 페이스로 나눠 목표 거리로 환산하고, 러닝 후 "길었다/짧았다"는
  답으로 그 사람에게 맞게 늘이거나 줄인다(distance_scale).
"""

DEFAULT_PACE_MIN_PER_KM = 8.0   # 숙련도·페이스 입력을 뺐다. 예전 기본값(입문자) 그대로

# 고도 선호별 목표 오르막(m). 고도는 지금 꺼져 있다(score.ELEVATION_ENABLED) — 켤 때 쓴다.
ELEVATION_PREFERENCE_TARGET_M = {
    "low": 20,
    "medium": 60,
    "high": 150,
}


def resolve_target_distance_km(user: dict):
    """목표 거리(km). 거리를 직접 골랐으면 그대로, 시간만 골랐으면 기본 페이스로 환산한다."""
    if user.get("preferred_distance_km"):
        return user["preferred_distance_km"]
    if user.get("preferred_time_min"):
        # 시간으로 고른 경우에만 그 사람의 "길었다/짧았다" 평가를 반영한다. 거리를 직접 고른 건 그대로 따른다
        return round(user["preferred_time_min"] / DEFAULT_PACE_MIN_PER_KM * user.get("distance_scale", 1.0), 2)
    return None


def elevation_target_m(user: dict) -> float:
    """사용자가 고른 고도 선호 기준. 러닝 후 "힘들었다/평탄했다"는 답으로 그 사람의 기준을 맞춘다."""
    pref = user.get("elevation_preference") or "medium"
    target = ELEVATION_PREFERENCE_TARGET_M.get(pref, ELEVATION_PREFERENCE_TARGET_M["medium"])
    return target * user.get("elevation_scale", 1.0)
