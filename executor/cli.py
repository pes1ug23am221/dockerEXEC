import argparse
import asyncio
import sys
import uuid
from pathlib import Path

from executor.extractor import extract_job
from executor.validator import validate_job
from executor.metadata import create_metadata, load_metadata, update_metadata
from executor.runner import DockerRunner
from executor.credits import verify_code, redeem_code


def prepare_job(zip_path: Path, jobs_base_dir: Path = Path("jobs"), access_code: str = "") -> tuple[Path, Path]:
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    job_dir = jobs_base_dir / job_id
    workspace = job_dir / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    create_metadata(job_dir, source_zip=str(zip_path.name))
    if access_code:
        update_metadata(job_dir, access_code=access_code.strip().upper())

    extract_job(zip_path, workspace)
    validate_job(workspace)

    return job_dir, workspace


async def run_cli(args):
    zip_path = Path(args.zip_file)
    if not zip_path.exists():
        print(f"Error: Archive not found: {zip_path}", file=sys.stderr)
        sys.exit(1)

    code = getattr(args, "code", "").strip()
    if not args.no_code_check:
        if not code:
            print("Error: A single-use access code is required. Specify with --code <CODE>", file=sys.stderr)
            sys.exit(1)

        valid, reason, record = verify_code(code)
        if not valid:
            print(f"Error: Access authorization failed: {reason}", file=sys.stderr)
            sys.exit(1)

        print(f"--> [Access] Code verified ({code} is UNUSED).")

    print(f"--> [CLI] Preparing job for {zip_path.name}...")
    job_dir, workspace = prepare_job(zip_path, jobs_base_dir=Path(args.workdir), access_code=code)
    print(f"--> [CLI] Job ID: {job_dir.name}")
    print(f"--> [CLI] Workspace: {workspace}")

    if args.prepare_only:
        print("--> [CLI] Job prepared successfully (--prepare-only specified).")
        return

    # Redeem / burn the code for this run
    if not args.no_code_check and code:
        success, msg = redeem_code(code, job_dir.name)
        if not success:
            print(f"Error: Failed to redeem access code: {msg}", file=sys.stderr)
            sys.exit(1)
        print(f"--> [Access] Code {code} successfully redeemed for this job (now consumed).")

    runner = DockerRunner(
        image=args.image,
        cpu_limit=args.cpus,
        memory_limit=args.memory,
        timeout=args.timeout,
    )

    print(f"--> [CLI] Launching container for {job_dir.name}...")
    meta = await runner.run_job(
        job_dir=job_dir,
        workspace=workspace,
        on_log=lambda line: print(line),
    )

    print(f"\n==========================================")
    print(f"Job Status: {meta['status'].upper()} (Exit Code: {meta['exit_code']})")
    print(f"Duration: {meta['duration_seconds']}s")
    if meta.get("generated_files"):
        print(f"Generated Files: {', '.join(meta['generated_files'])}")
    print(f"Log file: {workspace / 'execution.log'}")
    print(f"==========================================")

    if meta["exit_code"] != 0:
        sys.exit(meta["exit_code"] or 1)


def main():
    parser = argparse.ArgumentParser(description="Distributed Containerized Python Executor")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run command
    run_parser = subparsers.add_parser("run", help="Prepare and execute job in Docker container")
    run_parser.add_argument("zip_file", type=str, help="Path to input ZIP archive")
    run_parser.add_argument("--code", type=str, default="", help="Single-use access code (e.g. ACC-XXXX-XXXX)")
    run_parser.add_argument("--no-code-check", action="store_true", help="Bypass code check for local testing")
    run_parser.add_argument("--workdir", type=str, default="jobs", help="Base directory for jobs")
    run_parser.add_argument("--image", type=str, default="executor-base:latest", help="Docker base image")
    run_parser.add_argument("--cpus", type=str, default="2", help="Container CPU limit")
    run_parser.add_argument("--memory", type=str, default="2g", help="Container memory limit")
    run_parser.add_argument("--timeout", type=int, default=300, help="Execution timeout in seconds")
    run_parser.add_argument("--prepare-only", action="store_true", help="Only prepare without executing")

    args = parser.parse_args()
    if args.command == "run":
        asyncio.run(run_cli(args))


if __name__ == "__main__":
    main()
