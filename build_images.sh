#!/usr/bin/env bash
# build_images.sh
# Builds all executor Docker images.
# Run this once before starting the server.
set -e

echo "===> Building executor-base:latest (Python 3.11-slim + numpy + pandas)..."
docker build -f docker/Dockerfile.base -t executor-base:latest .
echo "[OK] executor-base:latest built."

echo ""
echo "===> Building executor-polyglot:latest (Python 3.11 + Node.js 20 + GCC/Make)..."
docker build -f docker/Dockerfile.polyglot -t executor-polyglot:latest .
echo "[OK] executor-polyglot:latest built."

echo ""
echo "Images available:"
docker images | grep -E "executor-(base|polyglot)"
