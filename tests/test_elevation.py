"""표고 조회: 코스 만드는 시간의 대부분(12.8초 중 11.3초)이 무료 표고 API를 기다리는 시간이었다."""
import pytest

from src.api_clients import elevation


class FakeApi:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def __call__(self, url, params=None, timeout=None):
        points = [tuple(map(float, p.split(","))) for p in params["locations"].split("|")]
        self.calls.append(points)
        if self.fail:
            import requests
            raise requests.HTTPError("429 Too Many Requests")
        return type("R", (), {"raise_for_status": lambda self: None,
                              "json": lambda self: {"results": [{"elevation": lat * 1000} for lat, _ in points]}})()


@pytest.fixture
def api(monkeypatch):
    fake = FakeApi()
    monkeypatch.setattr(elevation.requests, "get", fake)
    return fake


def test_looked_up_points_are_not_asked_again(api):
    first = elevation.get_elevation_profile([(34.0, 127.0), (34.001, 127.0)])
    again = elevation.get_elevation_profile([(34.0, 127.0), (34.001, 127.0), (34.002, 127.0)])
    assert again[:2] == first
    assert len(api.calls) == 2 and api.calls[1] == [(34.002, 127.0)], "이미 아는 지점까지 다시 물었다"


def test_remembered_points_survive_a_server_restart(api, monkeypatch):
    elevation.get_elevation_profile([(35.0, 128.0)])
    monkeypatch.setattr(elevation, "_memory", {})          # 서버를 다시 켠 것처럼
    elevation.get_elevation_profile([(35.0, 128.0)])
    assert len(api.calls) == 1


def test_several_courses_are_measured_with_one_request(api):
    from src.recommend.generate_live import sample_elevation_gains

    paths = [[(34.0 + i * 0.0001, 127.0 + k * 0.001) for i in range(40)] for k in range(3)]
    gains = sample_elevation_gains(paths)
    assert len(gains) == 3 and all(g > 0 for g in gains)
    assert len(api.calls) == 1


def test_elevation_failure_does_not_lose_the_course(monkeypatch):
    """표고 API가 막혀도(무료 한도) 코스는 내보낸다 — 고도는 모른다고 표시한다."""
    from src.recommend.generate_live import sample_elevation_gains

    monkeypatch.setattr(elevation.requests, "get", FakeApi(fail=True))
    assert sample_elevation_gains([[(34.0, 127.0), (34.01, 127.0)]]) == [None]


def test_scenery_tags_do_not_need_the_elevation_yet():
    """고도는 후보를 다 만든 뒤 한 번에 잰다. 그 전에 풍경을 재도 멈추면 안 된다 (다시 추천받기가 500이 났다)."""
    from src.data_collection import scenery

    tags = scenery.scenery_tags({"forest": 1.0}, {"distance_km": 3.0, "elevation_gain_m": None})
    assert "숲길" in tags and "산길" not in tags


def test_mountain_tag_is_added_once_the_elevation_is_known(monkeypatch):
    from src.recommend import generate_live

    from src.recommend import score

    monkeypatch.setattr(score, "ELEVATION_ENABLED", True)
    monkeypatch.setattr(generate_live, "sample_elevation_gains", lambda paths: [300.0])
    course = {"path": [[34.0, 127.0], [34.01, 127.0]], "distance_km": 3.0, "elevation_gain_m": None,
              "scenery": {"forest": 1.0}, "tags": ["숲길"]}
    generate_live.measure_elevations([course])
    assert course["elevation_gain_m"] == 300.0 and "산길" in course["tags"]


def test_no_elevation_lookup_while_elevation_is_off(monkeypatch):
    """고도를 꺼 둔 동안에는 표고 API를 부르지 않는다 (코스 만드는 시간 대부분이 그 대기였다)."""
    from src.recommend import generate_live

    monkeypatch.setattr(elevation.requests, "get", lambda *a, **k: pytest.fail("표고 API를 불렀다"))
    course = {"path": [[34.0, 127.0], [34.01, 127.0]], "distance_km": 3.0, "elevation_gain_m": None}
    generate_live.measure_elevations([course])
    assert course["elevation_gain_m"] is None
