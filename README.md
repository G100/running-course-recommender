# 러닝 코스 추천 앱 — 모델/데이터 파트

## 우선순위 (진행 순서)

1. ✅ **코스 후보 데이터 스키마 + DB 뼈대** — [data/courses_schema.md](data/courses_schema.md)
2. ✅ **키 불필요 데이터부터 자동 수집** — OSM Overpass API로 신호등/녹지/해안선 태깅 ([src/data_collection/osm_overpass.py](src/data_collection/osm_overpass.py)), 코스 경로에 자동 매칭 ([src/data_collection/enrich.py](src/data_collection/enrich.py)), 등재 CLI ([src/data_collection/add_course.py](src/data_collection/add_course.py))
3. ✅ **추천 스코어링 로직** — 규칙 기반 가중치 매칭 ([src/recommend/score.py](src/recommend/score.py))
4. ✅ **자연어 키워드 매칭** — 문장형 입력 → 환경태그 ([src/recommend/nl_keywords.py](src/recommend/nl_keywords.py))
5. ✅ **추천 API 스켈레톤** — Android 팀 연동용 FastAPI (`POST /recommend`) ([src/api/main.py](src/api/main.py))
6. ✅ **카카오 Directions API** — 실제 키로 검증 완료했으나 자동차 도로 기준이라 러닝 코스 생성에는 더 이상 안 씀 (7번 참고). 지도 표시/앱 UI용으로는 계속 사용 가능 ([src/api_clients/kakao_map.py](src/api_clients/kakao_map.py))
7. ✅ **고도(표고) API** — VWorld(포인트조회 REST 없음) → OpenTopography(무료 등급 하루 50건이라 개발 중 바로 소진됨) → **Open Topo Data로 최종 정착** (키 불필요, 배치조회, 하루 1000건) ([src/api_clients/elevation.py](src/api_clients/elevation.py))
7-1. ✅ **Tmap 보행자 경로 API** — 러닝은 인도 기준이어야 해서 카카오(자동차 도로) 대신 교체. 무료체험 등급 하루 1,000건 ([src/api_clients/tmap_pedestrian.py](src/api_clients/tmap_pedestrian.py)). 참고: 카카오도 도보 길찾기가 있지만 제휴 신청·승인이 필요해 병행 신청만 해둔 상태
8. ✅ **코스 후보 실데이터 15개 등록 + 완전 자동화 파이프라인** — 랜드마크 이름 두 개만 주면 좌표조회(Nominatim)→실제 인도 경로(Tmap)→고도(Open Topo Data)→OSM태그까지 전부 자동 ([src/data_collection/build_courses_from_landmarks.py](src/data_collection/build_courses_from_landmarks.py) → [data/courses.json](data/courses.json)). 목표 30개 중 15개 완료, 계속 진행 중 ([data/candidate_courses_todo.md](data/candidate_courses_todo.md))
9. ✅ **기상청 단기예보 API** — 위경도→격자 자동변환 포함, 실제 키로 검증 완료 ([src/api_clients/kma_weather.py](src/api_clients/kma_weather.py))
10. ✅ **에어코리아 대기질 API** — 실제 키로 검증 완료, 측정소명 매핑 문서화 ([src/api_clients/airkorea.py](src/api_clients/airkorea.py), [data/air_quality_stations.md](data/air_quality_stations.md))
11. ✅ **실시간 날씨/대기질을 추천 점수에 반영** — MVP 스코프에 명시된 기능이었는데 API만 만들고 실제로 안 붙어있던 걸 연결함 ([src/recommend/environment.py](src/recommend/environment.py), `/recommend`에 `use_live_environment` 옵션으로 노출)
12. 🔲 **공공데이터 치안시설/CCTV API** — 안전점수(`safety_score`) 계산용, 키 발급 대기 중 (지금은 모든 코스 0.75 고정값)
13. ✅ **현위치 기반 하이브리드 추천** — DB에 근처(기본 5km) 코스가 있으면 즉시 반환, 없으면 그 자리에서 실제 도로/지형 데이터로 코스를 생성해 반환하고 백그라운드로 정밀 보강해 DB에 편입 (다음 요청부터는 빨라짐) ([src/recommend/generate_live.py](src/recommend/generate_live.py), [src/recommend/location.py](src/recommend/location.py))
14. ✅ **선호 태그는 필수 조건으로 처리** — "바다뷰"를 골랐는데 내륙 코스가 점수로 끼어드는 문제 수정. `environment_tags`가 있으면 하나도 안 겹치는 코스는 결과에서 완전히 제외 ([src/recommend/score.py](src/recommend/score.py) `filter_by_required_tags`)
15. ✅ **선호 거리보다 긴 코스는 잘라서 반환** — "5km 달리고 싶다"인데 8km 코스를 그대로 주지 않고, 목표 거리만큼 경로를 잘라서(중간에 돌아오면 되니까) 정확히 원하는 길이로 응답 ([src/recommend/trim.py](src/recommend/trim.py))
16. ✅ **실제 지도 + 실시간 백엔드 연동 페이지** — `/`에서 실제 서버에 매 요청을 보내고 실제 지도 위에 실제 경로를 그리는, 진짜 동작하는 내비게이션 스타일 데모. 지도는 카카오맵 JS SDK → (반복 요청으로 "API limit has been exceeded" 일시 차단) → OpenStreetMap+Leaflet(임시) → **Tmap 자체 지도 SDK(`Tmapv2.Map`)로 최종 정착** — 이미 갖고 있던 TMAP_APP_KEY로 바로 되고, 경로·턴바이턴과 같은 소스(Tmap)라 일관성도 있음 ([src/api/static/navigate.html](src/api/static/navigate.html))
17. ✅ **왕복/편도 선택** — `route_type: "roundtrip" | "oneway"`. 왕복은 갈 때·올 때 둘 다 실제 Tmap을 불러 진짜 왕복 경로+턴바이턴을 만든다(좌표 미러링이 아님) ([src/recommend/route_type.py](src/recommend/route_type.py))
18. ✅ **실제 턴바이턴 안내** — Tmap 응답에 이미 "우회전 후 오동도로를 따라 213m 이동" 같은 한국어 안내가 들어있어서 그대로 사용. 직접 좌/우회전 판정 로직을 만들 필요가 없었음 ([src/api_clients/tmap_pedestrian.py](src/api_clients/tmap_pedestrian.py) `extract_steps`, 데모 페이지에서 진행률에 맞춰 실시간 표시)
19. ✅ **도보 전용 내비게이션 UI** — 폰 화면 프레임 안에 실제 내비 앱처럼 대형 안내 배너(화살표+거리+장소명)·하단 상태바(도착예정시각·남은거리)를 구현. 자동차 내비와 구분되도록 사람 아이콘 마커 + "🚶 도보" 배지 사용
20. ✅ **실제 GPS 기반 내비게이션** — "네비게이션 API를 따로 가져올 수 없나"라는 질문에 대한 답: 실시간 내비게이션은 별도 API가 아니라 (경로 API 1회 호출 + 기기 GPS를 경로에 매칭하는 클라이언트 로직)의 조합이고, 이미 그 매칭 로직(`locateStepsOnPath`/`updateTurnBanner`)을 갖고 있었으므로 가짜 애니메이션 대신 진짜 위치를 흘려보내면 됐음. `navigator.geolocation.watchPosition`으로 실제 위치를 받아 경로에 매칭 — 폰에서 실제로 걸으면 실제로 안내됨. GPS 권한이 없거나 응답이 없으면(데스크톱 등) 자동으로 시뮬레이션 재생으로 폴백 ([src/api/static/navigate.html](src/api/static/navigate.html) `startNavigationGPS`)
21. ✅ **GitHub 공유 전 정리** — 데모 페이지에 하드코딩돼 있던 Tmap JS 키를 제거하고 서버가 요청마다 환경변수에서 주입하도록 변경(`{{TMAP_APP_KEY}}` 플레이스홀더, [src/api/main.py](src/api/main.py) `navigate_page`), `.gitignore`/`.env.example` 추가, 테스트 중 생성된 임시 파일 정리, 독립 저장소로 분리
22. ✅ **키 없는 환경에서도 원인을 알 수 있게** — 팀원들이 clone 후 "API가 안 된다"고 한 문제. 원인은 키 미설정이었지만, 지도는 조용히 빈 화면(`Tmapv2 is not defined`)이 되고 코스 생성은 `500 Internal Server Error`로 끝나서 원인을 알 수 없었다. `.env` 자동 로드(python-dotenv) 추가, 서버 시작 시 누락된 키와 그로 인해 안 되는 기능 출력, `/health`가 키 설정 여부 보고(값은 비노출), 키 누락 시 `500` 대신 안내가 담긴 `503`, 데모 페이지 상단에 안내 배너 ([tests/test_missing_keys.py](tests/test_missing_keys.py))
23. ✅ **등재된 코스 22개 전부에 턴바이턴 안내 채움** — 감사해보니 DB 코스 **22개 전부 `steps`가 비어 있었다**. 초기 코스들이 턴바이턴 기능 추가 이전에 등재된 탓인데, 여수·광주에서 추천받으면 전부 DB 코스라 **실사용에서는 내비게이션 안내가 아예 안 뜨는 상태**였다(지도에 경로는 그려져서 눈에 띄지 않았음). 저장된 시작·끝 좌표로 Tmap 경로를 다시 받아 채웠고, 재경로가 저장된 경로와 2% 넘게 다르면 코스가 바뀌는 것이므로 덮어쓰지 않고 건너뛴다 ([src/data_collection/backfill_steps.py](src/data_collection/backfill_steps.py)). 22개 전부 경로가 일치해 그대로 반영됨. 같은 종류의 구멍을 다시 놓치지 않도록 DB 무결성 테스트 추가 ([tests/test_course_db.py](tests/test_course_db.py)) — steps 존재, 안내 지점이 경로에서 50m 이내, route_type 선언 여부를 검사한다
24. ✅ **온보딩에서 물어본 걸 실제로 추천에 반영** — `fitness_level`·`purpose`·`preferred_time_min`을 받아만 놓고 `score.py`에서 **한 번도 쓰지 않고** 있었다(사용 0회). 체력을 물어보고 무시했으니 입문자와 상급자에게 같은 코스가 나가던 셈. 세 가지를 연결함 ([src/recommend/profile.py](src/recommend/profile.py)):
    - **페이스**: 아는 사람은 `pace_min_per_km`로 직접 입력, 모르면 `experience_level`(beginner/intermediate/advanced)로 추정
    - **시간 → 거리 환산**: "30분 뛸래"가 이제 동작한다. 같은 30분이 입문자 3.75km / 중급 4.84km / 상급 6.0km로 환산됨
    - **목적 → 고도 목표 + 가중치 조정**: 체중 감량은 완만하게(중간에 걸으면 지속이 안 되므로), 체력 기르기는 오르막 환영, 기록 단축은 신호등을 강하게 회피(끊기면 기록이 안 나옴). 실제로 1순위 코스의 고도가 27m↔82m로 갈린다
    - 목적 항목은 숙련도마다 다르다(입문자에게 "인터벌 훈련"을 물어볼 수 없으므로). 앱이 문항을 하드코딩하지 않도록 `GET /onboarding/purposes?experience_level=` 로 서버가 내려준다
    - `fitness_level`(아무 역할도 없던 필드)은 `pace_min_per_km` + `experience_level`로 대체됨 — **안드로이드 팀 온보딩 연동 시 참고**

