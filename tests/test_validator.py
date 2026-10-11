import stat
import pytest
from pathlib import Path
from executor.validator import validate_job, ValidationError


def test_validator_success(tmp_path):
    run_file = tmp_path / "run.sh"
    run_file.write_text("#!/bin/bash\necho ok\n")

    res = validate_job(tmp_path)
    assert res["valid"] is True
    assert res["has_requirements"] is False

    # Check executable bit was set
    mode = run_file.stat().st_mode
    assert bool(mode & stat.S_IXUSR)


def test_validator_with_requirements(tmp_path):
    (tmp_path / "run.sh").write_text("#!/bin/bash\n")
    (tmp_path / "requirements.txt").write_text("numpy\n")

    res = validate_job(tmp_path)
    assert res["valid"] is True
    assert res["has_requirements"] is True


def test_validator_missing_run_sh(tmp_path):
    (tmp_path / "main.py").write_text("print('no run.sh')\n")

    with pytest.raises(ValidationError, match="run.sh"):
        validate_job(tmp_path)
