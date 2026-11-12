"""러너가 매긴 별점으로 코스 점수식을 새로 찾고, 지금 식과 견준다.

평가할 때 남긴 기록(user_store.feedback_log의 measures: 추천할 때의 항목별 점수 + 코스 측정값)을 쓴다.
지금 식(score.DEFAULT_WEIGHTS)은 설문과 연구로 정했다. 여기서는 측정값 그대로(신호등 km당, 차 없는 길 비율 …)를
놓고 '어떤 길일 때 별점이 높았나'를 선형식으로 찾는다.

- 사람마다 별점 기준이 다르다(후하게 주는 사람·짜게 주는 사람). 평가가 2건 이상인 사람은 그 사람 평균과의
  차이로 본다.
- 오차는 하나씩 빼고 나머지로 식을 찾아 그 하나를 맞혀 본 평균(별점 몇 점 틀렸나)이다. 같은 기록으로 찾고
  같은 기록으로 맞히면 늘 좋아 보이기 때문이다.
- 식이 과하게 맞추지 않도록 계수를 줄이는 힘(리지)을 몇 가지로 해 보고 오차가 가장 작은 것을 쓴다.
- 앱의 점수식을 바꾸지 않는다. 평가가 MIN_RATINGS건 이상이고 새 식의 오차가 지금 식보다 BETTER_BY 넘게
  작을 때만 '새 식이 낫다'고 알려 준다.

사용: python -m src.recommend.formula_search
"""
import json
import math

from . import score, user_store

MIN_RATINGS = 30      # 이보다 적으면 식을 바꿀 근거로 보지 않는다
BETTER_BY = 0.10      # 새 식의 오차가 지금 식보다 이 비율 넘게 작아야 '낫다'
RIDGE = (0.1, 1.0, 3.0, 10.0, 30.0, 100.0)


def _ratio(m: dict, *keys):
    value = m
    for key in keys:
        value = (value or {}).get(key)
    return value if isinstance(value, (int, float)) else None


def _distance_error(m: dict, scores: dict):
    km, asked = _ratio(m, "km"), _ratio(m, "asked_km")
    return abs(km - asked) / asked if km is not None and asked else None


def _green_blue(m: dict, scores: dict):
    values = [_ratio(m, "scenery", k) for k in score.GREEN_BLUE]
    values = [v for v in values if v is not None]
    return max(values) if values else None


SHARE = "비율"
PER_KM = {"km당 개": "개", "km당 번": "번"}


def _amount(value: float, unit: str) -> str:
    """'보통만큼'을 쉬운 말로: 28%p, km당 1.2개, 0.28."""
    if unit == SHARE:
        return f"{value * 100:.0f}%p"
    if unit in PER_KM:
        return f"km당 {value:.1f}{PER_KM[unit]}"
    return f"{value:.2f}"


# (이름, 쉬운 말, 단위, 값 꺼내기). 인도 비율은 1 − 차 없는 길 − 골목이라 빼 둔다 (셋이 같이 들어가면 식이 흔들린다)
FEATURES = (
    ("distance_error", "요청 거리와의 차이", "비율", _distance_error),
    ("signals_per_km", "신호등", "km당 개", lambda m, s: _ratio(m, "signals_per_km")),
    ("turns_per_km", "꺾는 곳", "km당 번", lambda m, s: _ratio(m, "turns_per_km")),
    ("junctions_per_km", "갈림길", "km당 개", lambda m, s: _ratio(m, "junctions_per_km")),
    ("car_free", "차 없는 길 비율", "비율", lambda m, s: _ratio(m, "road_mix", "car_free")),
    ("alley", "골목 비율", "비율", lambda m, s: _ratio(m, "road_mix", "alley")),
    ("green_blue", "녹지·물가 비율", "비율", _green_blue),
    ("chosen_scenery", "고른 풍경 점수", "0~1", lambda m, s: s.get("tag_match")),
)


def load_ratings() -> list:
    """평가 기록 전부: [{user_id, rating, record}]. record는 추천 없이 남긴 후기면 None."""
    with user_store._open() as db:
        rows = db.execute("SELECT user_id, rating, measures FROM feedback_log ORDER BY id").fetchall()
    return [{"user_id": user, "rating": rating, "record": json.loads(kept) if kept else None}
            for user, rating, kept in rows]


def _current_score(scores: dict) -> float:
    """지금 식의 점수 (score.score_course와 같은 합치기)."""
    weights = {k: w for k, w in score.default_weights().items() if k in scores}
    total = sum(weights.values()) or 1.0
    return sum(scores[k] * w for k, w in weights.items()) / total


def _usable(rows: list) -> list:
    return [r for r in rows if r.get("record") and r["record"].get("measures") and r["record"].get("scores") is not None]


def _centered_ratings(rows: list) -> list:
    """사람마다의 기준을 뺀 별점. 평가가 하나뿐인 사람은 모두의 평균을 뺀다."""
    overall = sum(r["rating"] for r in rows) / len(rows)
    by_user = {}
    for r in rows:
        by_user.setdefault(r["user_id"], []).append(r["rating"])
    mean = {u: (sum(v) / len(v) if len(v) >= 2 else overall) for u, v in by_user.items()}
    return [r["rating"] - mean[r["user_id"]] for r in rows]


def _solve(a: list, b: list) -> list:
    """a x = b (가우스 소거). a는 정사각 행렬."""
    n = len(a)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(n):
            if r != col and m[r][col]:
                f = m[r][col] / m[col][col]
                m[r] = [x - f * y for x, y in zip(m[r], m[col])]
    return [m[i][n] / m[i][i] for i in range(n)]


def _inverse(a: list) -> list:
    n = len(a)
    columns = [_solve(a, [1.0 if i == j else 0.0 for i in range(n)]) for j in range(n)]
    return [[columns[j][i] for j in range(n)] for i in range(n)]