## 현위치 기반 추천 흐름

```
POST /recommend { current_lat, current_lng, preferred_distance_km, environment_tags, ... }
  -> 반경 max_distance_km(기본 5km) 안에 DB 코스 있음 -> 그걸로 즉시 추천 (source: "db", 수십ms)
  -> 없음 -> 그 자리에서 실제 Tmap 보행자 경로 + OSM 지형으로 왕복 코스 생성 (source: "generated", ~10초)
             -> 백그라운드로 정밀 보강 후 DB에 저장 -> 다음부터 그 동네는 "db" 경로로 즉시 응답
```
현위치를 안 보내면 기존처럼 DB 전체에서 조건 매칭만 수행 (하위호환).

왜 완전한 순환 루프 대신 왕복(out-and-back)인가: Tmap 보행자 경로 API는 A→B 경로만 계산하고 "여기서
N km 루프"는 지원하지 않는다. 왕복은 목표 거리를 정확히 맞추면서 실제 보행 경로를 그대로 쓸 수 있는
가장 단순하고 신뢰할 수 있는 방법이라 MVP로 선택했다. 완전한 루프(경유지 체이닝)는 추후 확장 가능.

## 왜 코사인 유사도 대신 가중치 스코어링인가

사용자 조건 벡터 `[체력수준, 목적, 거리, 시간, 고도선호, 환경태그]`와 코스 벡터
`[거리, 고도, 안전점수, 신호등수, 녹지비율, 해안근접도, 노면상태]`는 축이 1:1로 대응하지 않는다.
raw 코사인 유사도를 적용하면 스케일이 다른 축(거리 km vs 신호등 개수 vs 비율 0~1)이 왜곡되므로,
축마다 정규화된 매칭 점수를 계산한 뒤 가중합하는 방식을 채택했다 (`src/recommend/score.py`).

