# Jarvis Lite — serverda avto-javob (Mac o'chiq bo'lsa ham ishlaydi)

Server — internetda doim yoniq turadigan kichik kompyuter. Unda Jarvis Lite kontaktlaringizdan kelgan xabarni **darrov** ko'radi
(o'qilgan-o'qilmaganidan qat'i nazar), Claude bilan tushunib, javob yozadi. Mac ham, telefon ham o'chiq bo'lishi mumkin.

## 0. Nima kerak
| | |
|---|---|
| Server | Ubuntu 22.04/24.04, 1 GB RAM yetadi. Narxi ~4-6 dollar/oy (Hetzner, DigitalOcean, Vultr, Contabo va boshqalar). **Diqqat:** ba'zi xorijiy xizmatlar O'zbekiston kartalarini qabul qilmaydi — Visa/Mastercard (xorijiy) kerak bo'lishi mumkin. |
| Telegram | my.telegram.org dan `api_id` va `api_hash` (Mac'dagi `config.py` da allaqachon bor) |
| Claude kaliti | console.anthropic.com → API Keys (Mac'dagisini ishlatsangiz bo'ladi) |

## 1. Server oching
Xizmatda **Ubuntu 24.04** serverini yarating, u sizga **IP manzil** va kirish usulini beradi. Mac'dagi Terminal'dan kiring:
```bash
ssh root@SERVER_IP_MANZILI
```

## 2. O'rnating (serverda, bitta buyruq)
```bash
apt-get update -qq && apt-get install -y -qq git && rm -rf /root/jl && git clone --depth 1 -b claude/jarvis-v12 https://github.com/samadbekxolmamatov2009/Jarivsfor_macOS.git /root/jl && sudo bash /root/jl/jarvis_lite/install_server.sh
```

## 3. Sozlamalarni kiriting (savol-javob)
```bash
sudo bash /opt/jarvis-lite/configure.sh
```
U `api_id`, `api_hash`, Claude kaliti (va ixtiyoriy: Jarvis bot tokeni, chat id) so'raydi. Kalitlar ekranda ko'rinmaydi, Enter — o'tkazib yuborish.
Telefoningizga "Brother'ga shunday javob berdim" xabari kelsin desangiz bot tokeni va chat id'ni ham kiriting; bo'lmasa xabarlar "Saved Messages" ga tushadi (bildirishnoma bermaydi).

## 4. Telegram'ga bir marta kiring
```bash
sudo -u jarvis /opt/jarvis-lite/venv/bin/python /opt/jarvis-lite/lite.py login
```
Telefon raqamingizni (`+998...`), Telegram yuborgan kodni va (bo'lsa) 2 bosqichli parolni kiriting. Bu server uchun **alohida sessiya** — Mac'dagisiga tegmaydi.

## 5. Ishga tushiring
```bash
systemctl start jarvis-lite
journalctl -u jarvis-lite -f        # jonli jurnal (chiqish: Ctrl+C)
```
"🤖 Jarvis Lite is running. Contacts: 5  Claude: on" chiqishi kerak. Server qayta yoqilsa ham o'zi ishga tushadi.

## 6. Mac'dagi avto-javobni o'chiring (ikki marta javob bo'lmasligi uchun)
Mac'da:
```bash
echo 'AUTOREPLY_ENABLED = False' >> ~/jarvis/config.py
```
va Jarvis'ni yangilab qayta yoqing (oldingi yangilash buyrug'i).

## Kundalik ishlatish
- **Ro'yxatni o'zgartirish:** `nano /var/lib/jarvis-lite/contacts.txt` (qayta yoqish shart emas). Har qatorga: ism, `@username`, `+998...` yoki `id:123`.
- **O'zingiz haqingizda ma'lumot:** `nano /var/lib/jarvis-lite/info.txt` (dars narxi, jadval...). Faylda yo'q narsani bot o'ylab topmaydi.
- **To'xtatish / yoqish:** `systemctl stop jarvis-lite` / `systemctl start jarvis-lite`.
- **Yangilash:** 2-qadamdagi buyruqni qayta bajaring (contacts.txt va info.txt tahrirlaringiz saqlanadi).

## Qoidalar (xavfsizlik)
Faqat shaxsiy chatlar va faqat ro'yxatdagi odamlar · har javob "🤖 Jarvis (avto-javob)" belgisi bilan · pul/karta/parol/kod/zudlik haqidagi xabarlarga javob **yo'q**, o'rniga sizga xabar · ovozli xabarga tayyor javob ("Zufarbek Jumayev hozir band, o'zi javob yozadi") ·
siz o'zingiz javob yozsangiz (30 soniya ichida) bot jim turadi · chatga soatiga 3 ta, kuniga 40 ta chegarasi.

## Xavfsizlik ogohlantirishi
`/var/lib/jarvis-lite/session*` fayli Telegram akkauntingizga to'liq kirish beradi, `/etc/jarvis-lite.env` da esa kalitlaringiz bor. Server parolini murakkab qiling,
imkon bo'lsa SSH'ga parol o'rniga kalit bilan kiring, fayllarni hech kimga ko'rsatmang. Akkaunt xavf ostida bo'lsa: Telegram → Settings → Devices → serverni "Terminate".
