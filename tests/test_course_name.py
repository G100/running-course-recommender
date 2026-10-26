"""만든 코스의 이름은 러너가 알아볼 수 있는 말이어야 한다.

예전 이름은 "현위치 기반 순환 코스 (바다뷰·해변, -20°, 반경 80%)"였다. 각도·반경은 코스를 만드는 내부 값이라
러너에게는 뜻이 없다(발표 화면에도 그대로 나왔다). 왕복을 요청해도 "편도 코스"라고 나왔다.
이름은 출발점에서 어느 쪽으로 가는지 + 코스 모양 + 대표 풍경으로 짓는다.
"""
from src.recommend.generate_live import course_name

LAT, LNG = 35.0, 127.0


def _loop_toward(dlat, dlng):
    """출발점에서 (dlat, dlng) 쪽으로 다녀오는 작은 고리."""
    return [[LAT, LNG], [LAT + dlat, LNG], [LAT + dlat, LNG + dlng], [LAT, LNG + dlng], [LAT, LNG]]


def test_loop_is_named_by_the_side_it_runs_on():
    assert course_name(LAT, LNG, _loop_toward(0.0, -0.01), "loop", []) == "서쪽 순환 코스"
    assert course_name(LAT, LNG, _loop_toward(0.01, 0.01), "loop", []) == "북동쪽 순환 코스"


def test_one_way_and_round_trip_are_named_by_where_they_head():
    out = [[LAT, LNG], [LAT - 0.005, LNG], [LAT - 0.01, LNG]]
    assert course_name(LAT, LNG, out, "oneway", []) == "남쪽 편도 코스"
    there_and_back = out + out[-2::-1]
    assert course_name(LAT, LNG, there_and_back, "roundtrip", []) == "남쪽 왕복 코스"


def test_main_scenery_is_added_in_the_words_the_runner_chose_from():
    name = course_name(LAT, LNG, _loop_toward(0.0, -0.01), "loop", ["해변", "바다뷰", "공원"])
    assert name == "서쪽 순환 코스 · 바다·공원"


def test_name_has_no_internal_values():
    name = course_name(LAT, LNG, _loop_toward(0.01, 0.0), "loop", ["강변"])
    assert "°" not in name and "반경" not in name and "기본" not in name and "현위치" not in name
