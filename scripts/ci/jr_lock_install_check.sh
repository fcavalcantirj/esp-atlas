#!/usr/bin/env bash
# Jr runtime lock — recipe/install verification on x86_64 / CPython 3.12 (CI job jr-lock-install).
#
# WHAT THIS CHECKS: the hash-pinned recipe in jr/runtime-lock/ downloads (wheels only, every
# file hash-checked), the esptool sdist matches its locked sha256 and builds offline against a
# hash-pinned setuptools, and the full 31-package set installs into a clean venv with
# --no-index --require-hashes --only-binary :all:, passes `pip check`, and imports.
#
# WHAT IT DOES NOT CHECK: this is recipe/install verification on x86_64 with a CI-built esptool
# wheel, NOT proof of the Pi archive. The Pi runs aarch64 wheels and its own esptool wheel,
# whose hashes this job never sees.
#
# Network is used ONLY in step 2. After it, PIP_NO_INDEX=1 is exported and every pip call also
# passes --no-index. No secrets, no env inputs; optional $1 = interpreter (default python3).
set -euo pipefail

LABEL="recipe/install verification on x86_64 with a CI-built esptool wheel, NOT proof of the Pi archive"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOCK_DIR="$ROOT/jr/runtime-lock"
RUNTIME_IN="$LOCK_DIR/runtime.in"
RUNTIME_LOCK="$LOCK_DIR/runtime-cp312-x86_64.lock"
BUILD_IN="$LOCK_DIR/build.in"
BUILD_LOCK="$LOCK_DIR/build-constraints.lock"
EXPECTED_PACKAGES=31

PY="$(command -v "${1:-python3}")"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
WHEELHOUSE="$WORK/wheelhouse"
BUILDHOUSE="$WORK/buildhouse"
SDIST_DIR="$WORK/sdist"
BUILT_DIR="$WORK/built"
BUILD_VENV="$WORK/build-venv"
RUN_VENV="$WORK/run-venv"
DERIVED_LOCK="$WORK/runtime-wheelhouse.lock"
TAMPERED_LOCK="$WORK/runtime-tampered.lock"
NO_ESPTOOL_WHEELHOUSE="$WORK/wheelhouse-without-esptool"

# Pip reads config files and PIP_* env vars, Python reads PYTHONPATH/HOME; none may loosen this run.
while IFS= read -r var; do unset "$var"; done < <(compgen -e | grep '^PIP_' || true)
unset PYTHONPATH PYTHONHOME
export PIP_CONFIG_FILE=/dev/null PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_INPUT=1 PYTHONNOUSERSITE=1

step() { printf '\n=== %s\n' "$*"; }
die() { printf 'FAIL jr-lock-install: %s\n' "$*" >&2; exit 1; }
tool() { "$PY" -I "$ROOT/scripts/ci/jr_lock_tool.py" "$@"; }
sha256() { sha256sum "$1" | cut -d' ' -f1; }
count_lines() { grep -c . "$1" || true; }
canonical_names() { sed -E 's/==.*//; s/[-_.]+/-/g' | tr '[:upper:]' '[:lower:]' | sort; }

# Runs a pip install that MUST fail; asserts non-zero exit and the expected reason in its log.
expect_install_fails() {
  local what="$1" reason="$2" venv="$3" log="$WORK/neg-$4.log" left
  shift 4
  if "$venv/bin/python" -m pip install --no-cache-dir "$@" > "$log" 2>&1; then
    tail -20 "$log"
    die "negative check '$what' INSTALLED — it must fail"
  fi
  grep -q "$reason" "$log" || { tail -20 "$log"; die "negative check '$what' failed for the wrong reason (wanted: $reason)"; }
  left="$("$venv/bin/python" -m pip freeze)" || die "pip freeze failed after negative check '$what'"
  [ -z "$left" ] || die "negative check '$what' left packages behind"
  echo "ok: '$what' was refused ($reason)"
}

step "1. interpreter and platform — $LABEL"
"$PY" -I -c 'import sys, sysconfig; print("interpreter:", sys.executable); print("python:", sys.version.replace("\n", " ")); print("sysconfig platform:", sysconfig.get_platform())'
echo "uname -m: $(uname -m)"
"$PY" -I -c 'import sys; sys.exit(sys.version_info[:2] != (3, 12))' \
  || die "the lock is cp312; run this with CPython 3.12"
OFF_TARGET=""
if [ "$(uname -m)" != x86_64 ]; then
  OFF_TARGET=" [OFF-TARGET run on $(uname -m): NOT the x86_64 verification the CI job performs]"
  echo "NOTE:${OFF_TARGET}"
fi

step "2. download (the only networked step)"
tool select "$RUNTIME_LOCK" --exclude esptool > "$WORK/runtime-no-esptool.lock"
[ "$(tool names "$WORK/runtime-no-esptool.lock" | wc -l)" -eq $((EXPECTED_PACKAGES - 1)) ] \
  || die "expected $((EXPECTED_PACKAGES - 1)) non-esptool packages"
