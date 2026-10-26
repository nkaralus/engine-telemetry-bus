import pytest

from subnetbus import AABB, Action, PathGuard, check_all, gi_1, gi_2, gi_3

from conftest import SN, SN2, task


# ---- GI_1 ------------------------------------------------------------------
def test_good_task_passes_all_gates(reg):
    v = check_all(reg, task())
    assert v.ok and [r.gate for r in v.results] == ["GI_1", "GI_2", "GI_3"] and v.failed is None


@pytest.mark.parametrize("override,code", [
    ({"target": "%Ghost"}, "UNKNOWN_TARGET"),
    ({"ref": "10.1.1.99"}, "REF_MISMATCH"),
    ({"ref": "10.1.1.14"}, "REF_MISMATCH"),              # a real IP, but not this target's
    ({"subnet": "10.9.9.0/24"}, "UNKNOWN_SUBNET"),
    ({"target": None}, "MALFORMED_TASK"),
    ({"ref": 5}, "MALFORMED_TASK"),
])
def test_gi_1_rejections(reg, override, code):
    r = gi_1(reg, task(**override))
    assert not r.ok and r.code == code


def test_gi_1_unknown_extra_ref(reg):
    assert gi_1(reg, task(), Action(refs=("%Wall", "10.1.1.14"))).ok
    assert gi_1(reg, task(), Action(refs=("%Nope",))).code == "UNKNOWN_REF"
    assert gi_1(reg, task(), Action(refs=("10.1.1.200",))).code == "UNKNOWN_REF"


def test_gi_1_non_mapping(reg):
    assert gi_1(reg, ["x"]).code == "MALFORMED_TASK"


# ---- GI_2 ------------------------------------------------------------------
def test_gi_2_cross_subnet_target(reg):
    assert gi_2(reg, task(target="%Foreign", ref="10.1.2.10")).code == "CROSS_SUBNET_TARGET"
    assert check_all(reg, task(target="%Foreign", ref="10.1.2.10")).failed.gate == "GI_2"


def test_gi_2_cross_subnet_ref_by_name_and_ip(reg):
    assert gi_2(reg, task(), Action(refs=("%Foreign",))).code == "CROSS_SUBNET_REF"
    assert gi_2(reg, task(), Action(refs=("10.1.2.10",))).code == "CROSS_SUBNET_REF"
    assert gi_2(reg, task(), Action(refs=("%Wall",))).ok


@pytest.mark.parametrize("path,code", [
    ("../etc/passwd", "PATH_TRAVERSAL"), ("a/../../b", "PATH_TRAVERSAL"), ("res://../x", "PATH_TRAVERSAL"),
    ("/etc/passwd", "PATH_ABSOLUTE"), ("//server/share", "PATH_ABSOLUTE"),
    ("C:/Windows", "PATH_SCHEME"), ("C:\\Windows", "PATH_SCHEME"), ("file:///etc/passwd", "PATH_SCHEME"),
    ("user://save", "PATH_SCHEME"), ("a\\b", "PATH_BACKSLASH"), ("..\\x", "PATH_BACKSLASH"),
    ("%2e%2e/x", "PATH_SEGMENT"), ("a//b", "PATH_SEGMENT"), ("a/", "PATH_SEGMENT"), ("./a", "PATH_SEGMENT"),
    (".hidden", "PATH_SEGMENT"), ("-rf", "PATH_SEGMENT"), ("a b", "PATH_SEGMENT"), ("name.", "PATH_SEGMENT"),
    ("...", "PATH_SEGMENT"), ("~/x", "PATH_SEGMENT"), ("x\n", "PATH_CONTROL_CHAR"), ("x\x00y", "PATH_CONTROL_CHAR"),
    ("\u202epng.exe", "PATH_NON_ASCII"), ("caf\u00e9", "PATH_NON_ASCII"),
    ("CON", "PATH_RESERVED_NAME"), ("dir/nul.txt", "PATH_RESERVED_NAME"), ("", "PATH_EMPTY"),
    ("a/" * 33 + "b", "PATH_TOO_DEEP"), ("a" * 2000, "PATH_TOO_LONG"),
])
def test_gi_2_path_rejections(reg, path, code):
    r = gi_2(reg, task(), Action(paths=(path,)))
    assert not r.ok and r.code == code


