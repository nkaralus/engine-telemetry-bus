# engine-telemetry-bus

Give every engine resource a virtual IP. Check every AI-proposed action against that map
**before** anything touches disk.

```
  validated task block  (subnet, target, ref, op)
          │
          ▼
   ┌─ GI_1 boundary ──── does target / ref / subnet exist, and do they match?
   ├─ GI_2 isolation ─── same subnet only? any ../ or absolute path?
   └─ GI_3 safety ────── solid overlap? out of world? symlink / mountpoint / root drive?
          │
          ▼
   Verdict(ok, revision)  ──►  harness executes  ──►  Verdict.still_valid(reg) just before commit
```

Decoupled from Mule: gates take any mapping with `subnet`, `target`, `ref`.

## Quickstart
```bash
pip install -e ".[dev]" && pytest
```
```python
from subnetbus import Registry, AABB, Action, PathGuard, check_all

reg = Registry()
reg.add_subnet("10.1.1.0/24", label="main", world=AABB(0, 0, 1000, 1000))
reg.allocate("%Player", "10.1.1.0/24", ip="10.1.1.10", bounds=AABB(100, 100, 32, 32))
reg.allocate("%Wall",   "10.1.1.0/24", ip="10.1.1.14", bounds=AABB(200, 100, 32, 200))
reg.save("state_registry.json")

task = {"subnet": "10.1.1.0/24", "target": "%Player", "ref": "10.1.1.10"}
v = check_all(reg, task, Action(proposed_bounds=AABB(190, 100, 32, 32)))
v.ok, v.failed.code      # (False, 'SOLID_OVERLAP')
```

## Rules
| Rule | Where |
|---|---|
| /24 inside 10.0.0.0/8; hosts .1-.9 and broadcast reserved | `addressing.py` |
| One IP per node, one name per node (case-insensitive) | `registry.py` |
| Load is strict: no unknown keys, duplicate keys, NaN, bad IPs, overlaps | `registry.py` |
| Touching edges are fine, any overlap above 1e-6 px is rejected | `geometry.py` |
| Paths: ASCII, no `..`, no absolute, no drive/URI, no `.dotfiles`, no `%` | `fsguard.py` |

## Limits you must know
- **Advisory in time.** A gate result describes the instant it ran. Open files without following
  symlinks and call `verdict.still_valid(reg)` right before committing.
- **Single writer.** `save` is atomic but there is no file lock. Two processes: last write wins.
- **Registry is not the engine.** Gates trust the registry. Re-sync it from the real scene after commits.
- **Mountpoints.** Linux reads `/proc/self/mountinfo`. Other systems rely on `os.path.ismount` and device-id checks.
- **Scope v1.** 2D boxes only. IPv4 /24 in 10/8 only.