"$PY" -m pip download --no-cache-dir --require-hashes --only-binary :all: \
  --dest "$WHEELHOUSE" -r "$WORK/runtime-no-esptool.lock"
[ "$(find "$WHEELHOUSE" -name '*.whl' | wc -l)" -eq $((EXPECTED_PACKAGES - 1)) ] \
  || die "wheelhouse does not hold exactly $((EXPECTED_PACKAGES - 1)) wheels"

"$PY" -m pip download --no-cache-dir --require-hashes --only-binary :all: \
  --dest "$BUILDHOUSE" -r "$BUILD_LOCK"
"$PY" -m venv "$BUILD_VENV"
"$BUILD_VENV/bin/python" -m pip install --no-index --find-links "$BUILDHOUSE" \
  --require-hashes --only-binary :all: -r "$BUILD_LOCK"

# Through the build venv with --no-build-isolation, so even the sdist's metadata step runs on
# the hash-pinned setuptools rather than an unpinned one pip would fetch for isolation.
tool select "$RUNTIME_LOCK" --only esptool > "$WORK/esptool-sdist.lock"
"$BUILD_VENV/bin/python" -m pip download --no-cache-dir --require-hashes --no-binary esptool \
  --no-deps --no-build-isolation --dest "$SDIST_DIR" -r "$WORK/esptool-sdist.lock"
SDIST="$(find "$SDIST_DIR" -name 'esptool-*.tar.gz')"
[ "$(printf '%s\n' "$SDIST" | grep -c .)" -eq 1 ] || die "expected exactly one esptool sdist"
SDIST_LOCK_SHA="$(tool hashes "$RUNTIME_LOCK" esptool)"
SDIST_SHA="$(sha256 "$SDIST")"
echo "esptool sdist sha256 (lock):       $SDIST_LOCK_SHA"
echo "esptool sdist sha256 (downloaded): $SDIST_SHA"
[ "$SDIST_SHA" = "$SDIST_LOCK_SHA" ] || die "esptool sdist hash does not match the lock"

export PIP_NO_INDEX=1
echo "network phase over: PIP_NO_INDEX=1 from here on"

step "3. build the esptool wheel offline (no build isolation, only hash-pinned setuptools)"
"$BUILD_VENV/bin/python" -m pip freeze --all > "$WORK/build-venv.freeze"
cat "$WORK/build-venv.freeze"
[ "$(canonical_names < "$WORK/build-venv.freeze" | tr '\n' ' ')" = "pip setuptools " ] \
  || die "build venv must hold only pip + setuptools"
grep -qx "$(grep -E '^setuptools==' "$BUILD_LOCK" | cut -d' ' -f1)" "$WORK/build-venv.freeze" \
  || die "build venv setuptools is not the locked version"
"$BUILD_VENV/bin/python" -m pip wheel --no-cache-dir --no-index --no-deps --no-build-isolation \
  --require-hashes --no-binary esptool --find-links "$SDIST_DIR" \
  --wheel-dir "$BUILT_DIR" -r "$WORK/esptool-sdist.lock"
BUILT_WHEEL="$(find "$BUILT_DIR" -name 'esptool-*.whl')"
[ "$(printf '%s\n' "$BUILT_WHEEL" | grep -c .)" -eq 1 ] || die "expected exactly one built esptool wheel"
cp "$BUILT_WHEEL" "$WHEELHOUSE/"

step "4. derive the wheelhouse lock (only the esptool hash may change)"
WHEEL_SHA="$(sha256 "$BUILT_WHEEL")"
echo "esptool hash in original lock (sdist): $SDIST_LOCK_SHA"
echo "esptool hash in derived lock (wheel):  $WHEEL_SHA"
tool derive "$RUNTIME_LOCK" esptool "$WHEEL_SHA" > "$DERIVED_LOCK"
CHANGED="$(tool changed "$RUNTIME_LOCK" "$DERIVED_LOCK")"
echo "packages whose hashes differ: $(printf '%s\n' "$CHANGED" | grep -c .) ($CHANGED)"
[ "$CHANGED" = esptool ] || die "derived lock must differ from the original in exactly one package (esptool)"
DIFF_LINES="$(diff "$RUNTIME_LOCK" "$DERIVED_LOCK" | grep -c '^[<>]' || true)"
[ "$DIFF_LINES" -eq 2 ] || die "derived lock must differ in exactly one line (diff shows $DIFF_LINES)"

step "5. clean offline install from the wheelhouse"
"$PY" -m venv "$RUN_VENV"
"$RUN_VENV/bin/python" -m pip install --no-cache-dir --no-index --find-links "$WHEELHOUSE" --require-hashes --only-binary :all: -r "$DERIVED_LOCK"
"$RUN_VENV/bin/python" -m pip check
"$RUN_VENV/bin/python" -m pip freeze > "$WORK/run-venv.freeze"
FROZEN="$(count_lines "$WORK/run-venv.freeze")"
echo "pip freeze: $FROZEN packages"
[ "$FROZEN" -eq "$EXPECTED_PACKAGES" ] || die "pip freeze shows $FROZEN packages, expected $EXPECTED_PACKAGES"
[ "$(canonical_names < "$WORK/run-venv.freeze")" = "$(tool names "$RUNTIME_LOCK" | sort)" ] \
  || die "installed package names do not match the lock"
