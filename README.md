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
12. ✅ **종합 치안 점수** — 30번 참고 (모든 코스 0.75 고정값이던 문제 해결)
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
25. ✅ **신호등 점수를 총 개수 대신 km당 밀도로** — `1/(1+총개수)` 라서 9km 코스(신호등 30개)가 2km 코스(0개)보다 무조건 불리했다. 게다가 개수가 10개만 넘어가면 점수가 0.52 근처로 포화돼서, 가중치 20%가 실제로는 코스를 거의 구분하지 못했다. 밀도 기준으로 바꾸니 도심 코스들이 0.516~0.536(사실상 동점)에서 0.588~0.651로 벌어져 실제 순위가 생긴다. 달리면서 체감하는 건 총 몇 번 멈췄느냐가 아니라 얼마나 자주 멈추느냐다
26. ✅ **캐시된 경로가 낡지 않게 (stale-while-revalidate)** — 실시간 생성 결과를 DB에 쌓으면 같은 동네 요청이 즉시 처리되는 대신, 공사나 도로 변경이 있어도 예전 경로를 계속 안내하게 된다. 그렇다고 요청 때마다 확인하면 실시간 생성과 다를 게 없다. 그래서 **저장된 경로로 즉시 응답하고, 오래된 코스는 뒤에서 다시 받아 갱신한다** — 기다리는 사람은 없고 다음 요청부터 최신 경로가 나간다 ([src/recommend/freshness.py](src/recommend/freshness.py), [src/data_collection/refresh_route.py](src/data_collection/refresh_route.py)). 한 요청이 Tmap 할당량을 몰아 쓰지 않도록 **한 번에 한 개씩만** 갱신하며(응답시간 30~57ms 유지 확인), 거리가 2% 넘게 달라지면 길이 실제로 바뀐 것이므로 새 경로를 받아들이고 `previous_distance_km`에 이전 값을 남겨 추적할 수 있게 한다
27. ✅ **왕복이면 돌아오는 길도 진짜 턴바이턴으로** — 왕복을 고르면 갈 때만 안내가 나오고 복귀 구간은 "반환점 — 왔던 길로 돌아갑니다" 한 줄이 전부였다. 좌표를 뒤집어 안내를 만들 수는 없다 — 일방통행·횡단보도 때문에 갈 때와 올 때 실제 안내가 다르다("우측 횡단보도 후..."는 반대 방향엔 없는 안내다). 그래서 코스마다 B→A 경로를 따로 받아 `return_path`/`return_steps`로 저장하고 왕복 조립 시 사용한다. 7km 왕복 기준 안내가 16개 → **28개(갈 때 16 + 올 때 12)**로 늘었다.
    - 부수적으로 드러난 문제: 안내 위치를 "경로에서 가장 가까운 점"으로 찾고 있었는데, 왕복은 갈 때와 올 때 좌표가 같아서 복귀 안내가 갈 때 구간으로 끌려가 절반쯤 달렸을 때 "도착"이 뜨는 구조였다. 코스를 만들 때 순방향으로 위치를 확정해 `cum_m`으로 저장하고, 자르기·화면 표시가 같은 값을 쓰도록 통일 ([src/recommend/step_position.py](src/recommend/step_position.py))

28. ✅ **사용자 맞춤 선택지 확장 — 시간대(자동)·동반자 7종** — 선택지를 늘리기 전에 데이터를 먼저 확인했다. 코스가 22개뿐이라 **필터를 늘리면 "조건에 맞는 코스 없음"만 늘어난다**(이미 10km 이상 0개, `도심` 태그 1개, `숲길`은 20/22라 골라도 필터가 안 됨). 그래서 카탈로그를 거르는 선택지 대신 **점수를 바꾸는 선택지**를 넣었다.
    - **시간대는 묻지 않고 요청 시각으로 판단한다** ([src/recommend/timeofday.py](src/recommend/timeofday.py)). `safety_score`가 전 코스 0.75 고정이라 안전 점수로는 밤낮을 구분할 수 없어서, 실제로 코스마다 다른 녹지비율·신호등밀도를 쓴다 — 녹지비율이 높으면 낮에는 그늘이지만 밤에는 인적이 드물다는 뜻이므로 야간엔 감점하고 사람 다니는 길을 우대한다
    - **동반자 7종**: 혼자/소형견/중대형견/유아차/어린이/러닝크루/어르신 ([src/recommend/companion.py](src/recommend/companion.py)). 가중치 조정에 더해 **거리·고도 상한**을 건다 — 유아차에 200m 오르막은 "덜 어울리는 정도"가 아니라 불가능한 코스라 점수가 아니라 제외로 다뤄야 한다
    - 노면(흙길/트레일)은 **일부러 넣지 않았다**: 22개 전부 `paved`라 선택지를 만들어도 전부 같은 값이다. 트레일 코스를 먼저 수집해야 의미가 생긴다
