package com.runmate.app

import org.junit.Assert.assertEquals
import org.junit.Test

/** 거리 고르기는 웹 페이지의 다이얼과 같다: 10km까지 0.5km씩, 그 위는 1km씩, 맨 끝은 풀코스. */
class DistanceTest {
    @Test fun up_to_ten_km_it_moves_by_half_a_km() {
        assertEquals(5.5, Distance.up(5.0), 1e-9)
        assertEquals(10.0, Distance.up(9.5), 1e-9)
        assertEquals(4.5, Distance.down(5.0), 1e-9)
    }

    @Test fun above_ten_km_it_moves_by_one_km() {
        assertEquals(11.0, Distance.up(10.0), 1e-9)
        assertEquals(10.0, Distance.down(11.0), 1e-9)
        assertEquals(22.0, Distance.up(Distance.HALF), 1e-9)
        assertEquals(21.0, Distance.down(Distance.HALF), 1e-9)
    }

    @Test fun after_42_comes_the_full_marathon_and_going_down_from_it_works() {
        assertEquals(Distance.MAX, Distance.up(41.0), 1e-9)
        assertEquals(Distance.MAX, Distance.up(Distance.MAX), 1e-9)
        assertEquals(42.0, Distance.down(Distance.MAX), 1e-9)   // 웹에서는 풀코스에서 −가 멈췄었다
    }

    @Test fun it_never_goes_below_one_km() {
        assertEquals(1.0, Distance.down(1.0), 1e-9)
    }

    @Test fun labels_name_the_race_distances() {
        assertEquals("풀코스 42.195km", Distance.label(Distance.MAX))
        assertEquals("하프 21.1km", Distance.label(Distance.HALF))
        assertEquals("5km", Distance.label(5.0))
        assertEquals("7.5km", Distance.label(7.5))
    }
}
