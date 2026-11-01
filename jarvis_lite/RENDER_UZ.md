# Jarvis Lite — Render'da (Mac o'chiq bo'lsa ham ishlaydi)

> Render sozlamalari va narxlari o'zgarib turadi; men ularni shu sessiyadan tekshira olmadim. Ekrandagi nomlar biroz boshqacha bo'lsa, ma'nosiga qarab tanlang.

## A. Telegram sessiyasini yarating (Mac'da, bir marta)
Render'da fayllar saqlanmaydi, shuning uchun sessiya **matn** ko'rinishida beriladi. Mac Terminal'da:
```bash
rm -rf ~/.jl_src && git clone --depth 1 -b claude/jarvis-v12 https://github.com/samadbekxolmamatov2009/Jarivsfor_macOS.git ~/.jl_src && ~/jarvis/venv/bin/python ~/.jl_src/jarvis_lite/make_session.py
```
"No module named telethon" chiqsa: `~/jarvis/venv/bin/python -m pip install telethon` va yuqoridagi buyruqni qaytaring.
U so'raydi: `api_id`, `api_hash` (yozganingiz ko'rinmaydi; ikkalasi `~/jarvis/config.py` da: `grep -i -E "api_?id|api_?hash" ~/jarvis/config.py`), keyin telefon raqamingiz, Telegram kodi va (bo'lsa) parol.
Oxirida **bitta uzun qator** chiqadi — bu `TG_SESSION`. Uni nusxalang (Cmd+C). **Bu qator Telegram akkauntingizga to'liq kirish beradi**: faqat Render'ga qo'ying, chatga/GitHub'ga yubormang; keyin Terminal'ni tozalang (Cmd+K).

## B. Render'da xizmat yarating
1. dashboard.render.com → **New +** → **Background Worker** (doim ishlaydi; pullik, ~7 dollar/oy dan — narxni sahifada tekshiring).
2. **Public Git Repository** → `https://github.com/samadbekxolmamatov2009/Jarivsfor_macOS` → **Connect**.
3. Sozlamalar:
   - **Name:** jarvis-lite
   - **Language:** Python 3
   - **Branch:** `claude/jarvis-v12`
   - **Root Directory:** `jarvis_lite`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python lite.py run`
   - **Instance type:** eng arzon pullik (Starter)
4. **Environment Variables** (Add):

| Nomi | Qiymati |
|---|---|
| `TG_API_ID` | api_id (raqam) |
| `TG_API_HASH` | api_hash |
| `TG_SESSION` | A-qadamdagi uzun qator |
| `ANTHROPIC_API_KEY` | Claude kaliti (`sk-ant-...`) |
| `INFO` | `Men kimman: Zufarbek Jumayev, 18 yoshdaman, dasturchiman.;Nima qilaman: har qanday dasturlarni yozaman. IT (dasturlash) fanidan dars ham o'taman.` (qatorlar `;` bilan ajratiladi; o'zingiz haqingizda faktlar — shaxsiy ma'lumot GitHub'da emas, faqat shu yerda turadi) |
| `PYTHON_VERSION` | `3.12.7` (qurish (build) Python versiyasi bilan xato bersa) |
| `NOTIFY_BOT_TOKEN`, `NOTIFY_CHAT_ID` | ixtiyoriy: telefonga bildirishnoma (bo'lmasa xabarlar Telegram'dagi "Saved Messages"ga tushadi, bildirishnoma bermaydi) |
| `CONTACTS` | ixtiyoriy: `Brother;Otabek Akam;@username` — bo'sh qoldirsangiz tayyor ro'yxat ishlaydi (Brother, NAVOIY-QORAKO'L O'QUV MARKAZI, Otabek Akam, Muhammad Akam, Javohir Aka) |

5. **Create Background Worker**. **Logs** bo'limida `🤖 Jarvis Lite is running. Contacts: 5  Claude: on` chiqishi kerak.

## Bepul variant (ehtiyotkorlik bilan)
Pullik narx yoqmasa, **Web Service** + **Free** tarifini sinab ko'rsa bo'ladi: Dastur `PORT` da kichik "ok" javob beradi. Lekin bepul xizmat bir muddat so'rov kelmasa uxlab qoladi, shuning uchun uni tashqi "uptime" xizmati (masalan uptimerobot.com, har 5 daqiqada sizning `https://jarvis-lite.onrender.com` manzilingizga murojaat qiladi) uyg'oq tutishi kerak.
Bu ishonchsizroq: uxlab turgan paytda kelgan xabar javobsiz qolishi mumkin. Menga **pullik Worker** ishonchliroq tuyuladi.

## Sinash
Brother'dan savol yozishini so'rang: 35-45 soniyada javob kelishi, oxirida "🤖 Jarvis (avto-javob)" belgisi bo'lishi kerak. **Mac'dagi Jarvis o'chiq bo'lsin** (yoki `AUTOREPLY_ENABLED = False`), aks holda ikki marta javob oladi.

## Keyin
- **Ro'yxat/ma'lumotni o'zgartirish:** Render → Environment → `CONTACTS` / `INFO` ni o'zgartiring; xizmat o'zi qayta ishga tushadi.
- **Kod yangilanishi:** shu filialga yangi o'zgarish yuklansa Render o'zi qayta quradi (Auto-Deploy yoqilgan bo'lsa).
- **To'xtatish:** Render → Suspend.

## Muammolar
| Xabar (Logs'da) | Sabab / yechim |
|---|---|
| `Not logged in to Telegram yet` | `TG_SESSION` yo'q yoki noto'g'ri nusxalangan — A-qadamni qaytaring |
| `AuthKeyDuplicatedError` / sessiya o'chdi | Shu sessiya ikki joyda ishlatilgan — A-qadamni qaytarib yangisini yarating, faqat Render'da ishlating |
| Build xatosi (Python) | `PYTHON_VERSION=3.12.7` qo'shing |
| `⚠️ Claude: ...` | Kalit noto'g'ri yoki Billing'da pul tugagan; vaqtincha tayyor jumlalar yuboriladi |

## Xavfsizlik
`TG_SESSION` va kalitlar faqat Render'ning Environment bo'limida turadi. Akkaunt xavf ostida bo'lsa: Telegram → Settings → Devices → "Terminate" va Render'dagi xizmatni to'xtating.
