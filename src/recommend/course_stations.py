"""코스 id -> (기상청 격자용 대표좌표, 에어코리아 측정소명) 매핑.

정밀하지 않은 근사 매핑(코스가 속한 동네의 대표 측정소)이며, 실제 서비스에서는
코스 좌표 기준으로 가장 가까운 측정소를 자동 탐색하도록 개선 필요.
"""

COURSE_ENV_CONTEXT = {
    "yeosu-coastal-01": {"lat": 34.7419, "lng": 127.7549, "station": "여수항"},
    "yeosu-coastal-03": {"lat": 34.7303, "lng": 127.7396, "station": "여수항"},
    "yeosu-sports-01": {"lat": 34.7615, "lng": 127.7243, "station": "덕충동"},
    "yeosu-coastal-04": {"lat": 34.7472, "lng": 127.6683, "station": "월내동"},
    "yeosu-expo-01": {"lat": 34.7440, "lng": 127.7580, "station": "여수항"},
    "gwangju-urban-01": {"lat": 35.1565, "lng": 126.8386, "station": "치평동"},
    "gwangju-river-01": {"lat": 35.1116, "lng": 126.9367, "station": "두암동"},
}
