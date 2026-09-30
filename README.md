# 러닝 코스 추천 — 추천 모델 · 데이터 · API

사용자 조건(거리·시간·페이스·목적·동반자)과 현위치로 러닝 코스를 추천하고, 실제 보행 경로와 턴바이턴 안내를 내려주는 FastAPI 서버.

## 빠른 시작

**Python 3.10 이상 필요** (3.10 ~ 3.14, 아나콘다 3.11에서 확인). `python --version`으로 먼저 확인하세요.

```bash
git clone https://github.com/G100/running-course-recommender.git
cd running-course-recommender
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env             # macOS/Linux, Git Bash: cp .env.example .env
python -m uvicorn src.api.main:app --reload
```

- 데모 화면: http://localhost:8000
- API 문서(직접 호출 가능): http://localhost:8000/docs
- 테스트: `python -m pytest`

> `git pull` 후에는 항상 `pip install -r requirements.txt`를 다시 실행하세요. 의존성 버전이 고정돼 있습니다.

## API 키

`.env`에 입력합니다. 키는 저장소에 없으며, 커밋하면 안 됩니다(`.env`는 `.gitignore` 대상).

| 키 | 용도 | 없으면 |
|---|---|---|
| `TMAP_APP_KEY` | DB에 없는 지역의 실시간 코스 생성 | 해당 요청만 `503` |
| `KMA_API_KEY` | 실시간 날씨 반영 | 날씨 미반영 |

지도 표시, DB 코스 추천, 턴바이턴 안내는 **키 없이 동작**합니다. 설정 상태는 `/health`에서 확인할 수 있습니다(값은 노출 안 됨).

## API

| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/recommend` | 코스 추천 |
| `GET` | `/onboarding/purposes?experience_level=beginner` | 숙련도별 목적 선택지 |
| `GET` | `/onboarding/companions` | 동반자 선택지 |
| `GET` | `/health` | 서버·키 상태 |

### `POST /recommend` 요청

모든 필드는 선택입니다.

| 필드 | 값 | 설명 |
|---|---|---|
| `preferred_distance_km` | 숫자 | 목표 거리 |
| `preferred_time_min` | 숫자 | 거리 대신 시간으로 지정 (페이스로 환산) |
| `pace_min_per_km` | 숫자 | 평소 페이스(분/km). 모르면 생략 |
| `experience_level` | `beginner` `intermediate` `advanced` | 페이스를 모를 때 추정에 사용 |
| `purpose` | `/onboarding/purposes` 값 | 고도 목표·가중치 조정 |
| `companion` | `/onboarding/companions` 값 | 가중치 조정 + 거리·고도 상한. 목록에 없는 값은 `422` |
| `environment_tags` | `바다뷰` `숲길` `차없는길` | 고르면 필수 조건 |
| `text` | 문장 | 자연어에서 태그 추출 (예: "바다 보이는 코스") |
| `elevation_preference` | `low` `medium` `high` | 목적이 없을 때 고도 기준 |
| `route_type` | `roundtrip`(기본) `loop` `oneway` | 왕복(갔던 길로 되돌아옴) / 순환(한 바퀴 돌아 제자리, 현위치 필요) / 편도 |
| `destination` | 장소 이름 | 목적지 지정 (예: "오동도, 여수"). 주면 추천 대신 그곳까지 경로를 만듦. 현위치 필요 |
| `destination_lat`, `destination_lng` | 좌표 | 장소 이름 대신 좌표로 목적지 지정 |
| `current_lat`, `current_lng` | 좌표 | 현위치. 반경 내 DB 코스가 없으면 실시간 생성 |
| `max_distance_km` | 숫자 (기본 5) | 현위치 기준 DB 코스 탐색 반경 |
| `time_of_day` | `morning` `afternoon` `evening` `night` | 생략하면 서버 시각으로 자동 판단 |
| `use_live_environment` | `true`(기본) / `false` | 실시간 날씨 반영 여부 |
| `top_n` | 숫자 (기본 5) | 결과 개수 |

### 응답

```jsonc
{
  "source": "db",                  // "db" | "generated"(실시간 생성) | "destination"(목적지 지정)
  "results": [{
    "score": 0.84,
    "course": {
      "name": "...", "distance_km": 5.0, "elevation_gain_m": 58, "safety_score": 0.88,
      "path": [[lat, lng], ...],     // 지도에 그릴 경로
      "steps": [{ "description": "우회전 후 오동도로를 따라 213m 이동",
                  "turn_type": 13, "cum_m": 812.4 }]   // cum_m: 출발점부터 이 안내까지 거리(m)
    }
  }]
}
```

턴바이턴은 현재 위치의 누적 거리가 `cum_m`에 가까워질 때 해당 `description`을 안내하면 됩니다.

## 추천 방식

규칙 기반 가중치 점수(학습 데이터 불필요). 항목: 거리, 고도, 안전, 신호등 밀도, 풍경 태그, 시간대, 날씨.

- **목적·동반자**에 따라 가중치를 조정하고, 동반자는 거리·고도 상한도 적용 (예: 유아차는 고도 40m 이하)
- **시간대**: 야간엔 인적 드문 길 감점, 한낮엔 그늘(녹지) 우대
- **안전 점수**: CCTV 밀도 + 편의점 밀도(야간 유동인구) + 지구대·파출소 거리
- **거리**: 긴 코스는 목표 거리로 잘라서 반환. 왕복은 반환점을 당겨 출발점으로 돌아옴
- **코스 형태는 세 가지**: 왕복은 저장된 편도 코스에 실제 복귀 경로를 붙이고, 편도는 그대로 쓴다. **순환**은 저장된 편도 코스를 되짚는 대신, 목표 거리로 가상 꼭짓점을 잡아 OSM 보행로에 스냅하고 Tmap 경유지로 **실제 순환 코스**를 만든다(자기 교차 검사 + 각도·반경을 바꿔 재시도). 한 번 만든 루프는 DB에 쌓이고, 같은 자리·같은 거리 요청이면 다시 만들지 않고 그걸 쓴다
- 왕복의 복귀 구간도 실제 경로·안내 사용 (좌표를 뒤집지 않음)

## 데이터

`data/courses.json` — 실제 코스 26개 (여수 14, 광주 12), 편도 2.4~13.2km.

```bash
# 코스 추가 (랜드마크 두 개만 주면 경로·고도·태그 자동 수집)
python -m src.data_collection.build_courses_from_landmarks --id my-course --name "코스이름" --region 여수 --start "오동도, 여수" --end "이순신광장, 여수"

