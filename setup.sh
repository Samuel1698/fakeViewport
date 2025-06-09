#!/bin/bash
RED='\e[0;31m'
GREEN='\e[0;32m'
YELLOW='\e[1;33m'
CYAN='\e[36m'
NC='\e[0m'
SCRIPT_PATH="$(pwd)/viewport.py"
VENV_PYTHON="$(pwd)/venv/bin/python3"
echo -e "${YELLOW}===== FakeViewport Setup =====${NC}"

# ----------------------------------------------------------------------------- 
# Helper: move $1 → $2 only if $2 doesn’t already exist (analogous to mv -n)
# ----------------------------------------------------------------------------- 
ss_mv_if_not_exists() {
    # ensure target directory exists
    command mkdir -p "$(dirname "$2")"
    # if target is missing, do the move
    command test ! -e "$2" && command mv "$1" "$2"
}
# ----------------------------------------------------------------------------- 
# Verify Python 3 is installed
# ----------------------------------------------------------------------------- 
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 not found! Installing...${NC}"
    sudo apt update && sudo apt install -y python3
else
    echo -e "${GREEN}✓ Python 3 is already installed${NC}"
fi

# ----------------------------------------------------------------------------- 
# Verify python3-venv is available
# ----------------------------------------------------------------------------- 
sleep 0.25
if ! python3 -c "import ensurepip; import venv" &> /dev/null; then
    echo -e "${RED}python3-venv not found! Installing...${NC}"
    sudo apt install -y python3-venv
else
    echo -e "${GREEN}✓ python3-venv is available${NC}"
fi

# ----------------------------------------------------------------------------- 
# Create virtual environment (if doesn't exist)
# ----------------------------------------------------------------------------- 
sleep 0.25
VENV_DIR="venv"
if [ ! -d "$VENV_DIR" ]; then
    echo -e "\n${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}✓ Virtual environment created${NC}"
else
    echo -e "${GREEN}✓ Virtual environment already exists${NC}"
fi
# ----------------------------------------------------------------------------- 
# Install requirements
# ----------------------------------------------------------------------------- 
if [ "$1" == "dev" ]; then
    echo -e "\n${YELLOW}Development mode enabled. Using dev_requirements.txt.${NC}"
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
        echo -e "\n${YELLOW}Installing dependencies...${NC}"
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
            echo -e "${CYAN}  source ${VENV_DIR}/bin/activate${NC}"
            echo -e "${CYAN}  pip install -r requirements.txt${NC}"
            INSTALL_SUCCESS=false
        fi
    fi
else
    echo -e "${RED}requirements.txt not found!${NC}"
    exit 1
fi
# ----------------------------------------------------------------------------- 
# Verify Google Chrome, Chromium, or Firefox
# ----------------------------------------------------------------------------- 
any_browser_installed=false
if command -v google-chrome-stable &> /dev/null; then
    echo -e "${GREEN}✓ Google Chrome is installed${NC}"
    any_browser_installed=true
fi

if command -v chromium &> /dev/null; then
    echo -e "${GREEN}✓ Chromium is installed${NC}"
    any_browser_installed=true
fi

if command -v firefox &> /dev/null; then
    echo -e "${GREEN}✓ Firefox is installed${NC}"
    any_browser_installed=true
fi

if [ "$any_browser_installed" = false ]; then
    echo -e "${RED}No supported browser found! Install one of:${NC}"
    echo -e "${CYAN}    sudo apt install -y google-chrome-stable${NC}"
    echo -e "${CYAN}    sudo apt install -y chromium${NC}"
    echo -e "${CYAN}    sudo apt install -y firefox${NC}"
fi
# ----------------------------------------------------------------------------- 
# Rename .env.example to .env
# ----------------------------------------------------------------------------- 
sleep 0.5
if [ -f ".env.example" ]; then
    if [ -f ".env" ]; then
        echo -e "${GREEN}✓ .env already exists. Skipping...${NC}"
    else
        echo -e "\n${YELLOW}Renaming .env.example to .env...${NC}"
        if ss_mv_if_not_exists .env.example .env; then
            echo -e "${GREEN}✓ Configuration file prepared${NC}"
            echo -e "${CYAN}  Please edit .env to set your UniFi Protect credentials.${NC}"
            echo -e "${CYAN}  You can do so with the command: nano .env${NC}"
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
# ----------------------------------------------------------------------------- 
# Rename config.ini.example to config.ini
# ----------------------------------------------------------------------------- 
sleep 0.5
if [ -f "config.ini.example" ]; then
    if [ -f "config.ini" ]; then
        echo -e "${GREEN}✓ config.ini already exists. Skipping...${NC}"
    else
        echo -e "\n${YELLOW}Renaming config.ini.example to config.ini...${NC}"
        if ss_mv_if_not_exists config.ini.example config.ini; then
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
# ----------------------------------------------------------------------------- 
# Create Desktop Shortcut
# ----------------------------------------------------------------------------- 
sleep 0.5
if [[ -d "$HOME/Desktop" ]]; then
    SHORTCUT_DIR="$HOME/Desktop"
    SHORTCUT_PATH="$SHORTCUT_DIR/Viewport.desktop"
