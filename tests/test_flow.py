"""끊기지 않는 길: 꺾는 횟수와 갈림길 수를 경로에서 직접 잰다."""
from src.recommend.flow import junctions_per_km, turns_per_km

# 위도 0.009° ≈ 1km
NORTH_2KM = [[37.0 + i * 0.0009, 127.0] for i in range(21)]


def test_straight_path_has_no_turns():
    assert turns_per_km(NORTH_2KM) == 0


def test_each_right_angle_counts_once():
    # 1km 북쪽 → 1km 동쪽 → 1km 북쪽: 꺾은 곳 2번, 3km
    east = [[37.009, 127.0 + i * 0.00113] for i in range(1, 11)]
    north = [[37.009 + i * 0.0009, 127.0113] for i in range(1, 11)]
    path = NORTH_2KM[:11] + east + north
    assert round(turns_per_km(path) * 3) == 2


def test_small_wiggles_are_not_turns():
    wiggly = [[lat, 127.0 + (0.00003 if i % 2 else 0)] for i, (lat, _) in enumerate(NORTH_2KM)]
    assert turns_per_km(wiggly) == 0


class FakeGraph:
    """노드마다 이웃 목록을 가진 도로망 (RoadGraph와 같은 모양)."""

    def __init__(self, junctions):
        self.adjacent = {}
        for j in junctions:
            j = tuple(j)
            self.adjacent[j] = [((j[0] + d, j[1]), 10, 0) for d in (0.001, 0.002, 0.003)]
        self._grid = {}
        for node in self.adjacent:
            self._grid.setdefault(self._cell(node), []).append(node)

    @staticmethod
    def _cell(node):
        return int(node[0] / 0.002), int(node[1] / 0.002)


def test_junctions_on_the_path_are_counted_per_km():
    graph = FakeGraph([[37.0009, 127.0], [37.009, 127.0]])
    assert junctions_per_km(NORTH_2KM, graph) == 1.0     # 2곳 / 2km


def test_junctions_away_from_the_path_do_not_count():
    graph = FakeGraph([[37.0009, 127.001]])              # 경로에서 약 90m 옆
    assert junctions_per_km(NORTH_2KM, graph) == 0


def test_one_junction_passed_twice_in_a_row_counts_once():
    graph = FakeGraph([[37.0009, 127.0], [37.00095, 127.0]])   # 6m 떨어진 두 노드 = 한 교차로
    assert junctions_per_km(NORTH_2KM, graph) == 0.5