## 팀원용 설치 (처음 clone 했다면 여기부터)

```bash
git clone https://github.com/G100/running-course-recommender.git
cd running-course-recommender
pip install -r requirements.txt
copy .env.example .env      # macOS/Linux: cp .env.example .env
```

그 다음 `.env` 파일을 열어 API 키를 채운다. **키는 저장소에 올라가 있지 않다**(공개 저장소라 올리면 안 됨).
팀 내에서 공유받은 키를 붙여넣거나 각자 발급받으면 된다 — 발급처는 [.env.example](.env.example)에 적혀 있다.

```bash
uvicorn src.api.main:app --reload    # http://localhost:8000
```

키가 빠져 있으면 서버 시작 시 무엇이 안 되는지 콘솔에 표시되고, `http://localhost:8000/health` 에서도
어떤 키가 설정됐는지 확인할 수 있다 (키 값 자체는 노출되지 않음).

### 안 될 때

| 증상 | 원인 | 해결 |
|---|---|---|
| 지도 자리가 비어 있음, 콘솔에 `Tmapv2 is not defined` | `TMAP_APP_KEY` 없음 | `.env`에 키 입력 후 서버 재시작 |
| 코스 추천 시 `503` + "TMAP_APP_KEY 환경변수가..." | 〃 | 〃 |
| 코스는 나오는데 날씨/대기질이 반영 안 됨 | `KMA_API_KEY` / `AIRKOREA_API_KEY` 없음 | `.env`에 키 입력 (없어도 추천 자체는 동작) |
| `ModuleNotFoundError: dotenv` | 의존성 미설치 | `pip install -r requirements.txt` 다시 실행 |
| `.env`를 채웠는데도 그대로 | 서버가 이전 상태로 떠 있음 | 서버 종료 후 재시작 (`.env`는 시작 시 1회만 읽음) |

