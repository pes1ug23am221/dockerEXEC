import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_metadata(job_dir: Path, source_zip: Optional[str] = None) -> Dict[str, Any]:
    """Create initial metadata.json for a newly prepared job."""
    job_dir = Path(job_dir).resolve()
    metadata: Dict[str, Any] = {
        "job_id": job_dir.name,
        "status": "prepared",
        "created_at": now_iso(),
        "started_at": None,
        "finished_at": None,
        "duration_seconds": None,
        "source_archive": source_zip,
        "exit_code": None,
        "error": None,
        "generated_files": [],
    }

    metadata_file = job_dir / "metadata.json"
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)

    return metadata


def load_metadata(job_dir: Path) -> Dict[str, Any]:
    """Load metadata.json from job directory."""
    metadata_file = Path(job_dir) / "metadata.json"
    if not metadata_file.exists():
        raise FileNotFoundError(f"metadata.json not found in {job_dir}")
    with open(metadata_file, "r") as f:
        return json.load(f)


def update_metadata(job_dir: Path, **kwargs) -> Dict[str, Any]:
    """Update metadata.json with given keyword arguments."""
    job_dir = Path(job_dir).resolve()
    current = load_metadata(job_dir)
    current.update(kwargs)

    metadata_file = job_dir / "metadata.json"
    with open(metadata_file, "w") as f:
        json.dump(current, f, indent=2)

    return current
