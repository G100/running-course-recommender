"""Open Topo Data 표고 API 클라이언트 (무료, 키 불필요).

VWorld는 표고를 포인트 단위 REST API가 아닌 DEM 래스터 파일 다운로드로만 제공하고,
OpenTopography Point Elevation API는 무료 등급이 하루 50건으로 너무 빡빡해서(개발 중 바로 소진됨)
Open Topo Data(api.opentopodata.org, SRTM 기반, 키 불필요, 요청당 최대 100지점 배치 조회,
하루 1000건)로 교체했다.

무료 서버는 초당 1건이라 후보마다 따로 물으면 줄을 서서 기다렸다(코스 하나 만드는 12.8초 중 11.3초).
땅 높이는 바뀌지 않으므로 한 번 물은 지점은 기억해 두고(메모리 + 파일), 모르는 지점만 묻는다.
"""
import contextlib
import os
import sqlite3
import threading

import requests

ELEVATION_URL = "https://api.opentopodata.org/v1/srtm30m"
BATCH_SIZE = 100
# SRTM은 30m 격자라 소수 넷째 자리(약 11m)로 묶어도 값이 같다
PRECISION = 4
CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "elevation_cache.sqlite")
_memory = {}
_lock = threading.Lock()


def _key(lat: float, lng: float) -> tuple:
    return round(lat, PRECISION), round(lng, PRECISION)


@contextlib.contextmanager
def _open():
    os.makedirs(os.path.dirname(CACHE_PATH) or ".", exist_ok=True)
    db = sqlite3.connect(CACHE_PATH, timeout=10)
    try:
        db.execute("CREATE TABLE IF NOT EXISTS elevation (lat REAL, lng REAL, m REAL, PRIMARY KEY (lat, lng))")
        yield db
        db.commit()
    finally:
        db.close()


def _remembered(keys: list) -> dict:
    found = {k: _memory[k] for k in keys if k in _memory}
    missing = [k for k in keys if k not in found]
    if missing and os.path.exists(CACHE_PATH):
        with _open() as db:
            for lat, lng in missing:
                row = db.execute("SELECT m FROM elevation WHERE lat = ? AND lng = ?", (lat, lng)).fetchone()
                if row is not None:
                    found[(lat, lng)] = _memory[(lat, lng)] = row[0]
    return found


def _remember(values: dict) -> None:
    _memory.update(values)
    with _lock, _open() as db:
        db.executemany("INSERT OR REPLACE INTO elevation VALUES (?, ?, ?)", [(a, b, m) for (a, b), m in values.items()])


def get_elevation(lat: float, lng: float) -> float:
    """지정 좌표의 표고(m)를 반환."""
    return get_elevation_profile([(lat, lng)])[0]


def get_elevation_profile(path: list) -> list:
    """path = [(lat, lng), ...] 순서로 각 지점의 표고(m) 리스트 반환. 모르는 지점만 최대 100개씩 묶어 묻는다."""
    keys = [_key(lat, lng) for lat, lng in path]
    known = _remembered(list(dict.fromkeys(keys)))
    missing = [k for k in dict.fromkeys(keys) if k not in known]
    fetched = {}
    for i in range(0, len(missing), BATCH_SIZE):
        chunk = missing[i:i + BATCH_SIZE]
        locations = "|".join(f"{lat},{lng}" for lat, lng in chunk)
        resp = requests.get(ELEVATION_URL, params={"locations": locations}, timeout=20)
        resp.raise_for_status()
        fetched.update(zip(chunk, (r["elevation"] for r in resp.json()["results"])))
    if fetched:
        _remember(fetched)
    known.update(fetched)
    return [known[k] for k in keys]
