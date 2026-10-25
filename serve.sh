#!/bin/sh
# Serve the app locally and save army lists as JSON files in ./armies
cd "$(dirname "$0")" && python3 server.py "${1:-8000}"
