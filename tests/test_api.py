import io
import zipfile
import pytest
from fastapi.testclient import TestClient
from server.app import app
from executor.credits import generate_code

client = TestClient(app)


def test_api_upload_invalid_file_extension():
    code = generate_code()["code"]
    res = client.post(
        "/api/jobs",
        files={"file": ("test.txt", b"plain text", "text/plain")},
        data={"code": code},
    )
    assert res.status_code == 400
    assert "Only .zip files" in res.json()["detail"]


def test_api_upload_valid_zip():
    code = generate_code()["code"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("run.sh", "#!/bin/bash\necho test\n")
        z.writestr("script.py", "print('hello')\n")
    buf.seek(0)

    res = client.post(
        "/api/jobs",
        files={"file": ("valid_job.zip", buf.getvalue(), "application/zip")},
        data={"code": code},
    )
    assert res.status_code == 200
    data = res.json()
    assert "job_id" in data
    assert data["status"] == "prepared"
    assert data["has_requirements"] is False

    # Check status endpoint
    status_res = client.get(f"/api/jobs/{data['job_id']}/status")
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "prepared"


def test_api_upload_zip_missing_run_sh():
    code = generate_code()["code"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("script.py", "print('hello')\n")
    buf.seek(0)

    res = client.post(
        "/api/jobs",
        files={"file": ("invalid.zip", buf.getvalue(), "application/zip")},
        data={"code": code},
    )
    assert res.status_code == 400
    assert "Validation error" in res.json()["detail"]
