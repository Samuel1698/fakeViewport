#!/bin/bash

# -------------------------------------------------------------------
# UniFi Protect View Initialization Script
# -------------------------------------------------------------------
# Checks for Python 3, creates venv, installs requirements, and activates
# -------------------------------------------------------------------

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== UniFi Protect View Setup ===${NC}"

# -------------------------------------------------------------------
# 1. Verify Python 3 is installed
# -------------------------------------------------------------------
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 not found! Installing...${NC}"
    sudo apt update && sudo apt install -y python3
else
    echo -e "${GREEN}✓ Python 3 is already installed${NC}"
fi

# -------------------------------------------------------------------
# 2. Verify python3-venv is available
# -------------------------------------------------------------------
if ! python3 -c "import ensurepip; import venv" &> /dev/null; then
    echo -e "${RED}python3-venv not found! Installing...${NC}"
    sudo apt install -y python3-venv
else
    echo -e "${GREEN}✓ python3-venv is available${NC}"
fi

# -------------------------------------------------------------------
# 3. Create virtual environment (if doesn't exist)
# -------------------------------------------------------------------
VENV_DIR="venv"
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}✓ Virtual environment created${NC}"
else
    echo -e "${GREEN}✓ Virtual environment already exists${NC}"
fi

# -------------------------------------------------------------------
# 4. Install requirements
# -------------------------------------------------------------------
REQUIREMENTS="requirements.txt"
if [ -f "$REQUIREMENTS" ]; then
    echo -e "${YELLOW}Installing dependencies...${NC}"
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip
    pip install -r "$REQUIREMENTS"
    echo -e "${GREEN}✓ Dependencies installed${NC}"
else
    echo -e "${RED}requirements.txt not found!${NC}"
    exit 1
fi

# -------------------------------------------------------------------
# 5. Verify Chrome/Chromium and ChromeDriver
# -------------------------------------------------------------------
echo -e "${YELLOW}Checking browser dependencies...${NC}"
if ! command -v google-chrome-stable &> /dev/null; then
    if ! command -v chromium-browser &> /dev/null; then
        echo -e "${RED}Chrome/Chromium not found! Install manually:"
        echo -e "  sudo apt install -y chromium-browser${NC}"
    else
        echo -e "${GREEN}✓ Chromium is installed${NC}"
    fi
else
    echo -e "${GREEN}✓ Google Chrome is installed${NC}"
fi

# -------------------------------------------------------------------
# 6. Activate script
# -------------------------------------------------------------------
echo -e "\n${GREEN}Setup complete! To activate the script, run python3 protect.py"
