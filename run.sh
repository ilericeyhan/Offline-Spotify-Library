#!/bin/bash
source venv/bin/activate
# Clear caches to ensure latest code runs
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
python3 main.py

