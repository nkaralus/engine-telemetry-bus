import os
import random

import pytest

from subnetbus import PathError, PathGuard, active_mountpoints


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "proj"
    for d in ("scenes", "mnt", "outside_target"):
        (r / d).mkdir(parents=True) if d != "outside_target" else (tmp_path / d).mkdir()
    (r / "scenes" / "main.tscn").write_text("x")
    (r / "mnt" / "inner.txt").write_text("y")
    return r


def code(g, rel, op):
    with pytest.raises(PathError) as e:
        g.check(rel, op)
    return e.value.code


def test_resolves_inside_root(root):
    g = PathGuard(root, mountpoints=())
    assert g.check("scenes/main.tscn", "read") == root.resolve() / "scenes" / "main.tscn"
    assert g.check("scenes/new.gd", "create") == root.resolve() / "scenes" / "new.gd"       # not yet existing
    assert g.check("res://scenes/main.tscn", "write").name == "main.tscn"


@pytest.mark.parametrize("root_path", ["/", "/etc", "/usr/local", "/proc", "/home", "/tmp", "relative/dir"])
def test_dangerous_project_roots_rejected(root_path):
    with pytest.raises(PathError):
        PathGuard(root_path, mountpoints=())


def test_home_directory_as_root_rejected():
    from pathlib import Path
    with pytest.raises(PathError):
        PathGuard(Path.home(), mountpoints=())


def test_missing_root_rejected(tmp_path):
    with pytest.raises(PathError):
        PathGuard(tmp_path / "nope", mountpoints=())


def test_symlinks_refused_by_default(root, tmp_path):
    os.symlink(tmp_path / "outside_target", root / "link")
    os.symlink(root / "scenes", root / "inner_link")
    g = PathGuard(root, mountpoints=())
    assert code(g, "link", "read") == "SYMLINK"
    assert code(g, "link/file.txt", "write") == "SYMLINK"
    assert code(g, "inner_link/main.tscn", "read") == "SYMLINK"


def test_symlink_escape_caught_even_when_symlinks_allowed(root, tmp_path):
    os.symlink(tmp_path / "outside_target", root / "link")
    g = PathGuard(root, mountpoints=(), allow_symlinks=True)
    assert code(g, "link/f.txt", "write") == "ESCAPES_ROOT"
    os.symlink(root / "scenes", root / "ok_link")
    assert g.check("ok_link/main.tscn", "read").name == "main.tscn"


def test_mountpoints_refused(root):
    g = PathGuard(root, mountpoints=[str(root.resolve() / "mnt")])
    assert code(g, "mnt", "read") == "MOUNTPOINT"
    assert code(g, "mnt/inner.txt", "read") == "MOUNTPOINT"
    assert code(g, "mnt", "delete") == "MOUNTPOINT"
    assert g.check("scenes/main.tscn", "read")


def test_destructive_op_on_parent_of_mountpoint_refused(root):
    g = PathGuard(root, mountpoints=[str(root.resolve() / "mnt")])
    # a tree containing a mount: recursive delete/move would cross into it
    (root / "wrapper").mkdir()
    g2 = PathGuard(root, mountpoints=[str(root.resolve() / "wrapper" / "m")])
    assert code(g2, "wrapper", "delete") == "MOUNTPOINT_INSIDE"
    assert code(g2, "wrapper", "move") == "MOUNTPOINT_INSIDE"
    assert g2.check("wrapper", "read")                                  # reading the parent is fine
    assert g.check("wrapper", "delete")                                 # no mount inside it


def test_real_mountinfo_parses():
    m = active_mountpoints()
    assert isinstance(m, frozenset)
    assert not m or "/" in m


def test_mountinfo_octal_unescape(tmp_path):
    f = tmp_path / "mi"
    f.write_text("36 35 98:0 / /mnt/my\\040disk rw - ext4 /dev/x rw\nshort line\n")
    assert active_mountpoints(str(f)) == frozenset({"/mnt/my disk"})
    assert active_mountpoints(str(tmp_path / "missing")) == frozenset()


def test_hardlinked_file_cannot_be_written(root, tmp_path):
    victim = tmp_path / "outside_target" / "victim.txt"
    victim.write_text("precious")
    os.link(victim, root / "hl.txt")
    g = PathGuard(root, mountpoints=())
    assert code(g, "hl.txt", "write") == "HARDLINKED"
    assert code(g, "hl.txt", "overwrite") == "HARDLINKED"
    assert g.check("hl.txt", "read")


def test_unknown_ops_fail_closed(root):
    g = PathGuard(root, mountpoints=())
    for op in ("format", "", None, "READ", "rm -rf", 5):
        assert code(g, "scenes/main.tscn", op) == "UNKNOWN_FS_OP"


def test_cannot_target_root_itself(root):
    g = PathGuard(root, mountpoints=())
    for rel in ("", ".", "./", "scenes/.."):
        with pytest.raises(PathError):
            g.check(rel, "delete")


def test_fuzz_nothing_escapes_the_root(root, tmp_path):
    g = PathGuard(root, mountpoints=())
    rng = random.Random(7)
    toks = ["..", ".", "a", "scenes", "main.tscn", "", "/", "\\", ":", "%2e", "~", "\x00", "\n", " ", "C:", "res://",
            "\u202e", "mnt", "CON", "-x", "....", "a.", "link"]
    os.symlink(tmp_path / "outside_target", root / "link")
    accepted = 0
    for _ in range(5000):
        p = rng.choice(["", "/", "res://"]).join(["", ""]) + "/".join(rng.choice(toks) for _ in range(rng.randint(1, 5)))
        try:
            real = g.check(p, rng.choice(["read", "write", "delete"]))
        except PathError:
            continue
        accepted += 1
        assert real.is_relative_to(root.resolve()) and real != root.resolve(), p
    assert accepted > 0
