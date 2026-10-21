#!/usr/bin/env bash
# Build the standalone GUI executable for the current OS into dist/.
# Requires: pip install -e ".[build]" and the spaCy model (python -m spacy download en_core_web_lg).
set -euo pipefail
cd "$(dirname "$0")/.."

pyinstaller --noconfirm --clean --windowed --name PII-rip \
  --paths src \
  --collect-all en_core_web_lg \
  --collect-all spacy \
  --collect-all presidio_analyzer \
  --collect-all tkinterdnd2 \
  --collect-data piirip \
  packaging/piirip-gui.py
