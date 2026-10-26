import json

import pytest

from subnetbus import AABB, BusError, Registry, RegistryError, parse_host, parse_subnet

from conftest import SN, SN2


# ---- addressing ------------------------------------------------------------
@pytest.mark.parametrize("bad", ["10.1.1.0/16", "10.1.1.5/24", "192.168.1.0/24", "10.1.1.0", "10.01.1.0/24",
                                 "10.300.1.0/24", "10.1.1.0/255.255.255.0", "::1/24", "10.1.1.0/24\n",
                                 "\uff11\uff10.1.1.0/24", 5, None, "x" * 30])
def test_bad_subnets(bad):
    with pytest.raises(RegistryError):
        parse_subnet(bad)


@pytest.mark.parametrize("bad", ["10.1.1.256", "10.1.01.10", "10.1.1", "10.1.1.10 ", "1.2.3.4.5", "", None, 167837962])
def test_bad_hosts(bad):
    with pytest.raises(RegistryError):
        parse_host(bad)


def test_auto_allocation_starts_above_reserved_and_fills_gaps():
    r = Registry()
    r.add_subnet(SN)
    assert r.allocate("%A", SN).ip == "10.1.1.10"
    assert r.allocate("%B", SN).ip == "10.1.1.11"
    r.release("%A")
    assert r.allocate("%C", SN).ip == "10.1.1.10"


def test_explicit_ip_rules():
    r = Registry()
    r.add_subnet(SN)
    for ip in ("10.1.1.0", "10.1.1.1", "10.1.1.9", "10.1.1.255", "10.1.2.10", "bogus"):
        with pytest.raises(RegistryError):
            r.allocate("%X", SN, ip=ip)
    assert len(r) == 0 and r.revision == 1          # failed allocations changed nothing


def test_duplicate_ip_and_names_rejected(reg):
    with pytest.raises(RegistryError) as e:
        reg.allocate("%Other", SN, ip="10.1.1.10")
    assert e.value.code == "DUPLICATE_IP"
    with pytest.raises(RegistryError) as e:
        reg.allocate("%Player", SN)
    assert e.value.code == "DUPLICATE_NAME"
    with pytest.raises(RegistryError) as e:
        reg.allocate("%PLAYER", SN)
    assert e.value.code == "DUPLICATE_NAME"        # case-insensitive collision
    reg.allocate("%Twin", SN2, ip="10.1.2.20")       # same host octet range in another subnet is fine


def test_same_host_octet_in_two_subnets_is_not_a_duplicate(reg):
    assert reg.get("%Foreign").ip == "10.1.2.10" and reg.get("%Player").ip == "10.1.1.10"


@pytest.mark.parametrize("name", ["Player", "%player", "%", "%P layer", "%Pl/ayer", "%../x", "%" + "A" * 65, "%P\u0430"])
def test_bad_names(name):
    r = Registry()
    r.add_subnet(SN)
    with pytest.raises(RegistryError):
        r.allocate(name, SN)


def test_subnet_exhaustion():
    r = Registry()
    r.add_subnet(SN)
    for i in range(245):                            # hosts .10 - .254
        r.allocate(f"%N{i}", SN)
    with pytest.raises(RegistryError) as e:
        r.allocate("%Last", SN)
    assert e.value.code == "SUBNET_EXHAUSTED"


def test_release_and_resolve(reg):
    assert reg.resolve("%Wall").ip == "10.1.1.14"
    assert reg.resolve("10.1.1.14").name == "%Wall"
    assert reg.resolve("10.1.1.99") is None and reg.resolve("nonsense") is None and reg.resolve(5) is None
    reg.release("%Wall")
    assert reg.resolve("10.1.1.14") is None
    with pytest.raises(RegistryError):
        reg.release("%Wall")


def test_revision_and_fingerprint(reg):
    rev, fp = reg.revision, reg.fingerprint()
    reg.allocate("%New", SN)
    assert reg.revision == rev + 1 and reg.fingerprint() != fp


# ---- persistence -----------------------------------------------------------
def test_roundtrip_and_atomic_save(reg, tmp_path):
    f = tmp_path / "state_registry.json"
    reg.save(f)
    assert [p.name for p in tmp_path.iterdir()] == ["state_registry.json"]   # no temp litter
    back = Registry.load(f)
    assert back.to_dict() == reg.to_dict() and back.fingerprint() == reg.fingerprint()


def _mut(reg, fn):
    d = json.loads(json.dumps(reg.to_dict()))
    fn(d)
    return d


