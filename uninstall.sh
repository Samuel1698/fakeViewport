#!/bin/bash
RED='\e[0;31m'
GREEN='\e[0;32m'
YELLOW='\e[1;33m'
NC='\e[0m'

echo -ne "${YELLOW}This will uninstall the script and related files. Continue? (y/n):${NC} " 
read -r confirm
if [[ ! "$confirm" =~ ^[Yy]([Ee][Ss])?$ ]]; then
    echo -e "${GREEN}Aborted.${NC}"
    exit 0
fi

# Remove desktop shortcut
desktop_file="$HOME/Desktop/Viewport.desktop"
[ -f "$desktop_file" ] && rm "$desktop_file" && echo -e "Desktop shortcut removed."

# Remove alias from ~/.bashrc or ~/.zshrc
if grep -q "alias viewport=" ~/.bashrc 2>/dev/null; then
    sed -i '/alias viewport=/d' ~/.bashrc
    echo -e "${GREEN}Alias removed from .bashrc${NC}"
fi

if grep -q "alias viewport=" ~/.zshrc 2>/dev/null; then
    sed -i '/alias viewport=/d' ~/.zshrc
    echo -e "${GREEN}Alias removed from .zshrc${NC}"
fi

# Remove cron job
tmp_cron=$(mktemp)
crontab -l 2>/dev/null | grep -v "viewport.py" > "$tmp_cron"
crontab "$tmp_cron"
rm "$tmp_cron"
echo "${GREEN}Cron job removed.${NC}"

find . -mindepth 1 -maxdepth 1 \
    ! -name ".env" \
    -exec rm -rf {} +

echo "${GREEN}All project files removed except .env${NC}"

echo "${GREEN}Uninstall complete. You may want to manually delete .env file if desired.${NC}"
