"""python3 tests/test_lite.py   — no Telegram, no internet: the brain is tested with fakes."""
import asyncio
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lite  # noqa: E402
from lite import Msg, Responder, Sender, Settings, allowed  # noqa: E402

fails = 0


def check(cond, label):
    global fails
    print(("PASS " if cond else "FAIL ") + label)
    fails += (not cond)


class FakeTG:
    def __init__(self):
        self.msgs, self.sent, self.next = [], [], 1000
        self.on_sleep = None

    def add(self, text="", out=False, kind="text", id=None):
        self.next += 1
        self.msgs.append(Msg(id or self.next, out, text, kind))
        return self.msgs[-1].id

    async def recent(self, chat, n):
        return list(self.msgs[-n:])

    async def send(self, chat, text):
        self.sent.append(text)
        return self.add(text, out=True)


async def instant(_):
    return None


def make(claude=None, **kw):
    tg, notes = FakeTG(), []

    async def notify(t):
        notes.append(t)
    d = tempfile.mkdtemp()
    st = Settings(grace=0, contacts_file=os.path.join(d, "c.txt"), info_file=os.path.join(d, "i.txt"), **kw)
    r = Responder(st, tg, notify, claude, sleep=instant, log=lambda m: None)
    return r, tg, notes, st


def run(coro):
    return asyncio.run(coro)


bro = Sender(name="Brother", id=1)

# ---- who is allowed
c = ["Brother", "NAVOIY-QORAKO'L O'QUV MARKAZI", "@aziz_u", "+998 90 123 45 67", "id:777", "Otabek Akam"]
check(allowed(Sender(name="Brother"), c) and allowed(Sender(name="my brother 🙂"), c), "name match, both directions")
check(allowed(Sender(name="Navoiy-Qorakoʻl Oʻquv Markazi"), c), "Telegram's ʻ apostrophes and capitals match")
check(allowed(Sender(name="x", username="Aziz_U"), c) and allowed(Sender(name="x", phone="998901234567"), c) and allowed(Sender(name="x", id=777), c), "@username, phone and id lines")
check(not allowed(Sender(name="Stranger"), c) and not allowed(Sender(name="Brother", bot=True), c) and not allowed(Sender(name=""), c), "strangers, bots, nameless are not")

# ---- a normal answer
seen = []


async def fake_claude(system, user):
    seen.append((system, user))
    return "Darslar 15:00 da boshlanadi."


r, tg, notes, st = make(fake_claude)
tg.add("old message from yesterday", id=1)                    # before Jarvis saw anything
mid = tg.add("dars soat nechada?")
run(r.on_message(5, mid, bro))
check(len(tg.sent) == 1 and tg.sent[0].startswith("Darslar 15:00") and tg.sent[0].endswith("🤖 Jarvis (avto-javob)"), "answers with the signature")
check("dars soat nechada?" in seen[0][1] and "is writing to Zufarbek, not to you" in seen[0][0] and "siz" in seen[0][0], "Claude gets the message, owner rule and tone notes")
check("old message" in seen[0][1] and notes == [], "context included; a routine answer does NOT bother your phone")
n = len(tg.sent)
run(r.on_message(5, mid, bro))
check(len(tg.sent) == n, "the same message is never answered twice")

# ---- burst of messages = one answer
r, tg, notes, st = make(fake_claude)
tg.add("hello", id=1)
a = tg.add("are you there")
b = tg.add("bro")
seen.clear()
run(r.on_message(5, a, bro))
check(len(tg.sent) == 1 and "are you there" in seen[0][1] and "bro" in seen[0][1], "several quick messages -> one answer covering all")

# ---- you answered yourself
r, tg, notes, st = make(fake_claude)
mid = tg.add("salom")
tg.add("qalaysan, men shu yerdaman", out=True)                 # you, from your phone
run(r.on_message(5, mid, bro))
check(not tg.sent, "you replied yourself during the wait -> Jarvis stays quiet")

# ---- messages that arrive while it is busy are not lost
r, tg, notes, st = make(fake_claude)
first = tg.add("birinchi")
orig = r.process
state = {"n": 0}


async def slow_process(chat, sender):
    state["n"] += 1
    if state["n"] == 1:
        asyncio.get_running_loop().create_task(r.on_message(chat, tg.add("ikkinchi (kech keldi)"), sender))
        await asyncio.sleep(0)
    return await orig(chat, sender)


