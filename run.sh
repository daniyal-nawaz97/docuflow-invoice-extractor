#!/usr/bin/env bash
# Start DocuFlow locally: ./run.sh   then open http://localhost:8001
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Creating virtual environment and installing packages (first run only)..."
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip -q
  .venv/bin/pip install -r requirements.txt
fi
[ -f .env ] || cp .env.example .env
[ -f sample_data/ground_truth.json ] || .venv/bin/python -m scripts.make_samples
echo "DocuFlow running at http://localhost:${PORT:-8001}  (landing page: /landing)"
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8001}"