(cd "$WORK" && "$RUN_VENV/bin/python" -I - "$RUN_VENV") <<'PY'
import sys
from importlib.metadata import version
from pathlib import Path

import esptool
import esptool.bin_image  # noqa: F401
import jsonschema
import requests
import rpds
import yaml
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

venv = Path(sys.argv[1]).resolve()
assert venv in Path(esptool.__file__).resolve().parents, f"esptool imported from outside the venv: {esptool.__file__}"
assert version("esptool") == "5.6.0", version("esptool")

digest = hashes.Hash(hashes.SHA256())
digest.update(b"abc")
assert digest.finalize().hex() == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
key = Ed25519PrivateKey.generate()
key.public_key().verify(key.sign(b"jr"), b"jr")

assert hasattr(yaml, "CLoader"), "PyYAML built without libyaml (no CLoader)"
assert yaml.load("a: [1, 2]", Loader=yaml.CLoader) == {"a": [1, 2]}
assert rpds.HashTrieMap({"a": 1})["a"] == 1
jsonschema.validate({"a": 1}, {"type": "object", "required": ["a"]})
try:
    jsonschema.validate({}, {"type": "object", "required": ["a"]})
    raise AssertionError("jsonschema accepted an invalid instance")
except jsonschema.ValidationError:
    pass
requests.Session().close()
print("imports ok:", ", ".join(f"{p} {version(p)}" for p in
      ("esptool", "cryptography", "PyYAML", "rpds-py", "jsonschema", "requests")))
PY

step "6. negative checks (each install MUST fail)"
ATTRS_WHEEL="$(find "$WHEELHOUSE" -name 'attrs-*.whl')"
ATTRS_SHA="$(sha256 "$ATTRS_WHEEL")"
tool hashes "$DERIVED_LOCK" attrs | grep -qx "$ATTRS_SHA" || die "attrs wheel hash not in the derived lock"
tool tamper "$DERIVED_LOCK" "$ATTRS_SHA" > "$TAMPERED_LOCK"
[ "$(tool changed "$DERIVED_LOCK" "$TAMPERED_LOCK")" = attrs ] || die "tampered lock must differ only in attrs"
echo "tampered attrs hash: $ATTRS_SHA -> $(tool hashes "$TAMPERED_LOCK" attrs | grep -vxF -f <(tool hashes "$DERIVED_LOCK" attrs))"
mkdir "$NO_ESPTOOL_WHEELHOUSE"
cp "$WHEELHOUSE"/*.whl "$NO_ESPTOOL_WHEELHOUSE/"
rm -f "$NO_ESPTOOL_WHEELHOUSE"/esptool-*.whl
[ "$(find "$NO_ESPTOOL_WHEELHOUSE" -name '*.whl' | wc -l)" -eq "$(( $(find "$WHEELHOUSE" -name '*.whl' | wc -l) - 1 ))" ] \
  || die "the esptool-less wheelhouse must be the full wheelhouse minus exactly one wheel"
[ -z "$(find "$NO_ESPTOOL_WHEELHOUSE" -name 'esptool-*')" ] || die "esptool still present in the esptool-less wheelhouse"
for neg in tampered noesptool; do "$PY" -m venv "$WORK/neg-$neg-venv"; done
expect_install_fails "one hash tampered" "DO NOT MATCH THE HASHES" "$WORK/neg-tampered-venv" tampered \
  --no-index --find-links "$WHEELHOUSE" --require-hashes --only-binary :all: -r "$TAMPERED_LOCK"
expect_install_fails "wheelhouse missing only esptool" "No matching distribution found for esptool" "$WORK/neg-noesptool-venv" noesptool \
  --no-index --find-links "$NO_ESPTOOL_WHEELHOUSE" --require-hashes --only-binary :all: -r "$DERIVED_LOCK"

step "7. sha256 of inputs and wheelhouse"
sha256sum "$RUNTIME_IN" "$RUNTIME_LOCK" "$BUILD_IN" "$BUILD_LOCK" | sed "s|$ROOT/||"
sha256sum "$DERIVED_LOCK" | sed "s|$WORK/||"
(cd "$WHEELHOUSE" && sha256sum -- *)

PLATFORM="$("$PY" -I -c 'import sysconfig; print(sysconfig.get_platform())')"
printf '\nPASS jr-lock-install: %s/%s packages installed offline with --require-hashes on %s (%s, CPython %s) — %s%s\n' \
  "$FROZEN" "$EXPECTED_PACKAGES" "$(uname -m)" "$PLATFORM" \
  "$("$PY" -I -c 'import platform; print(platform.python_version())')" "$LABEL" "$OFF_TARGET"
