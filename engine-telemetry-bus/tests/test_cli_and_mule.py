import json

import pytest

from subnetbus.__main__ import main


def run(*a):
    return main([str(x) for x in a])


def test_cli_lifecycle(tmp_path, capsys):
    f = tmp_path / "r.json"
    assert run("init", f) == 0
    assert run("add-subnet", f, "10.1.1.0/24", "--label", "main", "--world", "0,0,1000,1000") == 0
    assert run("alloc", f, "%Player", "10.1.1.0/24", "--ip", "10.1.1.10", "--bounds", "100,100,32,32") == 0
    assert run("alloc", f, "%Wall", "10.1.1.0/24", "--ip", "10.1.1.14", "--bounds", "200,100,32,200") == 0
    capsys.readouterr()
    assert run("validate", f) == 0
    task = json.dumps({"subnet": "10.1.1.0/24", "target": "%Player", "ref": "10.1.1.10"})
    assert run("check", f, "--task", task, "--bounds", "168,100,32,32") == 0
    capsys.readouterr()
    assert run("check", f, "--task", task, "--bounds", "190,100,32,32") == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["results"][-1]["code"] == "SOLID_OVERLAP"
    assert run("alloc", f, "%Dup", "10.1.1.0/24", "--ip", "10.1.1.10") == 2           # duplicate IP
    assert run("alloc", f, "%Box", "10.1.1.0/24", "--bounds", "190,100,32,32") == 2   # overlap at allocation
    assert run("release", f, "%Wall") == 0 and run("release", f, "%Wall") == 2


def test_cli_fs_check(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    f = tmp_path / "r.json"
    run("init", f); run("add-subnet", f, "10.1.1.0/24"); run("alloc", f, "%Player", "10.1.1.0/24", "--ip", "10.1.1.10")
    task = json.dumps({"subnet": "10.1.1.0/24", "target": "%Player", "ref": "10.1.1.10"})
    assert run("check", f, "--task", task, "--path", "a.txt", "--fs-op", "write", "--fs-root", root) == 0
    assert run("check", f, "--task", task, "--path", "../a.txt", "--fs-op", "write", "--fs-root", root) == 1


def test_cli_errors_exit_2(tmp_path):
    assert run("show", tmp_path / "missing.json") == 2
    bad = tmp_path / "bad.json"
    bad.write_text("{")
    assert run("validate", bad) == 2


def test_mule_block_flows_through_gates(reg):
    mule = pytest.importorskip("mule")
    from subnetbus import check_all
    v = mule.MuleValidator()
    raw = ('{"frame_id":"0x0001","time_slot":"SLOT_3_EXECUTE","subnet":"10.1.1.0/24","op":"bind_move",'
           '"target":"%Player","ref":"10.1.1.10","exclude":["untyped_variables"]}')
    ok, block, errs = v.validate_raw(raw)
    assert ok, errs
    assert check_all(reg, block).ok
    ok, block, _ = v.validate_raw(raw.replace('"%Player"', '"%Ghost"'))
    assert ok and not check_all(reg, block).ok                    # syntactically fine, semantically ungrounded
