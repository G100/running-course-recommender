"""누구와 함께 뛰는지에 따라 맞는 코스가 다르다.

유아차는 계단·턱이 문제이고, 반려견은 뜨거운 아스팔트와 신호등 대기가 문제이고,
러닝크루는 여럿이 나란히 달릴 폭이 필요하다. 같은 "5km 코스"가 전부 다른 뜻이 된다.
"""
import pytest

from src.recommend.companion import COMPANIONS, companion_limits, companion_options, tune_for_companion
from src.recommend.score import DEFAULT_WEIGHTS

FLAT_CARFREE = {"distance_km": 5, "elevation_gain_m": 10, "traffic_signal_count": 0, "tags": ["차없는길"]}
HILLY_URBAN = {"distance_km": 5, "elevation_gain_m": 200, "traffic_signal_count": 20, "tags": ["도심"]}


def test_every_companion_is_offered_to_the_app():
    options = companion_options()
    assert len(options) >= 5
    assert all("value" in o and "label" in o for o in options)
    assert {o["value"] for o in options} == set(COMPANIONS)


def test_unknown_companion_leaves_weights_untouched():
    assert tune_for_companion(DEFAULT_WEIGHTS, "듣도보도못한동반자") == DEFAULT_WEIGHTS


def test_weights_still_sum_to_one():
    for companion in COMPANIONS:
        assert sum(tune_for_companion(DEFAULT_WEIGHTS, companion).values()) == pytest.approx(1.0)


def test_stroller_cares_most_about_flat_and_uninterrupted():
    tuned = tune_for_companion(DEFAULT_WEIGHTS, "유아차")
    assert tuned["elevation"] > DEFAULT_WEIGHTS["elevation"]
    assert tuned["signal_free"] > DEFAULT_WEIGHTS["signal_free"]


def test_dog_avoids_traffic_signals_more_than_running_alone():
    assert tune_for_companion(DEFAULT_WEIGHTS, "반려견")["signal_free"] > DEFAULT_WEIGHTS["signal_free"]


def test_companions_cap_distance_and_elevation_differently():
    stroller = companion_limits("유아차")
    alone = companion_limits("혼자")
    assert stroller["max_distance_km"] < alone["max_distance_km"]
    assert stroller["max_elevation_gain_m"] < alone["max_elevation_gain_m"]


def test_running_alone_has_no_special_limits():
    limits = companion_limits("혼자")
    assert limits["max_distance_km"] == float("inf")


def test_small_dog_is_capped_shorter_than_big_dog():
    assert companion_limits("소형견")["max_distance_km"] < companion_limits("반려견")["max_distance_km"]
