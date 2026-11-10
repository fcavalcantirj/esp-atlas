"""Pure text transforms over pip-compile style hash-pinned lock files (stdlib only).

Used by scripts/ci/jr_lock_install_check.sh. Every transform keeps the lock's text verbatim
except for the one thing it is asked to change, so a derived lock can be diffed against the
original and shown to differ in exactly one package. Run it with `python -I`.

    names   LOCK                       canonical package names, lock order
    hashes  LOCK NAME                  that package's sha256 hashes
    select  LOCK --only|--exclude NAME a lock with just / without that package
    derive  LOCK NAME SHA256           replace that package's single hash
    changed A B                        packages whose hash sets differ
    tamper  LOCK SHA256                flip one character of that hash
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REQ_LINE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==")
HASH = re.compile(r"--hash=sha256:([0-9a-f]{64})\b")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class LockError(ValueError):
    """The lock does not have the shape the requested transform needs."""


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _blocks(text: str) -> list[tuple[str | None, str]]:
    """Split into (canonical name, block text); the preamble before the first pin has name None."""
    blocks: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in text.splitlines(keepends=True):
        match = REQ_LINE.match(line)
        if match:
            blocks.append((canonical(match.group(1)), []))
        blocks[-1][1].append(line)
    return [(name, "".join(lines)) for name, lines in blocks]


def _block(text: str, name: str) -> str:
    wanted = canonical(name)
    for block_name, block in _blocks(text):
        if block_name == wanted:
            return block
    raise LockError(f"{name} is not pinned in the lock")


def names(text: str) -> list[str]:
    return [name for name, _ in _blocks(text) if name is not None]


def hashes(text: str, name: str) -> list[str]:
    return HASH.findall(_block(text, name))


def _hash_sets(text: str) -> dict[str, set[str]]:
    return {name: set(HASH.findall(block)) for name, block in _blocks(text) if name is not None}


def select(text: str, only: str | None = None, exclude: str | None = None) -> str:
    if (only is None) == (exclude is None):
        raise LockError("select needs exactly one of only / exclude")
    target = canonical(only or exclude)
    _block(text, target)
    keep = (lambda n: n == target) if only else (lambda n: n != target)
    return "".join(block for name, block in _blocks(text) if name is None or keep(name))


def derive(text: str, name: str, new_hash: str) -> str:
    if not SHA256.match(new_hash):
        raise LockError(f"not a sha256 hex digest: {new_hash!r}")
    old = _block(text, name)
    found = HASH.findall(old)
    if len(found) != 1:
        raise LockError(f"{name} has {len(found)} hashes; derive replaces exactly one")
    target = canonical(name)
    new = old.replace(found[0], new_hash)
    return "".join(new if block_name == target else block for block_name, block in _blocks(text))


def changed(a: str, b: str) -> list[str]:
    sets_a, sets_b = _hash_sets(a), _hash_sets(b)
    if set(sets_a) != set(sets_b):
        raise LockError(f"package sets differ: {sorted(set(sets_a) ^ set(sets_b))}")
    return [name for name in sets_a if sets_a[name] != sets_b[name]]


def tamper(text: str, target: str) -> str:
    if text.count(target) != 1:
        raise LockError(f"hash {target} appears {text.count(target)} times; tamper needs exactly one")
    flipped = target[:-1] + ("0" if target[-1] != "0" else "1")
    return text.replace(target, flipped)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("names").add_argument("lock")
    p = sub.add_parser("hashes")
    p.add_argument("lock")
    p.add_argument("name")
    p = sub.add_parser("select")
    p.add_argument("lock")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--only")
    group.add_argument("--exclude")
    p = sub.add_parser("derive")
    p.add_argument("lock")
    p.add_argument("name")
    p.add_argument("sha256")
    p = sub.add_parser("changed")
    p.add_argument("a")
    p.add_argument("b")
    p = sub.add_parser("tamper")
    p.add_argument("lock")
    p.add_argument("sha256")
    return parser


def _run(args: argparse.Namespace) -> str:
    read = lambda p: Path(p).read_text()  # noqa: E731
    if args.cmd == "names":
        return "\n".join(names(read(args.lock))) + "\n"
    if args.cmd == "hashes":
        return "\n".join(hashes(read(args.lock), args.name)) + "\n"
    if args.cmd == "select":
        return select(read(args.lock), only=args.only, exclude=args.exclude)
    if args.cmd == "derive":
        return derive(read(args.lock), args.name, args.sha256)
    if args.cmd == "changed":
        return "".join(f"{name}\n" for name in changed(read(args.a), read(args.b)))
    return tamper(read(args.lock), args.sha256)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        sys.stdout.write(_run(args))
    except LockError as err:
        print(f"jr_lock_tool: {err}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
