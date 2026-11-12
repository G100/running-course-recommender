"""점들을 칸에 나눠 담아, 한 점에서 radius_m 안에 있는 점만 빨리 찾는다.

코스의 모든 점을 다른 모든 점과 비교하면 거리가 2배일 때 계산은 4배가 된다. 21km 순환 요청 하나에
두 점 사이 거리 계산이 2억 1천만 번, 12분이었다. 칸 한 변을 radius_m보다 조금 크게 잡으면 radius_m 안의
점은 반드시 자기 칸이나 이웃 여덟 칸에 있으므로, 그 아홉 칸의 점만 재면 결과가 같다.
"""
import math
from collections import defaultdict

from ..data_collection.enrich import haversine_m

M_PER_DEG = 111_320
MARGIN = 1.05   # 위도에 따라 경도 1도의 길이가 달라지고 거리 계산식도 조금 다르다 — 칸을 그만큼 넉넉히


class PointGrid:
    def __init__(self, points: list, radius_m: float):
        self.points = points
        self.radius_m = radius_m
        # 가장 높은 위도에서 경도 1도가 가장 짧다. 거기서도 칸이 radius_m보다 넓어야 한다
        narrowest = min((math.cos(math.radians(p[0])) for p in points), default=1.0)
        self._dlat = radius_m * MARGIN / M_PER_DEG
        self._dlng = radius_m * MARGIN / (M_PER_DEG * max(narrowest, 0.01))
        self._cells = defaultdict(list)
        for i, p in enumerate(points):
            self._cells[self._cell(p)].append(i)

    def _cell(self, p) -> tuple:
        return math.floor(p[0] / self._dlat), math.floor(p[1] / self._dlng)

    def _candidates(self, p):
        r, c = self._cell(p)
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                yield from self._cells.get((r + dr, c + dc), ())

    def near(self, p) -> list:
        """p에서 radius_m 안에 있는 점들의 번호."""
        return [i for i in self._candidates(p) if haversine_m(p, self.points[i]) <= self.radius_m]

    def any_near(self, p) -> bool:
        return any(haversine_m(p, self.points[i]) <= self.radius_m for i in self._candidates(p))
