"""정량 평가: 우리 방식으로 만든 코스와 Tmap 최단 경로로 이은 코스를 같은 조건에서 비교한다.

    python -m src.evaluate                    # 기본 10곳 × 3·5·8km, 낮·밤
    python -m src.evaluate --places 3 --distances 5 --no-night   # 빠르게

같은 출발점·같은 경유지 후보에서
  - 기준(Tmap): 경유지를 Tmap 보행자 경로로 이은 순환 코스 (예전 방식)
  - 우리: 도로망 직접 탐색 + 인도 규칙 + (밤이면) 사람 있는 길
을 만들고, 같은 잣대로 잰다:
  목표 거리 오차, 인도 없는 차도 비율, 골목 비율, 밤 인적 드문 길 비율, 요청한 풍경 비율, 걸린 시간, Tmap 호출 수, 실패.

결과는 data/evaluation/에 JSON으로 남고, 요약 표를 출력한다. 로컬 지형 DB와 TMAP_APP_KEY가 필요하다.
"""
import argparse
import json
import os
import statistics
import time

from .api_clients import tmap_pedestrian
from .api_clients.tmap_pedestrian import extract_path
from .data_collection import area_cache, local_osm, scenery
from .data_collection.scenery import resample
from .recommend import generate_live, sidewalk

# (이름, 위도, 경도, 그 동네에서 고를 만한 풍경)
PLACES = [
    ("광주 상무지구", 35.1595, 126.8526, "강변"),
    ("여수 이순신광장", 34.7393, 127.7359, "바다뷰"),
    ("부산 해운대", 35.1587, 129.1604, "바다뷰"),
    ("서울 여의도", 37.5262, 126.9326, "강변"),
    ("서울 망원동", 37.5560, 126.9020, "강변"),
    ("대전 둔산", 36.3668, 127.3880, "공원"),
    ("대구 동성로", 35.8693, 128.5950, "공원"),
    ("인천 송도", 37.3925, 126.6390, "공원"),
    ("수원 광교", 37.2850, 127.0500, "호수"),
    ("광주 첨단", 35.2185, 126.8445, "공원"),
]
DISTANCES = (3.0, 5.0, 8.0)
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "evaluation")

_calls = {"tmap": 0}


def _count_tmap():
    """Tmap 호출 수를 센다 (경로를 고르는 쪽과 인도를 확인하는 쪽 모두)."""
    original = tmap_pedestrian.get_route

    def counted(*args, **kwargs):
        _calls["tmap"] += 1
        return original(*args, **kwargs)

    for module in (generate_live, sidewalk):
        module.get_route = counted


def _secluded_ratio(area, path: list) -> float:
    """경로 중 밤에 인적 드문 길 위를 지나는 비율 (두 방식에 같은 잣대)."""
    graph = area.graph
    points = resample(path)
    if not points:
        return 0.0
    secluded = 0
    for lat, lng in points:
        ways = graph.ways_near(lat, lng, 15)
        if ways and all(graph.night_kind(way) == "secluded" for way in ways):
            secluded += 1
    return secluded / len(points)


def _scenery_share(path: list, tag: str):
    measured = scenery.tags_for_path(path, {})
    if measured is None or not tag:
        return None
    return measured[0].get(scenery.THRESHOLDS[tag][0])


def baseline(lat, lng, km, tag, area):
    """예전 방식: 같은 규칙으로 고른 경유지를 Tmap 최단 경로로 잇는다."""
    waypoints = (generate_live.scenic_vertices_for_length(area, {tag} if tag else set(), lat, lng, km)
                 or generate_live.pick_land_vertices(lat, lng, km, area.roads, 0.0, 1.0, area))
    if not waypoints:
        return None
    route = generate_live.get_route((lng, lat), (lng, lat), start_name="출발지", end_name="출발지",
                                    waypoints=[(p[1], p[0]) for p in waypoints])
    path, distance_m = extract_path(route)
    road_mix = sidewalk.mix_of(sidewalk.resolve(route, area.graph))
    return {"path": path, "distance_km": distance_m / 1000, "car_lane": road_mix["car_lane"],
            "alley": road_mix["alley"]}


def ours(lat, lng, km, tag, night):
    courses = generate_live.generate_loop_candidates(lat, lng, km, {tag} if tag else set(), night=night)
    best = min(courses, key=lambda c: abs(c["distance_km"] - km))
    mix = best.get("road_mix") or {}
    return {"path": best["path"], "distance_km": best["distance_km"], "car_lane": mix.get("car_lane"),
            "alley": mix.get("alley")}