r.process = slow_process
run(r.on_message(5, first, bro))
check(len(tg.sent) >= 1 and state["n"] >= 1, "late message does not crash / deadlock")

# ---- voice
r, tg, notes, st = make(fake_claude)
v = tg.add("", kind="voice")
seen.clear()
run(r.on_message(5, v, bro))
check(len(tg.sent) == 1 and "Zufarbek Jumayev hozir band" in tg.sent[0] and "o'zi javob yozadi" in tg.sent[0] and not seen, "voice message -> fixed reply, no AI call")
v2 = tg.add("", kind="voice")
run(r.on_message(5, v2, bro))
check(len(tg.sent) == 1 and any("yana ovozli xabar" in x for x in notes), "second voice within 30 min -> not answered, you are told")
p = tg.add("", kind="other")
run(r.on_message(5, p, bro))
check(len(tg.sent) == 1 and any("fayl/rasm" in x for x in notes), "photo without text -> you are told, nothing sent")

# ---- sensitive / ping-pong / limits
r, tg, notes, st = make(fake_claude)
run(r.on_message(5, tg.add("menga pul o'tkazib ber, karta raqamingni ayt"), bro))
check(not tg.sent and any("javob bermaydigan" in x for x in notes), "money -> no answer, you are told")
run(r.on_message(5, tg.add("🤖 Jarvis (avto-javob): hozir band"), bro))
check(not tg.sent, "another auto-reply bot is ignored")
r, tg, notes, st = make(fake_claude)
for i in range(5):
    run(r.on_message(5, tg.add(f"savol {i}"), bro))
check(len(tg.sent) == 3 and any("chegarasi tugadi" in x for x in notes), "max 3 replies per chat per hour")

# ---- no key / Claude down -> fixed sentences in the right language
r, tg, notes, st = make(None)
run(r.on_message(5, tg.add("nima gap, qalaysan, ishlar yaxshimi"), bro))
check("sun'iy intellekt" in tg.sent[0] and "Zufarbek" in tg.sent[0], "no Claude key -> correct Uzbek sentence")


async def broken(system, user):
    raise ConnectionError("offline")


r, tg, notes, st = make(broken)
run(r.on_message(5, tg.add("hello bro how are you"), bro))
check("AI assistant" in tg.sent[0], "Claude fails -> English sentence")

# ---- files and the prompt
r, tg, notes, st = make(fake_claude)
open(st.info_file, "w").write("# izoh\nNarx: 100 000 so'm")
check("Narx: 100 000 so'm" in r.info() and "izoh" not in r.info() and "Brother — Zufarbekning do'sti" in r.info(), "info.txt is read fresh, comments ignored, tone notes built in")
check(lite.read_lines("/nonexistent") == [], "missing file is fine")
env = tempfile.mktemp()
open(env, "w").write('OWNER_FULL_NAME=Zufarbek Jumayev\n# c\nX="q"\n')
for k in ("OWNER_FULL_NAME", "X"):
    os.environ.pop(k, None)
lite.load_env(env)
check(os.environ["OWNER_FULL_NAME"] == "Zufarbek Jumayev" and os.environ["X"] == "q", "env file with spaces and quotes")

# ---- Render: settings from environment variables, no disk
st = Settings.from_env({"CONTACTS": "Brother;Otabek Akam\n@aziz_u", "INFO": "Men kimman: Zufarbek;Narx: 100 000 so'm", "DATA_DIR": "/nonexistent"})
check(lite.get_contacts(st) == ["Brother", "Otabek Akam", "@aziz_u"], "CONTACTS env var (; or new lines)")
r2 = Responder(st, FakeTG(), None, None, sleep=instant, log=lambda m: None)
check("Men kimman: Zufarbek" in r2.info() and "Narx: 100 000 so'm" in r2.info() and "Brother — Zufarbekning do'sti" in r2.info(), "INFO env var + built-in tone notes")
st = Settings.from_env({"DATA_DIR": "/nonexistent"})
check("Brother" in lite.get_contacts(st) and "Javohir Aka" in lite.get_contacts(st), "no env, no file -> the built-in default contact list")
check("age" not in Responder(st, FakeTG(), None, None, sleep=instant).info().lower() and "18" not in Responder(st, FakeTG(), None, None, sleep=instant).info(), "built-in defaults contain no personal data")


