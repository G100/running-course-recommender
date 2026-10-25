"""코스 DB 파일(courses.json)을 여러 요청이 동시에 읽고 쓰게 한다.

실시간으로 만든 코스는 응답을 보낸 뒤 뒤에서 저장한다. 그동안 다음 요청이 같은 파일을 읽으면 반쯤
쓰인 JSON을 만나 서버가 500을 냈다. 그래서
  - 읽기·쓰기를 한 잠금으로 묶고(같은 서버 안의 요청과 백그라운드 작업이 서로 기다린다),
  - 쓸 때는 임시 파일에 다 쓴 뒤 한 번에 바꿔 끼운다(읽는 쪽은 항상 완성된 파일만 본다),
  - 읽고-고치고-쓰는 일(upsert)도 잠금 안에서 해서 동시에 저장한 코스가 서로를 지우지 않게 한다.
"""
import json
import os
import threading

LOCK = threading.RLock()


def read(path: str) -> list:
    with LOCK:
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            return json.load(f)


def write(path: str, courses: list) -> None:
    with LOCK:
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(courses, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


def upsert(path: str, course: dict) -> None:
    """같은 id가 있으면 바꾸고 없으면 더한다."""
    with LOCK:
        courses = [c for c in read(path) if c.get("id") != course.get("id")]
        courses.append(course)
        write(path, courses)


def replace_one(path: str, course: dict) -> bool:
    """이미 있는 코스만 바꾼다. 없으면(그사이 지워졌으면) False."""
    with LOCK:
        courses = read(path)
        for i, c in enumerate(courses):
            if c.get("id") == course.get("id"):
                courses[i] = course
                write(path, courses)
                return True
        return False
