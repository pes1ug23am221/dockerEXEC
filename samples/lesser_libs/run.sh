#!/bin/bash
set -e
echo "=========================================="
echo "Starting job: lesser_libs (base image only)"
echo "Python version: $(python --version)"
echo "=========================================="

python main.py

echo "=========================================="
echo "Job lesser_libs completed successfully!"
echo "=========================================="
