#!/bin/bash
RED='\e[0;31m'
GREEN='\e[0;32m'
YELLOW='\e[1;33m'
CYAN='\e[36m'
NC='\e[0m'
echo -e "${YELLOW}===== FakeViewport Uninstall =====${NC}"
echo -ne "\n${YELLOW}This will uninstall the script and related files. Continue? (y/n):${NC} " 
read -r confirm
if [[ ! "$confirm" =~ ^[Yy]([Ee][Ss])?$ ]]; then
    echo -e "${GREEN}Aborted.${NC}"
    exit 0
fi

# Remove desktop shortcut
desktop_file="$HOME/Desktop/Viewport.desktop"
[ -f "$desktop_file" ] && rm "$desktop_file" && echo -e "${GREEN}✓ Desktop shortcut removed.${NC}"

# Remove alias from ~/.bashrc or ~/.zshrc
for file in ~/.bashrc ~/.zshrc; do
    if [ -f "$file" ] && grep -q "alias viewport=" "$file"; then
        sed -i '/alias viewport=/d' "$file"
        echo -e "${GREEN}✓ Removed 'viewport' alias from ${file}${NC}"
    fi
done
# Remove cron job
tmp_cron=$(mktemp)
crontab -l 2>/dev/null | grep -v "viewport.py" > "$tmp_cron"
crontab "$tmp_cron"
rm "$tmp_cron"
echo -e "${GREEN}✓ Cron job removed.${NC}"

find . -mindepth 1 -maxdepth 1 \
    ! -name ".env" \
    -exec rm -rf {} +

echo -e "${GREEN}✓ All project files removed except .env${NC}"

echo -e "${YELLOW}✓ Uninstall complete. You may want to manually delete .env file if desired.${NC}"
echo -e "\n${YELLOW}Run this command to remove the alias from your shell: ${NC}"
echo -e "${CYAN}  unalias viewport${NC}"