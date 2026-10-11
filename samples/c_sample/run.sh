#!/usr/bin/env bash
set -e
echo "===> Compiling C program..."
make
echo "===> Running compiled binary..."
./sieve
