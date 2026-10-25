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
from contextlib import asynccontextmanager
from html import escape as html_escape
from typing import List, Literal, Optional

import requests
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

from ..data_collection.add_course import add_course as register_course_full
from ..data_collection.refresh_route import refresh_course_in_db
from ..data_collection.scenery import THRESHOLDS as SCENERY_THRESHOLDS, tag_descriptions
from ..api_clients.tmap_poi import search_places
from ..recommend.destination import course_to_destination
from ..recommend.freshness import stale_courses, stamp_verified
from ..recommend.generate_live import generate_loop_candidates
from ..recommend.location import filter_nearby
from ..recommend.profile import resolve_target_distance_km
from ..data_collection.enrich import haversine_m
from ..recommend.route_type import apply_route_type, attach_actual_return_path
from ..recommend.personalize import forget_legacy
from ..recommend.personalize import (answer_labels, answers_view, explain, feedback_questions, invalid_aspects, learn,
                                     learn_aspects,
                                     load_profile, new_profile, recalled, remember_recommendation, save_profile,
                                     taste_summary, weights_for)
from ..recommend.score import component_scores, filter_by_required_tags, recommend
from ..recommend.trim import truncate_course
from ..recommend.step_position import assign_positions
from ..data_collection import course_file, local_osm
from ..recommend import auth, nearby_scenery, scenery_choices, tmap_follow, user_store
from ..data_collection import area_cache
from ..api_clients.tmap_pedestrian import extract_path, extract_steps
from ..recommend.timeofday import current_period

load_dotenv()

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
MAIN_DB_PATH = os.path.join(DATA_DIR, "courses.json")
SAMPLE_DB_PATH = os.path.join(DATA_DIR, "courses.sample.json")

# 키가 없으면 무엇이 안 되는지. 키를 소스에 넣지 않는 대신 이걸로 안내한다.
API_KEYS = {
    "TMAP_APP_KEY": "코스 생성, 턴바이턴 안내, 지도",
}

SCENERY_TAGS = tag_descriptions()  # {태그: 붙는 기준}


