#!/usr/bin/env bash
# Local dev runner: venv + deps + single poll (or --run for the loop).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

[ -f config/config.yaml ] || cp config/config.example.yaml config/config.yaml
[ -f .env ] || cp .env.example .env
mkdir -p data

exec python -m propertypresence.main --config config/config.yaml "${1:---once}"