else
echo -e "${RED}No desktop directory found; skipping shortcut creation.${NC}"
fi
OVERRIDE_SHORTCUT=false
for arg in "$@"; do
    case "$arg" in
    -s|--shortcut)
        OVERRIDE_SHORTCUT=true
        shift
        ;;
    esac
done
# helper to create the file
_create_shortcut() {
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
}
if [[ -e "$SHORTCUT_PATH" ]]; then
    if $OVERRIDE_SHORTCUT; then
        echo -e "\n${YELLOW}Shortcut already exists at $SHORTCUT_PATH, overwriting...${NC}"
        _create_shortcut
    else
        echo -e "${GREEN}✓ Desktop Shortcut already exists. Skipping...${NC}"
        echo -e "${GREEN}✓ To override it, run:${NC}${CYAN} ./setup.sh -s${NC}"
    fi
elif [[ -e "$SHORTCUT_DIR" ]]; then
    if $OVERRIDE_SHORTCUT; then
        echo -e "\n${YELLOW}Creating shortcut without prompt (override flag given)${NC}"
        _create_shortcut
    else
        echo -ne "\n${YELLOW}Would you like to create a desktop shortcut for FakeViewport (y/n)? ${NC}"
        read -r reply
        if [[ "$reply" =~ ^[Yy]([Ee][Ss])?$ ]]; then
            _create_shortcut
        else
            echo -e "${GREEN}✓ Skipping desktop shortcut creation.${NC}"
        fi
    fi
fi
# ----------------------------------------------------------------------------- 
# Create an alias for running the script
# ----------------------------------------------------------------------------- 
sleep 0.5
ALIAS_NAME="viewport"
# Check if the alias already exists in ~/.bashrc or ~/.zshrc
if grep -q "alias $ALIAS_NAME=" ~/.bashrc 2>/dev/null || grep -q "alias $ALIAS_NAME=" ~/.zshrc 2>/dev/null; then
    echo -e "${GREEN}✓ Alias '$ALIAS_NAME' already exists. Skipping...${NC}"
else
    echo -e "\n${YELLOW}Adding alias '$ALIAS_NAME' to your shell configuration...${NC}"
    # Add the alias to ~/.bashrc or ~/.zshrc
    if [ -f ~/.bashrc ]; then
        echo "alias $ALIAS_NAME='$VENV_PYTHON $SCRIPT_PATH'" >> ~/.bashrc
        echo -e "${GREEN}✓ Alias added to ~/.bashrc${NC}"
        echo -e "${GREEN}Reload your shell terminal to use the new alias: ${NC}"
        echo -e "${CYAN}  source ~/.bashrc${NC}"
    fi
    if [ -f ~/.zshrc ]; then
        echo "alias $ALIAS_NAME='$VENV_PYTHON $SCRIPT_PATH'" >> ~/.zshrc
        echo -e "${GREEN}✓ Alias added to ~/.zshrc${NC}"
        echo -e "${GREEN}Reload your shell terminal to use the new alias: ${NC}"
        echo -e "${CYAN}  source ~/.zshrc${NC}"
    fi
fi
# ----------------------------------------------------------------------------- 
# Set up a cron job
# ----------------------------------------------------------------------------- 
sleep 0.5
cron_entry="@reboot sleep 60 && $VENV_PYTHON $SCRIPT_PATH"
# Check if the cron job already exists
if crontab -l 2>/dev/null | grep -Fxq "$cron_entry"; then
    echo -e "${GREEN}✓ Startup cron job already exists. Skipping...${NC}"
else
    echo -ne "\n${YELLOW}Do you want to set up the script to run automatically at startup using cron? (y/n):${NC} " 
    read -r setup_cron
    if [[ "$setup_cron" =~ ^[Yy]([Ee][Ss])?$ ]]; then
        (crontab -l 2>/dev/null; echo "$cron_entry") | crontab -
        echo -e "${GREEN}✓ Cron job added to run the script at startup.${NC}"
    else
        echo -e "${GREEN}✓ Skipping cron setup.${NC}"
    fi
fi
# ----------------------------------------------------------------------------- 
# Final Report
# ----------------------------------------------------------------------------- 
sleep 0.5
if [ "$INSTALL_SUCCESS" = false ]; then
    echo -e "\n\n${RED}===== SETUP INCOMPLETE - Some steps failed =====${NC}"
    echo -e "${YELLOW}Check the error messages above and try again.${NC}"
    exit 1
else
    echo -e "\n\n${GREEN}===== Setup complete! =====${NC}\n"
    echo -e "${GREEN}Check the different ways to launch the script with:${NC}"
    echo -e "${CYAN}  viewport -h${NC}"
    echo -e "${GREEN}If the 'viewport' alias doesn't work run:${NC}"
    if [ -f ~/.bashrc ]; then
        echo -e "${CYAN}  source ~/.bashrc${NC}"
    fi
    if [ -f ~/.zshrc ]; then
        echo -e "${CYAN}  source ~/.zshrc${NC}"
    fi
fi