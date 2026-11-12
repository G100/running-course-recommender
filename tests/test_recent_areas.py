"""최근 코스를 만든 동네의 지도를 기억해 두었다가, 서버가 다시 켜질 때 뒤에서 미리 불러 둔다.

처음 요청에서 그 동네 지도를 읽고 길마다 점수를 매기는 데만 5~6초가 들었다(여의도 5km 순환). 코스는 매번 새로
짜고, 미리 해 두는 건 지도 데이터뿐이다. 기억하는 건 동네(격자 칸)의 위치라 사람의 정확한 위치는 남지 않는다.
"""
import json
import threading

import pytest

from src.data_collection import area_cache, local_osm

LAT, LNG = 35.0, 127.0


def _way(wid, coords, **tags):
    return {"type": "way", "id": wid, "geometry": [{"lat": a, "lon": b} for a, b in coords], "tags": tags}


TOWN = [_way(1, [(LAT, LNG), (LAT, LNG + 0.002)], highway="footway"),
        _way(2, [(LAT, LNG + 0.002), (LAT + 0.002, LNG + 0.002)], highway="residential"),
        _way(9, [(LAT + 0.001, LNG - 0.001), (LAT + 0.001, LNG + 0.003)], waterway="river")]


@pytest.fixture
def local_map(monkeypatch, tmp_path):
    """로컬 지형 DB가 있는 것처럼: 읽을 때마다 센다."""
    reads = []
    monkeypatch.setattr(local_osm, "available", lambda: True)
    monkeypatch.setattr(local_osm, "load_bbox", lambda bbox, *a, **k: reads.append(bbox) or list(TOWN))
    monkeypatch.setattr(area_cache, "RECENT_PATH", str(tmp_path / "recent_areas.json"))
    return reads


def recent(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_a_new_neighbourhood_is_remembered(local_map):
    area_cache.load_area(LAT, LNG, radius_m=900)
    remembered = recent(area_cache.RECENT_PATH)
    assert len(remembered) == 1
    lat, lng, half = remembered[0]
    assert (lat, lng) == area_cache._cell(LAT, LNG), "격자 칸의 위치만 남긴다 (사람의 정확한 위치가 아니다)"


def test_the_most_recent_neighbourhoods_come_first_and_only_a_few_are_kept(local_map):
    for i in range(area_cache.RECENT_KEEP + 3):
        area_cache.load_area(LAT + 0.1 * i, LNG, radius_m=900)
    remembered = recent(area_cache.RECENT_PATH)
    assert len(remembered) == area_cache.RECENT_KEEP
    assert remembered[0][0] == area_cache._cell(LAT + 0.1 * (area_cache.RECENT_KEEP + 2), LNG)[0]
    reads = len(local_map)
    area_cache.load_area(LAT + 0.1 * 4, LNG, radius_m=900)   # 불러 둔 동네를 다시 쓰면 — 새로 읽지 않고 맨 앞으로
    assert len(local_map) == reads
    assert recent(area_cache.RECENT_PATH)[0][0] == area_cache._cell(LAT + 0.1 * 4, LNG)[0]


def test_asking_again_for_a_remembered_neighbourhood_moves_it_to_the_front(local_map, monkeypatch):
    area_cache.load_area(LAT, LNG, radius_m=900)
    area_cache.load_area(LAT + 0.5, LNG, radius_m=900)
    monkeypatch.setattr(area_cache, "_memory", {})        # 서버를 다시 켰다
    area_cache.load_area(LAT, LNG, radius_m=900)
    remembered = recent(area_cache.RECENT_PATH)
    assert [r[0] for r in remembered] == [area_cache._cell(LAT, LNG)[0], area_cache._cell(LAT + 0.5, LNG)[0]]


def test_warming_loads_the_remembered_neighbourhoods_and_scores_their_roads(local_map, monkeypatch):
    area_cache.load_area(LAT, LNG, radius_m=900)
    area_cache.load_area(LAT + 0.5, LNG, radius_m=900)
    monkeypatch.setattr(area_cache, "_memory", {})        # 서버를 다시 켰다
    local_map.clear()
    area_cache.warm_recent()
    assert len(local_map) == 2 and len(area_cache._memory) == 2
    for area in area_cache._memory.values():
        assert len(area.graph._scores) == len(area.graph.ways), "길 점수를 미리 다 매겨 둔다"
    local_map.clear()
    area_cache.load_area(LAT, LNG, radius_m=900)
    assert local_map == [], "미리 불러 둔 동네는 요청 때 다시 읽지 않는다"


def test_warming_with_nothing_remembered_does_nothing(local_map):
    area_cache.warm_recent()
    assert local_map == [] and area_cache._memory == {}


def test_a_broken_memory_file_is_ignored(local_map):
    with open(area_cache.RECENT_PATH, "w", encoding="utf-8") as f:
        f.write("{깨진 파일")
    area_cache.warm_recent()
    area_cache.load_area(LAT, LNG, radius_m=900)
    assert len(recent(area_cache.RECENT_PATH)) == 1


def test_a_request_while_warming_does_not_read_the_same_neighbourhood_twice(local_map, monkeypatch):
    area_cache.load_area(LAT, LNG, radius_m=900)
    monkeypatch.setattr(area_cache, "_memory", {})
    local_map.clear()
    slow_read = threading.Event()
    real = local_osm.load_bbox

    def slow(bbox, *a, **k):
        slow_read.set()
        threading.Event().wait(0.3)   # 지도를 읽는 동안 요청이 들어온다
        return real(bbox, *a, **k)

    monkeypatch.setattr(local_osm, "load_bbox", slow)
    warmer = threading.Thread(target=area_cache.warm_recent)
    warmer.start()
    slow_read.wait(2)
    area = area_cache.load_area(LAT, LNG, radius_m=900)
    warmer.join(5)
    assert len(local_map) == 1, "미리 불러오는 중인 동네를 요청이 한 번 더 읽었다"
    assert area is area_cache._memory[next(iter(area_cache._memory))]


def test_without_a_local_map_nothing_is_remembered(monkeypatch, tmp_path):
    monkeypatch.setattr(local_osm, "available", lambda: False)
    monkeypatch.setattr(area_cache, "RECENT_PATH", str(tmp_path / "recent_areas.json"))
    area_cache.warm_recent()
    assert area_cache.load_area(LAT, LNG, radius_m=900, allow_fetch=False) is None
    import os
    assert not os.path.exists(area_cache.RECENT_PATH)