# 추가한 코스에 턴바이턴·복귀 경로·안전 점수 채우기
python -m src.data_collection.backfill_steps
python -m src.data_collection.backfill_safety
```

## 구조

```
src/api/              FastAPI 서버, 데모 페이지(static/navigate.html)
src/recommend/        점수 계산, 프로필·동반자·시간대·안전, 코스 자르기
src/data_collection/  코스 수집·보강 스크립트
src/api_clients/      Tmap, 기상청, 고도 API
data/                 코스 DB와 스키마
tests/                테스트
```

## 코드 기여

```bash
git checkout -b 작업내용        # master에 직접 올리지 않기
python -m pytest               # 올리기 전 통과 확인
```

- **GitHub 웹 업로드("Add files via upload") 대신 git으로 올려주세요.** 웹 업로드는 `.gitignore`를 무시해서 `__pycache__` 같은 파일이 같이 커밋됩니다.
- 테스트는 임시 DB 사본에서 돌고 외부 API 호출은 차단됩니다([tests/conftest.py](tests/conftest.py)). 실제 `data/courses.json`이나 Tmap 할당량을 건드리지 않습니다. 외부 호출이 필요한 테스트는 해당 함수를 `monkeypatch` 하세요.
- 실행 중 생성된 `generated-*` 코스는 커밋하지 마세요. 테스트 부산물입니다.

## 최근 변경

- **순환 코스를 추가했습니다** (PR #1, zb0535). 가상 꼭짓점 → OSM 보행로 스냅 → Tmap 경유지. `route_type: "loop"`로 고르며, 왕복(`roundtrip`)과는 별개입니다.
- **목적지를 직접 고를 수 있습니다.** `destination`에 장소 이름을 주면 그곳까지(왕복이면 돌아오는 길까지) 실제 경로를 만듭니다.
- 만들어 둔 루프는 재사용합니다. 출발점이 600m 이내이고 목표 거리와 20% 이내로 맞으면 다시 만들지 않습니다(재요청 1초 이내, Tmap 호출 0건).
- 이미 닫힌 루프에 왕복 처리를 또 하던 문제를 고쳤습니다(6.8km 코스가 13.6km로 나가던 문제).
- 테스트 격리를 추가했습니다. 이전에는 테스트가 실제 코스 DB에 코스를 등재하고 Tmap 할당량을 소모했습니다.

## 문제 해결

| 증상 | 해결 |
|---|---|
| `pip install`에서 `No matching distribution` / `requires Python>=3.10` | 파이썬 3.10 이상 설치 후 가상환경을 다시 만들기 |
| `uvicorn`을 찾을 수 없음 | `python -m uvicorn ...`으로 실행 |
| `ModuleNotFoundError` 또는 테스트 수집 오류 | `pip install -r requirements.txt` 다시 실행 |
| 실시간 코스 생성이 `503` | `.env`에 `TMAP_APP_KEY` 입력 후 서버 재시작 |
| `.env`를 고쳤는데 반영 안 됨 | 서버 재시작 (`.env`는 시작할 때만 읽음) |
| 첫 화면에서 지도가 늦게 뜸 | 정상 — 지도 타일 첫 로딩에 10초 안팎 걸림 |
| 새 지역 첫 추천이 오래 걸림(10~30초) | 정상 — 그 자리에서 순환 코스를 만드는 중. 같은 자리 재요청은 1초 이내 |

## 알려진 한계

- 가로등 데이터 없음(OSM에 한국 데이터 부재). CCTV는 공식 데이터가 아닌 OSM 기준이라 실제보다 적게 잡힘
- Tmap 무료 등급 하루 1,000건 — 실시간 왕복 생성 1회에 2건 사용
- 데모 지도(MapLibre + OpenFreeMap)는 OSM 기반이라 상호 정보가 Tmap보다 적음. 경로·안내 데이터는 Tmap
