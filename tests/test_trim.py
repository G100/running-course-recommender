from src.recommend.trim import truncate_course

LONG_COURSE = {
    "id": "long",
    "distance_km": 10.0,
    "elevation_gain_m": 100.0,
    "tags": ["숲길"],
    # 4 points roughly 0.01 lat apart (~1.11km each) along a line, ~3.33km total
    "path": [[34.70, 127.70], [34.71, 127.70], [34.72, 127.70], [34.73, 127.70]],
}


def test_truncate_shortens_path_and_distance():
    trimmed = truncate_course(LONG_COURSE, target_km=1.0)
    assert trimmed["trimmed"] is True
    assert trimmed["original_distance_km"] == 10.0
    assert abs(trimmed["distance_km"] - 1.0) < 0.05
    assert len(trimmed["path"]) < len(LONG_COURSE["path"])
    assert trimmed["path"][0] == LONG_COURSE["path"][0]


def test_truncate_leaves_short_course_untouched():
    short = dict(LONG_COURSE, distance_km=2.0)
    result = truncate_course(short, target_km=5.0)
    assert result is short
    assert "trimmed" not in result


def test_truncate_drops_steps_past_the_cut():
    course_with_steps = dict(LONG_COURSE, steps=[
        {"lat": 34.70, "lng": 127.70, "description": "출발", "turn_type": 200},
        {"lat": 34.71, "lng": 127.70, "description": "1.1km 지점 좌회전", "turn_type": 12},
        {"lat": 34.73, "lng": 127.70, "description": "도착 (3.3km 지점)", "turn_type": 201},
    ])
    trimmed = truncate_course(course_with_steps, target_km=1.0)
    descriptions = [s["description"] for s in trimmed["steps"]]
    assert "출발" in descriptions
    assert "도착 (3.3km 지점)" not in descriptions