async def health():
    srv = await lite.health_server(0)
    port = srv.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")
    await writer.drain()
    data = await reader.read(200)
    writer.close()
    srv.close()
    return data


check(b"200 OK" in run(health()), "health server answers 200 (Render web service / uptime pinger)")

good = "1" + "A" * 352
check(lite.clean_session("  \"" + good[:100] + "\n" + good[100:] + "\"  ") == good, "TG_SESSION: spaces, new lines and quotes are cleaned")
for bad in (good[:300], good + "x", "2" + "A" * 352, ""):
    try:
        lite.clean_session(bad)
        check(False, f"damaged TG_SESSION ({len(bad)} chars) must be rejected")
    except SystemExit as e:
        check("damaged" in str(e) and "353" in str(e), f"damaged TG_SESSION ({len(bad)} chars) -> clear message")

check(Settings().grace == 240 and Settings.from_env({}).grace == 240 and Settings.from_env({"GRACE_SECONDS": "60"}).grace == 60, "default wait is 4 minutes (GRACE_SECONDS can change it)")
waits = []


async def record(sec):
    waits.append(sec)


r3, tg3, n3, st3 = make(fake_claude)
st3.grace = 240
r3.sleep = record
run(r3.on_message(5, tg3.add("salom"), bro))
check(waits and 240 <= waits[0] <= 260 and len(tg3.sent) == 1, f"waits about 4 minutes before answering ({waits[0]:.0f}s)")
tg3.msgs.clear(); waits.clear()
mid = tg3.add("savol")
orig_sleep = r3.sleep


async def owner_answers(sec):                                   # you reply during the 4 minutes
    waits.append(sec)
    tg3.add("men shu yerdaman", out=True)


r3.sleep = owner_answers
n = len(tg3.sent)
run(r3.on_message(6, mid, bro))
check(len(tg3.sent) == n and waits, "you answer within the 4 minutes -> Jarvis stays quiet")

