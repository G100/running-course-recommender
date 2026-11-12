"""평가 기록(측정값 + 별점)에서 새 점수식을 찾고, 지금 식과 견준다.

지금 점수식(거리 30·풍경 25·흐름 25·차 없는 길 20)은 설문과 연구로 정했다. 러너가 실제로 매긴 별점으로
'어떤 길일 때 별점이 높았나'를 찾으면 식을 고칠 근거가 생긴다. 앱의 식을 바로 바꾸지는 않는다 — 기록이
충분하고 새 식이 확실히 나을 때만 그렇다고 알려 준다.
"""
import random

import pytest

from src.recommend import formula_search as fs
from src.recommend import score, user_store


def course(rng, **fixed):
    """가짜 코스 측정값 (score.measures 모양) + 추천할 때 기억한 항목별 점수."""
    asked = rng.choice([3, 5, 7, 10])
    m = {
        "asked_km": asked, "km": round(asked * rng.uniform(0.95, 1.05), 2), "route_type": "loop", "laps": 1,
        "signals_per_km": round(rng.uniform(0, 4), 2), "turns_per_km": round(rng.uniform(1, 7), 2),
        "junctions_per_km": round(rng.uniform(2, 15), 2),
        "road_mix": {"sidewalk": 0.0, "car_free": round(rng.uniform(0, 1), 3), "alley": round(rng.uniform(0, 0.2), 3)},
        "scenery": {"park": round(rng.uniform(0, 0.6), 3), "river": round(rng.uniform(0, 0.6), 3)},
        "chosen_scenery": [],
    }
    m["road_mix"]["sidewalk"] = round(1 - m["road_mix"]["car_free"] - m["road_mix"]["alley"], 3)
    m.update(fixed)
    scores = {"distance": 1 - abs(m["km"] - asked) / asked / 0.1, "tag_match": rng.uniform(0, 1),
              "flow": rng.uniform(0, 1), "car_free": m["road_mix"]["car_free"]}
    return {"scores": scores, "baseline": None, "measures": m}


def rated(seed, n, rule, users=("a",), noise=0.3, lenient=None):
    """rule(측정값) → 별점 (1~5로 자르고 반올림). lenient={사용자: 더 후하게 주는 점수}."""
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        record = course(rng)
        user = users[i % len(users)]
        stars = rule(record["measures"]) + rng.gauss(0, noise) + (lenient or {}).get(user, 0)
        rows.append({"user_id": user, "rating": max(1, min(5, round(stars))), "record": record})
    return rows


def car_free_and_signals(m):
    return 2.2 + 2.5 * m["road_mix"]["car_free"] - 0.45 * m["signals_per_km"]


def test_a_rule_hidden_in_the_ratings_is_found():
    report = fs.search(rated(1, 90, car_free_and_signals))
    effects = report["effects"]
    assert effects[0]["feature"] in ("car_free", "signals_per_km") and effects[1]["feature"] in ("car_free", "signals_per_km")
    signs = {e["feature"]: e["per_typical_change"] for e in effects}
    assert signs["car_free"] > 0 and signs["signals_per_km"] < 0, "차 없는 길은 별점을 올리고 신호등은 내린다"
    assert report["error"]["new"] < report["error"]["current"] < report["error"]["mean"] + 1e-9
    assert report["verdict"] == "better"


def test_with_few_ratings_nothing_is_recommended():
    report = fs.search(rated(2, 12, car_free_and_signals))
    assert report["verdict"] == "too_few" and report["ratings"] == 12
    assert "30" in report["summary"], "몇 건이 더 필요한지 말한다"


def test_when_the_current_formula_already_explains_ratings_it_is_kept():
    """별점이 지금 식 그대로라면 새 식이 더 나을 게 없다."""
    def by_current(m, scores=None):
        return 1 + 4 * m["_current"]

    rng = random.Random(3)
    rows = []
    for _ in range(80):
        record = course(rng)
        current = sum(record["scores"][k] * w for k, w in score.DEFAULT_WEIGHTS.items())
        rows.append({"user_id": "a", "rating": max(1, min(5, round(1 + 4 * current + rng.gauss(0, 0.2)))), "record": record})
    assert fs.search(rows)["verdict"] == "keep"


def test_each_runners_own_scale_is_taken_out():
    """후하게 주는 사람과 짜게 주는 사람이 섞여도 같은 규칙을 찾는다."""
    report = fs.search(rated(4, 120, car_free_and_signals, users=("kind", "strict"), lenient={"kind": 1.0, "strict": -1.0}))
    signs = {e["feature"]: e["per_typical_change"] for e in report["effects"]}
    assert signs["car_free"] > 0 and signs["signals_per_km"] < 0
    assert report["verdict"] == "better"


def test_ratings_without_measures_and_missing_values_are_handled():
    rows = rated(5, 60, car_free_and_signals)
    for row in rows[:10]:
        row["record"]["measures"]["turns_per_km"] = None           # 잴 수 없던 값
    rows.append({"user_id": "a", "rating": 5, "record": None})     # 추천 없이 남긴 후기
    rows.append({"user_id": "a", "rating": 5, "record": {"scores": {}, "measures": None}})
    report = fs.search(rows)
    assert report["ratings"] == 60


def test_ratings_are_read_from_the_feedback_log():
    rows = rated(6, 35, car_free_and_signals)
    for row in rows:
        user_store.log_feedback(row["user_id"], "c", row["rating"], measures=row["record"])
    user_store.log_feedback("a", "c", 4)   # 측정값 없는 평가
    loaded = fs.load_ratings()
    assert len(loaded) == 36 and sum(r["record"] is not None for r in loaded) == 35
    assert fs.search(loaded)["ratings"] == 35


def test_the_report_reads_as_plain_words():
    text = fs.report_text(fs.search(rated(7, 90, car_free_and_signals)))
    assert "차 없는 길" in text and "신호등" in text and "평가 90건" in text