def missing_keys() -> list:
    return [name for name in API_KEYS if not os.environ.get(name)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    missing = missing_keys()
    if missing:
        lines = ["", "=" * 62, "  환경변수(API 키)가 설정되지 않아 일부 기능이 동작하지 않습니다."]
        lines += [f"    - {name:<18} 없음 -> {API_KEYS[name]} 불가" for name in missing]
        lines += ["", "  해결: .env.example을 .env로 복사하고 키를 채운 뒤 서버를 다시 시작하세요.",
                  "        (DB에 저장된 코스 추천은 키 없이도 동작합니다)", "=" * 62, ""]
        print("\n".join(lines), flush=True)
    yield


app = FastAPI(title="러닝 코스 추천 API", lifespan=lifespan)


_db_cache = {"key": None, "courses": None}


def load_courses() -> list:
    """파일이 바뀌었을 때만 다시 읽는다(백그라운드 갱신·신규 등록이 파일을 고치면 수정 시각이 바뀜).
    요청마다 전체 JSON을 파싱하면 경로·복귀 경로까지 담긴 DB라 그것만으로 0.15초가 든다."""
    path = MAIN_DB_PATH if os.path.exists(MAIN_DB_PATH) else SAMPLE_DB_PATH
    key = (path, os.path.getmtime(path))
    if _db_cache["key"] != key:
        # 뒤에서 새 코스를 저장하는 중이면 다 쓸 때까지 기다렸다가 완성된 파일을 읽는다
        _db_cache["courses"] = course_file.read(path)
        _db_cache["key"] = key
    return _db_cache["courses"]


def register_in_background(course: dict):
    try:
        register_course_full(stamp_verified(course), MAIN_DB_PATH)
    except Exception as e:
        print(f"[background] 코스 정밀 보강 등록 실패 ({course.get('id')}): {e}")


def refresh_in_background(course_id: str):
    """오래된 경로를 뒤에서 다시 받아 둔다. 실패해도 사용자 응답에는 영향이 없다."""
    try:
        refreshed = refresh_course_in_db(course_id, MAIN_DB_PATH)
        if refreshed and refreshed.get("previous_distance_km"):
            print(f"[background] 경로 변경 감지 {course_id}: "
                  f"{refreshed['previous_distance_km']}km -> {refreshed['distance_km']}km")
    except Exception as e:
        print(f"[background] 경로 갱신 실패 ({course_id}): {e}")


class RecommendRequest(BaseModel):
    # 러닝 코스 추천에 직접 필요한 것만 받는다. 동반자·목적·숙련도·페이스·문장 입력·날씨는 뺐다
    # (예전 앱이 그 필드를 보내도 오류 없이 무시된다)
    preferred_distance_km: Optional[float] = None
    preferred_time_min: Optional[int] = None
    elevation_preference: Optional[str] = "medium"   # 고도는 지금 꺼져 있다 (score.ELEVATION_ENABLED)
    environment_tags: Optional[List[str]] = []
    top_n: int = 5
    current_lat: Optional[float] = None
    current_lng: Optional[float] = None
    max_distance_km: float = 5.0
    route_type: Literal["roundtrip", "loop", "oneway"] = "roundtrip"  # 왕복 / 순환 / 편도
    user_id: Optional[str] = None           # 주면 이 사람의 만족도로 학습한 가중치로 추천한다
    destination: Optional[str] = None       # 목적지 장소 이름 (예: "오동도, 여수")
    destination_lat: Optional[float] = None  # 장소 이름 대신 좌표로 지정할 때
    destination_lng: Optional[float] = None
    time_of_day: Optional[Literal["morning", "afternoon", "evening", "night"]] = None  # 생략하면 서버 시각 기준
    # 고른 조건대로 못 만들었을 때 앱이 사용자에게 묻고 다시 보내는 값 (응답 choice.options[].set)
    allow_secluded_at_night: bool = False   # 밤이라도 인적 드문 풍경 길로 가겠다
    extend_for_scenery: bool = False        # 거리를 늘려서라도 고른 풍경까지 가겠다

    @field_validator("environment_tags")
    @classmethod
    def _known_scenery(cls, v):
        # 없는 태그(예: "벚꽃길")를 조용히 받으면 결과가 0개로 나가고 앱은 이유를 모른다
        # 선택지 이름('바다')과 측정 태그('바다뷰') 둘 다 받는다
        unknown = [tag for tag in (v or []) if tag not in SCENERY_TAGS and not scenery_choices.is_choice(tag)]
        if unknown:
            raise ValueError(f"알 수 없는 풍경 태그 {unknown}. 사용할 수 있는 값은 GET /onboarding/scenery 참고")
        return v


class CourseResult(BaseModel):
    course: dict
    score: float
    score_breakdown: Optional[dict] = None  # 항목별 적합도 0~1 (왜 이 코스인지)
    rating: Optional[dict] = None           # 다른 사용자들의 평가 {"average", "count"} (있을 때만)
    favorite: Optional[bool] = None         # user_id를 줬을 때, 이 사람이 즐겨찾기한 코스인가


class FeedbackRequest(BaseModel):
    user_id: str
    course_id: str
    rating: int = Field(ge=1, le=5, description="러닝 후 만족도 1~5")
    comment: Optional[str] = Field(default=None, max_length=500, description="후기 (선택)")
    # 항목별 답 (선택). 문항과 값은 GET /onboarding/feedback. 예: {"stops": "many", "elevation": "hard"}
    aspects: Optional[dict] = None

    @field_validator("aspects")
    @classmethod
    def _known_aspects(cls, v):
        bad = invalid_aspects(v)
        if bad:
            raise ValueError(f"알 수 없는 항목 {bad}. 문항과 값은 GET /onboarding/feedback 참고")
        return v


class FavoriteRequest(BaseModel):
    user_id: str
    course_id: str
    # 추천 응답으로 받은 코스를 그대로 넣어 준다. 실시간 생성 코스는 아직 DB에 없을 수 있다.
    course: Optional[dict] = None


# 경로·풍경·안전 시설은 OpenStreetMap 데이터로 만든다. ODbL 라이선스상 이 데이터로 만든 결과를
# 보여주는 화면에는 출처를 표시해야 한다 — 앱이 그대로 띄울 수 있게 응답에 넣어 준다.
DATA_ATTRIBUTION = "지도 데이터 © OpenStreetMap contributors (ODbL) · 경로 확인·장소 검색 Tmap"


class RecommendResponse(BaseModel):
    results: List[CourseResult]
    source: str  # "db" | "generated" | "destination"
    attribution: str = DATA_ATTRIBUTION  # 결과 화면 어딘가에 표시
    notice: Optional[str] = None  # 고른 조건대로 못 만들어 대신 준 코스일 때, 그 이유 (앱이 그대로 띄운다)
    # 사용자가 정할 일: {question, options: [{label, set}]}. 고른 option의 set을 요청에 더해 다시 보낸다
    choice: Optional[dict] = None


class Credentials(BaseModel):
    username: str
    password: str
    # 가입할 때만: 로그인 없이 쓰던 기기의 user_id. 주면 그동안 쌓인 취향·이력·즐겨찾기를 계정으로 옮긴다
    guest_id: Optional[str] = None


def _owner_only(user_id: Optional[str], authorization) -> None:
    """계정의 데이터는 그 계정으로 로그인한 요청만 다룰 수 있다. 손님 id는 그대로 통과한다."""
    try:
        auth.require_owner(user_id, authorization if isinstance(authorization, str) else None)
    except auth.AuthError as error:
        raise HTTPException(status_code=error.status, detail=error.message)


@app.post("/auth/signup")
def auth_signup(req: Credentials):
    """계정을 만들고 로그인한 상태로 돌려준다. 받은 `token`을 이후 요청의 `Authorization: Bearer <token>`으로,
    `user_id`를 각 요청의 user_id로 쓴다."""
    try:
        if req.guest_id:
            load_profile(req.guest_id)   # 예전 파일에만 있던 손님이면 먼저 DB로 가져온 뒤 옮긴다
        return auth.sign_up(req.username, req.password, req.guest_id)
    except auth.AuthError as error:
        raise HTTPException(status_code=error.status, detail=error.message)


@app.post("/auth/login")
def auth_login(req: Credentials):
    try:
        return auth.log_in(req.username, req.password)
    except auth.AuthError as error:
        raise HTTPException(status_code=error.status, detail=error.message)


@app.post("/auth/logout")
def auth_logout(authorization: Optional[str] = Header(default=None)):
    return {"logged_out": auth.log_out(authorization)}


@app.get("/auth/me")
def auth_me(authorization: Optional[str] = Header(default=None)):
    """지금 토큰이 누구 것인지. 앱을 다시 열었을 때 로그인 상태를 확인하는 데 쓴다."""
    user = auth.current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return user


@app.get("/onboarding/scenery")
def onboarding_scenery(lat: Optional[float] = None, lng: Optional[float] = None, radius_km: float = 10.0):
    """고를 수 있는 풍경 선택지. 쉬운 이름과 한 줄 설명으로 준다.

    현위치(lat, lng)를 주면 반경(기본 10km) 안에 실제로 있는 풍경만, 가까운 순서로 준다 — 내륙에서
    '바다'가 선택지로 나오지 않게. 위치를 안 주면 저장된 코스에 있는 풍경 전체.
    받은 `value`를 그대로 `/recommend`의 `environment_tags`에 넣으면 된다.
    """
    courses = load_courses()
    has_location = lat is not None and lng is not None
    if has_location:
        courses = filter_nearby(courses, lat, lng, radius_km)
    around = nearby_scenery.nearby(lat, lng, radius_km) if has_location else None

    options = []
    for name, group, hint, tags in scenery_choices.CHOICES:
        count = sum(1 for course in courses if set(course.get("tags", [])) & set(tags))
        distances = [around[tag] for tag in tags if around and tag in around]
        if not count and not distances:
            continue  # 골라도 결과가 없는 선택지는 보여주지 않는다
        distance = min(distances) if distances else None
        options.append({
            "value": name, "label": name, "group": group, "hint": hint,
            "distance_km": distance, "near": scenery_choices.near_text(distance),
            "course_count": count,
            # 개발자용: 이 선택지가 어떤 측정 기준에 대응하는지
            "criteria": {tag: SCENERY_TAGS[tag] for tag in tags if tag in SCENERY_TAGS},
        })
    if around is not None:
        # 가까운 것부터. 거리를 모르는 것(근처 저장 코스에만 있는 풍경)은 뒤로
        options.sort(key=lambda o: (o["distance_km"] is None, o["distance_km"] or 0))
        basis = "location"
    else:
        basis = "nearby_courses" if has_location else "all_courses"
    return {"scenery": options, "groups": scenery_choices.GROUPS, "basis": basis,
            **({"radius_km": radius_km} if basis == "location" else {})}


@app.get("/places")
def get_places(q: str, lat: Optional[float] = None, lng: Optional[float] = None):
    """목적지 검색 후보. 입력창 아래에 목록으로 보여주고, 고른 것의 좌표를 `/recommend`의
    `destination_lat`·`destination_lng`로 보내면 된다. 현위치를 주면 가까운 곳을 우선한다."""
    return {"places": search_places(q, lat, lng)}


@app.get("/onboarding/feedback")
def onboarding_feedback():
    """러닝 후 물어볼 항목별 질문. 별점과 함께 `/feedback`의 `aspects`로 보낸다 (전부 선택 사항)."""
    return {"questions": feedback_questions()}


@app.post("/feedback")
def post_feedback(req: FeedbackRequest, authorization: Optional[str] = Header(default=None)):
    """러닝 후 만족도를 받아 그 사람의 가중치를 학습한다.

    무엇 때문에 추천했는지(항목별 적합도)는 추천할 때 남겨 두었으므로, 앱은 코스 id와
    점수만 보내면 된다.
    """
    _owner_only(req.user_id, authorization)
    profile = load_profile(req.user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="추천을 받은 적 없는 사용자입니다. 먼저 user_id를 넣어 추천을 받아야 합니다.")
    remembered = recalled(profile, req.course_id)
    if remembered is None:
        raise HTTPException(status_code=404, detail="이 사용자에게 최근 추천된 코스가 아닙니다.")
    scores, baseline = remembered
    learn(profile, scores, req.rating, baseline)
    # 별점은 "무엇이" 좋았는지를 다른 코스와의 차이로 추정한다. 항목별 답은 그 항목에 대한 직접 증거다
    learn_aspects(profile, req.aspects)
    save_profile(profile)
    # 학습에 쓰고 버리지 않고 기록으로도 남긴다 — 다른 사람에게 평균 별점과 후기를 보여줄 수 있게
    user_store.save_review(req.user_id, req.course_id, req.rating, req.comment, req.aspects)
    _log_feedback(req, profile["weights"])
    return _profile_view(profile)


def _log_feedback(req, weights: Optional[dict]) -> None:
    """평가 한 번을 이력으로 남긴다 — 그 사람이 나중에 자기 취향이 어떻게 만들어졌는지 볼 수 있게."""
    course = _known_course(req.course_id) or next(
        (item["course"] for item in user_store.favorites(req.user_id) if item["course"]["id"] == req.course_id), None)
    user_store.log_feedback(
        req.user_id, req.course_id, req.rating, req.aspects, req.comment,
        course_name=course.get("name") if course else None,
        labels=scenery_choices.labels_for(course.get("tags")) if course else [],
        weights={k: round(v, 4) for k, v in weights.items()} if weights else None)


def _known_course(course_id: str):
    return next((c for c in load_courses() if c["id"] == course_id), None)


@app.post("/reviews")
def post_review(req: FeedbackRequest, authorization: Optional[str] = Header(default=None)):
    """추천받지 않은 코스(즐겨찾기에서 다시 뛴 코스 등)에도 별점·후기를 남긴다. 가중치 학습은 하지 않는다."""
    _owner_only(req.user_id, authorization)
    if _known_course(req.course_id) is None and req.course_id not in user_store.favorite_ids(req.user_id):
        raise HTTPException(status_code=404, detail="없는 코스입니다.")
    user_store.save_review(req.user_id, req.course_id, req.rating, req.comment, req.aspects)
    _log_feedback(req, None)
    return get_reviews(req.course_id)


@app.get("/courses/{course_id}/reviews")
def get_reviews(course_id: str, limit: int = 20):
    """코스의 평균 별점과 최근 후기. 누가 썼는지는 아이디(가입한 사람)나 '러너'로만 보여준다."""
    body = user_store.reviews_for(course_id, limit)
    names = user_store.usernames([review["user_id"] for review in body["reviews"]])
    for review in body["reviews"]:
        # 내부 user_id는 내보내지 않는다 — 다른 사람의 데이터를 가리키는 열쇠라서
        review["author"] = names.get(review.pop("user_id"), "러너")
    return body


@app.post("/favorites")
def post_favorite(req: FavoriteRequest, authorization: Optional[str] = Header(default=None)):
    """코스를 즐겨찾기에 저장한다. 코스 내용을 통째로 보관하므로 나중에 경로가 바뀌어도 저장한 그대로 남는다."""
    _owner_only(req.user_id, authorization)
    course = req.course or _known_course(req.course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="없는 코스입니다. 실시간 생성 코스는 course에 내용을 같이 보내주세요.")
    if course.get("id") != req.course_id or not course.get("path"):
        raise HTTPException(status_code=422, detail="course는 추천 응답으로 받은 코스 그대로여야 합니다(id, path 포함).")
    user_store.add_favorite(req.user_id, course)
    return {"saved": True, "count": len(user_store.favorite_ids(req.user_id))}


@app.get("/favorites/{user_id}")
def get_favorites(user_id: str, authorization: Optional[str] = Header(default=None)):
    _owner_only(user_id, authorization)
    saved = user_store.favorites(user_id)
    marks = user_store.ratings([item["course"]["id"] for item in saved])
    for item in saved:
        item["rating"] = marks.get(item["course"]["id"])
    return {"favorites": saved}


@app.delete("/favorites/{user_id}/{course_id}")
def delete_favorite(user_id: str, course_id: str, authorization: Optional[str] = Header(default=None)):
    _owner_only(user_id, authorization)
    if not user_store.remove_favorite(user_id, course_id):
        raise HTTPException(status_code=404, detail="즐겨찾기에 없는 코스입니다.")
    return {"saved": False}


@app.get("/profile/{user_id}")
def get_profile(user_id: str, authorization: Optional[str] = Header(default=None)):
    """학습된 취향. 어떤 요소를 기본값보다 더/덜 중시하게 됐는지 설명과 함께."""
    _owner_only(user_id, authorization)
    profile = load_profile(user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="프로필이 없습니다.")
    return _profile_view(profile)


def _profile_view(profile: dict) -> dict:
    return {
        "user_id": profile["user_id"],
        "n_feedback": profile["n_feedback"],
        "survey": profile.get("survey", {}),
        "weights": {k: round(v, 3) for k, v in profile["weights"].items()},
        "explanation": explain(profile),
        # 사용자에게 그대로 보여줄 수 있는 취향 요약 문장 (답한 내용에 근거가 있는 것만)
        "summary": taste_summary(profile),
        # 항목별 답으로 옮겨진 목표: 1보다 작으면 더 완만하게/짧게, 크면 더 가파르게/길게
        "tuning": {"elevation_scale": profile.get("elevation_scale", 1.0),
                   "distance_scale": profile.get("distance_scale", 1.0)},
        "aspect_log": profile.get("aspect_log", {}),
    }


@app.get("/users/{user_id}/taste")
def get_my_taste(user_id: str, limit: int = 50, authorization: Optional[str] = Header(default=None)):
    """내 취향 데이터 전부: 요약, 항목별 중요도, 맞춰진 기준, 지금까지 한 답, 평가 이력, 취향이 변해 온 과정.

    앱의 '내 취향' 화면이 이것 하나로 그려진다. 평가한 적이 없어도(프로필만 있어도) 빈 이력으로 응답한다.
    """
    _owner_only(user_id, authorization)
    profile = load_profile(user_id)
    history = user_store.feedback_history(user_id, limit)
    if profile is None and not history:
        raise HTTPException(status_code=404, detail="아직 저장된 취향 데이터가 없습니다.")

    ratings = [item["rating"] for item in history]
    liked = {}
    for item in history:
        if item["rating"] >= 4:
            for label in item["scenery_labels"]:
                liked[label] = liked.get(label, 0) + 1
    view = _profile_view(profile) if profile else {"user_id": user_id, "n_feedback": 0, "survey": {}, "weights": {},
                                                    "explanation": [], "summary": [], "tuning": {}, "aspect_log": {}}
    view.pop("aspect_log", None)
    return {
        **view,
        "stats": {
            "feedback_count": len(ratings),
            "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
            # 4점 이상 준 코스들이 지나던 풍경 (많은 순)
            "liked_scenery": [{"label": label, "count": count}
                              for label, count in sorted(liked.items(), key=lambda kv: -kv[1])],
            "favorite_count": len(user_store.favorite_ids(user_id)),
        },
        "answers": answers_view(profile) if profile else [],
        "history": [{
            "created_at": item["created_at"], "course_id": item["course_id"], "course_name": item["course_name"],
            "scenery_labels": item["scenery_labels"], "rating": item["rating"],
            "answers": answer_labels(item["aspects"]), "comment": item["comment"],
        } for item in history],
        # 평가할 때마다의 가중치 (오래된 것부터) — 취향이 어떻게 변해 왔는지 그래프로 그릴 수 있다
        "weight_history": [{"created_at": item["created_at"], "weights": item["weights"]}
                           for item in reversed(history) if item["weights"]],
    }


@app.delete("/users/{user_id}")
def delete_my_data(user_id: str, authorization: Optional[str] = Header(default=None)):
    """내 데이터 전부 삭제: 학습된 취향, 평가 이력, 별점·후기, 즐겨찾기. 되돌릴 수 없다."""
    _owner_only(user_id, authorization)
    forget_legacy(user_id)   # 예전 파일에 남은 것까지 지운다 (안 그러면 다음 조회 때 되살아난다)
    removed = user_store.delete_user(user_id)
    if not any(removed.values()):
        raise HTTPException(status_code=404, detail="저장된 데이터가 없습니다.")
    return {"deleted": removed}


class FollowRequest(BaseModel):
    path: List[List[float]] = Field(min_length=2)   # 우리 코스 [[lat, lng], ...] (추천 응답의 course.path)
    target_km: Optional[float] = None               # 요청 거리 (주면 그 거리에 가까운 쪽을 고른다)


def _follow_with_tmap(path: list, target_km: float = None) -> dict:
    start = tuple(path[0])
    reach = max(haversine_m(start, p) for p in path)
    area = area_cache.load_area(start[0], start[1], radius_m=reach + 300)
    if area is None or area.graph is None:
        raise HTTPException(status_code=503, detail="이 지역 도로망이 없어 Tmap 경로로 이을 수 없습니다.")
    return tmap_follow.follow(area.graph, path, target_km=target_km)


MAX_TMAP_ROUNDS = 3     # Tmap으로 잇고 거리를 재는 횟수 (처음 + 크기를 고쳐 다시 짜기 2번)
DISTANCE_OK = 0.05      # 실제로 달릴 경로가 요청 거리와 이 비율 안이어야 한다


def _deliver_on_tmap(plan: dict, target_km: float, route_type: str, regenerate) -> dict:
    """우리가 짠 코스를 실제로 달릴 Tmap 경로로 바꿔 준다. 그 거리가 요청과 5% 넘게 다르면 맞춘다.

    우리 설계가 맞아도 Tmap으로 이으면 길이가 달라졌다(36개 중 5% 안 12개, 평균 +13%). 사용자가 실제로
    달리는 건 Tmap 경로이므로 그 거리로 맞춘다.
    - 편도: 길면 요청 거리에서 끝낸다(잘라도 코스가 된다).
    - 순환·왕복: 자르면 출발점으로 돌아오지 못하니, Tmap이 늘린(줄인) 비율만큼 크기를 고쳐 다시 짜고
      다시 잇는다(최대 2번). 가장 가까웠던 것을 쓴다.
    Tmap을 쓸 수 없으면(키 없음·장애) 우리가 짠 코스를 그대로 준다 — 안내 시작 때 다시 잇는다.
    """
    if not target_km or not plan.get("path"):
        return plan
    tries = []
    for attempt in range(MAX_TMAP_ROUNDS):
        try:
            route = _follow_with_tmap(plan["path"], target_km)
        except (RuntimeError, requests.RequestException, HTTPException):
            break
        km = route["follow"]["distance_km"]
        tries.append((abs(km - target_km) / target_km, plan, route))
        if abs(km - target_km) <= target_km * DISTANCE_OK:
            break
        if route_type == "oneway" and km > target_km:
            break   # 아래에서 요청 거리만큼 자른다
        if attempt == MAX_TMAP_ROUNDS - 1 or not km:
            break
        resized = regenerate(plan["distance_km"] * target_km / km)
        if resized is None:
            break
        plan = resized
    if not tries:
        return plan
    _, plan, route = min(tries, key=lambda t: t[0])
    path, _ = extract_path(route)
    delivered = dict(plan, path=path, steps=assign_positions(extract_steps(route), path),
                     distance_km=route["follow"]["distance_km"], plan_path=plan["path"], tmap=route["follow"])
    delivered.pop("return_path", None)      # 왕복이면 Tmap 경로가 이미 갔다 오는 길 전체다
    delivered.pop("return_steps", None)
    if route_type == "oneway" and delivered["distance_km"] > target_km * (1 + DISTANCE_OK):
        delivered = truncate_course(delivered, target_km)
    return delivered


@app.post("/courses/follow")
def follow_course(req: FollowRequest):
    """사용자가 고른 코스를 Tmap 보행자 경로로 잇는다. 길 안내는 이 경로와 Tmap의 회전 안내로 한다."""
    try:
        route = _follow_with_tmap([list(p) for p in req.path], req.target_km)
    except (RuntimeError, requests.RequestException) as error:
        raise HTTPException(status_code=502, detail=f"Tmap 경로를 받지 못했습니다: {error}")
    path, _ = extract_path(route)
    follow = route["follow"]
    return {"path": path, "steps": extract_steps(route), "distance_km": follow["distance_km"], "follow": follow}


@app.get("/health")
def health():
    """키 '값'은 절대 내보내지 않고, 설정 여부만 알려준다 (팀원 환경 자가진단용)."""
    from ..recommend import sidewalk

    return {
        "status": "ok",
        "keys": {name: bool(os.environ.get(name)) for name in API_KEYS},
        # 로컬 지형 DB: 없으면 직접 경로 탐색 대신 Tmap 최단 경로로 동작한다.
        # matches_team이 true면 팀 기준 파일·코드로 만든 것 (python -m src.setup_local 로 맞춘다)
        "local_map": local_osm.info(),
        "sidewalk_facts": len(sidewalk.load_facts()),
    }


@app.get("/")
def navigate_page():
    path = os.path.join(os.path.dirname(__file__), "static", "navigate.html")
    with open(path, encoding="utf-8") as f:
        html = f.read()

    # 지도 자체는 키가 없어도 뜨지만(OpenFreeMap), 현위치 기반 코스 생성은 Tmap 경로가 필요하다.
    warning = ""
    if not os.environ.get("TMAP_APP_KEY"):
        warning = (
            '<div class="setup-warning"><strong>TMAP_APP_KEY 환경변수가 설정되지 않았습니다 — '
            '현위치 기반 코스 생성을 쓸 수 없습니다.</strong>'
            '프로젝트 폴더의 <code>.env.example</code>을 <code>.env</code>로 복사하고 '
            'TMAP_APP_KEY 값을 채운 뒤 서버를 다시 시작하세요. '
            '지도 표시와 DB에 저장된 코스 추천·턴바이턴 안내는 키 없이도 동작합니다.</div>'
        )

    html = html.replace("{{KEY_WARNING}}", warning)
    # 지도는 Tmap 벡터 지도. 키는 파일에 두지 않고 여기서 끼운다(브라우저가 지도를 받으려면 키가 필요하다).
    # 키가 없으면 비워 두고, 페이지는 MapLibre 지도로 그린다
    key = os.environ.get("TMAP_APP_KEY")
    script = (f'<script src="https://apis.openapi.sk.com/tmap/vectorjs?version=1&appKey={html_escape(key)}"></script>'
              if key else "")
    html = html.replace("{{TMAP_MAP_SCRIPT}}", script)
    return HTMLResponse(html)


def _user_from_request(req) -> dict:
    user = req.model_dump()
    chosen = list(user.get("environment_tags") or [])
    # 사용자가 고른 선택지('바다')를 측정 태그(바다뷰·해변)로 푼다. 이후 단계는 측정 태그로 동작한다
    user["environment_tags"], user["scenery_groups"] = scenery_choices.resolve(chosen)
    return user


SURVEY_FIELDS = ("environment_tags", "preferred_distance_km", "preferred_time_min")


@app.post("/recommend", response_model=RecommendResponse)
def post_recommend(req: RecommendRequest, background_tasks: BackgroundTasks,
                   authorization: Optional[str] = Header(default=None)):
    """user_id를 주면 그 사람의 학습된 가중치로 추천하고, 평가를 받을 수 있게 추천 근거를 남긴다."""
    _owner_only(req.user_id, authorization)
    user = _user_from_request(req)

    profile = None
    if req.user_id:
        profile = load_profile(req.user_id)
        if profile is None:
            # 첫 요청의 온보딩 답변이 곧 초기 설문이다
            survey = {k: user.get(k) for k in SURVEY_FIELDS if user.get(k) not in (None, [], set())}
            survey["environment_tags"] = sorted(survey.get("environment_tags", []))
            profile = new_profile(req.user_id, survey=survey)
    weights = weights_for(profile) if profile else None
    if profile:
        # 러닝 후 "힘들었다/길었다" 같은 답으로 맞춰 둔 이 사람의 기준
        user["elevation_scale"] = profile.get("elevation_scale", 1.0)
        user["distance_scale"] = profile.get("distance_scale", 1.0)

    response = _recommend(req, background_tasks, user, weights)

    # 항목별 적합도를 같이 내려준다: 앱은 "왜 이 코스인지" 보여줄 수 있고,
    # 서버는 나중에 만족도 평가가 오면 이걸로 이 사람의 가중치를 학습한다
    breakdowns = []
    marks = user_store.ratings([result["course"]["id"] for result in response["results"]])
    saved = user_store.favorite_ids(req.user_id) if req.user_id else None
    for result in response["results"]:
        # 코스 카드에 보여줄 쉬운 이름 (측정 태그 16종 대신 선택지 이름)
        result["course"] = dict(result["course"],
                                scenery_labels=scenery_choices.labels_for(result["course"].get("tags")))
        result["rating"] = marks.get(result["course"]["id"])
        if saved is not None:
            result["favorite"] = result["course"]["id"] in saved
        course = result["course"]
        breakdown = component_scores(course, user)
        result["score_breakdown"] = {k: round(v, 3) for k, v in breakdown.items()}
        breakdowns.append((course["id"], breakdown))

    if profile is not None:
        for course_id, breakdown in breakdowns:
            # 비교 기준은 "이 코스 말고 같이 보여준 다른 코스들"의 평균
            others = [b for cid, b in breakdowns if cid != course_id]
            baseline = {k: sum(o[k] for o in others) / len(others) for k in breakdown} if others else None
            remember_recommendation(profile, course_id, breakdown, baseline)
        save_profile(profile)
    return response


def _recommend(req: RecommendRequest, background_tasks: BackgroundTasks, user: dict, weights: Optional[dict]):
    tags = user["environment_tags"]
    # "30분 뛸래"처럼 시간만 준 경우 페이스로 거리를 환산해 이후 단계 전부에서 같은 값을 쓴다
    target_km = resolve_target_distance_km(user)

    courses = load_courses()
    has_location = req.current_lat is not None and req.current_lng is not None

    candidates = courses
    if has_location:
        candidates = filter_nearby(courses, req.current_lat, req.current_lng, req.max_distance_km)
    originals = {c["id"]: c for c in candidates}
    candidates = [apply_route_type(c, req.route_type, with_steps=False) for c in candidates]

    def trim_if_needed(course: dict) -> dict:
        # 생성된 순환 루프를 단순 거리 절단하면 마지막 복귀 구간이 잘려 열린 코스가 된다.
        if course.get("route_type") == "loop":
            return course
        if target_km:
            return truncate_course(course, target_km)
        return course

    # 현재 위치에서 왕복을 요청하면 저장된 편도 코스를 되짚지 않고,
    # 가상 꼭짓점 + OSM 스냅 + Tmap passList로 새 순환 코스를 만든다.
    # 목적지를 지정했으면 추천이 아니라 지정이다 — 점수로 고르지 않고 거기까지 경로를 만든다.
    if req.destination or (req.destination_lat is not None and req.destination_lng is not None):
        if not has_location:
            raise HTTPException(
                status_code=400,
                detail="목적지까지의 코스를 만들려면 현위치(current_lat, current_lng)가 필요합니다.",
            )
        try:
            course = course_to_destination(
                req.current_lat, req.current_lng, req.destination,
                req.destination_lat, req.destination_lng, route_type=req.route_type,
                night=(user.get("time_of_day") or current_period()) == "night",
                tags=tags, want_km=target_km,
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=f"{e} .env에 TMAP_APP_KEY를 넣고 서버를 다시 시작하세요.")
        return {"results": [{"course": course, "score": 1.0}], "source": "destination"}

    # 순환은 갔던 길을 되짚는 왕복과 다른 코스다. 고른 대로 내보낸다.
    wants_loop = req.route_type == "loop"
    if wants_loop and not has_location:
        raise HTTPException(
            status_code=400,
            detail="순환 코스는 그 자리에서 만들기 때문에 현위치(current_lat, current_lng)가 필요합니다.",
        )

    # 현위치가 있으면 저장된 코스보다 그 자리에서 새로 만든 경로가 먼저다. 저장된 코스는 예전 규칙으로
    # 만든 것일 수 있다(인도 확인·거리 맞추기·풍경 기준이 계속 바뀌었다). 만들 수 없을 때만 저장된 코스로
    # 답한다(아래 except). 현위치가 없으면 만들 자리가 없으니 저장된 코스로 추천한다.
    if not has_location:
        ranked = recommend(candidates, user, top_n=req.top_n, weights=weights)
        # 저장된 경로는 즉시 주되, 오래된 건 뒤에서 갱신해 다음 사람이 최신 경로를 받게 한다.
        # 한 요청이 Tmap 할당량을 몰아 쓰지 않도록 한 번에 한 개만 갱신한다.
        for stale in stale_courses([c for c, _ in ranked], limit=1):
            background_tasks.add_task(refresh_in_background, stale["id"])

        # 턴바이턴 위치 계산은 결과로 나갈 코스에만 한다
        return {
            "results": [
                {
                    "course": trim_if_needed(
                        apply_route_type(
                            attach_actual_return_path(originals[c["id"]])
                            if req.route_type == "roundtrip" else originals[c["id"]],
                            req.route_type,
                        )
                    ),
                    "score": round(s, 4),
                }
                for c, s in ranked
            ],
            "source": "db",
        }

    # 순환 요청은 서로 다른 경유지 배치로 여러 루프를 만든 뒤 개인화 점수로 정렬한다.
    generate_km = target_km or 3.0
    deliver_km = generate_km   # 실제로 달릴 경로를 맞출 거리 (풍경까지 늘리기로 했으면 늘린 거리)
    notice = choice = None
    plain = False   # 고른 풍경 없이 만든 코스인가
    try:
        # 밤에는 상가·큰길처럼 사람이 있는 길 쪽으로 경로를 짠다 (시간대는 요청값, 없으면 서버 시각).
        # 사용자가 위험을 알고도 풍경 길을 골랐으면 그렇게 하지 않는다.
        night = (user.get("time_of_day") or current_period()) == "night"
        route_night = night and not req.allow_secluded_at_night
        generate = lambda km, wanted: generate_loop_candidates(
            req.current_lat, req.current_lng, km, wanted, route_type=req.route_type, night=route_night)
        try:
            generated_candidates = generate(generate_km, tags)
        except ValueError:
            if not tags:
                raise
            generated_candidates = None   # 고른 풍경 쪽으로는 차도를 피해 갈 길이 없다 (수원 광교 호수 3km)
        if tags and req.extend_for_scenery and not filter_by_required_tags(generated_candidates or [], user):
            longer, longer_km = _extend_for_scenery(generate, generate_km, tags, user)
            if longer:
                generated_candidates, deliver_km = longer, longer_km
                notice = f"{_wanted_label(tags)}까지 가려고 요청보다 {longer_km - generate_km:.1f}km 길게 만들었어요."
        if generated_candidates is None:
            # 코스는 반드시 준다 — 풍경 없이라도. 늘릴지는 사용자가 정한다
            generated_candidates, plain = generate(generate_km, set()), True
            label = _wanted_label(tags)
            if req.extend_for_scenery:
                notice = f"거리를 늘려도 {label}까지 인도로만 갈 수 있는 코스를 찾지 못해, 풍경 없이 만든 코스예요."
            else:
                notice = f"이 거리로는 {label}까지 인도로만 갈 수 있는 코스가 없어, 풍경 없이 만든 코스예요."
                choice = _extend_choice(label)
    except ValueError as e:
        candidates = [c for c in candidates if _distance_fits(c, target_km, req.route_type)]
        if candidates:
            # 실시간 외부 API가 일시적으로 실패하면 기존 DB 추천은 계속 제공한다 (거리가 맞는 것만).
            ranked = recommend(candidates, user, top_n=req.top_n, weights=weights)
            return {
                "results": [
                    {
                        "course": trim_if_needed(
                            apply_route_type(
                                attach_actual_return_path(originals[c["id"]]), req.route_type
                            )
                        ),
                        "score": round(s, 4),
                    }
                    for c, s in ranked
                ],
                "source": "db",
            }
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        candidates = [c for c in candidates if _distance_fits(c, target_km, req.route_type)]
        if candidates:
            ranked = recommend(candidates, user, top_n=req.top_n, weights=weights)
            return {
                "results": [
                    {
                        "course": trim_if_needed(
                            apply_route_type(
                                attach_actual_return_path(originals[c["id"]]), req.route_type
                            )
                        ),
                        "score": round(s, 4),
                    }
                    for c, s in ranked
                ],
                "source": "db",
            }
        # 키 미설정으로 코스 생성이 불가능한 상태. 500으로 삼키면 받는 쪽이 원인을 알 수 없다.
        raise HTTPException(
            status_code=503,
            detail=f"{e} .env.example을 .env로 복사해 키를 채운 뒤 서버를 다시 시작하세요.",
        )

    for course in generated_candidates:
        # 요청한 풍경이 아니어도 만든 코스는 저장해 둔다 — 다음에 조건이 맞는 요청에서 다시 쓴다
        background_tasks.add_task(register_in_background, course)
    if req.route_type != "loop":
        # 생성기는 편도 경로를 준다. 왕복이면 실제 복귀 경로를 붙여 왕복 거리로 점수를 매긴다
        generated_candidates = [
            apply_route_type(attach_actual_return_path(c) if req.route_type == "roundtrip" else c, req.route_type)
            for c in generated_candidates
        ]
    ranked = recommend(
        generated_candidates,
        dict(user, environment_tags=[]) if plain else user,
        top_n=req.top_n,
        weights=weights,
    )
    if not ranked and generated_candidates:
        # 만들긴 했지만 고른 풍경을 기준만큼 지나는 코스가 없다(밤에는 인적 드문 강변·공원 길을 피해서 더 그렇다).
        # 코스는 반드시 준다 — 그 풍경을 가장 많이 지나는 것부터, 그렇다고 알리며.
        ranked = recommend(generated_candidates, dict(user, environment_tags=[]), top_n=req.top_n,
                           weights=weights)
        ranked.sort(key=lambda pair: _scenery_reach(pair[0], tags), reverse=True)
        label = _wanted_label(tags)
        if route_night:
            notice = f"밤이라 인적 드문 길을 피했더니 {label}을(를) 충분히 지나지 못했어요."
            choice = {"question": f"{label} 쪽 길은 밤에 인적이 드물어 위험할 수 있어요. 그래도 그 길로 갈까요?",
                      "options": [{"label": f"그래도 {label} 길로", "set": {"allow_secluded_at_night": True}},
                                  {"label": "안전한 지금 코스로", "set": {}}]}
        else:
            notice = f"이 주변에서는 {label}을(를) 충분히 지나는 코스를 만들지 못해, 가장 많이 지나는 코스를 드려요."
            if not req.extend_for_scenery:
                choice = _extend_choice(label)
    if not ranked:
        raise HTTPException(status_code=404, detail="이 주변에서는 코스를 만들지 못했습니다. 다른 거리나 코스 형태로 시도해 보세요.")
    results = [{"course": trim_if_needed(course), "score": round(score, 4)} for course, score in ranked]

    def resize(km: float):
        """같은 조건으로 크기만 바꿔 다시 짠다 (Tmap으로 이은 거리가 요청과 달랐을 때)."""
        try:
            made = generate(km, set() if plain else tags)
        except ValueError:
            return None
        if req.route_type != "loop":
            made = [apply_route_type(attach_actual_return_path(c) if req.route_type == "roundtrip" else c,
                                     req.route_type) for c in made]
        wanted = dict(user, preferred_distance_km=km, preferred_time_min=None,
                      environment_tags=[] if plain else user["environment_tags"])
        best = recommend(made, wanted, top_n=1, weights=weights)
        return best[0][0] if best else (made[0] if made else None)

    # 1등 코스는 실제로 달릴 Tmap 경로로 바꿔 준다 — 화면에 보이는 거리가 곧 실제로 달릴 거리다
    results[0]["course"] = _deliver_on_tmap(results[0]["course"], deliver_km, req.route_type, resize)
    return {
        "results": results,
        "source": "generated",
        "notice": notice,
        "choice": choice,
    }


def _distance_fits(course: dict, target_km, route_type: str) -> bool:
    """저장된 코스가 요청 거리에 맞나. 편도·왕복은 길면 잘라서 주므로 짧지만 않으면 되고, 순환은 자를 수 없다."""
    if not target_km:
        return True
    km = course.get("distance_km") or 0
    if route_type == "loop":
        return abs(km - target_km) <= target_km * DISTANCE_OK
    return km >= target_km * (1 - DISTANCE_OK)


SCENERY_EXTEND = (1.4, 1.8, 2.3, 3.0)   # 풍경까지 닿을 때까지 요청 거리의 이 배수로 늘려 본다


def _extend_for_scenery(generate, km: float, tags, user: dict):
    """고른 풍경을 지나는 가장 짧은 순환. (후보, 거리) 또는 (None, None)."""
    for mult in SCENERY_EXTEND:
        try:
            made = generate(km * mult, tags)
        except ValueError:
            continue
        if filter_by_required_tags(made, user):
            return made, km * mult
    return None, None


def _extend_choice(label: str) -> dict:
    return {"question": f"요청한 거리로는 {label}까지 가기 어려워요. 거리를 늘려서 {label}까지 갈까요?",
            "options": [{"label": f"거리를 늘려 {label}까지", "set": {"extend_for_scenery": True}},
                        {"label": "지금 코스로", "set": {}}]}


def _wanted_label(tags) -> str:
    return ", ".join(scenery_choices.labels_for(tags)) or ", ".join(sorted(tags)) or "고른 풍경"


def _scenery_reach(course: dict, tags) -> float:
    """고른 풍경을 기준 대비 얼마나 지나는지 (1이면 기준을 채움)."""
    measured = course.get("scenery") or {}
    return max((measured.get(SCENERY_THRESHOLDS[t][0], 0) / SCENERY_THRESHOLDS[t][1]
                for t in tags if t in SCENERY_THRESHOLDS), default=0.0)
