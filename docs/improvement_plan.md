# System Improvement & Evolution Plan

This document outlines the architectural roadmap, planned features, and implemented capabilities for the **Distributed Containerized Executor Platform**.

---

## 1. Feature Roadmap (Yet to be Implemented)

### 1. Multi-Node Distributed Cluster via Kubernetes
*Status: Priority 1 (Architecture Validated)*

#### Objective
Distribute container execution across **multiple physical or cloud server nodes** so that heavy concurrent jobs do not overwhelm a single machine.

#### How Kubernetes Solves Multi-Node Scaling:
```
                       [User Uploads Job]
                               │
                               ▼
               [API Server / Gateway Pod]
                               │
            Submits K8s Job to Kubernetes API
                               │
                               ▼
                [Kubernetes Kube-Scheduler]
       (Evaluates CPU, RAM, & GPU across all nodes)
                               │
     ┌─────────────────────────┼─────────────────────────┐
     ▼                         ▼                         ▼
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│ Worker Node 1│         │ Worker Node 2│         │ Worker Node 3│
│ (80% RAM -   │         │ (20% RAM -   │         │ (Free Node)  │
│  Busy)       │         │  Placing Pod)│         │              │
└──────────────┘         └──────────────┘         └──────────────┘
                               │
                     [Runs Container Pod]
                               │
               (Streams logs back to API Server)
```

1. **Intelligent Node Selection (Kube-Scheduler):**
   - The API server submits a standard Kubernetes `batch/v1 Job`.
   - The scheduler checks RAM, CPU, and disk capacity across all nodes in the cluster.
   - If Server Node 1 is busy running a heavy training task, Kubernetes automatically routes the new container to Server Node 2 or Server Node 3.
2. **Node Failure Resilience:**
   - If a physical server hardware fails mid-run, Kubernetes detects the node failure and reschedules the job on another healthy node.
3. **Cluster Autoscaling:**
   - In cloud environments (EKS, GKE, AKS), if all servers are at 100% capacity, the **Cluster Autoscaler** automatically spins up new physical/virtual server nodes on demand and shuts them down when idle.

---

### 2. Crash-Proof Durable Job Queue (SQLite)
*Status: **DONE***

#### What Was Built
- `executor/job_queue.py` — SQLite queue at `data/queue.db` with WAL mode for concurrent reads.
- State machine: `QUEUED` → `DISPATCHED` → `RUNNING` → `COMPLETED` / `FAILED`.
- **Crash recovery on server boot**: any job stuck in `QUEUED` or `DISPATCHED` is automatically detected and marked `FAILED` with a descriptive error message.
- `GET /api/admin/queue?state=RUNNING` — admin endpoint to inspect the live queue.
- 14 unit tests covering: enqueue idempotency, all state transitions, queue position ordering, pending count, and crash recovery detection.

---

### 2. Multi-Language Support (Option A: Polyglot Container)
*Status: **DONE***

#### What Was Built
- `Dockerfile.polyglot` — Ubuntu 22.04 + Python 3.11 + Node.js 20 LTS + GCC/G++/Make/CMake, tagged `executor-polyglot:latest`.
- `executor/runner.py` updated with `detect_image(workspace)`:
  - `package.json` present → Node.js needed → polyglot image
  - `Makefile` / `CMakeLists.txt` present → C/C++ needed → polyglot image
  - Python-only or empty → base image (smaller, faster)
- Bash pre-script auto-runs `pip install` (requirements.txt) **and/or** `npm install` (package.json) before `bash run.sh`.
- `build_images.sh` — one-command script to build both images.
- Sample archives: `sample_nodejs.zip` (Node.js + simple-statistics) and `sample_c.zip` (C sieve + Makefile).
- 10 unit tests covering all auto-detection cases and bash command generation.

---

## 2. Completed & Working Features

| Feature | Status | Details |
|---|---|---|
| **Multi-Language Polyglot Executor** | **DONE** | `Dockerfile.polyglot` (Python + Node.js + C/C++), auto image selection, npm/pip pre-installers, Node.js + C sample ZIPs, 10 passing tests. |
| **Crash-Proof Durable Job Queue** | **DONE** | SQLite queue (`data/queue.db`), WAL mode, state machine (QUEUED→DISPATCHED→RUNNING→COMPLETED/FAILED), boot crash recovery, `GET /api/admin/queue` inspection endpoint, 14 passing tests. |
| **Server Busy & Concurrency Gate** | **DONE** | Bounded execution slots (`MAX_CONCURRENT_JOBS`), live queue position notifications (`QUEUED (#1)`), and safe code burning only when execution actually starts. |
| **One-Time Access Codes** | **DONE** | Single-use codes (`ACC-XXXX-XXXX`), permanently burned upon job execution, reuse prevention. |
| **Admin Web Portal (`/admin`)** | **DONE** | Code generator, real-time WebSocket sync, status filter tabs (**All**, **Unused**, **Used**, **Revoked**). |
| **Admin CLI (`executor/admin.py`)** | **DONE** | CLI commands for generating, listing, inspecting, and revoking codes. |
| **Isolated Docker Runner** | **DONE** | Ephemeral container per job, volume mounts, dynamic dependency installation, and log preservation. |
| **Web Dashboard (`/`)** | **DONE** | Minimalist dark UI, drag-and-drop ZIP upload, live console streaming, and output ZIP download. |
| **Sample Test Archives** | **DONE** | Python (×2), Node.js, and C sample ZIPs for end-to-end testing. |
| **Automated Test Suite** | **DONE** | 39 passing unit and integration tests (`pytest tests/`). |

---

## 3. Remaining: Multi-Node Kubernetes Dispatcher

*Status: Architecture designed, not yet wired to live runner*

The K8s manifests exist in `k8s/`. The actual `DockerRunner` still uses `docker run` locally. To connect:
1. Replace `docker run` in `runner.py` with a `kubectl apply` of a `batch/v1 Job` manifest.
2. Stream pod logs via `kubectl logs -f`.
3. Mark job COMPLETED/FAILED based on pod exit status.
