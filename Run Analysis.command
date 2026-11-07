#!/bin/bash
# Double-click to run the whole analysis (macOS).
cd "$(dirname "$0")"
echo "=== The UK Succession Crisis ==="
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 isn't installed. Get it from https://www.python.org/downloads/"
  read -n 1 -s -r -p "Press any key to close"; exit 1
fi
python3 -c "import requests, pandas, matplotlib, numpy" 2>/dev/null || {
  echo "Installing the libraries this needs (one-time)..."
  python3 -m pip install --user requests pandas matplotlib numpy
}
caffeinate -i python3 run_analysis.py
open output 2>/dev/null
read -n 1 -s -r -p "Press any key to close"
