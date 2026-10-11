#!/bin/bash
set -e
echo "=========================================="
echo "Starting job: more_libs (dynamic dependencies)"
echo "Python version: $(python --version)"
echo "=========================================="

python main.py

echo "=========================================="
echo "Job more_libs completed successfully!"
echo "=========================================="
