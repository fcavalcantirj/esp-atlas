"""Safety contract for the test harness after the accidental live PR incident."""
from __future__ import annotations

import os
import pwd
import subprocess
from pathlib import Path

import pytest

import popularity_run


def test_jr_fixture_rejects_real_gh_and_live_popularity_state(tmp_path):
    assert Path(os.environ["JR_POPULARITY_STATE_FILE"]).is_relative_to(tmp_path)
    with pytest.raises(AssertionError, match="real gh"):
        subprocess.run(["gh", "version"], capture_output=True, text=True)

    live = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".local/state/esp-atlas/jr-popularity.json"
    with pytest.raises(AssertionError, match="live state"):
        popularity_run._state_integrity(live)
    with pytest.raises(AssertionError, match="live state"):
        popularity_run._write_state(live, {})
