#!/bin/bash
# Savol-javob orqali sozlash:   sudo bash /opt/jarvis-lite/configure.sh
# Kalitlar ekranda ko'rinmaydi. Bo'sh qoldirsangiz (Enter) o'sha qiymat o'zgarmaydi.
ENVF="${ENVF:-/etc/jarvis-lite.env}"
[ -f "$ENVF" ] || { echo "❌ $ENVF yo'q — avval install_server.sh ni ishga tushiring"; exit 1; }

set_kv() {   # set_kv KEY VALUE
  if grep -q "^$1=" "$ENVF"; then
    awk -v k="$1" -v v="$2" 'BEGIN{FS=OFS="="} $1==k {print k"="v; next} {print}' "$ENVF" > "$ENVF.tmp" && cat "$ENVF.tmp" > "$ENVF" && rm -f "$ENVF.tmp"
  else
    echo "$1=$2" >> "$ENVF"
  fi
}
ask() {      # ask KEY "savol" [secret]
  local v
  if [ "${3:-}" = secret ]; then read -r -s -p "$2 " v; echo; else read -r -p "$2 " v; fi
  v="$(printf '%s' "$v" | tr -d '[:space:]')"
  if [ -n "$v" ]; then set_kv "$1" "$v"; echo "   ✔ $1 yozildi"; else echo "   – $1 o'zgarmadi"; fi
}

echo "Telegram (my.telegram.org → API development tools; Mac'dagi ~/jarvis/config.py da ham bor):"
ask TG_API_ID   "api_id (raqam):"
ask TG_API_HASH "api_hash (uzun harf-raqam):" secret
echo; echo "Claude kaliti (console.anthropic.com → API Keys). Bo'sh qoldirsangiz tayyor jumlalar yuboriladi:"
ask ANTHROPIC_API_KEY "kalit (sk-ant-...):" secret
echo; echo "Ixtiyoriy: telefoningizga bildirishnoma uchun Jarvis botingiz tokeni va sizning chat id'ingiz (Enter — o'tkazib yuborish):"
ask NOTIFY_BOT_TOKEN "bot token:" secret
ask NOTIFY_CHAT_ID   "chat id:"

chown root:jarvis "$ENVF" 2>/dev/null || true
chmod 640 "$ENVF"
echo; echo "✅ Saqlandi. Keyingi qadam:  sudo -u jarvis /opt/jarvis-lite/venv/bin/python /opt/jarvis-lite/lite.py login"
