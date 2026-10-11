import io
import zipfile
import pytest
from fastapi.testclient import TestClient

from executor.credits import generate_code, verify_code, redeem_code, revoke_code, list_codes
from server.app import app

client = TestClient(app)


def test_code_generation_and_verification():
    record = generate_code(note="Unit test code")
    code = record["code"]

    valid, reason, data = verify_code(code)
    assert valid is True
    assert data["status"] == "unused"


def test_one_time_code_redemption():
    record = generate_code(note="Single use test")
    code = record["code"]

    # First redemption succeeds
    success, msg = redeem_code(code, "job_test_123")
    assert success is True
    assert "successfully redeemed" in msg

    # Second redemption attempt fails
    valid, reason, data = verify_code(code)
    assert valid is False
    assert "already used" in reason

    success2, msg2 = redeem_code(code, "job_test_456")
    assert success2 is False
    assert "already used" in msg2


def test_code_revocation():
    record = generate_code(note="Revoke test")
    code = record["code"]

    revoked = revoke_code(code)
    assert revoked is True

    valid, reason, data = verify_code(code)
    assert valid is False
    assert "revoked" in reason


def test_api_single_use_enforcement():
    # Build minimal valid ZIP
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("run.sh", "#!/bin/bash\necho ok\n")
    buf.seek(0)
    zip_bytes = buf.getvalue()

    code_record = generate_code(note="API single-use test")
    code = code_record["code"]

    # 1. First job creation with fresh code succeeds
    res_first = client.post(
        "/api/jobs",
        files={"file": ("test.zip", zip_bytes, "application/zip")},
        data={"code": code},
    )
    assert res_first.status_code == 200
    job_id = res_first.json()["job_id"]

    # Simulate execution (redeeming the code)
    redeem_code(code, job_id)

    # 2. Second job submission with the SAME code must fail
    res_second = client.post(
        "/api/jobs",
        files={"file": ("test2.zip", zip_bytes, "application/zip")},
        data={"code": code},
    )
    assert res_second.status_code == 402
    assert "already used" in res_second.json()["detail"]
