import asyncio
import io
import json
import os
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from executor.extractor import extract_job, ExtractionSecurityError
from executor.validator import validate_job, ValidationError
from executor.metadata import create_metadata, load_metadata, update_metadata
from executor.runner import DockerRunner
from executor.credits import verify_code, redeem_code, generate_code, list_codes, revoke_code
from executor.job_queue import (
    init_db, enqueue, transition, get_job, list_jobs as list_queue_jobs,
    get_recoverable_jobs, queue_position, pending_count,
    QUEUED, DISPATCHED, RUNNING, COMPLETED, FAILED,
)

BASE_DIR = Path(__file__).resolve().parent.parent
JOBS_DIR = BASE_DIR / "jobs"
SAMPLES_DIR = BASE_DIR / "samples"
STATIC_DIR = BASE_DIR / "server" / "static"

JOBS_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)


import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Server startup: initialise durable queue and recover interrupted jobs."""
    init_db()
    recovered = get_recoverable_jobs()
    if recovered:
        logger.warning(
            "[Recovery] Found %d job(s) in an incomplete state from a previous run. "
            "Re-queuing them as FAILED so they can be retried.",
            len(recovered),
        )
        for rec in recovered:
            transition(rec["job_id"], FAILED, error_msg="Server restarted before job completed")
            job_dir = JOBS_DIR / rec["job_id"]
            if job_dir.exists():
                update_metadata(job_dir, status="failed")
            logger.warning("[Recovery] Marked job %s as FAILED.", rec["job_id"])
    else:
        logger.info("[Queue] Durable queue initialised. No interrupted jobs found.")
    yield
    # (shutdown logic can be added here if needed)


app = FastAPI(title="Containerised Python Executor API", version="1.0.0", lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/codes/verify/{code}")
async def check_access_code(code: str):
    """Checks validity of a single-use access code."""
    valid, reason, record = verify_code(code)
    if not valid:
        raise HTTPException(status_code=400, detail=reason)
    return {
        "valid": True,
        "code": record["code"],
        "status": record["status"],
    }


# Concurrency & Worker Queue Management
MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "1"))
execution_semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
active_jobs: set[str] = set()
waiting_clients: list[tuple[str, WebSocket]] = []


async def notify_waiting_queue():
    """Broadcasts updated queue positions to all waiting clients."""
    for idx, (w_job_id, ws) in enumerate(list(waiting_clients)):
        try:
            await ws.send_json({
                "type": "busy",
                "position": idx + 1,
                "total_waiting": len(waiting_clients),
                "active_jobs": len(active_jobs),
                "max_slots": MAX_CONCURRENT_JOBS,
                "message": f"Server is busy ({len(active_jobs)}/{MAX_CONCURRENT_JOBS} active slots). You are in queue at position #{idx + 1}.",
            })
        except Exception:
            pass


admin_subscribers: set[WebSocket] = set()


async def broadcast_code_change():
    """Notifies all connected admin UI clients that code state changed."""
    to_remove = set()
    for ws in list(admin_subscribers):
        try:
            await ws.send_json({"type": "codes_updated"})
        except Exception:
            to_remove.add(ws)
    for ws in to_remove:
        admin_subscribers.discard(ws)


@app.websocket("/ws/admin/updates")
async def ws_admin_updates(websocket: WebSocket):
    """Real-time WebSocket connection for admin dashboard auto-updates."""
    await websocket.accept()
    admin_subscribers.add(websocket)
    try:
        while True:
            # Keep socket open and await any heartbeat/ping
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        admin_subscribers.discard(websocket)


@app.post("/api/admin/codes/generate")
async def api_generate_code(note: str = ""):
    """Admin endpoint to generate a new single-use access code."""
    record = generate_code(note=note)
    await broadcast_code_change()
    return record


@app.get("/api/admin/codes")
async def api_list_codes():
    """Admin endpoint to list all access codes."""
    return list_codes()


@app.post("/api/admin/codes/revoke")
async def api_revoke_code(code: str = Form(...)):
    """Admin endpoint to revoke an access code."""
    success = revoke_code(code)
    if not success:
        raise HTTPException(status_code=404, detail="Code not found")
    await broadcast_code_change()
    return {"status": "revoked", "code": code}


@app.get("/admin")
async def admin_portal():
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/api/admin/queue")
async def api_list_queue(state: str | None = None):
    """
    Admin endpoint to inspect the durable job queue.
    Optionally filter by state: QUEUED, DISPATCHED, RUNNING, COMPLETED, FAILED.
    """
    return list_queue_jobs(state=state.upper() if state else None)


@app.post("/api/jobs")
async def create_job(
    file: UploadFile = File(...),
    code: str = Form(...),
):
    """
    Accepts a ZIP file and a single-use access code.
    Extracts safely, validates run.sh, and initializes metadata.
    """
    code_str = code.strip().upper()

    # 1. Verify access code is unused
    is_valid, reason, record = verify_code(code_str)
    if not is_valid:
        raise HTTPException(status_code=402, detail=reason)

    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted.")

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    job_dir = JOBS_DIR / job_id
    workspace = job_dir / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    temp_zip_path = job_dir / f"upload_{file.filename}"
    with open(temp_zip_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        extract_job(temp_zip_path, workspace)
        validation_info = validate_job(workspace)
        create_metadata(job_dir, source_zip=file.filename)
        update_metadata(
            job_dir,
            has_requirements=validation_info["has_requirements"],
            access_code=code_str,
        )
    except ExtractionSecurityError as e:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Security error: {str(e)}")
    except ValidationError as e:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Validation error: {str(e)}")
    except Exception as e:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Internal extraction error: {str(e)}")

    return {
        "job_id": job_id,
        "status": "prepared",
        "has_requirements": validation_info["has_requirements"],
        "access_code": code_str,
        "message": "Job prepared successfully. Access code will be redeemed upon execution start.",
    }


@app.get("/api/jobs/{job_id}/status")
async def get_job_status(job_id: str):
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    return load_metadata(job_dir)


@app.websocket("/ws/jobs/{job_id}/execute")
async def ws_execute_job(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint with durable queue persistence, concurrency limiting,
    real-time busy feedback, and safe single-use access code burning.

    Queue state transitions:
      QUEUED → (slot acquired) → DISPATCHED → (container starts) → RUNNING
           → (container exits ok) → COMPLETED
           → (error/crash/disconnect) → FAILED
    """
    await websocket.accept()

    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        await websocket.send_json({"type": "error", "message": "Job ID not found"})
        await websocket.close()
        return

    meta = load_metadata(job_dir)
    access_code = meta.get("access_code")

    # Pre-validate access code before entering queue
    valid, reason, _ = verify_code(access_code)
    if not valid:
        await websocket.send_json({"type": "error", "message": f"Authorization error: {reason}"})
        await websocket.close()
        return

    # --- Persist to durable queue (idempotent) ---
    enqueue(job_id, access_code)

    slot_acquired = False
    in_waiting_list = False
    execution_started = False

    try:
        # Check if server is currently busy
        if len(active_jobs) >= MAX_CONCURRENT_JOBS:
            waiting_clients.append((job_id, websocket))
            in_waiting_list = True
            pos = len(waiting_clients)
            await websocket.send_json({
                "type": "busy",
                "position": pos,
                "total_waiting": pos,
                "active_jobs": len(active_jobs),
                "max_slots": MAX_CONCURRENT_JOBS,
                "message": (
                    f"All execution slots are currently busy ({len(active_jobs)}/{MAX_CONCURRENT_JOBS} active). "
                    f"Your task has been queued at position #{pos}. Waiting for next available slot..."
                ),
            })

        # Block until an execution slot opens
        await execution_semaphore.acquire()
        slot_acquired = True

        if in_waiting_list:
            if (job_id, websocket) in waiting_clients:
                waiting_clients.remove((job_id, websocket))
            in_waiting_list = False
            await notify_waiting_queue()

        active_jobs.add(job_id)

        # Mark DISPATCHED in durable queue
        transition(job_id, DISPATCHED)

        await websocket.send_json({
            "type": "slot_acquired",
            "message": "Worker slot acquired! Redeeming access code and starting container...",
        })

        # Burn the single-use access code — only now, not before
        success, redeem_msg = redeem_code(access_code, job_id)
        if not success:
            transition(job_id, FAILED, error_msg=f"Authorization error: {redeem_msg}")
            await websocket.send_json({
                "type": "error",
                "message": f"Authorization error: {redeem_msg}",
            })
            return

        # Notify admin dashboards that code was consumed
        await broadcast_code_change()

        # Mark RUNNING — container is about to start
        transition(job_id, RUNNING)
        execution_started = True

        workspace = job_dir / "workspace"
        runner = DockerRunner()

        log_queue: asyncio.Queue[str] = asyncio.Queue()

        def handle_log(line: str):
            log_queue.put_nowait(line)

        async def sender_task():
            try:
                while True:
                    line = await log_queue.get()
                    if line is None:
                        break
                    await websocket.send_json({"type": "log", "line": line})
                    log_queue.task_done()
            except WebSocketDisconnect:
                pass
            except Exception:
                pass

        sender = asyncio.create_task(sender_task())

        await websocket.send_json({
            "type": "log",
            "line": f"[Access] Code {access_code} successfully redeemed for this job run.",
        })

        final_meta = await runner.run_job(job_dir, workspace, on_log=handle_log)
        await log_queue.put(None)
        await sender

        # Mark queue state based on exit code
        if final_meta.get("exit_code") == 0:
            transition(job_id, COMPLETED)
        else:
            transition(job_id, FAILED, error_msg=f"Container exited with code {final_meta.get('exit_code')}")

        await websocket.send_json({
            "type": "finish",
            "status": final_meta["status"],
            "exit_code": final_meta["exit_code"],
            "duration_seconds": final_meta["duration_seconds"],
            "generated_files": final_meta.get("generated_files", []),
        })

    except WebSocketDisconnect:
        if execution_started:
            transition(job_id, FAILED, error_msg="Client disconnected during execution")
    except Exception as e:
        if execution_started:
            transition(job_id, FAILED, error_msg=str(e))
        elif slot_acquired:
            # Failed after slot acquired but before container started
            transition(job_id, FAILED, error_msg=str(e))
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        if in_waiting_list and (job_id, websocket) in waiting_clients:
            waiting_clients.remove((job_id, websocket))
            await notify_waiting_queue()
        if job_id in active_jobs:
            active_jobs.remove(job_id)
        if slot_acquired:
            execution_semaphore.release()
        try:
            await websocket.close()
        except Exception:
            pass


@app.get("/api/jobs/{job_id}/download")
async def download_results(job_id: str):
    """Packages all workspace output files and logs into a results ZIP for download."""
    job_dir = JOBS_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job not found")

    workspace = job_dir / "workspace"

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for file_path in workspace.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(workspace)
                z.write(file_path, arcname=str(rel_path))

        meta_path = job_dir / "metadata.json"
        if meta_path.exists():
            z.write(meta_path, arcname="metadata.json")

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={job_id}_results.zip"},
    )


# Mount static web frontend
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
