import math

import pytest

from subnetbus import AABB, BusError, find_overlaps
from subnetbus.geometry import OVERLAP_TOLERANCE


def test_touching_edges_do_not_overlap():
    a, b = AABB(0, 0, 10, 10), AABB(10, 0, 10, 10)
    assert not a.intersects(b) and not b.intersects(a)
    assert not a.intersects(AABB(10, 10, 5, 5))          # corner touch


def test_overlap_and_depth():
    a, b = AABB(0, 0, 10, 10), AABB(9, 2, 10, 10)
    assert a.intersects(b)
    assert a.overlap_depth(b) == (1.0, 8.0)
    assert find_overlaps(a, [("%B", b)]) == [("%B", 1.0)]


def test_sub_pixel_penetration_is_still_rejected():
    # the harness verifies collisions to <= 0.081 px; the pre-commit guard must be at least as strict
    a, b = AABB(0, 0, 10, 10), AABB(9.919, 0, 10, 10)
    assert a.intersects(b)
    assert 0.081 > OVERLAP_TOLERANCE


def test_float_noise_is_tolerated():
    assert not AABB(0, 0, 10, 10).intersects(AABB(10 - 1e-9, 0, 10, 10))


def test_containment_and_disjoint():
    world = AABB(0, 0, 100, 100)
    assert world.contains(AABB(0, 0, 100, 100)) and world.contains(AABB(10, 10, 5, 5))
    assert not world.contains(AABB(95, 0, 10, 10))
    assert not AABB(0, 0, 1, 1).intersects(AABB(50, 50, 1, 1))


def test_find_overlaps_sorted_deepest_first():
    p = AABB(0, 0, 10, 10)
    hits = find_overlaps(p, [("%Shallow", AABB(9, 0, 10, 10)), ("%Deep", AABB(5, 0, 10, 10)), ("%Far", AABB(99, 99, 1, 1))])
    assert [n for n, _ in hits] == ["%Deep", "%Shallow"]


@pytest.mark.parametrize("args", [(math.nan, 0, 1, 1), (0, math.inf, 1, 1), (0, 0, 0, 1), (0, 0, 1, -1),
                                  (True, 0, 1, 1), ("1", 0, 1, 1), (None, 0, 1, 1), (1e9, 0, 1, 1), (0, 0, 1e9, 1)])
def test_bad_boxes(args):
    with pytest.raises(BusError):
        AABB(*args)


def test_from_dict_strict():
    assert AABB.from_dict({"x": 1, "y": 2, "w": 3, "h": 4}) == AABB(1, 2, 3, 4)
    for bad in ({"x": 1}, {"x": 1, "y": 2, "w": 3, "h": 4, "z": 5}, [], None):
        with pytest.raises(BusError):
            AABB.from_dict(bad)