# ---- Muhammad Akam: card number / amount (card lives only in env, never in the code)
CARD = "0000 1111 2222 3333"                                   # a made-up number for the test
check("9860" not in open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lite.py")).read(), "the real card number is not in the source code")
muh = Sender(name="Muhammad Akam", id=9, contact=True)


def pay_setup(**kw):
    r, tg, notes, st = make(fake_claude, **kw)
    st.pay_card, st.pay_contact, st.pay_amount, st.pay_for = CARD, "Muhammad Akam", "13$", "cefr tys boti serveri"
    return r, tg, notes, st


for q in ("karta raqamingizni tashlab yuboring", "Qayerga tashlay?", "Номер карты?", "send me your card number please"):
    r, tg, notes, st = pay_setup()
    run(r.on_message(5, tg.add(q), muh))
    check(len(tg.sent) == 1 and CARD in tg.sent[0] and "13$" in tg.sent[0] and "cefr tys" in tg.sent[0], f"card asked ({q!r}) -> card number + 13$")
for q in ("qancha tashlay?", "Summa necha?", "how much", "13$ mi?"):
    r, tg, notes, st = pay_setup()
    run(r.on_message(5, tg.add(q), muh))
    check(len(tg.sent) == 1 and "13$" in tg.sent[0] and CARD not in tg.sent[0], f"amount asked ({q!r}) -> only 13$")
r, tg, notes, st = pay_setup()
seen.clear()
run(r.on_message(5, tg.add("botda xatolik bor, tekshirib bering"), muh))
check(any("boshqa narsa yozdi" in x and "botda xatolik" in x for x in notes) and len(tg.sent) == 1 and CARD not in tg.sent[0] and seen, "something else -> you are told, normal AI reply (no card)")
r, tg, notes, st = pay_setup()
run(r.on_message(5, tg.add("ha tashladim, tekshirib ko'ring"), muh))
check(any("boshqa narsa yozdi" in x for x in notes) and CARD not in " ".join(tg.sent), "'I paid' -> you are told")
r, tg, notes, st = pay_setup()
run(r.on_message(5, tg.add("karta raqamingiz?"), Sender(name="Muhammad Akam", id=10, contact=False)))
check(CARD not in " ".join(tg.sent), "same name but NOT a saved contact -> card number is never given")
run(r.on_message(5, tg.add("karta raqamingiz?"), Sender(name="Muhammad Akam", id=10)))
check(CARD not in " ".join(tg.sent), "unknown contact status -> card number is never given")
r, tg, notes, st = pay_setup()
run(r.on_message(5, tg.add("karta raqamingiz?"), Sender(name="Brother", id=11, contact=True)))
check(CARD not in " ".join(tg.sent) and any("javob bermaydigan" in x for x in notes), "any other contact asking for the card -> not given, you are told")
r, tg, notes, st = make(fake_claude)
run(r.on_message(5, tg.add("karta raqamingiz?"), muh))
check(not tg.sent or all("karta raqami:" not in x for x in tg.sent), "PAY_CARD not set -> the rule is off")
check(Settings.from_env({"PAY_CARD": " 1111 "}).pay_card == "1111" and Settings.from_env({}).pay_amount == "13$", "PAY_* settings from env")

# ---- the bot writes to you ONLY when something needs you
r, tg, notes, st = make(fake_claude)
run(r.on_message(5, tg.add("salom, qalaysan"), bro))
check(len(tg.sent) == 1 and notes == [], "routine answer -> no message to your phone")
r, tg, notes, st = make(fake_claude)
st.notify_all = True
run(r.on_message(5, tg.add("salom, qalaysan"), bro))
check(len(notes) == 1 and "ga javob berdim" in notes[0], "NOTIFY_ALL_REPLIES=1 -> every reply is copied to your phone")
check(Settings.from_env({"NOTIFY_ALL_REPLIES": "1"}).notify_all and not Settings.from_env({}).notify_all, "NOTIFY_ALL_REPLIES setting")


async def needs_you(system, user):
    return "Bu savolga Zufarbek o'zi javob beradi. [[OWNER]]"


r, tg, notes, st = make(needs_you)
run(r.on_message(5, tg.add("ertaga uchrashamizmi?"), bro))
check(len(tg.sent) == 1 and "[[OWNER]]" not in tg.sent[0] and "Zufarbek o'zi javob beradi" in tg.sent[0], "the [[OWNER]] marker never reaches the other person")
check(len(notes) == 1 and "kutyapti" in notes[0] and "ertaga uchrashamizmi?" in notes[0], "Claude says it needs you -> your phone is told, with the message")
r, tg, notes, st = make(broken)
run(r.on_message(5, tg.add("hello bro how are you"), bro))
check(len(tg.sent) == 1 and len(notes) == 1 and "kutyapti" in notes[0], "Claude was down (fixed sentence sent) -> your phone is told")
r, tg, notes, st = make(fake_claude)
run(r.on_message(5, tg.add("", kind="voice"), bro))
check(len(notes) == 1 and "ovozli xabar yubordi" in notes[0], "voice message -> your phone is told")
check("[[OWNER]]" in Responder(st, tg, None, None).system_prompt() and "[[OWNER]]" not in lite.TEMPLATES["uz"], "Claude is told how to flag what needs you")
r, tg, notes, st = pay_setup()
run(r.on_message(5, tg.add("karta raqamingiz?"), muh))
check(len(notes) == 1 and "karta/summani so'radi" in notes[0] and CARD not in notes[0], "card asked -> your phone is told (without repeating the number)")


async def notify_check():
    sent_bot, sent_me = [], []

    class C:
        async def send_message(self, who, text):
            sent_me.append(text)

    import urllib.request as ur
    real = ur.urlopen
    ur.urlopen = lambda url, data=None, timeout=0: (sent_bot.append((url, data)) or type("R", (), {"read": lambda self: b"{}"})())
    try:
        await lite.make_notify(C(), {"NOTIFY_BOT_TOKEN": "TOKEN"}, 12345)("hello")
        def boom(*a, **k):
            raise OSError("chat not found")
        ur.urlopen = boom
        await lite.make_notify(C(), {"NOTIFY_BOT_TOKEN": "TOKEN"}, 12345)("fallback")
        await lite.make_notify(C(), {}, 12345)("no bot")
    finally:
        ur.urlopen = real
    return sent_bot, sent_me


sb, sm = run(notify_check())
check(len(sb) == 1 and "TOKEN" in sb[0][0] and b"chat_id=12345" in sb[0][1], "bot notification goes to your own account id (no NOTIFY_CHAT_ID needed)")
check(sm == ["fallback", "no bot"], "bot can't deliver / no bot -> Saved Messages")

# ---- reminders: nothing from you for 30 minutes -> "will you answer?"
clock = [1000.0]


def remind_setup(claude=needs_you, **kw):
    r, tg, notes, st = make(claude, **kw)
    r.now = lambda: clock[0]
    return r, tg, notes, st


r, tg, notes, st = remind_setup()
run(r.on_message(5, tg.add("ertaga uchrashamizmi?"), bro))
check(len(notes) == 1 and 5 in r.pending, "needs-you message -> notified once and a reminder is planned")
clock[0] += 29 * 60
run(r.check_reminders())
check(len(notes) == 1, "before 30 minutes -> no reminder")
clock[0] += 2 * 60
run(r.check_reminders())
check(len(notes) == 2 and "Javob berasizmi" in notes[1] and "yo'q" in notes[1] and "ertaga uchrashamizmi?" in notes[1], "after 30 minutes -> 'will you answer?' with the message and the way to say no")
clock[0] += 31 * 60
run(r.check_reminders())
check(len(notes) == 3 and not r.pending, "second (last) reminder, then it stops")
clock[0] += 99 * 60
run(r.check_reminders())
check(len(notes) == 3, "no more reminders after the limit")

r, tg, notes, st = remind_setup()
run(r.on_message(5, tg.add("ertaga uchrashamizmi?"), bro))
tg.add("ha, ertaga ko'rishamiz", out=True)                    # you answered (from the phone)
clock[0] += 31 * 60
run(r.check_reminders())
check(len(notes) == 1 and not r.pending, "you answered the person -> no reminder")

r, tg, notes, st = remind_setup(fake_claude)
run(r.on_message(5, tg.add("", kind="voice"), bro))
clock[0] += 31 * 60
run(r.check_reminders())
check(len(notes) == 2 and "Javob berasizmi" in notes[1], "Jarvis's own auto-reply does not count as YOUR answer -> still reminds")

r, tg, notes, st = remind_setup()
run(r.on_message(5, tg.add("ertaga uchrashamizmi?"), bro))
check(r.dismiss_all() == 1 and not r.pending, "«yo'q» to the bot -> reminders cancelled")
clock[0] += 99 * 60
run(r.check_reminders())
check(len(notes) == 1, "...and nothing is sent afterwards")
check(all(lite.DISMISS.fullmatch(lite.norm(x)) for x in ("yo'q", "Yo‘q", "/skip", "no", "нет", "bekor qil", "yo'q.")) and not any(lite.DISMISS.fullmatch(lite.norm(x)) for x in ("yoqimli", "keyin aytaman", "yo'q, unga ayt", "bunga javob berishni xohlamayman")), "dismiss words are only the WHOLE short message")

r, tg, notes, st = remind_setup(fake_claude)
run(r.on_message(5, tg.add("salom"), bro))
clock[0] += 99 * 60
run(r.check_reminders())
check(not r.pending and notes == [], "routine small talk never creates reminders")
r, tg, notes, st = pay_setup()
r.now = lambda: clock[0]
run(r.on_message(5, tg.add("karta raqamingiz?"), muh))
check(not r.pending, "card/amount answers never create reminders")
check(Settings.from_env({}).remind_after == 1800 and Settings.from_env({}).remind_times == 2 and Settings.from_env({"REMIND_MINUTES": "10", "REMIND_TIMES": "3"}).remind_after == 600, "REMIND_MINUTES / REMIND_TIMES settings")

# ---- you talk to the bot in plain words
import json as _json  # noqa: E402


def owner_setup(plan, **kw):
    prompts = []

    async def claude_owner(system, user):
        prompts.append((system, user))
        return plan if isinstance(plan, str) else _json.dumps(plan)

    r, tg, notes, st = make(claude_owner, **kw)
    r.now = lambda: clock[0]

    async def yielding(sec):                                   # like the real asyncio.sleep: lets other messages in
        await asyncio.sleep(0)
    r.sleep = yielding
    r.owner_hist.clear()
    return r, tg, notes, st, prompts


nav = Sender(name="NAVOIY-QORAKO'L O'QUV MARKAZI", id=21)
r, tg, notes, st, prompts = owner_setup({"action": "dismiss_and_send", "message": "Assalomu alaykum! Zufarbek hozir bu masalada javob berolmaydi, tushunganingiz uchun rahmat.", "reply": "ok"})
tg.add("menga hali ham javob bermadingiz nimaga")
last = tg.add("menga hali ham javob bermadingiz nimaga")
run(r.attention(5, nav.name, "menga hali ham javob bermadingiz nimaga", "🙋 NAVOIY kutyapti"))
check("🔖 5" in notes[0], "every note ends with 🔖 <chat id> (so a reply to it identifies the person)")


async def owner_burst():
    await asyncio.gather(r.on_owner_message("bunga javob berishni xohlamayman", "🙋 NAVOIY kutyapti\n\n🔖 5"),
                         r.on_owner_message("oziga aytib qoy"), r.on_owner_message("chiroyli ravishda"))


sent_before = len(tg.sent)
run(owner_burst())
check(len(prompts) == 1 and all(x in prompts[0][1] for x in ("bunga javob berishni xohlamayman", "oziga aytib qoy", "chiroyli ravishda")), "three quick messages -> ONE Claude call that sees all three")
check("menga hali ham javob bermadingiz" in prompts[0][1] and "NAVOIY-QORAKO'L" in prompts[0][1], "Claude also sees the person's recent messages")
check(len(tg.sent) == sent_before + 1 and "Zufarbek hozir bu masalada" in tg.sent[-1] and tg.sent[-1].endswith("🤖 Jarvis (avto-javob)"), "the polite message is sent to the person, marked as AI")
check(5 not in r.pending and any("✅" in x and "yubordim" in x and "Zufarbek hozir bu masalada" in x for x in notes), "reminders stopped, you are shown exactly what was sent")
check(tg.msgs[-1].id in r.our_ids, "that message counts as the assistant's, not yours")

r, tg, notes, st, prompts = owner_setup({"action": "dismiss", "reply": "ok"})
run(r.attention(5, nav.name, "savol", "🙋 kutyapti"))
run(r.on_owner_message("bunga javob berishni xohlamayman"))
check(not tg.sent and 5 not in r.pending and any("boshqa eslatmayman" in x for x in notes), "'I don't want to answer' -> reminders stop, nothing is sent to the person")

r, tg, notes, st, prompts = owner_setup({"action": "ask", "reply": "Unga nima deb yozay?"})
run(r.attention(5, nav.name, "savol", "🙋 kutyapti"))
run(r.on_owner_message("unga yoz"))
check(not tg.sent and any("Unga nima deb yozay?" in x for x in notes) and 5 in r.pending, "unclear -> the bot asks you, sends nothing")

r, tg, notes, st, prompts = owner_setup({"action": "send", "message": "salom", "reply": ""})
run(r.on_owner_message("unga salom ayt"))
check(not prompts and not tg.sent and any("Qaysi odam" in x for x in notes), "no person known -> asks which one, no AI call")

for bad in ("bu JSON emas", '{"action": "delete_everything", "message": "x"}', '{"action": "send", "message": ""}'):
    r, tg, notes, st, prompts = owner_setup(bad)
    run(r.attention(5, nav.name, "savol", "🙋 kutyapti"))
    run(r.on_owner_message("unga ayt"))
    check(not tg.sent, f"garbled/unknown AI answer {bad[:25]!r} -> nothing is sent")

r, tg, notes, st = make(None)
run(r.attention(5, nav.name, "savol", "🙋 kutyapti"))
run(r.on_owner_message("unga ayt"))
check(not tg.sent and any("AI ishlamayapti" in x for x in notes), "no Claude key -> told, nothing sent")

r, tg, notes, st, prompts = owner_setup({"action": "none", "reply": "Marhamat 🙂"})
run(r.attention(5, nav.name, "savol", "🙋 kutyapti"))
run(r.on_owner_message("rahmat"))
check(not tg.sent and 5 in r.pending, "'thanks' -> nothing happens")
check(lite.parse_plan('Mana: {"action": "send", "message": "Salom!", "reply": "ok"} tamom')["message"] == "Salom!", "JSON is found inside extra words")

check(Settings().model == "claude-haiku-5-5" and Settings.from_env({}).model == "claude-haiku-5-5" and Settings.from_env({"AUTOREPLY_MODEL": "claude-sonnet-5-5"}).model == "claude-sonnet-5-5", "default model is Haiku 5.5 (cheap); AUTOREPLY_MODEL can change it")

# ---- everyone is answered; parents are only reported; strangers get one fixed sentence
import types as _types  # noqa: E402
S = lambda **k: _types.SimpleNamespace(**k)  # noqa: E731
check(all(lite.skip_account(u) for u in (None, S(id=777000), S(id=5, bot=True), S(id=5, deleted=True), S(id=5, support=True), S(id=5, scam=True), S(id=5, is_self=True), S(id=5, verified=True)))
      and not lite.skip_account(S(id=5, bot=False, first_name="Ali")), "bots, Telegram's own account, deleted/flagged accounts and yourself are never answered")

dad = Sender(name="Dadajonim", id=31, contact=True)
mom = Sender(name="Ayajonim ❤️", id=32, contact=True)
stranger = Sender(name="Random Person", id=33, contact=False)
saved = Sender(name="Klassdosh Ali", id=34, contact=True)
r, tg, notes, st = make(fake_claude)
check([r.relation(x) for x in (dad, mom, stranger, saved, bro)] == ["parent", "parent", "stranger", "known", "known"], "relation: parents / strangers / saved contacts / listed")
check(Settings().parents == ("Dadajonim", "Ayajonim") and Settings.from_env({"PARENTS": "Dada;Oyi"}).parents == ("Dada", "Oyi") and Settings.from_env({}).reply_to == "all" and Settings.from_env({"REPLY_TO": "list"}).reply_to == "list", "REPLY_TO / PARENTS settings")

for who in (dad, mom):
    r, tg, notes, st = make(fake_claude)
    seen.clear()
    run(r.on_message(5, tg.add("o'g'lim, qayerdasan?"), who))
    check(not tg.sent and not seen and len(notes) == 1 and "👪" in notes[0] and "qayerdasan" in notes[0] and "🔖 5" in notes[0], f"{who.name}: no reply at all, you are told at once")
r, tg, notes, st = make(fake_claude)
run(r.on_message(5, tg.add("", kind="voice"), mom))
check(not tg.sent and len(notes) == 1 and "ovozli xabar yubordi" in notes[0], "parent voice message -> only you are told")
clock[0] += 31 * 60
r.now = lambda: clock[0]
run(r.on_message(6, tg.add("qayerdasan?"), dad))
clock[0] += 31 * 60
run(r.check_reminders())
check(any("Javob berasizmi" in x for x in notes), "parents' messages are reminded about if you do not answer")

r, tg, notes, st = make(fake_claude)
seen.clear()
run(r.on_message(7, tg.add("salom, qalaysan, ishlar yaxshimi"), stranger))
check(len(tg.sent) == 1 and "sun'iy intellekt" in tg.sent[0] and "Zufarbek" in tg.sent[0] and not seen and notes == [], "stranger -> fixed 'busy' sentence, no AI call, no note to you")
check("Dasturchi" not in tg.sent[0] and "yoshdaman" not in tg.sent[0], "stranger gets no personal facts")
run(r.on_message(7, tg.add("javob bering"), stranger))
check(len(tg.sent) == 1, "the same stranger is answered at most once per 6 hours")
r2, tg2, notes2, st2 = make(fake_claude)
run(r2.on_message(8, tg2.add("menga pul o'tkazing, karta raqami"), stranger))
check(not tg2.sent and notes2 == [], "stranger asking about money/cards -> ignored silently")
r2, tg2, notes2, st2 = make(fake_claude)
run(r2.on_message(8, tg2.add("", kind="voice"), stranger))
check(len(tg2.sent) == 1 and "ovozli xabarni eshita olmayman" in tg2.sent[0] and notes2 == [], "stranger voice message -> fixed reply")
r2, tg2, notes2, st2 = make(fake_claude)
for i in range(20):
    run(r2.on_message(100 + i, tg2.add("salom"), Sender(name=f"Spam {i}", id=100 + i, contact=False)))
check(len(tg2.sent) == lite.STRANGER_PER_DAY, f"strangers have their own daily cap ({len(tg2.sent)})")
run(r2.on_message(5, tg2.add("dars soat nechada?"), bro))
check(len(tg2.sent) == lite.STRANGER_PER_DAY + 1, "...so they can never use up your contacts' share")

r, tg, notes, st = make(fake_claude)
seen.clear()
run(r.on_message(9, tg.add("dars soat nechada?"), saved))
check(len(tg.sent) == 1 and seen, "a contact saved in your Telegram (not in the list) gets the normal AI answer")

print("\nFAILED:", fails) if fails else print("\nALL PASSED")
sys.exit(1 if fails else 0)