@pytest.mark.parametrize("path", ["scenes/main.tscn", "res://scripts/player.gd", "a/b/c_d-e.f.txt", "x"])
def test_gi_2_good_paths(reg, path):
    assert gi_2(reg, task(), Action(paths=(path,))).ok


def test_gi_2_requires_resolved_task(reg):
    assert gi_2(reg, task(target="%Ghost")).code == "UNRESOLVED_TASK"


# ---- GI_3 geometry ----------------------------------------------------------
def test_gi_3_overlap_rejected(reg):
    r = gi_3(reg, task(), Action(proposed_bounds=AABB(190, 100, 32, 32)))     # pushes into %Wall at x=200
    assert not r.ok and r.code == "SOLID_OVERLAP" and "%Wall" in r.detail


def test_gi_3_touching_is_allowed(reg):
    assert gi_3(reg, task(), Action(proposed_bounds=AABB(168, 100, 32, 32))).ok     # right edge == wall left edge


def test_gi_3_own_old_position_is_ignored(reg):
    assert gi_3(reg, task(), Action(proposed_bounds=AABB(101, 100, 32, 32))).ok


def test_gi_3_non_solid_nodes_never_block(reg):
    assert gi_3(reg, task(), Action(proposed_bounds=AABB(10, 10, 32, 32))).ok       # inside %Camera view


def test_gi_3_non_solid_mover_may_overlap(reg):
    cam = task(target="%Camera", ref=reg.get("%Camera").ip)
    assert gi_3(reg, cam, Action(proposed_bounds=AABB(150, 100, 640, 360))).ok


def test_gi_3_out_of_world(reg):
    for b in (AABB(-5, 0, 32, 32), AABB(990, 0, 32, 32), AABB(0, 980, 32, 32)):
        assert gi_3(reg, task(), Action(proposed_bounds=b)).code == "OUT_OF_WORLD"


def test_gi_3_other_subnets_are_separate_worlds(reg):
    reg.allocate("%Rock", SN2, bounds=AABB(100, 100, 32, 32))
    assert gi_3(reg, task(), Action(proposed_bounds=AABB(100, 100, 32, 32))).ok


def test_gi_3_bounds_type_checked():
    with pytest.raises(TypeError):
        Action(proposed_bounds={"x": 0})
    with pytest.raises(TypeError):
        Action(paths=(1,))


# ---- GI_3 filesystem ---------------------------------------------------------
@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    (root / "scenes").mkdir(parents=True)
    (root / "scenes" / "main.tscn").write_text("x")
    return root


def test_gi_3_fails_closed_without_guard_or_op(reg):
    assert gi_3(reg, task(), Action(paths=("a",), fs_op="read")).code == "NO_FS_GUARD"


def test_gi_3_fs_paths(reg, project):
    g = PathGuard(project, mountpoints=())
    assert gi_3(reg, task(), Action(paths=("scenes/main.tscn",), fs_op="write"), fs_guard=g).ok
    assert gi_3(reg, task(), Action(paths=("scenes/main.tscn",)), fs_guard=g).code == "NO_FS_OP"
    assert gi_3(reg, task(), Action(paths=("scenes/main.tscn",), fs_op="format"), fs_guard=g).code == "UNKNOWN_FS_OP"


# ---- pipeline ---------------------------------------------------------------
def test_fail_fast_and_collect_all(reg):
    t = task(target="%Ghost")
    assert len(check_all(reg, t).results) == 1
    assert len(check_all(reg, t, fail_fast=False).results) == 3


def test_verdict_goes_stale_when_registry_changes(reg):
    v = check_all(reg, task())
    assert v.still_valid(reg)
    reg.allocate("%New", SN)
    assert not v.still_valid(reg)
    assert not check_all(reg, task(target="%Ghost")).still_valid(reg)


def test_failed_result_is_truthy_not_inverted(reg):
    v = check_all(reg, task(target="%Ghost"))
    assert v.failed is not None and bool(v.failed)          # `if verdict.failed:` means "something failed"
    assert check_all(reg, task()).failed is None