29. ✅ **진짜 내비게이션 화면 — 3D·진행방향 회전·음성 안내** — "지도에 경로만 나오고 화살표만 움직이는 느낌"이라는 지적. 확인해보니 **Tmap 웹 SDK는 V2가 최신이고 2D 래스터뿐**이라(공식·스테이징 문서 모두 확인) 기울기·3D 건물·회전을 만들 수 없었다 — 네이버·카카오·티맵 앱에서 보는 3D는 네이티브 모바일 SDK 기능이다. 지도 렌더링만 **MapLibre GL JS + OpenFreeMap**(키 불필요·무료·무제한)으로 교체해 해결했다. **경로와 턴바이턴 안내는 계속 Tmap 응답을 쓴다 — 그림만 바뀌고 안내 데이터는 그대로다.**
    - 3D 건물(한국 커버리지 실측: 광주 도심은 실제 높이 반영, 여수 같은 소도시는 높이 데이터가 없어 균일 저층), 카메라 pitch 62°
    - **진행 방향이 화면 위를 향하도록 지도 회전**(heading-up). 북쪽 고정이면 "좌회전"이 화면에선 오른쪽으로 보이는 일이 생긴다. 주행 중 회전각이 -86°→-33°→17°→-146°로 실제로 따라가는 것 확인
    - **음성 안내**(브라우저 내장 음성합성, 키 불필요). 달리면서는 화면을 볼 수 없으므로 음성이 없으면 안내가 있어도 못 듣는 것과 같다. 안내당 두 번만 읽는다 — 멀리서 예고 한 번, 코앞에서 실행 한 번
    - 트레이드오프: 지도 라벨·POI가 OSM 기반이라 Tmap보다 상호 정보가 덜 촘촘하다. 대신 **지도 표시에 API 키가 아예 필요 없어져** 팀원 세팅이 더 쉬워졌다

30. ✅ **종합 치안 점수 — `safety_score`가 드디어 코스를 구분한다** — 26개 코스 전부 `0.75` 고정값이라 스코어링의 안전 가중치(13~15%)가 **아무 코스도 구분하지 못한 채** 돌아가고 있었다. CCTV 하나로 치안을 대표할 수 없어서 세 축으로 나눠 합쳤다 ([src/recommend/safety.py](src/recommend/safety.py)):
    - **감시 장비** (CCTV 밀도) · **밤에도 사람이 다니는가** (편의점 밀도 — 24시간 영업이라 야간 유동인구의 대리 지표) · **도움을 청할 곳이 가까운가** (지구대·파출소까지 거리)
    - 결과: 전부 0.75였던 값이 **0.264~1.0으로 분포**한다. 만점 기준은 임의로 정하지 않고 실제 26개 코스의 밀도 분포 상위 10% 지점에 맞췄다 — 처음 잡은 기준(CCTV 2/km)으로는 도심 코스 5개가 전부 만점으로 뭉쳐 서로 구분되지 않았다
    - 코스마다 따로 조회하면 Overpass 속도 제한에 걸리므로 **지역별로 한 번에 받아 로컬에서 계산**한다(26개 코스에 질의 2회) ([src/data_collection/backfill_safety.py](src/data_collection/backfill_safety.py))
    - **남은 한계 (솔직히)**: 가로등은 OSM에 한국 데이터가 사실상 없어(광주 전역 0개) 빠져 있고, CCTV도 지자체 공식 데이터가 아닌 OSM 수집분이라 실제보다 적게 잡힌다. 공공데이터포털 키는 **데이터셋마다 따로 활용신청**해야 해서(에어코리아 키로 다른 데이터셋 호출 시 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR` 확인) 가로등·공식 CCTV 데이터셋을 신청하면 같은 구조에 소스만 추가하면 된다
31. ✅ **왕복을 자르면 출발점으로 돌아오지 못하던 문제** — 기본값이 왕복인데, 7km 왕복을 3km로 요청하면 반환점 근처에서 잘려 **집에서 2.45km 떨어진 곳에 남겨졌다**. 목표 거리에서 그냥 끊는 대신 **반환점을 절반 지점으로 당기고** 거기서 가장 가까운 복귀 경로 지점부터 이어 붙인다. 실제 코스 전부에서 종료 지점이 출발점으로부터 **0m**가 되는 것을 확인했다 ([src/recommend/trim.py](src/recommend/trim.py) `_truncate_roundtrip`)
32. ✅ **장거리 코스 보강 (22개 → 26개)** — 앞서 "10km 이상 후보 0개"라고 적었던 건 **편도 기준만 본 것**이라 정정한다(왕복 감안 시 13개였음). 실제 구멍은 편도 10km 이상 0개, 왕복 15km 이상 1개였다. 장거리 4개를 추가해 편도 10km↑ 2개, 왕복 15km↑ 5개, 20km↑ 2개, 25km↑ 1개가 됐다

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

키가 빠져 있으면 서버 시작 시 무엇이 안 되는지 콘솔에 표시되고, `http://localhost:8000/health` 에서도 어떤 키가 설정됐는지 확인할 수 있다 (키 값 자체는 노출되지 않음). 참고: **지도 표시에는 API 키가 필요 없다** — 지도는 OpenFreeMap(OSM)을 쓰고, Tmap 키는 경로·안내 데이터에만 쓰인다.
어떤 키가 설정됐는지 확인할 수 있다 (키 값 자체는 노출되지 않음).

### 안 될 때

| 증상 | 원인 | 해결 |
|---|---|---|
| 현위치 기반 코스 생성이 `503` | `TMAP_APP_KEY` 없음 | `.env`에 키 입력 후 서버 재시작 (지도 표시는 키 없이도 됨) |
| 코스는 나오는데 날씨/대기질이 반영 안 됨 | `KMA_API_KEY` / `AIRKOREA_API_KEY` 없음 | `.env`에 키 입력 (없어도 추천 자체는 동작) |
| `ModuleNotFoundError: dotenv` | 의존성 미설치 | `pip install -r requirements.txt` 다시 실행 |
| `.env`를 채웠는데도 그대로 | 서버가 이전 상태로 떠 있음 | 서버 종료 후 재시작 (`.env`는 시작 시 1회만 읽음) |

DB에 저장된 26개 코스 추천은 **키가 하나도 없어도 동작한다**. 키가 필요한 건 지도 표시,
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
