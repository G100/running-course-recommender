"""회전 안내에 근처 가게 이름을 붙인다: '왼쪽으로 도세요' 대신 'GS25 앞에서 왼쪽 용주로로 도세요'.

Tmap 보행자 경로는 회전 지점의 근처 장소(nearPoiName)를 대부분 비워 준다. 그래서 러너에게 내보내는 코스의
회전 지점만 Tmap 주변 검색으로 가장 가까운 가게를 찾는다. 한 번 물은 자리는 저장해서 다시 묻지 않는다
(가게가 없던 자리도). 코스를 만드는 도중의 후보에는 묻지 않는다 — 하루 한도를 아낀다.
"""
import pytest
import requests

from src.recommend import landmarks


@pytest.fixture()
def tmap(monkeypatch, tmp_path):
    """주변 검색 대신 정해 둔 가게 목록을 돌려준다. 물은 자리를 기록한다."""
    monkeypatch.setattr(landmarks, "DB_PATH", str(tmp_path / "landmarks.sqlite"))
    monkeypatch.setenv("TMAP_APP_KEY", "test-key")
    asked = []
    shops = {"places": []}

    def around(lat, lng):
        asked.append((lat, lng))
        if shops.get("fail"):
            raise requests.ConnectionError("down")
        return shops["places"]

    monkeypatch.setattr(landmarks, "search_around", around)
    return asked, shops


def _shop(name, lat, lng):
    return {"name": name, "lat": lat, "lng": lng}


def _turn(lat, lng, turn=12, road=None, landmark=None):
    words = {12: "좌회전", 13: "우회전", 11: "직진", 200: "출발", 201: "도착"}[turn]
    return {"lat": lat, "lng": lng, "turn_type": turn, "road": road, "landmark": landmark,
            "description": f"{words} 후 {road + '를 따라 ' if road else ''}50m 이동", "instruction": "?"}


def test_the_nearest_shop_within_reach_is_the_landmark(tmap):
    asked, shops = tmap
    shops["places"] = [_shop("이마트24 전남대공대점", 35.18030, 126.90780), _shop("맘스터치 전남대교내점", 35.18010, 126.90780)]
    assert landmarks.near(35.18000, 126.90780) == "맘스터치", "가장 가까운 곳, 지점 이름은 뗀다"


def test_a_sign_everyone_knows_beats_a_closer_small_shop(tmap):
    """'나정오리꽃날개튀김'보다 조금 더 먼 'CU'가 달리면서 찾기 쉽다 — 둘 다 모퉁이에서 보이면 체인·은행·약국을 쓴다."""
    asked, shops = tmap
    shops["places"] = [_shop("나정오리꽃날개튀김", 35.18005, 126.90780), _shop("CU 용봉점", 35.18025, 126.90780),
                       _shop("행복약국", 35.18030, 126.90780)]
    assert landmarks.near(35.18000, 126.90780) == "CU"


def test_a_shop_too_far_to_see_from_the_corner_is_not_used(tmap):
    asked, shops = tmap
    shops["places"] = [_shop("CU 용봉점", 35.18100, 126.90780)]   # 약 110m
    assert landmarks.near(35.18000, 126.90780) is None


def test_each_corner_is_asked_once_even_when_nothing_was_there(tmap):
    asked, shops = tmap
    assert landmarks.near(35.18000, 126.90780) is None
    shops["places"] = [_shop("GS25", 35.18001, 126.90780)]
    assert landmarks.near(35.180004, 126.907803) is None, "같은 자리(약 10m 안)는 저장해 둔 답을 쓴다"
    assert len(asked) == 1


def test_a_failed_search_is_not_remembered(tmap):
    asked, shops = tmap
    shops["fail"] = True
    assert landmarks.near(35.18000, 126.90780) is None
    shops["fail"] = False
    shops["places"] = [_shop("GS25 용봉점", 35.18001, 126.90780)]
    assert landmarks.near(35.18000, 126.90780) == "GS25", "실패는 저장하지 않아서 다음에 다시 묻는다"


def test_without_a_tmap_key_nothing_is_asked(tmap, monkeypatch):
    asked, _ = tmap
    monkeypatch.delenv("TMAP_APP_KEY")
    assert landmarks.near(35.18000, 126.90780) is None and asked == []


def test_turns_get_the_landmark_and_the_road_in_one_sentence(tmap):
    asked, shops = tmap
    shops["places"] = [_shop("GS25 용봉점", 35.18001, 126.90780)]
    steps = [_turn(35.17000, 126.90000, 200), _turn(35.18000, 126.90780, 12, road="용주로"),
             _turn(35.18500, 126.90780, 11), _turn(35.19000, 126.90000, 201)]
    out = landmarks.add_landmarks(steps)
    assert [s["instruction"] for s in out] == ["?", "GS25 앞에서 왼쪽 용주로로 도세요", "?", "?"]
    assert len(asked) == 1, "출발·직진·도착에는 묻지 않는다"


def test_a_landmark_tmap_already_gave_is_kept_and_not_asked_again(tmap):
    asked, _ = tmap
    out = landmarks.add_landmarks([_turn(35.18000, 126.90780, 13, landmark="스타벅스")])
    assert asked == [] and out[0]["instruction"] == "?"
