"""짧은 순환을 여러 바퀴 도는 코스.

한 바퀴로 요청 거리의 순환을 못 만들 때 쓴다(산을 낀 동네의 21·42km 등). 한 바퀴만 만들고 Tmap으로 이은 뒤
그 길을 바퀴 수만큼 이어 붙인다 — Tmap 호출이 바퀴 수만큼 늘지 않는다. 바퀴가 끝날 때마다 안내를 하나 넣어
러너가 몇 바퀴째인지 알게 한다.
"""
from .step_position import assign_positions, cumulative_distances

LAP_TURN = 300            # 바퀴가 바뀌는 안내 (Tmap turnType에 없는 번호)
START, ARRIVE = 200, 201  # Tmap turnType: 출발·도착


def _lap_instruction(done: int, laps: int) -> str:
    return f"{done}바퀴 끝, " + ("마지막 바퀴입니다" if done + 1 == laps else f"{done + 1}바퀴째입니다")


def repeat(course: dict, laps: int) -> dict:
    """한 바퀴 코스(course)를 laps바퀴 도는 코스. 한 바퀴면 그대로 돌려준다."""
    if laps <= 1:
        return course
    path = course["path"]
    lap_m = cumulative_distances(path)[-1]
    steps = course.get("steps") or []
    if any(not isinstance(s.get("cum_m"), (int, float)) for s in steps):
        steps = assign_positions(steps, path)

    new_path = list(path)
    new_steps = []
    for lap in range(laps):
        offset = lap * lap_m
        if lap:
            new_path += path[1:]
            new_steps.append({"lat": path[0][0], "lng": path[0][1], "description": _lap_instruction(lap, laps),
                              "turn_type": LAP_TURN, "instruction": _lap_instruction(lap, laps), "cum_m": round(offset, 1)})
        for step in steps:
            if (step.get("turn_type") == START and lap) or (step.get("turn_type") == ARRIVE and lap < laps - 1):
                continue
            new_steps.append(dict(step, cum_m=round(step["cum_m"] + offset, 1)))
    return dict(course, path=new_path, steps=new_steps, distance_km=round(course["distance_km"] * laps, 2),
                name=f"{course['name']} · {laps}바퀴", laps=laps, lap_km=course["distance_km"],
                lap_path=path, lap_steps=steps, lap_name=course["name"])


def one_lap(course: dict) -> dict:
    """여러 바퀴 코스에서 한 바퀴만 (Tmap으로 다시 이을 때). 한 바퀴 코스는 그대로."""
    if (course.get("laps") or 1) <= 1:
        return course
    lap = {k: v for k, v in course.items() if k not in ("laps", "lap_km", "lap_path", "lap_steps", "lap_name")}
    return dict(lap, path=course["lap_path"], steps=course["lap_steps"], distance_km=course["lap_km"],
                name=course["lap_name"])
