"""실시간 날씨/대기질을 코스 추천 점수에 반영.

MVP 스코프: "실시간 날씨/대기질 반영한 추천 조정" (프로젝트 문서 명시).
코스별 대표좌표/측정소는 course_stations.py의 근사 매핑을 사용.
"""
from ..api_clients.airkorea import get_air_quality
from ..api_clients.kma_weather import get_short_term_forecast
from .course_stations import COURSE_ENV_CONTEXT

_station_cache = {}


def _nearest_forecast_item(items: list, category: str):
    for it in items:
        if it.get("category") == category:
            return it.get("fcstValue")
    return None


def fetch_weather(lat: float, lng: float) -> dict:
    """POP(강수확률%), TMP(기온), SKY(하늘상태코드) 반환. 실패 시 빈 dict."""
    try:
        resp = get_short_term_forecast(lat, lng)
        items = resp.get("response", {}).get("body", {}).get("items", {}).get("item", [])
        return {
            "pop": _nearest_forecast_item(items, "POP"),
            "tmp": _nearest_forecast_item(items, "TMP"),
            "sky": _nearest_forecast_item(items, "SKY"),
        }
    except Exception:
        return {}


def fetch_air_quality(station: str) -> dict:
    """pm10Grade/pm25Grade(1=좋음~4=매우나쁨) 반환. 실패 시 빈 dict. 측정소 단위로 캐싱."""
    if station in _station_cache:
        return _station_cache[station]
    try:
        resp = get_air_quality(station)
        items = resp.get("response", {}).get("body", {}).get("items", [])
        result = {}
        if items:
            latest = items[0]
            result = {"pm10_grade": latest.get("pm10Grade"), "pm25_grade": latest.get("pm25Grade")}
    except Exception:
        result = {}
    _station_cache[station] = result
    return result


def get_environment_context(course_id: str) -> dict:
    """코스 id -> {pop, tmp, sky, pm10_grade, pm25_grade}. 매핑 없으면 빈 dict."""
    mapping = COURSE_ENV_CONTEXT.get(course_id)
    if not mapping:
        return {}
    context = {}
    context.update(fetch_weather(mapping["lat"], mapping["lng"]))
    context.update(fetch_air_quality(mapping["station"]))
    return context


def environment_score(context: dict) -> float:
    """날씨/대기질이 지금 러닝하기 얼마나 적합한지 0~1. 데이터 없으면 중립값 0.5."""
    if not context:
        return 0.5

    score = 1.0

    pop = context.get("pop")
    if pop is not None:
        pop = int(pop)
        if pop >= 70:
            score -= 0.4
        elif pop >= 40:
            score -= 0.2
        elif pop >= 20:
            score -= 0.05

    grade = max(
        (g for g in [context.get("pm10_grade"), context.get("pm25_grade")] if g not in (None, "")),
        default=None, key=lambda g: int(g),
    )
    if grade is not None:
        grade = int(grade)
        if grade == 4:
            score -= 0.5
        elif grade == 3:
            score -= 0.25
        elif grade == 2:
            score -= 0.05

    tmp = context.get("tmp")
    if tmp is not None:
        tmp = float(tmp)
        if tmp >= 33 or tmp <= -5:
            score -= 0.15

    return max(0.0, min(1.0, score))
