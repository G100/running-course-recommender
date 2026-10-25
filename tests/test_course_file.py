"""코스 DB 파일은 여러 요청이 동시에 읽고 쓴다.

실시간 생성을 먼저 하게 하자, 만든 코스를 뒤에서 저장하는 동안 다음 요청이 같은 파일을 읽어
반쯤 쓰인 JSON을 만나 서버가 500을 냈다(36건 중 11건).
"""
import json
import threading

from src.data_collection import course_file


def test_readers_never_see_a_half_written_file(tmp_path):
    path = str(tmp_path / "courses.json")
    big = [{"id": f"c{i}", "path": [[34.0 + k * 1e-5, 127.0] for k in range(200)]} for i in range(60)]
    course_file.write(path, big)
    errors, stop = [], threading.Event()

    def keep_writing():
        n = 0
        while not stop.is_set():
            course_file.write(path, big + [{"id": f"extra{n}"}])
            n += 1

    writer = threading.Thread(target=keep_writing)
    writer.start()
    try:
        for _ in range(150):
            try:
                assert len(course_file.read(path)) >= 60
            except (json.JSONDecodeError, PermissionError) as error:
                errors.append(error)
    finally:
        stop.set()
        writer.join()
    assert not errors, errors[:1]


def test_two_saves_at_once_do_not_lose_a_course(tmp_path):
    path = str(tmp_path / "courses.json")
    course_file.write(path, [])
    threads = [threading.Thread(target=course_file.upsert, args=(path, {"id": f"c{i}"})) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(c["id"] for c in course_file.read(path)) == sorted(f"c{i}" for i in range(20))
