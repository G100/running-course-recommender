from src.recommend.environment import environment_score
from src.recommend.score import score_course

SAMPLE_COURSE = {
    "id": "test-course",
    "distance_km": 4,
    "elevation_gain_m": 20,
    "safety_score": 0.8,
    "traffic_signal_count": 0,
    "tags": ["바다뷰"],
}
SAMPLE_USER = {"preferred_distance_km": 4, "elevation_preference": "low", "environment_tags": {"바다뷰"}}


def test_environment_score_no_data_is_neutral():
    assert environment_score({}) == 0.5


def test_environment_score_penalizes_rain_and_bad_air():
    good = environment_score({"pop": 0, "pm10_grade": 1, "pm25_grade": 1, "tmp": 20})
    bad = environment_score({"pop": 80, "pm10_grade": 4, "pm25_grade": 4, "tmp": 20})
    assert good > bad
    assert bad < 0.2


def test_score_course_uses_environment_weight_when_context_given():
    without_env = score_course(SAMPLE_COURSE, SAMPLE_USER)
    with_bad_env = score_course(SAMPLE_COURSE, SAMPLE_USER, env_context={"pop": 90, "pm10_grade": 4})
    with_good_env = score_course(SAMPLE_COURSE, SAMPLE_USER, env_context={"pop": 0, "pm10_grade": 1})
    assert with_good_env > with_bad_env
    assert without_env != with_bad_env
