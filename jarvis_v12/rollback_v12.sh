#!/bin/bash
# Restores the newest backup made by update_v12.sh (the version you had before).
JARVIS="$HOME/jarvis"
BACKUP="$(ls -d "$HOME"/jarvis_backup_* 2>/dev/null | sort | tail -1)"
[ -n "$BACKUP" ] || { echo "❌ Zaxira topilmadi."; exit 1; }
echo "↩️  Qaytarilmoqda: $BACKUP"
for f in $(cat "$BACKUP/.files"); do
  if [ -f "$BACKUP/$f" ]; then cp -p "$BACKUP/$f" "$JARVIS/$f"; else rm -f "$JARVIS/$f"; fi
done
if launchctl print "gui/$(id -u)/com.jarvis.assistant" >/dev/null 2>&1; then
  launchctl kickstart -k "gui/$(id -u)/com.jarvis.assistant"
fi
echo "✅ Tayyor — eski Jarvis qaytdi."