def _ridge_loo(x: list, y: list, lam: float) -> tuple:
    """가운데를 맞춘 x(행: 평가, 열: 특징)와 y로 리지 회귀. (계수, 하나씩 빼고 맞혀 본 평균 오차)."""
    k = len(x[0])
    xtx = [[sum(row[i] * row[j] for row in x) + (lam if i == j else 0.0) for j in range(k)] for i in range(k)]
    xty = [sum(row[i] * t for row, t in zip(x, y)) for i in range(k)]
    inv = _inverse(xtx)
    beta = [sum(inv[i][j] * xty[j] for j in range(k)) for i in range(k)]
    n = len(y)
    errors = []
    for row, t in zip(x, y):
        fitted = sum(b * v for b, v in zip(beta, row))
        leverage = sum(row[i] * sum(inv[i][j] * row[j] for j in range(k)) for i in range(k)) + 1.0 / n
        errors.append(abs(t - fitted) / max(1e-9, 1 - leverage))   # 그 하나를 빼고 찾았다면 이만큼 틀린다
    return beta, sum(errors) / n


def _standardized(columns: list) -> tuple:
    """열마다 평균 0·표준편차 1로. 빠진 값은 그 열의 평균으로 채운다. (행렬, 열별 표준편차, 쓴 열 번호)."""
    kept, stds, scaled = [], [], []
    for index, column in enumerate(columns):
        present = [v for v in column if v is not None]
        if len(present) < 2:
            continue
        mean = sum(present) / len(present)
        std = math.sqrt(sum((v - mean) ** 2 for v in present) / len(present))
        if std < 1e-9:
            continue
        kept.append(index)
        stds.append(std)
        scaled.append([((v if v is not None else mean) - mean) / std for v in column])
    rows = [list(values) for values in zip(*scaled)] if scaled else []
    return rows, stds, kept


def _best_ridge(x: list, y: list) -> tuple:
    return min((_ridge_loo(x, y, lam) + (lam,) for lam in RIDGE), key=lambda t: t[1])


def search(rows: list) -> dict:
    """새 식을 찾고 지금 식·항상 평균과 견준다."""
    rows = _usable(rows)
    n = len(rows)
    report = {"ratings": n, "runners": len({r["user_id"] for r in rows}), "effects": [], "error": None}
    if n < 3:
        report.update(verdict="too_few", summary=f"평가가 {n}건뿐입니다. {MIN_RATINGS}건은 있어야 식을 견줄 수 있어요.")
        return report
    y = _centered_ratings(rows)
    y_mean = sum(y) / n
    y = [t - y_mean for t in y]

    # 항상 평균: 하나를 빼고 나머지 평균으로 맞힌다
    total = sum(y)
    mean_error = sum(abs(t - (total - t) / (n - 1)) for t in y) / n

    # 지금 식: 지금 점수를 별점으로 옮기는 직선만 찾는다
    current = [_current_score(r["record"]["scores"]) for r in rows]
    cx, _, _ = _standardized([current])
    current_error = _ridge_loo(cx, y, 1e-6)[1] if cx else mean_error

    columns = [[get(r["record"]["measures"], r["record"]["scores"]) for r in rows] for _, _, _, get in FEATURES]
    x, stds, kept = _standardized(columns)
    if not x:
        new_error, beta, lam = mean_error, [], None
    else:
        beta, new_error, lam = _best_ridge(x, y)
    report["error"] = {"mean": round(mean_error, 3), "current": round(current_error, 3), "new": round(new_error, 3)}
    report["ridge"] = lam
    report["effects"] = sorted(
        ({"feature": FEATURES[i][0], "label": FEATURES[i][1], "unit": FEATURES[i][2],
          "typical_change": round(std, 3), "per_typical_change": round(b, 3)}
         for i, std, b in zip(kept, stds, beta)),
        key=lambda e: -abs(e["per_typical_change"]))
    if n < MIN_RATINGS:
        report.update(verdict="too_few",
                      summary=f"평가가 {n}건이라 아직 판단하기 이릅니다. {MIN_RATINGS}건은 모인 뒤에 보세요.")
    elif new_error < current_error * (1 - BETTER_BY):
        report.update(verdict="better", summary=(
            f"새 식이 별점을 더 잘 맞힙니다 (평균 {current_error:.2f}점 → {new_error:.2f}점 틀림). "
            "아래 영향 순서를 보고 지금 식의 배점을 고칠지 정하세요."))
    else:
        report.update(verdict="keep", summary=(
            f"새 식이 지금 식보다 확실히 낫지 않습니다 (지금 {current_error:.2f}점 · 새 식 {new_error:.2f}점 틀림). "
            "지금 식을 그대로 둡니다."))
    return report


def report_text(report: dict) -> str:
    lines = [f"평가 {report['ratings']}건 (러너 {report['runners']}명) · 측정값이 남은 평가만 씁니다", report["summary"]]
    if report["error"]:
        e = report["error"]
        lines.append(f"별점 오차 (하나씩 빼고 맞혀 본 평균): 항상 평균 {e['mean']:.2f}점 · 지금 식 {e['current']:.2f}점 · "
                     f"새 식 {e['new']:.2f}점")
    if report["effects"]:
        lines.append("새 식이 찾은 것 (값이 보통만큼 늘 때 별점 변화, 큰 순서):")
        for effect in report["effects"]:
            lines.append(f"  {effect['label']}: {effect['per_typical_change']:+.2f}점 "
                         f"({_amount(effect['typical_change'], effect['unit'])} 늘 때)")
    return "\n".join(lines)


if __name__ == "__main__":
    print(report_text(search(load_ratings())))
