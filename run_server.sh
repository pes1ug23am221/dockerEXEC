#!/usr/bin/env bash
set -e

PORT=${1:-8000}
echo "=========================================================="
echo " Starting Distributed Containerized Python Executor Server"
echo " Web UI & API: http://localhost:${PORT}"
echo " WebSocket:    ws://localhost:${PORT}/ws/jobs/{id}/execute"
echo "=========================================================="

.venv/bin/uvicorn server.app:app --host 0.0.0.0 --port "${PORT}" --reload
