"""회전 안내에 근처 가게 이름을 붙인다: '왼쪽으로 도세요' 대신 'GS25 앞에서 왼쪽 용주로로 도세요'.

Tmap 보행자 경로는 회전 지점의 근처 장소(nearPoiName)를 대부분 비워 준다. 그래서 러너에게 내보내는
코스(추천 1등·고른 후보·목적지 코스·돌아가는 길)의 회전 지점만 Tmap 주변 검색으로 가장 가까운 가게를 찾는다.

- 모퉁이에서 보이는 거리(NEAR_M) 안의 가장 가까운 곳만 쓴다. 지점 이름은 뗀다('GS25 용봉점' → 'GS25').
- 한 번 물은 자리(약 10m 칸)는 저장해서 다시 묻지 않는다 — 가게가 없던 자리도 '없음'으로 저장한다.
  묻다가 실패한 자리는 저장하지 않는다(다음에 다시 묻는다).
- 코스를 만드는 도중의 후보에는 묻지 않는다: 하루 한도를 아낀다.
"""
import contextlib
import math
import os
import sqlite3
import time

import requests

from ..api_clients.tmap_pedestrian import runner_instruction, shop_name
from ..api_clients.tmap_poi import search_around

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "landmarks.sqlite")
NEAR_M = 40          # 모퉁이에서 간판이 보이는 거리
CELL = 4             # 좌표를 소수 넷째 자리(약 10m)로 묶어 같은 자리로 본다
TURNS = {12, 13, 16, 17, 18, 19, 211, 212, 213, 214, 215, 216, 217}   # 가게를 기준으로 말할 만한 안내
# 달리면서 멀리서도 알아보는 간판: 편의점·카페·빵집·패스트푸드 체인, 은행, 약국.
# 모퉁이에서 보이는 곳 중에 이런 곳이 있으면 더 가까운 작은 가게보다 먼저 쓴다
WELL_KNOWN = ("GS25", "CU", "세븐일레븐", "이마트24", "미니스톱", "스타벅스", "이디야", "투썸", "메가커피", "메가MGC",
              "컴포즈", "빽다방", "할리스", "파스쿠찌", "커피빈", "폴바셋", "파리바게뜨", "뚜레쥬르", "던킨", "배스킨라빈스",
              "맥도날드", "롯데리아", "버거킹", "맘스터치", "KFC", "서브웨이", "올리브영", "다이소", "농협", "국민은행",
              "신한은행", "우리은행", "하나은행", "기업은행", "광주은행", "새마을금고", "우체국")


def _well_known(name: str) -> bool:
    return name.startswith(WELL_KNOWN) or name.endswith(("약국", "은행", "우체국"))


@contextlib.contextmanager
def _open():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    try:
        with db:
            db.execute("CREATE TABLE IF NOT EXISTS corners (cell TEXT PRIMARY KEY, name TEXT, asked_at REAL)")
            yield db
    finally:
        db.close()


def _meters(lat1, lng1, lat2, lng2) -> float:
    return math.hypot(lat2 - lat1, (lng2 - lng1) * math.cos(math.radians(lat1))) * 111_320


def near(lat: float, lng: float):
    """이 모퉁이에서 보이는 가장 가까운 가게 이름. 없거나 물을 수 없으면 None."""
    if not os.environ.get("TMAP_APP_KEY"):
        return None
    cell = f"{round(lat, CELL)},{round(lng, CELL)}"
    with _open() as db:
        row = db.execute("SELECT name FROM corners WHERE cell = ?", (cell,)).fetchone()
    if row is not None:
        return row[0] or None
    try:
        places = search_around(lat, lng)
    except (requests.RequestException, ValueError, KeyError):
        return None
    close = [(d, shop_name(p["name"])) for p in places if (d := _meters(lat, lng, p["lat"], p["lng"])) <= NEAR_M]
    close = [(d, n) for d, n in close if n]
    known = [c for c in close if _well_known(c[1])]
    name = min(known or close)[1] if close else None
    with _open() as db:
        db.execute("INSERT OR REPLACE INTO corners VALUES (?, ?, ?)", (cell, name or "", time.time()))
    return name


def add_landmarks(steps: list) -> list:
    """회전 안내마다 근처 가게를 찾아 문장을 다시 만든다. Tmap이 이미 준 가게가 있으면 그대로 둔다."""
    out = []
    for step in steps or []:
        if step.get("turn_type") in TURNS and not step.get("landmark") and step.get("lat") is not None:
            name = near(step["lat"], step["lng"])
            if name:
                step = dict(step, landmark=name, instruction=runner_instruction(step.get("description", ""), step["turn_type"], name))
        out.append(step)
    return out
