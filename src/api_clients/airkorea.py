"""에어코리아 대기질 Open API 클라이언트 (스텁 — API 키 필요).

키 발급: https://www.data.go.kr (에어코리아 대기오염정보)
발급 후 환경변수 AIRKOREA_API_KEY 설정. 실시간 추천 조정(미세먼지)에 사용.
"""
import os

import requests

AIR_QUALITY_URL = "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty"


def get_air_quality(station_name: str) -> dict:
    api_key = os.environ.get("AIRKOREA_API_KEY")
    if not api_key:
        raise RuntimeError("AIRKOREA_API_KEY 환경변수가 설정되지 않았습니다.")

    params = {
        "serviceKey": api_key,
        "stationName": station_name,
        "dataTerm": "DAILY",
        "ver": "1.3",
        "returnType": "json",
    }
    resp = requests.get(AIR_QUALITY_URL, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()
