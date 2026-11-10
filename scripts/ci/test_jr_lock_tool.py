"""Tests for scripts/ci/jr_lock_tool.py — pure text transforms over hash-pinned lock files."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jr_lock_tool as lt  # noqa: E402

A1, A2 = "a" * 64, "b" * 64
E1, NEW = "e" * 64, "f" * 64

LOCK = f"""\
# header comment
Foo_Bar==1.0 \\
    --hash=sha256:{A1} \\
    --hash=sha256:{A2}
    # via -r runtime.in
esptool==5.6.0 \\
    --hash=sha256:{E1}
    # via -r runtime.in
"""


def test_names_are_canonical_and_in_lock_order():
    assert lt.names(LOCK) == ["foo-bar", "esptool"]


def test_hashes_of_one_package():
    assert lt.hashes(LOCK, "foo_bar") == [A1, A2]
    assert lt.hashes(LOCK, "esptool") == [E1]


def test_hashes_of_an_unknown_package_is_an_error():
    with pytest.raises(lt.LockError):
        lt.hashes(LOCK, "nope")


def test_select_excluding_drops_only_that_block_and_keeps_the_rest_verbatim():
    out = lt.select(LOCK, exclude="esptool")
    assert lt.names(out) == ["foo-bar"]
    assert out == LOCK.split("esptool==")[0]


def test_select_only_keeps_just_that_block():
    out = lt.select(LOCK, only="esptool")
    assert lt.names(out) == ["esptool"] and lt.hashes(out, "esptool") == [E1]


def test_select_needs_exactly_one_of_only_or_exclude():
    with pytest.raises(lt.LockError):
        lt.select(LOCK)
    with pytest.raises(lt.LockError):
        lt.select(LOCK, only="esptool", exclude="foo-bar")


def test_select_of_an_unknown_package_is_an_error():
    with pytest.raises(lt.LockError):
        lt.select(LOCK, exclude="nope")


def test_derive_replaces_only_that_packages_hash():
    out = lt.derive(LOCK, "esptool", NEW)
    assert lt.hashes(out, "esptool") == [NEW]
    assert lt.hashes(out, "foo-bar") == [A1, A2]
    assert out == LOCK.replace(E1, NEW)
    assert lt.changed(LOCK, out) == ["esptool"]


def test_derive_refuses_a_package_with_more_than_one_hash():
    with pytest.raises(lt.LockError):
        lt.derive(LOCK, "foo-bar", NEW)


def test_derive_refuses_a_malformed_hash():
    with pytest.raises(lt.LockError):
        lt.derive(LOCK, "esptool", "XYZ")


def test_changed_is_empty_for_identical_locks():
    assert lt.changed(LOCK, LOCK) == []


def test_changed_refuses_locks_with_different_package_sets():
    with pytest.raises(lt.LockError):
        lt.changed(LOCK, lt.select(LOCK, exclude="esptool"))


def test_tamper_flips_exactly_that_hash_and_nothing_else():
    out = lt.tamper(LOCK, A2)
    assert A2 not in out
    tampered = [h for h in lt.hashes(out, "foo-bar") if h != A1]
    assert len(tampered) == 1 and tampered[0] != A2 and len(tampered[0]) == 64
    assert lt.changed(LOCK, out) == ["foo-bar"]
    assert sum(a != b for a, b in zip(LOCK.splitlines(), out.splitlines())) == 1


def test_tamper_refuses_a_hash_that_is_not_in_the_lock():
    with pytest.raises(lt.LockError):
        lt.tamper(LOCK, NEW)


def test_cli_prints_names_and_reports_errors_with_exit_2(tmp_path, capsys):
    lock = tmp_path / "x.lock"
    lock.write_text(LOCK)
    assert lt.main(["names", str(lock)]) == 0
    assert capsys.readouterr().out.split() == ["foo-bar", "esptool"]
    assert lt.main(["hashes", str(lock), "nope"]) == 2
    assert "nope" in capsys.readouterr().err


def test_cli_derive_and_changed_round_trip(tmp_path, capsys):
    lock = tmp_path / "x.lock"
    lock.write_text(LOCK)
    assert lt.main(["derive", str(lock), "esptool", NEW]) == 0
    derived = tmp_path / "d.lock"
    derived.write_text(capsys.readouterr().out)
    assert lt.main(["changed", str(lock), str(derived)]) == 0
    assert capsys.readouterr().out.split() == ["esptool"]


def test_cli_select_and_tamper(tmp_path, capsys):
    lock = tmp_path / "x.lock"
    lock.write_text(LOCK)
    assert lt.main(["select", str(lock), "--only", "esptool"]) == 0
    assert lt.names(capsys.readouterr().out) == ["esptool"]
    assert lt.main(["select", str(lock), "--exclude", "esptool"]) == 0
    assert lt.names(capsys.readouterr().out) == ["foo-bar"]
    assert lt.main(["tamper", str(lock), A1]) == 0
    assert A1 not in capsys.readouterr().out
