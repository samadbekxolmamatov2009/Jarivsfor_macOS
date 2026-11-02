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
| `NOTIFY_BOT_TOKEN` | Jarvis botingiz tokeni (BotFather bergan). Bot sizga **faqat zarur paytda** yozadi: sizning javobingiz kerak bo'lsa, ovozli xabar/fayl kelsa, pul/parol kabi mavzu yoki chegaradan oshsa, Muhammad Akam karta so'rasa. Chat id kerak emas (o'z akkauntingizga yozadi), faqat botda bir marta Start bosilgan bo'lishi kerak. Qo'ymasangiz xabarlar "Saved Messages"ga tushadi (bildirishnoma bermaydi). |
| `REMIND_MINUTES`, `REMIND_TIMES` | ixtiyoriy (tayyor: `30` va `2`): muhim xabarga o'zingiz javob bermasangiz, bot 30 daqiqadan keyin «Javob berasizmi?» deb eslatadi (ko'pi bilan 2 marta). Javob berishni xohlamasangiz botga **«yo'q»** deb yozing — eslatmalar to'xtaydi. O'zingiz odamga javob yozsangiz ham eslatma to'xtaydi. |
| `NOTIFY_ALL_REPLIES` | ixtiyoriy: `1` qo'ysangiz botga har bir javob nusxasi ham keladi (tayyor holda o'chiq) |
| `AUTOREPLY_MODEL` | ixtiyoriy (tayyor: `claude-haiku-5-5`, juda arzon). O'zbekcha javob sifati yetmasa `claude-sonnet-5-5` (~20 baravar qimmatroq) qo'ying. |
| `PARENTS` | ixtiyoriy (tayyor: `Dadajonim;Ayajonim`): bu odamlarga Jarvis **hech qachon yozmaydi**, faqat sizga botdan xabar beradi. Ro'yxatni `;` bilan o'zgartirasiz. |
| `REPLY_TO` | ixtiyoriy (tayyor: `all`). `list` qo'ysangiz faqat `CONTACTS` ro'yxatidagilarga javob beradi. |
| `PAY_CARD` | **Muhammad Akam** uchun: karta raqamingiz (16 xona, bo'shliqlar bilan). U faqat shu yerda turadi, kodda/GitHub'da emas. Bo'sh qoldirsangiz bu qoida o'chiq. |
| `PAY_AMOUNT`, `PAY_FOR`, `PAY_CONTACT` | ixtiyoriy (tayyor qiymatlari: `13$`, `cefr tys boti serveri`, `Muhammad Akam`) |
| `CONTACTS` | ixtiyoriy: `Brother;Otabek Akam;@username` — bo'sh qoldirsangiz tayyor ro'yxat ishlaydi (Brother, NAVOIY-QORAKO'L O'QUV MARKAZI, Otabek Akam, Muhammad Akam, Javohir Aka) |

5. **Create Background Worker**. **Logs** bo'limida `🤖 Jarvis Lite is running. Contacts: 5  Claude: on` chiqishi kerak.

## Bepul variant (ehtiyotkorlik bilan)
Pullik narx yoqmasa, **Web Service** + **Free** tarifini sinab ko'rsa bo'ladi: Dastur `PORT` da kichik "ok" javob beradi. Lekin bepul xizmat bir muddat so'rov kelmasa uxlab qoladi, shuning uchun uni tashqi "uptime" xizmati (masalan uptimerobot.com, har 5 daqiqada sizning `https://jarvis-lite.onrender.com` manzilingizga murojaat qiladi) uyg'oq tutishi kerak.
Bu ishonchsizroq: uxlab turgan paytda kelgan xabar javobsiz qolishi mumkin. Menga **pullik Worker** ishonchliroq tuyuladi.

## Kimga qanday javob beriladi
| Kim yozsa | Jarvis nima qiladi |
|---|---|
| **Dadajonim, Ayajonim** | Umuman yozmaydi. Botdan sizga darrov xabar beradi (ovozli xabar bo'lsa ham). Javob bermasangiz 30 daqiqadan keyin eslatadi. |
| **Tanishlar** (ro'yxatdagilar va Telegram kontaktlaringizda saqlanganlar) | Claude mazmunga qarab javob beradi (4 daqiqa kutgach), kerak bo'lsa sizga xabar beradi. |
| **Notanishlar** (har qanday boshqa profil) | Faqat tayyor «band, o'zi javob beradi» jumlasi, AI yo'q, shaxsiy ma'lumot yo'q, sizga xabar yo'q. Bitta odamga 6 soatda 1 marta, jami kuniga 15 tagacha. Pul/karta/parol haqida yozsa — umuman javob yo'q. |
| **Guruh, kanal, bot, Telegram'ning o'zi (777000), o'chirilgan/belgilangan profillar** | Hech qachon javob berilmaydi. |

## Muhammad Akam va server to'lovi
`PAY_CARD` qo'yilsa: **Muhammad Akam** (faqat Telegram kontaktlaringizda saqlangan bo'lsa) karta raqamini so'rasa — karta raqami va 13$ yuboriladi; faqat summani so'rasa — "13$"; boshqa narsa yozsa — sizga xabar keladi (va oddiy avto-javob ketadi). Boshqa kontaktlar karta so'rasa, hech qachon berilmaydi, sizga xabar keladi.

## Botga o'zingiz yozing (Claude tushunadi)
Bot yuborgan xabarga **javob (reply)** qilib, oddiy so'z bilan yozing, masalan:
- «bunga javob berishni xohlamayman» → shu odam haqida eslatmalar o'chadi
- «oziga aytib qo'y, chiroyli ravishda» → bot unga nazokatli xabar yozadi (oxirida «🤖 Jarvis (avto-javob)» belgisi) va nima yuborganini sizga ko'rsatadi
- «ertaga javob beraman deb ayt» → shunday xabar ketadi

**Kimga ekanini o'zingiz ayting:** «Muhammad Akamga yoz: ...» yoki chat raqamini (`🔖` dan keyingi raqam) yozing — bot aynan o'sha odamga yuboradi, oxirgi xabar bergan odamga emas. Ismga bir nechta odam mos kelsa (masalan «Akam»), qaysi biri ekanini so'raydi. Topa olmasa, hech kimga yubormaydi.
**Xato ketsa:** «brotherga yuborganingni o'chir» desangiz, bot yuborgan xabarini o'sha odamdan o'chiradi (faqat o'zining belgili xabarlarini; sizniki hech qachon). Bir xil matnni bir odamga 10 daqiqada ikki marta yubormaydi.

2-3 ta qisqa xabar ketma-ket yozsangiz, bot ularni birga o'qiydi. Reply qilmasangiz, eng oxirgi xabar bergan odam haqida deb tushunadi. Tushunmasa, nima deb yozishini so'raydi, o'zboshimcha hech narsa yubormaydi. Oddiy «yo'q» (yoki `/skip`) — hamma eslatmalarni o'chiradi.
Bot odamga faqat o'zingiz aytgan narsani yozadi: va'da bermaydi, sana/pul qo'shmaydi.

## Sinash
Brother'dan savol yozishini so'rang: taxminan 4 daqiqadan keyin javob kelishi, oxirida "🤖 Jarvis (avto-javob)" belgisi bo'lishi kerak. **Mac'dagi Jarvis o'chiq bo'lsin** (yoki `AUTOREPLY_ENABLED = False`), aks holda ikki marta javob oladi.

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
