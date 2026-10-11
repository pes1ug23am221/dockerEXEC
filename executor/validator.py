import os
import stat
from pathlib import Path


class ValidationError(Exception):
    """Raised when job workspace fails validation."""
    pass


def validate_job(workspace: Path) -> dict:
    """
    Validates that run.sh exists at the workspace root and sets executable permissions.
    Returns summary dictionary with workspace checks.
    """
    workspace = Path(workspace).resolve()

    if not workspace.is_dir():
        raise ValidationError(f"Workspace directory does not exist: {workspace}")

    run_script = workspace / "run.sh"

    if not run_script.exists():
        raise ValidationError("Required script 'run.sh' not found at workspace root.")

    if not run_script.is_file():
        raise ValidationError("'run.sh' must be a regular file.")

    # Make run.sh executable
    current_mode = run_script.stat().st_mode
    run_script.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    has_requirements = (workspace / "requirements.txt").is_file()

    return {
        "valid": True,
        "run_script_path": str(run_script),
        "has_requirements": has_requirements,
    }
