import pytest

from subnetbus import AABB, Registry

SN = "10.1.1.0/24"
SN2 = "10.1.2.0/24"


@pytest.fixture
def reg():
    r = Registry()
    r.add_subnet(SN, label="main", world=AABB(0, 0, 1000, 1000))
    r.add_subnet(SN2, label="other")
    r.allocate("%Player", SN, ip="10.1.1.10", bounds=AABB(100, 100, 32, 32))
    r.allocate("%Wall", SN, ip="10.1.1.14", bounds=AABB(200, 100, 32, 200))
    r.allocate("%Camera", SN, kind="camera", bounds=AABB(0, 0, 640, 360), solid=False)
    r.allocate("%Foreign", SN2, ip="10.1.2.10")
    return r


def task(**kw):
    t = {"subnet": SN, "target": "%Player", "ref": "10.1.1.10", "op": "move"}
    t.update(kw)
    return t
