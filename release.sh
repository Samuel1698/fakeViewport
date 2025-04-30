#!/usr/bin/env bash
set -euo pipefail

# grab the tag (or fallback to commit SHA)
VERSION=$(git describe --tags --abbrev=0 2>/dev/null || git rev-parse --short HEAD)
OUTDIR=dist
mkdir -p "$OUTDIR"

# 1️⃣ Full repo
git archive \
  --format=tar.gz \
  --prefix="viewport ${VERSION}/" \
  -o "${OUTDIR}/viewport-full-${VERSION}.tar.gz" \
  HEAD

# 2️⃣ Minimal: only runtime files (adjust to your needs)
# you can keep a list in a text file, or enumerate here:
git archive \
  --format=tar.gz \
  --prefix="viewport ${VERSION}/" \
  -o "${OUTDIR}/viewport-minimal-${VERSION}.tar.gz" \
  HEAD \
    viewport.py \
    monitoring.py \
    templates/ \
    static/main-min.js \
    static/main.css \
    static/favicon* \
    setup.sh \
    config.ini.example \
    .env.example \
    css_selectors.py \
    logging_config.py \
    requirements.txt

# 3️⃣ Barebones: viewport.py + deps
git archive \
  --format=tar.gz \
  --prefix="viewport ${VERSION}/" \
  -o "${OUTDIR}/viewport-minimal-no-api-${VERSION}.tar.gz" \
  HEAD \
    viewport.py \
    setup.sh \
    config.ini.example \
    .env.example \
    css_selectors.py \
    logging_config.py \
    requirements.txt

echo "Created:"
ls -1 "${OUTDIR}"