LOAD_CASES = {
    "unknown_top_key": (lambda d: d.update(extra=1), "exactly registry_version"),
    "missing_top_key": (lambda d: d.pop("nodes"), "exactly registry_version"),
    "bad_version": (lambda d: d.update(registry_version="2.0.0"), "unsupported registry_version"),
    "neg_revision": (lambda d: d.update(revision=-1), "revision"),
    "bool_revision": (lambda d: d.update(revision=True), "revision"),
    "nodes_is_list": (lambda d: d.update(nodes=[]), "must be objects"),
    "unknown_node_field": (lambda d: d["nodes"]["%Player"].update(evil=1), "BAD_NODE"),
    "missing_ip": (lambda d: d["nodes"]["%Player"].pop("ip"), "BAD_NODE"),
    "dup_ip": (lambda d: d["nodes"]["%Wall"].update(ip="10.1.1.10"), "DUPLICATE_IP"),
    "ip_outside_subnet": (lambda d: d["nodes"]["%Wall"].update(ip="10.1.2.14"), "IP_NOT_USABLE"),
    "ip_reserved": (lambda d: d["nodes"]["%Wall"].update(ip="10.1.1.5"), "IP_NOT_USABLE"),
    "ip_broadcast": (lambda d: d["nodes"]["%Wall"].update(ip="10.1.1.255"), "IP_NOT_USABLE"),
    "ip_leading_zero": (lambda d: d["nodes"]["%Wall"].update(ip="10.1.1.014"), "BAD_IP"),
    "unknown_subnet": (lambda d: d["nodes"]["%Wall"].update(subnet="10.9.9.0/24"), "UNKNOWN_SUBNET"),
    "bad_name": (lambda d: d["nodes"].update({"%bad name": d["nodes"]["%Wall"]}), "BAD_NAME"),
    "casefold_dup": (lambda d: d["nodes"].update({"%PLAYER": {"ip": "10.1.1.50", "subnet": SN}}), "case-insensitive"),
    "bad_bounds_key": (lambda d: d["nodes"]["%Player"]["bounds"].update(z=1), "BAD_BOUNDS"),
    "zero_width": (lambda d: d["nodes"]["%Player"]["bounds"].update(w=0), "BAD_BOUNDS"),
    "bool_bounds": (lambda d: d["nodes"]["%Player"]["bounds"].update(x=True), "BAD_BOUNDS"),
    "huge_bounds": (lambda d: d["nodes"]["%Player"]["bounds"].update(x=1e12), "BAD_BOUNDS"),
    "solid_overlap": (lambda d: d["nodes"]["%Wall"].update(bounds={"x": 110, "y": 110, "w": 32, "h": 32}), "SOLID_OVERLAP"),
    "out_of_world": (lambda d: d["nodes"]["%Player"].update(bounds={"x": 990, "y": 0, "w": 32, "h": 32}), "OUT_OF_WORLD"),
    "traversal_path": (lambda d: d["nodes"]["%Player"].update(path="../etc/passwd"), "PATH_TRAVERSAL"),
    "absolute_path": (lambda d: d["nodes"]["%Player"].update(path="/etc/passwd"), "PATH_ABSOLUTE"),
    "solid_not_bool": (lambda d: d["nodes"]["%Player"].update(solid="yes"), "BAD_SOLID"),
    "bad_subnet_key": (lambda d: d["subnets"].update({"10.1.3.0/16": {}}), "BAD_SUBNET"),
    "unknown_subnet_field": (lambda d: d["subnets"][SN].update(evil=1), "BAD_SUBNET"),
}


def test_unmutated_document_loads(reg):
    assert Registry.from_dict(_mut(reg, lambda d: None)).fingerprint() == reg.fingerprint()


@pytest.mark.parametrize("name", list(LOAD_CASES))
def test_strict_load_rejections(reg, name):
    fn, expected = LOAD_CASES[name]
    with pytest.raises(RegistryError) as e:
        Registry.from_dict(_mut(reg, fn))
    assert expected in str(e.value), str(e.value)


def test_raw_json_rejections(tmp_path):
    base = '{"registry_version":"1.0.0","revision":0,"subnets":{},"nodes":{}}'
    assert Registry.loads(base).revision == 0
    for bad in ['{"registry_version":"1.0.0","registry_version":"1.0.0","revision":0,"subnets":{},"nodes":{}}',
                base.replace("0,", "NaN,", 1), "[]", "", "{", base + base, "\x00" + base]:
        with pytest.raises(BusError):
            Registry.loads(bad)
    f = tmp_path / "big.json"
    f.write_bytes(b" " * (4 * 1024 * 1024 + 1))
    with pytest.raises(RegistryError):
        Registry.load(f)
    f.write_bytes(b"\xff\xfe{}")
    with pytest.raises(RegistryError):
        Registry.load(f)


def test_save_refuses_inconsistent_registry(reg, tmp_path):
    from subnetbus import Node
    reg._insert(Node("%Ghost", "10.1.1.10", SN, bounds=None))     # sneaks a duplicate IP past the API
    with pytest.raises(RegistryError):
        reg.save(tmp_path / "x.json")
    assert not (tmp_path / "x.json").exists()
