"""지금이 어느 시간대인가. 밤이면 인적 드문 길을 피해 코스를 짜고, 그래도 그런 길로 가야
풍경을 볼 수 있으면 사용자에게 물어본다 (점수에는 넣지 않는다).

시간대는 사용자에게 물어볼 필요가 없다 — 요청이 들어온 시각을 보면 안다.
(밤에 미리 내일 아침 코스를 짜는 경우를 위해 `time_of_day`로 직접 지정할 수는 있다.)
"""
from datetime import datetime

PERIODS = ("morning", "afternoon", "evening", "night")


def current_period(now: datetime = None) -> str:
    hour = (now or datetime.now()).hour
    if 5 <= hour < 11:
        return "morning"
    if 11 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "night"
