from src.api_clients import tmap_pedestrian


def test_get_route_sends_waypoints_as_tmap_pass_list(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"features": []}

    def post(url, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setenv("TMAP_APP_KEY", "test-key")
    monkeypatch.setattr(tmap_pedestrian.requests, "post", post)

    tmap_pedestrian.get_route(
        (127.0, 34.0), (127.0, 34.0),
        waypoints=[(127.001, 34.001), (127.002, 34.002)],
    )

    assert captured["json"]["passList"] == "127.001,34.001_127.002,34.002"

def _point(description, turn, **props):
    return {"geometry": {"type": "Point", "coordinates": [127.0, 34.0]},
            "properties": dict(description=description, turnType=turn, **props)}


class TestRunnerFriendlyInstructions:
    """Tmap 안내 문구("우회전 후 보행자도로를 따라 125m 이동")는 달리는 사람이 듣기에 길고 어렵다.
    무엇을 하면 되는지를 먼저, 알아볼 수 있는 곳(가게·교차로)이 있으면 그곳을 기준으로 말한다."""

    def _say(self, *points):
        return [s["instruction"] for s in tmap_pedestrian.extract_steps({"features": list(points)})]

    def test_turns_become_plain_actions(self):
        assert self._say(_point("우회전 후 보행자도로를 따라 125m 이동", 13),
                         _point("좌회전 후 47m 이동", 12),
                         _point("10시 방향 좌회전 후 30m 이동", 17)) == [
            "오른쪽으로 도세요", "왼쪽으로 도세요", "왼쪽으로 살짝 꺾으세요"]

    def test_a_nearby_place_is_used_as_the_landmark(self):
        assert self._say(_point("우회전 후 30m 이동", 13, nearPoiName="GS25 해운대점")) == ["GS25 해운대점 앞에서 오른쪽으로 도세요"]

    def test_the_road_to_follow_is_named_but_generic_path_words_are_not(self):
        assert self._say(_point("좌회전 후 구남로를 따라 210m 이동", 12),
                         _point("직진 후 보행자도로를 따라 80m 이동", 11)) == [
            "왼쪽으로 도세요 · 구남로 따라", "쭉 가세요"]

    def test_crossings_and_stairs_say_what_is_ahead(self):
        assert self._say(_point("횡단보도 후 20m 이동", 211), _point("우측 횡단보도 후 15m 이동", 213),
                         _point("계단 진입 후 10m 이동", 127), _point("도착", 201)) == [
            "횡단보도를 건너세요", "오른쪽 횡단보도를 건너세요", "계단이 있어요", "도착했어요"]

    def test_unknown_turn_keeps_tmaps_own_words(self):
        assert self._say(_point("엘리베이터 이용 후 5m 이동", 999)) == ["엘리베이터 이용 후 5m 이동"]
        steps = tmap_pedestrian.extract_steps({"features": [_point("우회전 후 30m 이동", 13)]})
        assert steps[0]["description"] == "우회전 후 30m 이동", "원래 문구도 그대로 둔다"


class TestDailyLimit:
    """Tmap 하루 한도(무료 1,000건)를 넘으면 한도가 풀릴 때까지 무엇을 물어도 거절당한다. 그런데도 조각마다
    1·2초씩 쉬며 세 번씩 다시 물었고, 다른 곳(인도 확인)도 계속 물었다. 넘었다는 걸 기억하고 묻지 않는다."""

    def _tmap(self, monkeypatch, answers):
        import requests
        sent = []

        class Response:
            def __init__(self, status, body):
                self.status_code, self.body = status, body

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise requests.HTTPError(f"{self.status_code} Client Error", response=self)

            def json(self):
                return self.body

        def post(url, **kwargs):
            sent.append(kwargs)
            return Response(*answers.pop(0))

        monkeypatch.setenv("TMAP_APP_KEY", "test-key")
        monkeypatch.setattr(tmap_pedestrian.requests, "post", post)
        return sent

    QUOTA = (429, {"error": {"id": "429", "category": "gw", "code": "QUOTA_EXCEEDED", "message": "Limit Exceeded"}})
    BUSY = (429, {"error": {"code": "TOO_MANY_REQUESTS"}})
    OK = (200, {"features": []})

    def test_the_daily_limit_is_told_apart_from_being_busy(self, monkeypatch):
        import pytest
        import requests
        self._tmap(monkeypatch, [self.QUOTA])
        with pytest.raises(tmap_pedestrian.DailyLimitReached) as caught:
            tmap_pedestrian.get_route((127.0, 34.0), (127.01, 34.0))
        assert isinstance(caught.value, requests.HTTPError), "예전처럼 HTTPError로 받는 곳도 그대로 동작한다"

    def test_after_the_limit_tmap_is_not_asked_again_for_a_while(self, monkeypatch):
        import pytest
        sent = self._tmap(monkeypatch, [self.QUOTA, self.OK])
        clock = [1000.0]
        monkeypatch.setattr(tmap_pedestrian.time, "time", lambda: clock[0])
        with pytest.raises(tmap_pedestrian.DailyLimitReached):
            tmap_pedestrian.get_route((127.0, 34.0), (127.01, 34.0))
        clock[0] += tmap_pedestrian.LIMIT_RECHECK_S - 1
        with pytest.raises(tmap_pedestrian.DailyLimitReached):
            tmap_pedestrian.get_route((127.0, 34.0), (127.01, 34.0))
        assert len(sent) == 1, "한도를 넘은 동안은 묻지 않는다"
        clock[0] += 2
        assert tmap_pedestrian.get_route((127.0, 34.0), (127.01, 34.0)) == {"features": []}, "한동안 지나면 다시 물어본다"
        assert len(sent) == 2

    def test_being_busy_is_not_remembered(self, monkeypatch):
        import pytest
        import requests
        sent = self._tmap(monkeypatch, [self.BUSY, self.OK])
        with pytest.raises(requests.HTTPError) as caught:
            tmap_pedestrian.get_route((127.0, 34.0), (127.01, 34.0))
        assert not isinstance(caught.value, tmap_pedestrian.DailyLimitReached)
        assert tmap_pedestrian.get_route((127.0, 34.0), (127.01, 34.0)) == {"features": []} and len(sent) == 2
