"""팀 기준 지도 파일 받기: 날짜를 고정한 Geofabrik 파일은 1주일 뒤 사라졌다(south-korea-260929.osm.pbf, 404).
같은 파일을 우리 서버에서도 내려주고, 받을 곳을 차례로 시도한다. 어디서 받든 MD5로 같은 파일인지 확인한다."""
import hashlib

import pytest
import requests

from src.data_collection import local_osm

GOOD = b"team map file"
OTHER = b"some other day's map"


@pytest.fixture()
def sources(monkeypatch):
    """주소 → 돌려줄 내용(없으면 404). 물어본 주소를 기록한다."""
    asked, served = [], {}
    monkeypatch.setattr(local_osm, "PBF_MD5", hashlib.md5(GOOD).hexdigest())

    class Response:
        def __init__(self, url):
            self.url, self.body = url, served.get(url)
            self.headers = {"content-length": str(len(self.body or b""))}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def raise_for_status(self):
            if self.body is None:
                raise requests.HTTPError(f"404 for {self.url}")

        def iter_content(self, size):
            yield self.body

    def get(url, **kwargs):
        asked.append(url)
        return Response(url)

    monkeypatch.setattr(requests, "get", get)
    return asked, served


def test_the_next_source_is_tried_when_one_is_gone(sources, tmp_path):
    asked, served = sources
    first, second = local_osm.pbf_sources()[:2]
    served[second] = GOOD
    path = str(tmp_path / "map.pbf")
    local_osm.download(path)
    assert asked[:2] == [first, second]
    assert open(path, "rb").read() == GOOD


def test_a_source_with_a_different_file_is_not_used(sources, tmp_path):
    asked, served = sources
    first, second = local_osm.pbf_sources()[:2]
    served[first], served[second] = OTHER, GOOD
    path = str(tmp_path / "map.pbf")
    local_osm.download(path)
    assert open(path, "rb").read() == GOOD, "MD5가 다른 파일은 버리고 다음 곳에서 받는다"


def test_when_no_source_has_the_file_setup_stops_and_says_where_to_get_it(sources, tmp_path):
    with pytest.raises(SystemExit, match="팀원"):
        local_osm.download(str(tmp_path / "map.pbf"))
    assert not (tmp_path / "map.pbf").exists() and not (tmp_path / "map.pbf.part").exists()


def test_our_server_is_asked_first_and_can_be_changed(monkeypatch):
    assert "sslip.io" in local_osm.pbf_sources()[0], "우리 서버를 먼저 (Geofabrik에서 사라져도 받을 수 있게)"
    assert "geofabrik" in local_osm.pbf_sources()[-1]
    monkeypatch.setenv("RUNMATE_PBF_URL", "https://example.test/map.pbf")
    assert local_osm.pbf_sources()[0] == "https://example.test/map.pbf", "서버 주소가 바뀌면 환경변수로 준다"
