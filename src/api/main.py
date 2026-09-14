"""Android 앱이 붙일 추천 API 스켈레톤.

실행:
    uvicorn src.api.main:app --reload
    POST /recommend 로 온보딩 조건(+선택적 자연어 문장)을 보내면 상위 N개 코스를 반환.

현위치(current_lat/current_lng)를 같이 보내면:
    1) 그 주변 max_distance_km 안에 등록된 코스가 있으면 거기서 골라서 즉시 반환 (빠름)
    2) 없으면 그 자리에서 실제 도로/지형 데이터로 코스를 새로 만들어 반환하고(수 초 소요),
       백그라운드로 정밀 보강해 DB에 등록해 다음 요청부터는 빨라지게 한다.
"""
import json
import os
from typing import List, Literal, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..data_collection.add_course import add_course as register_course_full
from ..recommend.environment import get_environment_context
from ..recommend.generate_live import generate_loop_course
from ..recommend.location import filter_nearby
from ..recommend.nl_keywords import extract_tags
from ..recommend.route_type import apply_route_type
from ..recommend.score import recommend, score_course
from ..recommend.trim import truncate_course

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
MAIN_DB_PATH = os.path.join(DATA_DIR, "courses.json")
SAMPLE_DB_PATH = os.path.join(DATA_DIR, "courses.sample.json")

app = FastAPI(title="러닝 코스 추천 API")


def load_courses() -> list:
    path = MAIN_DB_PATH if os.path.exists(MAIN_DB_PATH) else SAMPLE_DB_PATH
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_env_context_map(courses: list, enabled: bool) -> Optional[dict]:
    if not enabled:
        return None
    return {c["id"]: get_environment_context(c["id"]) for c in courses}


def register_in_background(course: dict):
    try:
        register_course_full(course, MAIN_DB_PATH)
    except Exception as e:
        print(f"[background] 코스 정밀 보강 등록 실패 ({course.get('id')}): {e}")


class RecommendRequest(BaseModel):
    fitness_level: Optional[int] = None
    purpose: Optional[str] = None
    preferred_distance_km: Optional[float] = None
    preferred_time_min: Optional[int] = None
    elevation_preference: Optional[str] = "medium"
    environment_tags: Optional[List[str]] = []
    text: Optional[str] = None
    top_n: int = 5
    use_live_environment: bool = True
    current_lat: Optional[float] = None
    current_lng: Optional[float] = None
    max_distance_km: float = 5.0
    route_type: Literal["roundtrip", "oneway"] = "roundtrip"


class CourseResult(BaseModel):
    course: dict
    score: float


class RecommendResponse(BaseModel):
    results: List[CourseResult]
    source: str  # "db" | "generated"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def navigate_page():
    path = os.path.join(os.path.dirname(__file__), "static", "navigate.html")
    with open(path, encoding="utf-8") as f:
        html = f.read()
    html = html.replace("{{TMAP_APP_KEY}}", os.environ.get("TMAP_APP_KEY", ""))
    return HTMLResponse(html)


@app.post("/recommend", response_model=RecommendResponse)
def post_recommend(req: RecommendRequest, background_tasks: BackgroundTasks):
    user = req.model_dump()
    tags = set(user.get("environment_tags") or [])
    if req.text:
        tags |= extract_tags(req.text)
    user["environment_tags"] = tags

    courses = load_courses()
    has_location = req.current_lat is not None and req.current_lng is not None

    candidates = courses
    if has_location:
        candidates = filter_nearby(courses, req.current_lat, req.current_lng, req.max_distance_km)
    candidates = [apply_route_type(c, req.route_type) for c in candidates]

    def trim_if_needed(course: dict) -> dict:
        if req.preferred_distance_km:
            return truncate_course(course, req.preferred_distance_km)
        return course

    if not has_location or candidates:
        env_context_map = build_env_context_map(candidates, req.use_live_environment)
        ranked = recommend(candidates, user, top_n=req.top_n, env_context_map=env_context_map)
        return {
            "results": [{"course": trim_if_needed(c), "score": round(s, 4)} for c, s in ranked],
            "source": "db",
        }

    # 현위치 근처에 등록된 코스가 없음 -> 그 자리에서 실제 데이터로 생성
    target_km = req.preferred_distance_km or 3.0
    try:
        generated = generate_loop_course(req.current_lat, req.current_lng, target_km, tags, route_type=req.route_type)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    background_tasks.add_task(register_in_background, generated)

    score = score_course(generated, user)
    return {
        "results": [{"course": trim_if_needed(generated), "score": round(score, 4)}],
        "source": "generated",
    }
