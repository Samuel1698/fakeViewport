#!/bin/bash

RED='\e[0;31m'
GREEN='\e[0;32m'
YELLOW='\e[1;33m'
NC='\e[0m'

echo -e "${YELLOW}===== FakeViewport Minimize =====${NC}"

if [[ "$1" =~ ^(-f|--force)$ ]]; then
    confirm="y"
else
    echo -ne "\n${YELLOW}This will delete all development files and tests. Continue? (y/n):${NC} "
    read -r confirm
fi

if [[ ! "$confirm" =~ ^[Yy]([Ee][Ss])?$ ]]; then
    echo -e "${GREEN}Aborted.${NC}"
    exit 0
fi

echo -e "${GREEN}Removing development files...${NC}"

# Function to remove files and print a green dot
remove_and_dot() {
    for target in "$@"; do
        if [ -e "$target" ]; then
            rm -rf "$target"
            echo -ne "${GREEN}.${NC}"
        fi
    done
}

# Remove known paths
remove_and_dot tests/ .github/ conftest.py requirements.in
remove_and_dot .pytest_cache/ .mypy_cache/ __pycache__/

# Remove *.md
find . -type f -name "*.md" -not -path "./venv/*" -print0 | while IFS= read -r -d '' file; do
    rm -f "$file" && echo -ne "${GREEN}.${NC}"
done

# Remove dev_* files
find . -type f -name "dev_*" -not -path "./venv/*" -print0 | while IFS= read -r -d '' file; do
    rm -f "$file" && echo -ne "${GREEN}.${NC}"
done

# Remove *.coveragerc and *release.sh
find . -type f \( -name "*.coveragerc" -o -name "release.sh" \) -not -path "./venv/*" -print0 | while IFS= read -r -d '' file; do
    rm -f "$file" && echo -ne "${GREEN}.${NC}"
done

# Delete static/*.scss and static/main.js
find ./static -type f \( -name "*.scss" -o -name "main.js" \) -print0 | while IFS= read -r -d '' file; do
    rm -f "$file" && echo -ne "${GREEN}.${NC}"
done

echo -e "\n${GREEN}Minimization complete.${NC}"
