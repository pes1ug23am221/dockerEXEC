import asyncio
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Any, List, Optional

from executor.metadata import update_metadata, now_iso

# ── Image registry ─────────────────────────────────────────────────────────────
IMAGE_BASE = "executor-base:latest"        # Python 3.11-slim only
IMAGE_POLYGLOT = "executor-polyglot:latest"  # Python + Node.js + C/C++

DEFAULT_TIMEOUT_SECONDS = 300  # 5 minutes

# Markers that indicate a polyglot image is needed
_POLYGLOT_MARKERS = ("package.json", "Makefile", "CMakeLists.txt")


def detect_image(workspace: Path) -> str:
    """
    Auto-selects the Docker image based on what's in the workspace.

    Rules (first match wins):
      - package.json present  →  needs Node.js  →  polyglot
      - Makefile / CMakeLists.txt present  →  needs GCC  →  polyglot
      - requirements.txt or .py files only  →  base (Python-only, smaller)
    """
    for marker in _POLYGLOT_MARKERS:
        if (workspace / marker).exists():
            return IMAGE_POLYGLOT
    return IMAGE_BASE


def _build_bash_command(workspace: Path) -> str:
    """
    Generates the bash pre-script that runs inside the container before run.sh.

    Dependency installers (run in order if their trigger file exists):
      requirements.txt   →  pip install
      package.json       →  npm install
      Makefile           →  make (treated as a build step, not a dep installer)
    """
    lines = ["set -e"]

    # Python deps
    lines += [
        "if [ -f requirements.txt ]; then",
        "  echo '===> [Executor] Installing Python dependencies from requirements.txt...'",
        "  pip install --no-cache-dir -r requirements.txt",
        "fi",
    ]

    # Node.js deps
    lines += [
        "if [ -f package.json ]; then",
        "  echo '===> [Executor] Installing Node.js dependencies from package.json...'",
        "  npm install --prefer-offline 2>&1",
        "fi",
    ]

    lines += [
        "echo '===> [Executor] Starting execution of run.sh...'",
        "bash run.sh",
    ]

    return "\n".join(lines) + "\n"


class DockerRunner:
    def __init__(
        self,
        image: Optional[str] = None,   # None = auto-detect from workspace
        cpu_limit: Optional[str] = "2",
        memory_limit: Optional[str] = "2g",
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ):
        self._image_override = image
        self.cpu_limit = cpu_limit
        self.memory_limit = memory_limit
        self.timeout = timeout

    async def run_job(
        self,
        job_dir: Path,
        workspace: Path,
        on_log: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Executes a job in an isolated Docker container, streaming logs live
        and updating metadata.

        Image selection:
          - If an image was explicitly passed to __init__, that image is used.
          - Otherwise auto-detect: polyglot if package.json / Makefile present,
            base (Python-only) otherwise.
        """
        job_dir = Path(job_dir).resolve()
        workspace = Path(workspace).resolve()
        log_file_path = workspace / "execution.log"

        # ── Image auto-detection ───────────────────────────────────────────────
        image = self._image_override or detect_image(workspace)

        container_name = f"exec_{job_dir.name[:16]}_{int(time.time())}"
        start_time = time.time()
        start_iso = now_iso()

        update_metadata(job_dir, status="running", started_at=start_iso)

        # Snapshot initial files before execution
        initial_files = {
            p.relative_to(workspace)
            for p in workspace.rglob("*")
            if p.is_file()
        }

        bash_command = _build_bash_command(workspace)

        docker_cmd = [
            "docker", "run", "--rm",
            "--name", container_name,
            "-v", f"{workspace}:/workspace",
            "-w", "/workspace",
            "-e", "PYTHONUNBUFFERED=1",
            "-e", "NODE_NO_WARNINGS=1",
        ]

        if self.cpu_limit:
            docker_cmd.extend(["--cpus", str(self.cpu_limit)])
        if self.memory_limit:
            docker_cmd.extend(["--memory", str(self.memory_limit)])

        docker_cmd.extend([image, "bash", "-c", bash_command])

        exit_code = -1
        error_msg = None

        with open(log_file_path, "a", encoding="utf-8") as log_f:
            header = (
                f"=== Job {job_dir.name} | Image: {image} | "
                f"Started: {start_iso} ===\n"
            )
            log_f.write(header)
            log_f.flush()
            if on_log:
                on_log(header.strip())

            process = None
            try:
                process = await asyncio.create_subprocess_exec(
                    *docker_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )

                # Stream stdout/stderr line-by-line
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace")
                    log_f.write(decoded)
                    log_f.flush()
                    if on_log:
                        on_log(decoded.rstrip("\r\n"))

                exit_code = await asyncio.wait_for(
                    process.wait(), timeout=self.timeout
                )

            except asyncio.TimeoutError:
                error_msg = f"Job exceeded timeout of {self.timeout}s"
                exit_code = 124
                subprocess.run(["docker", "kill", container_name], capture_output=True)
                msg = f"\n===> [Executor Error] {error_msg}\n"
                log_f.write(msg)
                if on_log:
                    on_log(msg.strip())

            except Exception as e:
                error_msg = str(e)
                exit_code = 1
                msg = f"\n===> [Executor Error] Execution failed: {e}\n"
                log_f.write(msg)
                if on_log:
                    on_log(msg.strip())

        duration = round(time.time() - start_time, 2)
        finish_iso = now_iso()
        status = "completed" if exit_code == 0 else "failed"

        # Detect output files generated during execution
        final_files = {
            p.relative_to(workspace)
            for p in workspace.rglob("*")
            if p.is_file()
        }
        new_files = [
            str(p)
            for p in (final_files - initial_files)
            if p.name not in ("execution.log", "metadata.json")
        ]

        meta = update_metadata(
            job_dir,
            status=status,
            finished_at=finish_iso,
            duration_seconds=duration,
            exit_code=exit_code,
            error=error_msg,
            generated_files=new_files,
        )

        return meta