def measure(method: str, place, km, tag, night, area) -> dict:
    name, lat, lng, _ = place
    before, started = _calls["tmap"], time.time()
    row = {"method": method, "place": name, "km": km, "tag": tag, "night": night}
    try:
        result = baseline(lat, lng, km, tag, area) if method == "tmap" else ours(lat, lng, km, tag, night)
    except Exception as error:   # 실패도 결과다 — 세어 둔다
        result, row["error"] = None, f"{type(error).__name__}: {error}"[:200]
    row.update(seconds=round(time.time() - started, 1), tmap_calls=_calls["tmap"] - before, ok=result is not None)
    if result:
        row.update(
            distance_km=round(result["distance_km"], 2),
            distance_error=round(abs(result["distance_km"] - km) / km, 3),
            car_lane=result["car_lane"], alley=result["alley"],
            secluded=round(_secluded_ratio(area, result["path"]), 3),
            scenery=_scenery_share(result["path"], tag),
        )
    return row


def summarize(rows: list) -> list:
    """방식·낮밤별 요약."""
    groups = {}
    for row in rows:
        groups.setdefault((row["method"], row["night"]), []).append(row)
    summary = []
    for (method, night), group in sorted(groups.items()):
        ok = [r for r in group if r["ok"]]
        mean = lambda key: round(statistics.mean(r[key] for r in ok if r.get(key) is not None), 3) \
            if any(r.get(key) is not None for r in ok) else None
        summary.append({
            "method": "우리" if method == "ours" else "Tmap 최단",
            "night": "밤" if night else "낮",
            "runs": len(group), "failed": len(group) - len(ok),
            "distance_error": mean("distance_error"),
            "within_10pct": round(sum(1 for r in ok if r["distance_error"] <= 0.10) / len(ok), 3) if ok else None,
            "car_lane": mean("car_lane"), "alley": mean("alley"), "secluded": mean("secluded"),
            "scenery": mean("scenery"), "seconds": mean("seconds"), "tmap_calls": mean("tmap_calls"),
        })
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--places", type=int, default=len(PLACES))
    parser.add_argument("--start", type=int, default=0, help="이 번째 장소부터 (나눠서 돌릴 때)")
    parser.add_argument("--merge", nargs="*", default=[], help="나눠 돌린 결과 JSON들을 합쳐 요약만 다시 낸다")
    parser.add_argument("--distances", type=float, nargs="*", default=list(DISTANCES))
    parser.add_argument("--no-night", action="store_true", help="밤 비교를 건너뛴다")
    parser.add_argument("--no-baseline", action="store_true", help="Tmap 기준을 건너뛴다 (Tmap 호출 절약)")
    args = parser.parse_args()
    if not local_osm.available():
        raise SystemExit("로컬 지형 DB가 없습니다. 먼저: python -m src.setup_local")
    if not os.environ.get("TMAP_APP_KEY"):
        raise SystemExit("TMAP_APP_KEY가 필요합니다.")

    if args.merge:
        rows = [row for path in args.merge for row in json.load(open(path, encoding="utf-8"))["rows"]]
        _report(rows)
        return

    _count_tmap()
    rows = []
    for place in PLACES[args.start: args.start + args.places]:
        name, lat, lng, tag = place
        area = area_cache.load_area(lat, lng, radius_m=max(args.distances) * 1000 * 1.1 * 1.1 / 5.7 + 200)
        for km in args.distances:
            for scenic in (None, tag):
                if not args.no_baseline:
                    rows.append(measure("tmap", place, km, scenic, False, area))
                rows.append(measure("ours", place, km, scenic, False, area))
                if not args.no_night and scenic is None:
                    rows.append(measure("ours", place, km, None, True, area))
                print(f"  {name} {km:g}km {scenic or '풍경 없음'}: "
                      + " | ".join(f"{r['method']}{'(밤)' if r['night'] else ''} "
                                   + (f"{r['distance_km']}km 차도 {r['car_lane']} 인적드문 {r['secluded']}"
                                      if r["ok"] else "실패")
                                   for r in rows[-(3 if not args.no_night and scenic is None else 2):]),
                      flush=True)

    _report(rows)


def _report(rows: list) -> None:
    summary = summarize(rows)
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M")
    with open(os.path.join(OUT_DIR, f"evaluation-{stamp}.json"), "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "rows": rows}, f, ensure_ascii=False, indent=1)
    print("\n방식      시간대  실행  실패  거리오차  10%이내  차도   골목   인적드문  풍경   초    Tmap")
    for s in summary:
        fmt = lambda v: "  -  " if v is None else f"{v:.2f}"
        print(f"{s['method']:<8}{s['night']:<6}{s['runs']:>4}{s['failed']:>6}   {fmt(s['distance_error'])}"
              f"   {fmt(s['within_10pct'])}  {fmt(s['car_lane'])}  {fmt(s['alley'])}  {fmt(s['secluded'])}"
              f"   {fmt(s['scenery'])}  {fmt(s['seconds'])}  {fmt(s['tmap_calls'])}")
    print(f"\n저장: data/evaluation/evaluation-{stamp}.json")


if __name__ == "__main__":
    main()
