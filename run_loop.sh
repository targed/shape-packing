#!/usr/bin/env bash
# run_loop.sh — autoresearch loop: repeatedly invoke train.py --auto-select
cd /Users/kaiserluke/Documents/Git/shape-packing
while true; do
  uv run train.py --auto-select 2>&1 | grep -E '(chosen problem|NEW RECORD|score:)' || true
  sleep 1
done