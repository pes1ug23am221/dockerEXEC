# Containerised Code Execution Platform

A self-hosted remote execution service that accepts user ZIP archives through a web interface, runs them in isolated Docker containers with live log streaming, and supports Python, Node.js, and C/C++ workloads out of the box.

Built with FastAPI, Docker, WebSockets, and SQLite.

---

## Features

- **Multi-language execution** — Python, Node.js, and C/C++ supported. The server automatically detects the language from the workspace and selects the right Docker image.
- **Live log streaming** — output from the running container streams line-by-line to the browser over WebSocket in real time.
- **Isolated sandboxing** — every job runs in an ephemeral Docker container with CPU and memory limits, destroyed after execution.
- **Single-use access codes** — the admin generates one-time codes (`ACC-XXXX-XXXX`) and shares them with users. Each code can only start one job and is burned the moment the container begins executing.
- **Crash-proof job queue** — jobs are persisted to an SQLite database before execution. If the server restarts mid-job, recovered jobs are automatically detected and marked failed on the next boot.
- **Server busy feedback** — when all execution slots are occupied, queued users see their live position (`Queued at #2`) and are promoted automatically when a slot opens.
- **Admin portal** — real-time dashboard at `/admin` to generate codes, monitor their status (unused / used / revoked), and filter by state.
- **Output download** — after execution, the user can download a ZIP of all files generated inside the container.

---

## Architecture

```
User Browser
     │
     ├── POST /api/jobs  (upload ZIP + access code)
     │        │
     │        └── Validate code → Extract ZIP → Validate workspace → Create metadata
     │
     └── WebSocket /ws/jobs/{id}/execute
              │
              ├── Verify code (pre-queue check, does NOT burn it yet)
              ├── Persist job to SQLite queue  (state: QUEUED)
              │
              ├── [if busy] → send queue position to client
              ├── await semaphore slot
              │
              ├── state: DISPATCHED
              ├── Burn access code  (single-use, burned here — not before)
              ├── Notify admin dashboard (WebSocket broadcast)
              │
              ├── state: RUNNING
              ├── docker run  (ephemeral container, CPU/memory limits)
              │        └── stdout/stderr streamed line-by-line to client
              │
              └── state: COMPLETED / FAILED
```

### Image selection

| Workspace contains | Docker image used |
|---|---|
| `package.json` | `executor-polyglot:latest` (Node.js 20 + Python + GCC) |
| `Makefile` or `CMakeLists.txt` | `executor-polyglot:latest` |
| Python-only or empty | `executor-base:latest` (Python 3.11-slim, smaller) |

---

## Project Structure

```
.
├── docker/                   # Docker image definitions
│   ├── Dockerfile.base       # Python 3.11-slim + numpy + pandas
│   ├── Dockerfile.polyglot   # Ubuntu 22.04 + Python + Node.js 20 + GCC/Make
│   └── Dockerfile.server     # Server deployment image
│
├── executor/                 # Core execution engine
│   ├── extractor.py          # Safe ZIP extraction (Zip Slip prevention, size limits)
│   ├── validator.py          # Workspace validation (run.sh required)
│   ├── runner.py             # DockerRunner — async subprocess, live log streaming
│   ├── job_queue.py          # SQLite-backed durable job queue
│   ├── credits.py            # Single-use access code store
│   ├── metadata.py           # Job metadata read/write
│   ├── admin.py              # Admin CLI (generate, list, revoke codes)
│   └── cli.py                # Local CLI runner
│
├── server/                   # FastAPI web server
│   ├── app.py                # All routes, WebSocket handlers, concurrency gate
│   └── static/
│       ├── index.html        # User dashboard
│       └── admin.html        # Admin portal
│
├── tests/                    # Test suite (39 tests)
│   ├── test_api.py
│   ├── test_credits.py
│   ├── test_extractor.py
│   ├── test_job_queue.py
│   ├── test_queue.py
│   ├── test_runner_polyglot.py
│   └── test_validator.py
│
├── samples/                  # Sample job archives for testing
│   ├── sample_lesser_libs.zip   # Python, pre-installed libs only
│   ├── sample_more_libs.zip     # Python, installs extra libs via requirements.txt
│   ├── sample_nodejs.zip        # Node.js, installs npm package
│   └── sample_c.zip             # C, compiles with gcc via Makefile
│
├── k8s/                      # Kubernetes manifests (multi-node scaling)
│   ├── deployment.yaml
│   └── job-template.yaml
│
├── docs/
│   └── improvement_plan.md   # Architecture roadmap
│
├── data/                     # Runtime data (gitignored)
│   ├── access_codes.json     # Active access codes
│   └── queue.db              # Durable job queue (SQLite)
│
├── jobs/                     # Job workspaces (gitignored)
│
├── build_images.sh           # Builds both Docker images
├── run_server.sh             # Starts the server
└── requirements.txt          # Python dependencies
```

---

## Setup

### Prerequisites

- Docker 20+
- Python 3.11+

### 1. Clone and install dependencies

```bash
git clone https://github.com/your-username/containerised-executor.git
cd containerised-executor

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Build Docker images

```bash
./build_images.sh
```

This builds:
- `executor-base:latest` — used for Python-only jobs
- `executor-polyglot:latest` — used for Node.js and C/C++ jobs

### 3. Start the server

```bash
./run_server.sh 8000
```

- User dashboard: [http://localhost:8000](http://localhost:8000)
- Admin portal: [http://localhost:8000/admin](http://localhost:8000/admin)

---

## Usage

### Admin: generate an access code

```bash
# Via CLI
python -m executor.admin generate --note "for Alice"

# Via Admin Portal
# Open http://localhost:8000/admin → enter a note → click Generate
```

The code looks like: `ACC-A3F2-9K1B`

Share it with the user. It can only be used once.

### User: submit a job

1. Open [http://localhost:8000](http://localhost:8000)
2. Drag and drop a ZIP file containing your code
3. Enter the access code
4. Click **Run** — logs stream live in the terminal panel
5. Download results when done

### ZIP format

Your ZIP must contain a `run.sh` at its root. The server calls `bash run.sh` inside the container.

**Python example:**
```
my_job/
├── run.sh
├── main.py
└── requirements.txt   (optional — installed automatically)
```

**Node.js example:**
```
my_job/
├── run.sh
├── main.js
└── package.json       (optional — npm install runs automatically)
```

**C example:**
```
my_job/
├── run.sh
├── main.c
└── Makefile           (presence triggers polyglot image with GCC)
```

---

## Running Tests

```bash
pytest tests/ -v
# 39 passed
```

---

## Configuration

| Environment variable | Default | Description |
|---|---|---|
| `MAX_CONCURRENT_JOBS` | `1` | Maximum containers running simultaneously |
| `PORT` | `8000` | Server port (set in `run_server.sh`) |

---

## Security Notes

- All ZIP extraction uses Zip Slip protection (no path traversal possible)
- Containers run with CPU and memory caps (`--cpus 2 --memory 2g`)
- Access codes are single-use and burned only when execution starts, not when queued
- Code is not burned if the user disconnects while waiting in queue

---

## Roadmap

See [`docs/improvement_plan.md`](docs/improvement_plan.md) for the full roadmap.

**Remaining:**
- Kubernetes dispatcher — submit jobs as `batch/v1 Job` objects and distribute across nodes

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI |
| Real-time streaming | WebSockets (native browser API) |
| Container runtime | Docker |
| Job queue | SQLite (WAL mode) |
| Frontend | Vanilla HTML/CSS/JS |
| Tests | pytest |
