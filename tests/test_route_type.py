from src.recommend.route_type import apply_route_type, make_roundtrip, mark_oneway

COURSE = {
    "id": "c1",
    "distance_km": 3.0,
    "elevation_gain_m": 30.0,
    "path": [[34.70, 127.70], [34.71, 127.70], [34.72, 127.70]],
    "steps": [{"lat": 34.70, "lng": 127.70, "description": "출발", "turn_type": 200}],
}


def test_make_roundtrip_doubles_distance_and_mirrors_path():
    rt = make_roundtrip(COURSE)
    assert rt["distance_km"] == 6.0
    assert rt["elevation_gain_m"] == 60.0
    assert rt["route_type"] == "roundtrip"
    assert len(rt["path"]) == 2 * len(COURSE["path"]) - 1
    assert rt["path"][0] == COURSE["path"][0]
    assert rt["path"][-1] == COURSE["path"][0]  # 왕복이니 출발점으로 되돌아옴


def test_make_roundtrip_adds_turnaround_step():
    rt = make_roundtrip(COURSE)
    assert len(rt["steps"]) == len(COURSE["steps"]) + 1
    assert "반환점" in rt["steps"][-1]["description"]


def test_mark_oneway_leaves_path_untouched():
    ow = mark_oneway(COURSE)
    assert ow["path"] == COURSE["path"]
    assert ow["distance_km"] == COURSE["distance_km"]
    assert ow["route_type"] == "oneway"


def test_apply_route_type_dispatches():
    assert apply_route_type(COURSE, "roundtrip")["distance_km"] == 6.0
    assert apply_route_type(COURSE, "oneway")["distance_km"] == 3.0
