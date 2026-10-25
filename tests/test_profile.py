"""고른 거리·시간이 목표 거리로 바뀌는지 검증. (숙련도·페이스·목적 입력은 뺐다)"""
from src.recommend.profile import DEFAULT_PACE_MIN_PER_KM, elevation_target_m, resolve_target_distance_km


class TestTimeToDistance:
    def test_time_converts_to_distance_with_the_default_pace(self):
        assert resolve_target_distance_km({"preferred_time_min": 40}) == round(40 / DEFAULT_PACE_MIN_PER_KM, 2)

    def test_explicit_distance_takes_priority_over_time(self):
        assert resolve_target_distance_km({"preferred_distance_km": 3, "preferred_time_min": 60}) == 3

    def test_runner_who_said_too_long_gets_shorter_course_for_the_same_time(self):
        usual = resolve_target_distance_km({"preferred_time_min": 30})
        assert resolve_target_distance_km({"preferred_time_min": 30, "distance_scale": 0.9}) < usual

    def test_chosen_distance_is_not_rescaled(self):
        assert resolve_target_distance_km({"preferred_distance_km": 5, "distance_scale": 0.8}) == 5

    def test_no_time_and_no_distance_returns_none(self):
        assert resolve_target_distance_km({}) is None


def test_elevation_preference_sets_the_climb_target():
    """고도는 지금 꺼져 있지만, 켤 때를 위해 기준은 남겨 둔다."""
    assert elevation_target_m({"elevation_preference": "high"}) > elevation_target_m({"elevation_preference": "low"})