DB에 저장된 22개 코스 추천은 **키가 하나도 없어도 동작한다**. 키가 필요한 건 지도 표시,
현위치 기반 코스 생성, 턴바이턴 안내, 실시간 날씨/대기질이다.

## 실행

```bash
pip install -r requirements.txt
python -m src.data_collection.osm_overpass --bbox 34.73,127.65,34.78,127.75 --out data/osm_features.json
python -m src.data_collection.add_course --input 새코스.json --db data/courses.json
python -m src.data_collection.build_courses_from_landmarks --id my-course --name "코스이름" --region 여수 --start "시작 랜드마크" --end "끝 랜드마크"
uvicorn src.api.main:app --reload   # http://localhost:8000 → 실제 Tmap 지도 데모, POST /recommend
pytest tests/
```

API 키는 프로젝트 루트의 `.env`에서 자동으로 읽는다 (`TMAP_APP_KEY`, `KMA_API_KEY`, `AIRKOREA_API_KEY`).
Open Topo Data와 Nominatim은 키가 필요 없다. `.env`는 `.gitignore` 대상이라 커밋되지 않는다 — 실제 키는 절대 커밋하지 말 것.

## 디렉토리

```
data/                코스 후보 DB(JSON), 스키마 문서
src/data_collection/ 외부 데이터 수집 스크립트
src/recommend/       벡터화 + 스코어링 + 자연어 키워드 매칭
src/api_clients/     키가 필요한 외부 API 클라이언트 (스텁)
tests/                단위 테스트
```
