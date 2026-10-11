import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CODES_FILE = DATA_DIR / "access_codes.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_data_store():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CODES_FILE.exists():
        with open(CODES_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2)


def _load_all() -> Dict[str, Dict[str, Any]]:
    _ensure_data_store()
    try:
        with open(CODES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_all(data: Dict[str, Dict[str, Any]]):
    _ensure_data_store()
    with open(CODES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def generate_code(note: str = "") -> Dict[str, Any]:
    """Generates a new single-use access code."""
    data = _load_all()

    # Format: ACC-XXXX-XXXX
    random_part = secrets.token_hex(4).upper()
    code = f"ACC-{random_part[:4]}-{random_part[4:]}"

    record = {
        "code": code,
        "status": "unused",  # "unused", "used", "revoked"
        "created_at": _now_iso(),
        "used_at": None,
        "used_by_job": None,
        "note": note,
    }

    data[code] = record
    _save_all(data)
    return record


def verify_code(code: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Checks if a code is valid and unused.
    Returns (valid, error_reason, record).
    """
    if not code:
        return False, "Access code is required.", None

    code = code.strip().upper()
    data = _load_all()

    if code not in data:
        return False, "Invalid access code.", None

    record = data[code]
    status = record.get("status", "unused")

    if status == "used":
        return False, f"This access code was already used on {record.get('used_at')}.", record

    if status == "revoked":
        return False, "This access code has been revoked by admin.", record

    return True, "", record


def redeem_code(code: str, job_id: str) -> Tuple[bool, str]:
    """
    Permanently redeems/consumes a one-time access code for a specific job.
    Returns (success, message).
    """
    valid, reason, record = verify_code(code)
    if not valid:
        return False, reason

    code = code.strip().upper()
    data = _load_all()
    data[code]["status"] = "used"
    data[code]["used_at"] = _now_iso()
    data[code]["used_by_job"] = job_id

    _save_all(data)
    return True, f"Access code {code} successfully redeemed for {job_id}."


def list_codes() -> List[Dict[str, Any]]:
    """Returns a list of all one-time access codes."""
    data = _load_all()
    return list(data.values())


def revoke_code(code: str) -> bool:
    """Revokes an unused access code."""
    code = code.strip().upper()
    data = _load_all()
    if code in data:
        data[code]["status"] = "revoked"
        _save_all(data)
        return True
    return False
