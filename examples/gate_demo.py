"""Build a registry, run three tasks through the gates, print the verdicts."""
from subnetbus import AABB, Action, Registry, check_all

reg = Registry()
reg.add_subnet("10.1.1.0/24", label="main", world=AABB(0, 0, 1000, 1000))
reg.add_subnet("10.1.2.0/24", label="menu")
reg.allocate("%Player", "10.1.1.0/24", ip="10.1.1.10", bounds=AABB(100, 100, 32, 32))
reg.allocate("%Wall", "10.1.1.0/24", ip="10.1.1.14", bounds=AABB(200, 100, 32, 200))
reg.allocate("%Button", "10.1.2.0/24", ip="10.1.2.10")
reg.save("state_registry.json")

player = {"subnet": "10.1.1.0/24", "target": "%Player", "ref": "10.1.1.10"}
runs = {
    "move beside wall": (player, Action(proposed_bounds=AABB(168, 100, 32, 32))),
    "move into wall": (player, Action(proposed_bounds=AABB(190, 100, 32, 32))),
    "touch other subnet": (player, Action(refs=("%Button",))),
    "path traversal": (player, Action(paths=("../secrets.txt",))),
    "hallucinated ip": ({**player, "ref": "10.1.1.77"}, Action()),
}
for name, (task, act) in runs.items():
    v = check_all(reg, task, act)
    print(f"{name:20} {'PASS' if v.ok else 'FAIL'}  {v.failed.gate + ' ' + v.failed.code if v.failed else ''}")
