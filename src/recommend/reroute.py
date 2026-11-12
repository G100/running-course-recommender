"""달리다 코스를 벗어났을 때 원래 코스로 돌아가는 길을 만든다.

돌아갈 곳은 아직 달리지 않은 코스 중 지금 위치에서 가장 가까운 지점이다 — 지나온 곳으로 되돌려 보내지 않는다.
다만 코스를 따라 REJOIN_AHEAD_M 앞까지만 찾는다. 순환 코스는 출발점과 도착점이 같아서, 끝까지 찾으면
출발 직후에 벗어난 러너를 도착점으로 보내 코스 전체를 건너뛰게 된다.

지금 위치에서 그 지점까지는 Tmap 보행자 경로로 잇고, 그 뒤에 원래 코스의 남은 부분을 그대로 붙인다.
"""
import math

from ..api_clients import tmap_pedestrian as tmap
from ..data_collection.enrich import haversine_m
from .step_position import assign_positions, cumulative_distances

REJOIN_AHEAD_M = 1000
ON_COURSE_M = 15           # 돌아갈 지점이 이 안이면 이미 코스 위다 — Tmap은 출발과 도착이 같은 길을 주지 못한다
START, ARRIVE = 200, 201   # Tmap turnType: 돌아가는 길의 '출발'·'도착'은 러너에게 할 말이 아니다


def _nearest_on_segment(position, a, b, t_from: float, t_to: float):
    """선분 a→b의 t_from~t_to 구간에서 position에 가장 가까운 점과 그 위치 t(0~1)."""
    k = math.cos(math.radians(a[0]))
    bx, by = (b[1] - a[1]) * k, b[0] - a[0]
    px, py = (position[1] - a[1]) * k, position[0] - a[0]
    length2 = bx * bx + by * by
    t = (px * bx + py * by) / length2 if length2 else 0.0
    t = max(t_from, min(t_to, t))
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t], t


def rejoin_point(position, path: list, progress_m: float, ahead_m: float = REJOIN_AHEAD_M) -> tuple:
    """(코스 위 거리 m, [lat, lng]): 코스의 progress_m ~ progress_m + ahead_m 구간에서 position에 가장 가까운 점."""
    cum = cumulative_distances(path)
    lo = max(0.0, min(progress_m, cum[-1]))
    hi = min(cum[-1], lo + ahead_m)
    best = None
    for i in range(1, len(path)):
        length = cum[i] - cum[i - 1]
        if cum[i] < lo or cum[i - 1] > hi or not length:
            continue
        point, t = _nearest_on_segment(position, path[i - 1], path[i],
                                       max(0.0, (lo - cum[i - 1]) / length), min(1.0, (hi - cum[i - 1]) / length))
        d = haversine_m(position, point)
        if best is None or d < best[0]:
            best = (d, cum[i - 1] + length * t, point)
    if best is None:
        return cum[-1], list(path[-1])
    return best[1], best[2]


def _point_at(path: list, cum: list, at_m: float) -> list:
    for i in range(1, len(path)):
        if cum[i] >= at_m:
            length = cum[i] - cum[i - 1]
            t = (at_m - cum[i - 1]) / length if length else 0.0
            return [path[i - 1][0] + (path[i][0] - path[i - 1][0]) * t, path[i - 1][1] + (path[i][1] - path[i - 1][1]) * t]
    return list(path[-1])


def back_to_course(position, path: list, steps: list, progress_m: float, get_route=None) -> dict:
    """벗어난 위치(position)에서 코스로 돌아가 남은 코스를 달리는 경로와 안내.

    extra_m은 벗어나지 않았을 때보다 전체 달리기가 늘어나는 거리다(지름길로 질러갔으면 음수). 벗어난 뒤
    달린 거리는 떠난 지점에서 지금 위치까지의 직선거리로 친다 — 실제로는 그보다 조금 더 달렸다.
    """
    cum = cumulative_distances(path)
    progress_m = max(0.0, min(progress_m, cum[-1]))
    rejoin_at, rejoin = rejoin_point(position, path, progress_m)

    if haversine_m(position, rejoin) <= ON_COURSE_M:
        # 안내받은 길 대신 곧장 코스로 돌아온 경우: 거기서부터 남은 코스를 그대로 준다
        detour, detour_steps = [list(position), rejoin], []
    else:
        route = (get_route or tmap.get_route)((position[1], position[0]), (rejoin[1], rejoin[0]))
        detour, _ = tmap.extract_path(route)
        if len(detour) < 2:
            raise ValueError("Tmap이 돌아가는 길을 주지 않았습니다.")
        # Tmap은 가장 가까운 길에서 출발한다. 러너가 선 자리부터 잇지 않으면, 길에 닿기 전까지 새 경로에서도
        # '벗어남'이 되어 재탐색이 되풀이된다
        if haversine_m(position, detour[0]) > 1:
            detour = [list(position)] + detour
        detour_steps = assign_positions([s for s in tmap.extract_steps(route) if s["turn_type"] not in (START, ARRIVE)], detour)
    detour_m = cumulative_distances(detour)[-1]

    rest = [rejoin] + [p for p, at in zip(path, cum) if at > rejoin_at]
    if haversine_m(detour[-1], rest[0]) < 1:
        rest = rest[1:]
    new_path = detour + rest
    shift = detour_m + haversine_m(detour[-1], rejoin) - rejoin_at   # 남은 코스의 안내가 새 경로에서 밀리는 거리

    if any(not isinstance(s.get("cum_m"), (int, float)) for s in steps):
        steps = assign_positions(steps, path)
    rest_steps = [dict(s, cum_m=round(s["cum_m"] + shift, 1)) for s in steps if s["cum_m"] > rejoin_at]

    off_course_m = haversine_m(_point_at(path, cum, progress_m), position)
    skipped_m = rejoin_at - progress_m
    return {
        "path": new_path, "steps": detour_steps + rest_steps,
        "distance_km": round(cumulative_distances(new_path)[-1] / 1000, 2),
        "rejoin_m": round(detour_m), "skipped_m": round(skipped_m),
        "extra_m": round(off_course_m + detour_m - skipped_m),
    }
