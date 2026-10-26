"""지금 시각으로 시간대를 정한다. 밤이면 인적 드문 길을 피해 코스를 짠다 (사용자에게 묻지 않는다)."""
from datetime import datetime

from src.recommend.timeofday import current_period


def _at(hour):
    return datetime(2026, 9, 16, hour, 0)


def test_hours_map_to_periods():
    assert current_period(_at(7)) == "morning"
    assert current_period(_at(14)) == "afternoon"
    assert current_period(_at(19)) == "evening"
    assert current_period(_at(23)) == "night"
    assert current_period(_at(3)) == "night"
