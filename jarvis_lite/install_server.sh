#!/bin/bash
# Ubuntu / Debian serverda (root sifatida) ishga tushiring:   sudo bash install_server.sh
set -e
[ "$(id -u)" = 0 ] || { echo "❌ sudo bilan ishga tushiring: sudo bash install_server.sh"; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"
APP=/opt/jarvis-lite; DATA=/var/lib/jarvis-lite; ENVF=/etc/jarvis-lite.env

echo "1/5 📦 Paketlar..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip >/dev/null

echo "2/5 👤 Foydalanuvchi va papkalar..."
id jarvis >/dev/null 2>&1 || useradd --system --home "$DATA" --shell /usr/sbin/nologin jarvis
mkdir -p "$APP" "$DATA"
cp "$HERE/lite.py" "$HERE/langdetect.py" "$HERE/configure.sh" "$APP/"
[ -f "$DATA/contacts.txt" ] || cp "$HERE/contacts.default.txt" "$DATA/contacts.txt"     # sizning tahrirlaringiz bosib ketilmaydi
[ -f "$DATA/info.txt" ] || cp "$HERE/info.default.txt" "$DATA/info.txt"
chown -R jarvis:jarvis "$DATA"; chmod 700 "$DATA"

echo "3/5 📚 Python kutubxonalari..."
[ -d "$APP/venv" ] || python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install -q --upgrade pip
"$APP/venv/bin/pip" install -q telethon anthropic

echo "4/5 ⚙️  Sozlamalar fayli..."
if [ ! -f "$ENVF" ]; then cp "$HERE/env.example" "$ENVF"; fi
chown root:jarvis "$ENVF"; chmod 640 "$ENVF"

echo "5/5 🔧 Xizmat..."
cp "$HERE/jarvis-lite.service" /etc/systemd/system/jarvis-lite.service
systemctl daemon-reload
systemctl enable jarvis-lite >/dev/null 2>&1

cat <<MSG

✅ O'rnatildi. Endi 3 ta qadam qoldi:
  1) Sozlamalarni kiriting (savol-javob):   sudo bash $APP/configure.sh
  2) Telegram'ga bir marta kiring (telefon raqam, kod, parol so'raydi):
       sudo -u jarvis $APP/venv/bin/python $APP/lite.py login
  3) Ishga tushiring:   sudo systemctl start jarvis-lite   va   sudo journalctl -u jarvis-lite -f   (jurnal)
Ro'yxat: sudo nano $DATA/contacts.txt     Ma'lumotlar: sudo nano $DATA/info.txt   (qayta yoqish shart emas)
MSG
