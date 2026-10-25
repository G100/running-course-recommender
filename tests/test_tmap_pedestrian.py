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
