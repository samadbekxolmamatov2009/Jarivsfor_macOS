#!/bin/bash
# Jarvis v12 for Mac — replaces your installed Jarvis (~/jarvis) with v12.
#   tasks + reminders (voice & phone), timed Telegram messages, Telegram call button, battery saver.
# Safe: your old files are backed up first, and if v12 fails its self-check it is rolled back automatically.
# Your config.py, tokens, Telegram login, memory, notes and models are NOT touched.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
JARVIS="$HOME/jarvis"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="$HOME/jarvis_backup_$STAMP"
FILES="main.py wake.py ears.py stt.py voice.py bargein.py hud.py skills/docs.py skills/lang.py skills/mac_commands.py skills/power.py skills/tasks.py skills/tg_call.py"

if [ ! -d "$JARVIS" ] || [ ! -x "$JARVIS/venv/bin/python" ]; then
  echo "❌ $JARVIS topilmadi (yoki venv yo'q). Avval oddiy o'rnatishni bajaring."; exit 1
fi

echo "1/5 💾 Eski versiya zaxiralanmoqda → $BACKUP"
mkdir -p "$BACKUP/skills"
for f in $FILES; do [ -f "$JARVIS/$f" ] && cp -p "$JARVIS/$f" "$BACKUP/$f"; done
echo "$FILES" > "$BACKUP/.files"

rollback() {
  echo "↩️  Eski versiyaga qaytarilmoqda..."
  for f in $FILES; do
    if [ -f "$BACKUP/$f" ]; then cp -p "$BACKUP/$f" "$JARVIS/$f"; else rm -f "$JARVIS/$f"; fi
  done
  if launchctl print "gui/$(id -u)/com.jarvis.assistant" >/dev/null 2>&1; then
    launchctl kickstart -k "gui/$(id -u)/com.jarvis.assistant"
  fi
  echo "✅ Eski Jarvis qaytarildi. Zaxira: $BACKUP"
}

echo "2/5 📦 Yangi fayllar nusxalanmoqda..."
mkdir -p "$JARVIS/skills"
for f in $FILES; do cp "$HERE/$f" "$JARVIS/$f" || { echo "❌ $f nusxalanmadi"; rollback; exit 1; }; done

echo "3/5 📚 Kutubxonalar tekshirilmoqda..."
"$JARVIS/venv/bin/python" -m pip install -q edge-tts pypdf || true
"$JARVIS/venv/bin/python" -m pip install -q pyobjc-framework-Quartz || echo "   (Quartz o'rnatilmadi — ekran qulflanganda mikrofonni o'chirish ishlamaydi, qolgani ishlaydi)"

echo "4/5 🔎 O'z-o'zini tekshirish..."
if ! (cd "$JARVIS" && "$JARVIS/venv/bin/python" -c "import skills.mac_commands, skills.tasks, skills.power, skills.tg_call, wake, bargein" 2>&1 | tail -5; exit ${PIPESTATUS[0]}); then
  echo "❌ v12 yuklanmadi."; rollback; exit 1
fi
echo "   ✅ tayyor"

echo "5/5 🔄 Jarvis qayta ishga tushirilmoqda..."
if launchctl print "gui/$(id -u)/com.jarvis.assistant" >/dev/null 2>&1; then
  launchctl kickstart -k "gui/$(id -u)/com.jarvis.assistant"
elif [ -x "$JARVIS/jarvis_toggle.sh" ]; then
  "$JARVIS/jarvis_toggle.sh" >/dev/null 2>&1
fi
echo ""
echo "✅ Jarvis v12 ishlayapti.  (Eski versiya: $BACKUP)"
echo "   Sinab ko'ring: «Hello» ... «Add task call mom tomorrow at five pm» ... «What are my tasks»"
echo "   Qaytarish kerak bo'lsa:  bash \"$HERE/rollback_v12.sh\""
