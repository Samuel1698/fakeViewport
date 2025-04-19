#!/bin/bash
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== UniFi Protect FakeViewport Setup ===${NC}"

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
    
    # Track installation success
    INSTALL_SUCCESS=true
    
    # Upgrade pip first (separate error check)
    if ! pip install --upgrade pip --quiet; then
        echo -e "${RED}✗ Failed to upgrade pip${NC}"
        INSTALL_SUCCESS=false
    fi
    
    # Install requirements (with retry logic)
    if ! pip install --quiet --trusted-host pypi.org --trusted-host files.pythonhosted.org --retries 3 --timeout 30 -r "$REQUIREMENTS"; then
        echo -e "${RED}✗ Failed to install some dependencies${NC}"
        echo -e "${YELLOW}This might be due to network issues."
        echo -e "Try manually running the command: "
        echo -e "pip install -r requirements.txt"
        INSTALL_SUCCESS=false
    fi
    
    if [ "$INSTALL_SUCCESS" = true ]; then
        echo -e "${GREEN}✓ All dependencies installed successfully${NC}"
        sleep 1
    else
        echo -e "${RED}!!! Dependency installation failed !!!${NC}"
        echo -e "${YELLOW}The script may not work properly.${NC}"
        exit 1  # Exit with error code
    fi
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
# 6: Rename DOTenv to .env
# -------------------------------------------------------------------
if [ -f "DOTenv" ]; then
    if [ -f ".env" ]; then
        echo -e "${GREEN}✓ .env already exists. Skipping...${NC}"
    else
        echo -e "${YELLOW}Renaming DOTenv to .env...${NC}"
        if mv -n DOTenv .env; then
            echo -e "${GREEN}✓ Configuration file prepared${NC}"
            echo -e "${YELLOW}Please edit .env to set your UniFi Protect credentials.${NC}"
            echo -e "${YELLOW}You can do so with the command: nano .env\n${NC}"
        else
            echo -e "${RED}Failed to rename DOTenv file!${NC}"
            exit 1
        fi
    fi
elif [ ! -f ".env" ]; then
    echo -e "${RED}Missing configuration file!${NC}"
    echo -e "${YELLOW}Either DOTenv or .env must exist${NC}"
    exit 1
fi
# -------------------------------------------------------------------
# 7: Rename config.ini.example to config.ini
# -------------------------------------------------------------------
if [ -f "config.ini.example" ]; then
    if [ -f "config.ini" ]; then
        echo -e "${GREEN}✓ config.ini already exists. Skipping...${NC}"
    else
        echo -e "${YELLOW}Renaming config.ini.example to config.ini...${NC}"
        if cp -n config.ini.example config.ini; then
            echo -e "${GREEN}✓ Configuration file prepared${NC}"
        else
            echo -e "${RED}Failed to rename configuration file!${NC}"
            exit 1
        fi
    fi
elif [ ! -f "config.ini" ]; then
    echo -e "${RED}Missing configuration file!${NC}"
    exit 1
fi
# -------------------------------------------------------------------
# 8: Create Desktop Shortcut
# -------------------------------------------------------------------
echo -e "${YELLOW}\nWould you like to create a desktop shortcut for FakeViewport? (y/n)${NC}"
read -r create_shortcut
if [[ "$create_shortcut" =~ ^[Yy]$ ]]; then
    DESKTOP_PATH="$HOME/Desktop"
    SHORTCUT_PATH="$DESKTOP_PATH/FakeViewport.desktop"
    SCRIPT_PATH="$(pwd)/protect.py"

    echo -e "${YELLOW}Creating desktop shortcut...${NC}"
    cat > "$SHORTCUT_PATH" <<EOL
[Desktop Entry]
Version=1.0
Name=FakeViewport
Comment=Run the FakeViewport script
Exec=$SCRIPT_PATH
Icon=camera-web
Terminal=false
Type=Application
Categories=Utility;
EOL

    chmod +x "$SHORTCUT_PATH"
    echo -e "${GREEN}✓ Desktop shortcut created at $SHORTCUT_PATH${NC}"
else
    echo -e "${GREEN}✓ Skipping desktop shortcut creation.${NC}"
fi
# -------------------------------------------------------------------
# Final Report
# -------------------------------------------------------------------
if [ "$INSTALL_SUCCESS" = false ]; then
    echo -e "\n${RED}SETUP INCOMPLETE - Some steps failed${NC}"
    echo -e "${YELLOW}Check the error messages above and try again.${NC}"
    exit 1
else
    echo -e "\n${GREEN}Setup complete! To launch the script, run:${NC}"
    echo -e "${YELLOW}  python3 protect.py${NC}"
    exit 0
fi