import io
import zipfile
import pytest
from fastapi.testclient import TestClient

from executor.credits import generate_code, verify_code
from server.app import app

client = TestClient(app)


def test_busy_queue_messaging():
    # Generate 2 access codes
    code1 = generate_code(note="Job 1")["code"]
    code2 = generate_code(note="Job 2")["code"]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("run.sh", "#!/bin/bash\nsleep 0.4\necho done\n")
    buf.seek(0)
    zip_bytes = buf.getvalue()

    # Submit Job 1
    res1 = client.post("/api/jobs", files={"file": ("j1.zip", zip_bytes, "application/zip")}, data={"code": code1})
    assert res1.status_code == 200
    j1_id = res1.json()["job_id"]

    # Submit Job 2
    res2 = client.post("/api/jobs", files={"file": ("j2.zip", zip_bytes, "application/zip")}, data={"code": code2})
    assert res2.status_code == 200
    j2_id = res2.json()["job_id"]

    # Test WebSocket concurrency
    with client.websocket_connect(f"/ws/jobs/{j1_id}/execute") as ws1:
        # Job 1 gets slot
        msg1 = ws1.receive_json()
        assert msg1["type"] in ("slot_acquired", "log")

        # Now connect Job 2 while Job 1 is holding the slot
        with client.websocket_connect(f"/ws/jobs/{j2_id}/execute") as ws2:
            # Job 2 should receive busy notification
            busy_msg = ws2.receive_json()
            assert busy_msg["type"] == "busy"
            assert busy_msg["position"] == 1
            assert "busy" in busy_msg["message"].lower()

            # Wait for Job 1 to finish
            while True:
                m = ws1.receive_json()
                if m["type"] == "finish":
                    break

            # Now Job 2 receives slot_acquired
            while True:
                m2 = ws2.receive_json()
                if m2["type"] == "slot_acquired":
                    assert "acquired" in m2["message"].lower()
                    break

            # Wait for Job 2 to finish
            while True:
                m2 = ws2.receive_json()
                if m2["type"] == "finish":
                    break


def test_code_not_burned_if_cancelled_in_queue():
    code_active = generate_code(note="Active")["code"]
    code_queued = generate_code(note="Queued")["code"]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("run.sh", "#!/bin/bash\nsleep 1\necho done\n")
    buf.seek(0)
    zip_bytes = buf.getvalue()

    res1 = client.post("/api/jobs", files={"file": ("j1.zip", zip_bytes, "application/zip")}, data={"code": code_active})
    res2 = client.post("/api/jobs", files={"file": ("j2.zip", zip_bytes, "application/zip")}, data={"code": code_queued})
    j1_id = res1.json()["job_id"]
    j2_id = res2.json()["job_id"]

    with client.websocket_connect(f"/ws/jobs/{j1_id}/execute") as ws1:
        ws1.receive_json()  # slot_acquired

        # Job 2 connects and enters queue
        with client.websocket_connect(f"/ws/jobs/{j2_id}/execute") as ws2:
            busy = ws2.receive_json()
            assert busy["type"] == "busy"
            # Now client 2 disconnects before acquiring slot!

    # Check that code_queued is STILL unused!
    valid, reason, record = verify_code(code_queued)
    assert valid is True
    assert record["status"] == "unused"
