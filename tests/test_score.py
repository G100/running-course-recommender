import json
import os

import pytest

from src.recommend.score import (DEFAULT_WEIGHTS, car_free_match, component_scores, distance_match, flow_match,
                                 recommend, score_course, tag_match)

SAMPLE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "courses.sample.json")


@pytest.fixture
def courses():
    with open(SAMPLE_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_score_is_distance_scenery_flow_and_car_free():
    assert DEFAULT_WEIGHTS == {"distance": 0.30, "tag_match": 0.25, "flow": 0.25, "car_free": 0.20}
    assert set(component_scores({"distance_km": 5}, {"preferred_distance_km": 5})) == set(DEFAULT_WEIGHTS)


def test_coastal_lover_prefers_coastal_course(courses):
    user = {"preferred_distance_km": 4, "environment_tags": {"바다뷰"}}
    top = recommend(courses, user, top_n=1)[0][0]
    assert top["id"] == "yeosu-coastal-01"


def test_required_tag_excludes_courses_without_it(courses):
    """바다뷰를 골랐으면 바다가 없는 내륙 코스는 점수와 무관하게 결과에서 빠져야 한다."""
    user = {"preferred_distance_km": 5, "environment_tags": {"바다뷰"}}
    ids = [c["id"] for c, _ in recommend(courses, user, top_n=10)]
    assert "gwangju-urban-01" not in ids
    assert "gwangju-park-01" not in ids
    assert "yeosu-coastal-01" in ids


# 거리: 1 − 0.5 × (오차 ÷ 5%). 5% 오차에서 0.5점, 10%에서 0점
def test_exact_distance_is_full_marks():
    assert distance_match({"distance_km": 5.0, "route_type": "loop"}, {"preferred_distance_km": 5}) == 1.0


def test_distance_loses_half_at_five_percent_and_all_at_ten():
    user = {"preferred_distance_km": 5}
    assert distance_match({"distance_km": 5.25, "route_type": "loop"}, user) == pytest.approx(0.5)
    assert distance_match({"distance_km": 4.75, "route_type": "loop"}, user) == pytest.approx(0.5)
    assert distance_match({"distance_km": 4.5, "route_type": "loop"}, user) == 0.0
    assert distance_match({"distance_km": 3.0, "route_type": "loop"}, user) == 0.0


def test_longer_one_way_counts_as_exact_because_it_is_trimmed():
    """편도·왕복은 목표 거리에서 잘라 주므로 길어도 목표 거리 그대로 달리게 된다."""
    user = {"preferred_distance_km": 5}
    assert distance_match({"distance_km": 9.0, "route_type": "oneway"}, user) == 1.0
    assert distance_match({"distance_km": 9.0, "route_type": "loop"}, user) == 0.0


def test_no_target_distance_is_neutral():
    assert distance_match({"distance_km": 5.0}, {}) == 0.5


# 풍경: 고른 풍경 비율 ÷ (기준 × 2), 기준을 겨우 넘으면 0.5점, 2배면 만점
def test_scenery_ratio_is_scored_against_twice_the_threshold():
    user = {"environment_tags": {"바다뷰"}}                     # 기준: 경로의 40%가 해안
    half = {"tags": ["바다뷰"], "scenery": {"coast": 0.4}}
    full = {"tags": ["바다뷰"], "scenery": {"coast": 0.9}}
    assert tag_match(half, user) == pytest.approx(0.5)
    assert tag_match(full, user) == 1.0


def test_each_chosen_scenery_counts_equally():
    user = {"environment_tags": {"바다뷰", "공원"}, "scenery_groups": [["바다뷰"], ["공원"]]}
    course = {"tags": ["바다뷰"], "scenery": {"coast": 0.8, "park": 0.0}}
    assert tag_match(course, user) == pytest.approx(0.5)


def test_without_chosen_scenery_green_and_water_count():
    """풍경을 안 골랐으면 녹지·물가를 얼마나 지나는지로 본다 (러너 77%가 녹지를 원한다)."""
    grey = {"scenery": {"park": 0.05}}
    green = {"scenery": {"park": 0.3, "river": 0.95}}
    assert tag_match(grey, {}) == 0.0
    assert tag_match(green, {}) == 1.0
    assert 0 < tag_match({"scenery": {"forest": 0.5}}, {}) < 1


# 흐름: 신호등·꺾기·갈림길(각각 km당). 실제 코스 53개의 상위 10%면 만점, 하위 10%면 0점
def test_flow_is_full_marks_without_stops_turns_or_junctions():
    course = {"distance_km": 5, "traffic_signal_count": 0, "turns_per_km": 1.0, "junctions_per_km": 2.0}
    assert flow_match(course, {}) == 1.0


def test_flow_is_zero_on_a_choppy_downtown_route():
    course = {"distance_km": 5, "traffic_signal_count": 15, "turns_per_km": 7, "junctions_per_km": 15}
    assert flow_match(course, {}) == 0.0


def test_flow_counts_stops_per_km_not_in_total():
    """9km에 신호 9개가 2km에 6개보다 낫다. 체감은 얼마나 자주 멈추는가다."""
    short_dense = {"distance_km": 2.0, "traffic_signal_count": 6}
    long_sparse = {"distance_km": 9.0, "traffic_signal_count": 9}
    assert flow_match(long_sparse, {}) > flow_match(short_dense, {})


def test_flow_measures_turns_from_the_path_when_not_stored():
    straight = {"distance_km": 2, "traffic_signal_count": 0,
                "path": [[37.0 + i * 0.0009, 127.0] for i in range(21)]}
    assert flow_match(straight, {}) == 1.0


def test_flow_without_any_measurement_is_neutral():
    assert flow_match({"distance_km": 5}, {}) == 0.5


# 차 없는 길: 경로 중 차가 다니지 않는 길의 비율
def test_car_free_is_the_share_of_car_free_paths():
    assert car_free_match({"road_mix": {"car_free": 0.8, "sidewalk": 0.2}}, {}) == 0.8


def test_car_free_falls_back_to_measured_scenery_then_neutral():
    assert car_free_match({"scenery": {"carfree": 0.3}}, {}) == 0.3
    assert car_free_match({}, {}) == 0.5


def test_park_beats_downtown_when_both_fit_the_distance(courses):
    user = {"preferred_distance_km": 3}
    urban = next(c for c in courses if c["id"] == "gwangju-urban-01")
    park = next(c for c in courses if c["id"] == "gwangju-park-01")
    assert score_course(park, user) > score_course(urban, user)


def test_elevation_does_not_change_the_ranking_while_it_is_off():
    """고도 데이터가 부정확해 꺼 둔 동안에는(평지도 25~40m로 잰다) 고도 선호가 순위를 바꾸지 않는다."""
    from src.recommend import score

    assert score.ELEVATION_ENABLED is False
    flat = {"id": "flat-loop", "route_type": "loop", "distance_km": 5.0, "elevation_gain_m": 20,
            "traffic_signal_count": 0, "tags": []}
    hilly = {**flat, "id": "hilly-loop", "elevation_gain_m": 150}
    low = {"preferred_distance_km": 5.0, "elevation_preference": "low"}
    high = dict(low, elevation_preference="high")
    assert score_course(flat, low) == score_course(flat, high) == score_course(hilly, low)
    assert "elevation" not in component_scores(flat, low)


def test_ranking_changes_with_elevation_preference_when_turned_on(monkeypatch):
    from src.recommend import score

    monkeypatch.setattr(score, "ELEVATION_ENABLED", True)
    flat = {"id": "flat-loop", "route_type": "loop", "distance_km": 5.0, "elevation_gain_m": 20,
            "traffic_signal_count": 0, "tags": []}
    hilly = {**flat, "id": "hilly-loop", "elevation_gain_m": 150}
    low_top = recommend([flat, hilly], {"preferred_distance_km": 5.0, "elevation_preference": "low"}, top_n=1)[0][0]
    high_top = recommend([flat, hilly], {"preferred_distance_km": 5.0, "elevation_preference": "high"}, top_n=1)[0][0]
    assert low_top["id"] == "flat-loop"
    assert high_top["id"] == "hilly-loop"
