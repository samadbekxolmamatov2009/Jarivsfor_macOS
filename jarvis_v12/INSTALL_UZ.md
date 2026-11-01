# Jarvis v12 — o'rnatish (Mac'dagi eski Jarvis o'rniga)

## Yangiliklar
| | |
|---|---|
| 📝 **Vazifalar** | `Add task call the bank tomorrow at ten am` · `What are my tasks` · `Task two is done` · `Postpone task two to friday at five pm` · `Delete task three` · `Clear finished tasks`. «important» desangiz — muhim, «every day» desangiz — har kuni takrorlanadi. Vaqti kelganda Jarvis **ovoz bilan aytadi** va **Telegram'ingizga ham yuboradi** (bajarmasangiz 30 daqiqadan keyin yana 2 marta eslatadi). Telefondagi Jarvis botiga ham xuddi shunday yozsangiz bo'ladi. |
| ⏰ **Saqlanadigan eslatma** | `Remind me at six pm to call mom` — fayl'ga yoziladi, Jarvis qayta ishga tushsa ham yo'qolmaydi. (`in ten minutes` — oddiy taymer bo'lib qoladi.) |
| ✉️ **Vaqtida xabar yuborish** | `Tomorrow at nine am tell Aziz the lesson is moved` — Jarvis tasdiq so'raydi, so'ng o'sha vaqtda o'zi Telegram'dan yuboradi. |
| 📞 **Telegram qo'ng'iroq** | `Call Aziz on Telegram` — chatni ochadi va qo'ng'iroq tugmasini o'zi bosadi (Accessibility ruxsati kerak). Tugmani topolmasa «trubka belgisini bosing» deydi. Oddiy telefon raqamlariga iPhone orqali qo'ng'iroq avvalgidek ishlaydi. |
| 🔋 **Batareya tejash** | Quyida. Ovoz bilan: `Battery saver on / off / auto / status`. |
| 🤖 **Avto-javob** | Telegram xabarlariga Jarvis sizning o'rningizga javob beradi. Ro'yxatni `config.py` ga yozsangiz o'zi ishlaydi (pastga qarang); yozmasangiz o'chiq. Faqat siz tanlagan odamlarga ishlaydi: `Auto reply on for Aziz` · `Auto reply off for Aziz` · `Turn off auto reply` · `Auto reply status` · `Auto reply for everyone` (tasdiq so'raydi). Telefondagi bot orqali ham boshqariladi. Quyida xavfsizlik qoidalari. |
| ☀️ **Ertalabki briefing** | endi ochiq vazifalaringizni ham aytadi. |

## O'rnatish (eski versiya o'rniga) — 3 qadam
1. **Terminal**ni oching (Spotlight: `Cmd+Space` → «Terminal»).
2. Shu bitta buyruqni qo'ying va Enter bosing:
   ```bash
   rm -rf ~/.jarvis_v12_src && git clone --depth 1 -b claude/jarvis-v12 https://github.com/samadbekxolmamatov2009/Jarivsfor_macOS.git ~/.jarvis_v12_src && bash ~/.jarvis_v12_src/jarvis_v12/update_v12.sh
   ```
   Skript o'zi: eski Jarvis'ni `~/jarvis_backup_<sana>` ga **zaxiralaydi** → yangi fayllarni `~/jarvis` ga ko'chiradi → kutubxonalarni qo'yadi → o'zini **tekshiradi** (xato bo'lsa eskisini avtomatik qaytaradi) → Jarvis'ni qayta yoqadi.
3. Tugadi. **Yorliq (shortcut) o'zgarmaydi** — `jarvis_toggle.sh` ga tegilmaydi, config.py, Telegram kirishi, xotira va modellar ham joyida.

`config.py`, token va Telegram sessiyasiga **tegilmaydi**.

### Bir marta beriladigan ruxsat
*System Settings → Privacy & Security → Accessibility* → Jarvis'ni ishga tushiradigan dastur (Terminal) yoqilgan bo'lsin. Telegram qo'ng'iroq tugmasi va «shu chatga yoz» uchun kerak.

### Orqaga qaytarish
```bash
bash ~/.jarvis_v12_src/jarvis_v12/rollback_v12.sh
```

## Batareya
Nima uchun tez yeydi: Jarvis butun kun mikrofonni tinglaydi va har ovozda Whisper'ni ishlatadi. v12 da:
- tinglash **tejamkor (efficiency) yadrolarda** past ustuvorlik bilan ishlaydi; gaplashayotganda esa to'liq tezlikda;
- **ekran qulflanganda / o'chganda mikrofon to'liq o'chadi** (siz yo'qsiz), ochilganda o'zi yoqiladi — telefondan Telegram orqali buyruq berish baribir ishlaydi;
- **batareyada (yoki Low Power Mode'da) avtomatik «eco»**: ovoz tekshiruvi qat'iyroq va kamroq, «stop»ni tinglash siyrakroq;
- **shovqinli xona** (TV, odamlar): ketma-ket yolg'on signal bo'lsa Jarvis o'zini kamroq tekshiradi;
- vazifa eslatmalari «har soniya» emas, keyingi eslatma vaqtigacha uxlaydi.

Sozlash (ixtiyoriy, `~/jarvis/config.py` ga qo'shing):
```python
ECO_MODE = "auto"                # auto | on | off
PAUSE_WHEN_SCREEN_OFF = True
```
Natijani ko'rish: *Activity Monitor → Energy* ichida «python» ning «Energy Impact» i, yoki Terminal'da `pmset -g batt` bilan soatlar bo'yicha taqqoslang.

## Avto-javobni buyruqsiz yoqish (tavsiya etiladi)
**Brother** va **NAVOIY-QORAKO'L O'QUV MARKAZI** kodga allaqachon kiritilgan — yangilangach darrov ishlaydi, `config.py` kerak emas. Boshqa odam qo'shish uchun:
Terminal'da bir marta (ismlarni o'zingizniki bilan almashtiring — Telegram'dagi ism yoki uning bir qismi):
```bash
echo 'AUTOREPLY_CONTACTS = ["Aziz", "Madina", "Brother"]' >> ~/jarvis/config.py
echo 'OWNER_NAME = "Samadbek"' >> ~/jarvis/config.py
launchctl kickstart -k gui/$(id -u)/com.jarvis.assistant
```
Tamom: endi Jarvis yonganda o'zi shu kontaktlarning xabarlarini o'qiydi, tushunadi va javob beradi — hech qanday buyruq kerak emas. **Ro'yxatdagi boshqa hech kimga yozmaydi.** Ro'yxatni keyin ham shu qator orqali o'zgartirasiz. Agar ovoz yoki telefon orqali «turn off auto reply» desangiz, u o'chiq qoladi (qayta yoqish: «turn on auto reply»).

## Avto-javob qoidalari (xavfsizlik)
- faqat **shaxsiy chatlar** — guruh, kanal va botlarga hech qachon yozmaydi;
- har javob oxirida **«🤖 Jarvis (avto-javob)»** belgisi bor (odamlar bot yozayotganini bilishi uchun; `config.py` da `AUTOREPLY_SIGNATURE` bilan o'zgartiriladi);
- **pul, karta, parol, kod, zudlik/favqulodda** haqidagi xabarlarga javob **bermaydi** — o'rniga telefoningizga «bu xabarga o'zingiz javob bering» deb yuboradi;
- hech narsaga va'da bermaydi, uchrashuv/pul kelishmaydi, shaxsiy ma'lumot aytmaydi; «sen botmisan» desa — AI yordamchi ekanini aytadi;
- bir chatga soatiga 3 tadan, kuniga jami 40 tadan ko'p yozmaydi; boshqa avto-javob botiga javob bermaydi (cheksiz yozishma bo'lmasligi uchun);
- siz o'zingiz javob yozib qo'ygan bo'lsangiz — o'tkazib yuboradi;
- **har bir javob nusxasi telefoningizga keladi**, nima deyilganini doim ko'rasiz.
`config.py` ga ixtiyoriy: `OWNER_NAME = "Samadbek"`, `AUTOREPLY_PERSONA = "Men o'qituvchiman, darslar haqida so'rashadi..."`.
Javob sifati Jarvis'dagi lokal AI (brain) ga bog'liq — avval bitta ishongan odamda sinab ko'ring. Xabarlar har 45 soniyada (batareyada 2-3 daqiqada) tekshiriladi, shuning uchun javob darrov emas, 1-3 daqiqada keladi.

## Batareya: qo'shimcha choralar (v12.1)
- **Sizsiz uxlaydi:** batareyada klaviatura/sichqoncha 30 daqiqa tegilmasa mikrofon o'chadi; biror tugma bosilsa yoki sichqoncha qimirlasa o'zi yoqiladi (`IDLE_PAUSE_MINUTES = 30`, `0` — o'chirish). Shu payt ovoz bilan uyg'otib bo'lmaydi, lekin telefon orqali buyruq berish va avto-javob ishlayveradi.
- **Tungi soatlar:** `QUIET_HOURS = ("23:30", "06:30")` — shu vaqtda mikrofon o'chiq.
- **Aniq sababni topish:** Jarvis tinch turganda (uxlab turganda) Terminal'da `bash ~/jarvis/energy_report.sh` ni ishga tushiring (20 soniya) va natijani yuboring — qaysi jarayon (Jarvis, Ollama, HUD yoki boshqa) batareyani yeyayotganini ko'rsatadi.

## Eslatma
- Bu kod Linux'da yozildi va mantiq testlari (`python3 jarvis_v12/tests/test_v12.py`) o'tdi, lekin **haqiqiy Mac'da sinab ko'rilmagan**. O'rnatish skripti shu sababli o'z-o'zini tekshiradi va xatoda avtomatik qaytaradi.
- Ovozni tanish ingliz tilida (v11.3 dagidek), shuning uchun buyruqlar inglizcha aytiladi.
- Telegram qo'ng'iroq tugmasini bosish Telegram ilovasi ichki tuzilishiga bog'liq — ba'zi versiyalarda topilmasligi mumkin; u holda Jarvis so'raydi.
