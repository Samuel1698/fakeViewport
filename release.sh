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
  -o "${OUTDIR}/viewport-${VERSION}-full.tar.gz" \
  HEAD

# 2️⃣ Minimal: only runtime files
git archive \
  --format=tar.gz \
  --prefix="viewport ${VERSION}/" \
  -o "${OUTDIR}/viewport-${VERSION}-minimal.tar.gz" \
  HEAD \
    viewport.py \
    monitoring.py \
    update.py \
    logging_config.py \
    validate_config.py \
    css_selectors.py \
    setup.sh \
    minimize.sh \
    uninstall.sh \
    requirements.txt \
    api/VERSION \
    templates/ \
    static/main-min.js \
    static/marked-min.js \
    static/main-min.css \
    static/favicon* \
    config.ini.example \
    .env.example

# 3️⃣ Barebones: viewport.py + deps
git archive \
  --format=tar.gz \
  --prefix="viewport ${VERSION}/" \
  -o "${OUTDIR}/viewport-${VERSION}-no-api.tar.gz" \
  HEAD \
    viewport.py \
    logging_config.py \
    validate_config.py \
    css_selectors.py \
    setup.sh \
    minimize.sh \
    uninstall.sh \
    requirements.txt \
    api/VERSION \
    config.ini.example \
    .env.example

echo "Created:"
ls -1 "${OUTDIR}"
