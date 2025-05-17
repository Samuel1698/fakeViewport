#!/bin/bash
RED='\e[0;31m'
GREEN='\e[0;32m'
YELLOW='\e[1;33m'
NC='\e[0m'

echo -e "${YELLOW}===== FakeViewport Minimize =====${NC}"

read -p "${YELLOW}This will delete all development files and tests. Continue? (y/n):${NC} " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}Aborted.${NC}"
    exit 0
fi

echo "${GREEN}Removing development files...${NC}"

# Delete everything inside tests/ and .github/
rm -rf tests/
rm -rf .github/
# Delete conftest.py
rm -f conftest.py
# Delete all .md files (e.g., README.md)
find . -type f -name "*.md" -not -path "./venv/*" -delete
# Delete files that start with dev_
find . -type f -name "dev_*" -not -path "./venv/*" -delete
rm -f requirements.in
# Delete files ending in .coveragerc or .bak
find . -type f \( -name "*.coveragerc" -o -name "*.bak" \) -not -path "./venv/*" -delete
# Delete Python cache dirs
rm -rf .pytest_cache/ .mypy_cache/ __pycache__/
# Within static/, delete *.scss and main.js (but not other static content)
find ./static -type f \( -name "*.scss" -o -name "main.js" \) -delete
# Double check exclusions

echo -e "${GREEN}Minimization complete.${NC}"
