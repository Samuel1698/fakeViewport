#!/bin/bash
RED='\e[0;31m'
GREEN='\e[0;32m'
YELLOW='\e[1;33m'
NC='\e[0m'
SCRIPT_PATH="$(pwd)/viewport.py"
VENV_PYTHON="$(pwd)/venv/bin/python3"
echo -e "${YELLOW}===== FakeViewport Setup =====${NC}"

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
if [ "$1" == "dev" ]; then
    echo -e "${YELLOW}Development mode enabled. Using dev_requirements.txt.${NC}"
    REQUIREMENTS="dev_requirements.txt"
else
    REQUIREMENTS="requirements.txt"
fi
if [ -f "$REQUIREMENTS" ]; then
    # Activate virtual environment
    source "$VENV_DIR/bin/activate"
    # Track installation success
    INSTALL_SUCCESS=true
    # Upgrade pip first (separate error check)
    if ! pip install --upgrade pip --quiet; then
        echo -e "${RED}✗ Failed to upgrade pip${NC}"
        INSTALL_SUCCESS=false
    else
        echo -e "${GREEN}✓ Pip upgraded successfully${NC}"
    fi
    # Install requirements (with progress dots)
    if [ "$INSTALL_SUCCESS" = true ]; then
        echo -e "${YELLOW}Installing dependencies...${NC}"
        # Run pip install in the background
        pip install --quiet --trusted-host pypi.org --trusted-host files.pythonhosted.org -r "$REQUIREMENTS" &
        PIP_PID=$!
        # Print green dots while pip is running
        while kill -0 "$PIP_PID" 2>/dev/null; do
            echo -ne "${GREEN}.${NC}"
            sleep 0.5
        done
        # Wait for pip to finish and check the exit code
        wait "$PIP_PID"
        if [ $? -eq 0 ]; then
            echo -e "\n${GREEN}✓ All dependencies installed successfully${NC}"
        else
            echo -e "\n${RED}✗ Failed to install some dependencies${NC}"
            echo -e "${GREEN}This might be due to network issues.${NC}"
            echo -e "${GREEN}Activate the virtual environment and install manually:${NC} "
            echo -e "${YELLOW}  source ${VENV_DIR}/bin/activate${NC}"
            echo -e "${YELLOW}  pip install -r requirements.txt${NC}"
            INSTALL_SUCCESS=false
        fi
    fi
else
    echo -e "${RED}requirements.txt not found!${NC}"
    exit 1
fi
# -------------------------------------------------------------------
# 5. Verify Chrome/Chromium and ChromeDriver
# -------------------------------------------------------------------
if ! command -v google-chrome-stable &> /dev/null; then
    if ! command -v chromium &> /dev/null; then
        echo -e "${RED}Chrome/Chromium not found! Install manually:"
        echo -e "  sudo apt install -y chromium${NC}"
    else
        echo -e "${GREEN}✓ Chromium is installed${NC}"
    fi
else
    echo -e "${GREEN}✓ Google Chrome is installed${NC}"
fi
# -------------------------------------------------------------------
# 6: Rename .env.example to .env
# -------------------------------------------------------------------
if [ -f ".env.example" ]; then
    if [ -f ".env" ]; then
        echo -e "${GREEN}✓ .env already exists. Skipping...${NC}"
    else
        echo -e "${YELLOW}Renaming .env.example to .env...${NC}"
        if mv -n .env.example .env; then
            echo -e "${GREEN}✓ Configuration file prepared${NC}"
            echo -e "${YELLOW}  Please edit .env to set your UniFi Protect credentials.${NC}"
            echo -e "${YELLOW}  You can do so with the command: nano .env\n${NC}"
        else
            echo -e "${RED}Failed to rename .env.example file!${NC}"
            exit 1
        fi
    fi
elif [ ! -f ".env" ]; then
    echo -e "${RED}Missing configuration file!${NC}"
    echo -e "${RED}Either .env.example or .env must exist${NC}"
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
echo -ne "${YELLOW}\nWould you like to create a desktop shortcut for FakeViewport (y/n)? ${NC}"
read -r create_shortcut
if [[ "$create_shortcut" =~ ^[Yy]([Ee][Ss])?$ ]]; then
    DESKTOP_PATH="$HOME/Desktop"
    SHORTCUT_PATH="$DESKTOP_PATH/Viewport.desktop"
    cat > "$SHORTCUT_PATH" <<EOL
[Desktop Entry]
Version=1.0
Name=Viewport
Comment=Run the Viewport script
Exec=$VENV_PYTHON $SCRIPT_PATH
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
# 9: Create an alias for running the script
# -------------------------------------------------------------------
ALIAS_NAME="viewport"
CREATED_ALIAS=false
# Check if the alias already exists in ~/.bashrc or ~/.zshrc
if grep -q "alias $ALIAS_NAME=" ~/.bashrc 2>/dev/null || grep -q "alias $ALIAS_NAME=" ~/.zshrc 2>/dev/null; then
    echo -e "${GREEN}✓ Alias '$ALIAS_NAME' already exists. Skipping...${NC}"
else
    echo -e "${YELLOW}Adding alias '$ALIAS_NAME' to your shell configuration...${NC}"
    # Add the alias to ~/.bashrc or ~/.zshrc
    if [ -f ~/.bashrc ]; then
        echo "# This alias was added by the FakeViewport setup script" >> ~/.bashrc
        echo "alias $ALIAS_NAME='$VENV_PYTHON $SCRIPT_PATH'" >> ~/.bashrc
        echo -e "${GREEN}✓ Alias added to ~/.bashrc${NC}"
        echo -e "${GREEN}If the viewport command doesn't work, reload the terminal with: ${NC}"
        echo -e "${YELLOW}  source ~/.bashrc${NC}"
        CREATED_ALIAS=true
    fi
    if [ -f ~/.zshrc ]; then
        echo "# This alias was added by the FakeViewport setup script" >> ~/.zshrc
        echo "alias $ALIAS_NAME='$VENV_PYTHON $SCRIPT_PATH'" >> ~/.zshrc
        echo -e "${GREEN}✓ Alias added to ~/.zshrc${NC}"
        echo -e "${GREEN}If the viewport command doesn't work, reload the terminal with: ${NC}"
        echo -e "${YELLOW}  source ~/.zshrc${NC}"
        CREATED_ALIAS=true
    fi
fi
# -------------------------------------------------------------------
# Final Report
# -------------------------------------------------------------------
if [ "$INSTALL_SUCCESS" = false ]; then
    echo -e "\n${RED}SETUP INCOMPLETE - Some steps failed${NC}"
    echo -e "${YELLOW}Check the error messages above and try again.${NC}"
    exit 1
else
    # Reload shell configuration files to apply the alias
    # Doing this here as to not lose the INSTALL_SUCCESS variable
    if [ "$CREATED_ALIAS" = true ]; then
        sleep 3
        if [ -f ~/.bashrc ]; then
            source ~/.bashrc
        fi
        if [ -f ~/.zshrc ]; then
            source ~/.zshrc
        fi
        sleep 3
        GREEN='\e[0;32m'
        YELLOW='\e[1;33m'
        NC='\e[0m'
    fi 
    echo -e "\n${GREEN}Setup complete!${NC}"
    echo -e "${GREEN}Check the different ways to launch the script with:${NC}"
    echo -e "${YELLOW}  viewport -h${NC}"
    echo -e "${GREEN}If the 'viewport' alias doesn't work run these commands:${NC}"
    echo -e "${YELLOW}  source venv/bin/activate${NC}"
    echo -e "${YELLOW}  python3 viewport.py -h${NC}"
    exit 0
fi