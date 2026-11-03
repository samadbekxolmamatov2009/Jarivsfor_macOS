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

    def add(self, text="", out=False, kind="text", id=None, ts=0.0):
        self.next += 1
        self.msgs.append(Msg(id or self.next, out, text, kind, ts))
        return self.msgs[-1].id

    async def recent(self, chat, n):
        return list(self.msgs[-n:])

    async def send(self, chat, text):
        self.sent.append(text)
        return self.add(text, out=True)


async def instant(_):
    return None


def make(claude=None, **kw):
    tg, notes, quiet = FakeTG(), [], []

    async def notify(t, silent=False):
        notes.append(t)
        if silent:
            quiet.append(t)
    d = tempfile.mkdtemp()
    kw.setdefault("busy_hours", "off")                      # tests do not depend on the real clock
    st = Settings(grace=0, contacts_file=os.path.join(d, "c.txt"), info_file=os.path.join(d, "i.txt"), **kw)
    r = Responder(st, tg, notify, claude, sleep=instant, log=lambda m: None)
    r.silent_notes = quiet
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

check(Settings().grace == 900 and Settings.from_env({}).grace == 900 and Settings.from_env({"GRACE_SECONDS": "60"}).grace == 60, "default wait is 15 minutes (GRACE_SECONDS can change it)")
waits = []


async def record(sec):
    waits.append(sec)


r3, tg3, n3, st3 = make(fake_claude)
st3.grace = 900
r3.sleep = record
run(r3.on_message(5, tg3.add("salom"), bro))
check(waits and 900 <= waits[0] <= 920 and len(tg3.sent) == 1, f"waits about 15 minutes before answering ({waits[0]:.0f}s)")
tg3.msgs.clear(); waits.clear()
mid = tg3.add("savol")
orig_sleep = r3.sleep


async def owner_answers(sec):                                   # you reply during the 4 minutes
    waits.append(sec)
    tg3.add("men shu yerdaman", out=True)


r3.sleep = owner_answers
n = len(tg3.sent)
run(r3.on_message(6, mid, bro))
check(len(tg3.sent) == n and waits, "you answer within the 15 minutes -> Jarvis stays quiet")

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
        async def send_message(self, who, text, silent=False):
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
check(not tg.sent and any("Qaysi odam" in x for x in notes), "no person named and none known -> asks which one, sends nothing")

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

# ---- the mistake from the screenshot: "send it to Muhammad Akam" must NOT go to Brother
class MultiTG:
    """Several chats: chat id -> messages; find() by name or id; delete()."""
    def __init__(self):
        self.chats = {5: [], 6046141246: []}
        self.people = [(5, "Brother"), (6046141246, "Muhammad Akam"), (7, "Otabek Akam"), (8, "Javohir Aka")]
        self.n = 5000
        self.deleted = []

    def add(self, chat, text, out=False, ts=0.0):
        self.n += 1
        self.chats[chat].append(Msg(self.n, out, text, "text", ts))
        return self.n

    async def recent(self, chat, n):
        return list(self.chats.get(chat, [])[-n:])

    async def send(self, chat, text):
        return self.add(chat, text, out=True)

    async def find(self, q):
        qn = lite.norm(q)
        if qn.isdigit():
            return [(c, nm) for c, nm in self.people if str(c) == qn]
        hits = [(c, nm) for c, nm in self.people if qn in lite.norm(nm) or lite.norm(nm) in qn]
        exact = [h for h in hits if lite.norm(h[1]) == qn]
        return exact if len(exact) == 1 else hits

    async def delete(self, chat, ids):
        self.deleted.append((chat, list(ids)))
        self.chats[chat] = [m for m in self.chats[chat] if m.id not in ids]


def multi_setup(plans):
    answers = list(plans)
    prompts = []

    async def claude_multi(system, user):
        prompts.append((system, user))
        return _json.dumps(answers.pop(0))

    notes = []

    async def notify(x, silent=False):
        notes.append(x)
    tg = MultiTG()
    d = tempfile.mkdtemp()
    st = Settings(grace=0, busy_hours="off", contacts_file=os.path.join(d, "c.txt"), info_file=os.path.join(d, "i.txt"))
    r = Responder(st, tg, notify, claude_multi, sleep=yielding_sleep, log=lambda m: None)
    r.now = lambda: clock[0]
    return r, tg, notes, prompts


async def yielding_sleep(sec):
    await asyncio.sleep(0)


MSG = "Zufarbek sizga yozishni so'radi: agar 5-noyabrgacha server to'lovi amalga oshirilmasa, botimiz ishlashdan to'xtaydi."
r, tg, notes, prompts = multi_setup([{"action": "send", "target": "Muhammad Akam", "message": MSG, "reply": ""}])
run(r.attention(5, "Brother", "bazani bering", "🙋 Brother kutyapti"))            # the latest note is about Brother
run(r.on_owner_message("6046141246 shu chat idilik Muhammad Akam degan contactimga xabar yoz: agar 5-noyabrgacha server tolovni amalga oshirmasak botimiz ishlashdan toxtaydi"))
akam = [m for m in tg.chats[6046141246] if m.out]
check(len(akam) == 1 and "5-noyabrgacha" in akam[0].text and not [m for m in tg.chats[5] if m.out], "named person gets the message, Brother (latest note) gets NOTHING")
check("Current conversation person: Brother" in prompts[0][1] and '"target"' in prompts[0][0], "Claude is told who the current person is and to fill 'target'")
check(any("Muhammad Akam ga yubordim" in x for x in notes), "you are shown who it was sent to")

r, tg, notes, prompts = multi_setup([{"action": "send", "target": "6046141246", "message": MSG, "reply": ""}])
run(r.on_owner_message("6046141246 ga yoz: ..."))
check(len([m for m in tg.chats[6046141246] if m.out]) == 1, "a chat id works as the target (even with no current person)")

r, tg, notes, prompts = multi_setup([{"action": "send", "target": "Akam", "message": MSG, "reply": ""}])
run(r.attention(5, "Brother", "x", "🙋"))
run(r.on_owner_message("Akamga yoz"))
check(not any(tg.chats[c] for c in tg.chats if any(m.out for m in tg.chats[c])) and any("qaysi biri" in x and "Otabek Akam" in x and "Muhammad Akam" in x for x in notes), "ambiguous name ('Akam') -> asks which one, sends nothing")

r, tg, notes, prompts = multi_setup([{"action": "send", "target": "Nonexistent Person", "message": MSG, "reply": ""}])
run(r.attention(5, "Brother", "x", "🙋"))
run(r.on_owner_message("Nonexistent Personga yoz"))
check(not any(m.out for c in tg.chats for m in tg.chats[c]) and any("topa olmadim" in x for x in notes), "unknown name -> 'not found', sends nothing (not to the latest person)")

# correction + duplicate guard
r, tg, notes, prompts = multi_setup([
    {"action": "send", "target": "", "message": MSG, "reply": ""},                          # first (wrong, it goes to Brother = current)
    {"action": "send", "target": "", "message": MSG, "reply": ""},                          # the same text again to the same person
    {"action": "send", "target": "Muhammad Akam", "message": MSG, "reply": ""},             # the correction
])
run(r.attention(5, "Brother", "x", "🙋"))
run(r.on_owner_message("serverga to'lov haqida yoz"))
run(r.on_owner_message("yana yoz"))
check(len([m for m in tg.chats[5] if m.out]) == 1 and any("allaqachon yuborilgan" in x for x in notes), "the same message is never sent twice to the same chat within 10 minutes")
run(r.on_owner_message("brotherga emas muhammad akam deganiga yubor degandim"))
check(len([m for m in tg.chats[6046141246] if m.out]) == 1, "'not to Brother, to Muhammad Akam' -> goes to Muhammad Akam")

# take back a wrong message
r, tg, notes, prompts = multi_setup([{"action": "send", "target": "", "message": MSG, "reply": ""},
                                     {"action": "delete_last", "target": "Brother", "message": "", "reply": ""}])
run(r.attention(5, "Brother", "x", "🙋"))
run(r.on_owner_message("yoz"))
mine = [m for m in tg.chats[5] if m.out]
tg.add(5, "oddiy xabarim, o'chirma", out=True)                                         # YOUR own message in the same chat
run(r.on_owner_message("brotherga yuborganingni o'chir"))
check(tg.deleted and tg.deleted[0][0] == 5 and tg.deleted[0][1] == [mine[0].id], "'delete it' removes the assistant's message from that chat")
check(any(m.text == "oddiy xabarim, o'chirma" for m in tg.chats[5]) and any("o'chirdim" in x for x in notes), "...and never touches your own messages")

# after a restart the in-memory list is empty: only messages carrying the assistant's mark are found
r, tg, notes, prompts = multi_setup([{"action": "delete_last", "target": "Brother", "message": "", "reply": ""}])
tg.add(5, "salom aka", out=True)
sig_id = tg.add(5, "Zufarbek band.\n\n🤖 Jarvis (avto-javob)", out=True)
run(r.on_owner_message("brotherga yuborganingni o'chir"))
check(tg.deleted == [(5, [sig_id])], "after a restart it still finds only the messages that carry the assistant's mark")
check(lite.parse_plan('{"action": "delete_last", "target": "Brother"}')["target"] == "Brother" and lite.parse_plan('{"action": "send", "message": "x"}')["target"] == "", "plan parsing: target and delete_last")

# ================= modes: 15 minutes, night ("uxladim"), work, busy, schedule, morning summary =================
import datetime as _dt  # noqa: E402
import modes  # noqa: E402

TZ = _dt.timezone(_dt.timedelta(hours=5))
at = lambda day, h, m=0: _dt.datetime(2026, 11, day, h, m, tzinfo=TZ).timestamp()  # noqa: E731   (2 Nov 2026 = Monday)
SCHED = "mon,wed,fri 16:00-18:00; tue,thu,sat 17:00-19:30"

sc = modes.parse_schedule(SCHED)
check(sc.is_open(_dt.datetime(2026, 11, 2, 16, 30, tzinfo=TZ)) and not sc.is_open(_dt.datetime(2026, 11, 2, 18, 0, tzinfo=TZ))
      and sc.is_open(_dt.datetime(2026, 11, 3, 17, 0, tzinfo=TZ)) and not any(sc.is_open(_dt.datetime(2026, 11, 8, h, 0, tzinfo=TZ)) for h in range(24)),
      "schedule windows: Mon/Wed/Fri 16-18, Tue/Thu/Sat 17-19:30, none on Sunday")
check(modes.parse_schedule("off") is None and modes.parse_schedule("") is None and modes.parse_schedule("garbage") is None, "BUSY_HOURS=off / garbage -> no schedule")
check(sc.describe() == "dushanba/chorshanba/juma 16:00–18:00; seshanba/payshanba/shanba 17:00–19:30", "schedule is described in Uzbek")


def mode_setup(sched=None, t0=None, claude=fake_claude):
    r, tg, notes, st = make(claude, busy_hours=sched or "off")
    r.now = lambda: clock[0]
    clock[0] = t0 if t0 is not None else at(2, 17, 0)
    r.last_kind = r.effective().kind                          # like a real start: remember the mode we begin in
    return r, tg, notes, st


# --- 1) free time (outside your busy hours): nobody answers for 15 minutes -> "busy" (the AI knows it)
r, tg, notes, st = mode_setup(SCHED, at(2, 12, 0))
check(r.effective().kind == "work", "outside the busy hours you are available")
st.grace = 900
seen.clear()
run(r.on_message(5, tg.add("dars soat nechada?"), bro))
check(len(tg.sent) == 1 and "really is busy right now" in seen[0][0] and "about 15 minutes" in seen[0][0], "free time: the AI is told he did not answer for 15 minutes, so he really is busy")

# --- 2) night: "uxladim"
r, tg, notes, st = mode_setup()
run(r.apply_mode("night"))
check(r.effective().kind == "night" and notes and "Tungi rejim yoqildi" in notes[0] and r.silent_notes, "'uxladim' -> night mode, confirmation arrives silently")
check(modes.parent_reply("Dadajonim", "Zufarbek") == "Assalomu alaykum, dadajon! Zufarbek hozir uxlayapti. Ertalab o'zi sizga yozadi.", "parents' night sentence")
seen.clear()
run(r.on_message(5, tg.add("salom, ertaga dars bormi?"), bro))
check(len(tg.sent) == 1 and "bugungi ish vaqti tugagani" in tg.sent[0] and "Ertaga o'zi sizga javob beradi" in tg.sent[0] and not seen,
      "night: 'today's working time is over, he will answer tomorrow' (fixed text, no AI call)")
run(r.on_message(5, tg.add("hoy javob ber"), bro))
check(len(tg.sent) == 1, "night: the same person is told only once")
run(r.on_message(6, tg.add("hello there"), Sender(name="Random Person", id=61, contact=False)))
check(len(tg.sent) == 2 and "working hours are over for today" in tg.sent[-1], "night: a stranger is told too, in English for English")
run(r.on_message(7, tg.add("", kind="voice"), Sender(name="Otabek Akam", id=62)))
check(len(tg.sent) == 3 and "ish vaqti tugagani" in tg.sent[-1], "night: a voice message gets the same sentence")
quiet_before = len(r.silent_notes)
run(r.attention(9, "Brother", "xabar", "🙋 Brother kutyapti"))
check(len(r.silent_notes) == quiet_before + 1, "night: notes to your phone are silent")

# --- 3) parents at night: polite sentence, silent note
r, tg, notes, st = mode_setup()
run(r.apply_mode("night"))
run(r.on_message(5, tg.add("o'g'lim, uxladingmi?"), dad))
check(len(tg.sent) == 1 and tg.sent[0].startswith("Assalomu alaykum, dadajon!") and "uxlayapti" in tg.sent[0] and "Zufarbek" in tg.sent[0], "night: Dad gets a polite message (third person, 'dadajon')")
check(any("Dadajonim yozdi" in x for x in r.silent_notes), "night: your note about Dad is silent")
r2, tg2, n2, st2 = mode_setup()
run(r2.apply_mode("night"))
run(r2.on_message(6, tg2.add("o'g'lim"), mom))
check(tg2.sent and tg2.sent[0].startswith("Assalomu alaykum, ayajon!"), "night: Mom is addressed as 'ayajon'")
r3, tg3, n3, st3 = mode_setup()
run(r3.on_message(6, tg3.add("o'g'lim"), mom))
check(not tg3.sent and any("Ayajonim" in x and "yozdi" in x for x in n3) and not r3.silent_notes, "daytime: parents still get NOTHING from Jarvis, and the note rings")

# --- 4) back to work + morning summary
r, tg, notes, st = mode_setup()
run(r.apply_mode("night"))
run(r.on_message(5, tg.add("salom, ertaga dars bormi?"), bro))
run(r.on_message(6, tg.add("o'g'lim"), dad))
notes.clear()
run(r.apply_mode("work"))
check(r.effective().kind == "work" and notes and "Ish rejimi yoqildi" in notes[0] and "2 kishi yozdi" in notes[0] and "Brother (1)" in notes[0] and "dars bormi" in notes[0] and "Dadajonim" in notes[0], "work: morning summary lists who wrote at night")
check(notes[0] not in r.silent_notes, "...and it is not silent")
notes.clear()
run(r.apply_mode("work"))
check(any("allaqachon" in x for x in notes), "work when already working -> says so")
seen.clear(); n = len(tg.sent)
run(r.on_message(5, tg.add("yana savol"), bro))
check(len(tg.sent) == n + 1 and seen, "back to work: normal AI answers again")

# --- 5) timed busy mode
r, tg, notes, st = mode_setup(None, at(2, 15, 0))
run(r.apply_mode("busy", minutes=120, note="dars o'tmoqda"))
check(r.effective().kind == "busy" and any("soat 17:00 gacha" in x for x in notes), "busy for 2 hours -> confirmed with the end time")
run(r.on_message(5, tg.add("salom"), bro))
check(len(tg.sent) == 1 and "hozir band (dars o'tmoqda)" in tg.sent[0] and "Soat 17:00 dan keyin" in tg.sent[0], "busy: 'busy (dars o'tmoqda), answers after 17:00'")
clock[0] = at(2, 17, 5)
notes.clear()
run(r.tick())
check(r.effective().kind == "work" and any("Band vaqt tugadi" in x and "Brother" in x for x in notes), "busy time over -> back to work by itself, with a summary")
r, tg, notes, st = mode_setup(None, at(2, 15, 0))
run(r.apply_mode("busy", until_str="17:30", note="yig'ilish"))
check(r.override["until"] == at(2, 17, 30), "busy 'until 17:30'")
r, tg, notes, st = mode_setup(None, at(2, 18, 0))
run(r.apply_mode("busy", until_str="17:30"))
check(r.override["until"] == at(3, 17, 30), "busy 'until 17:30' said at 18:00 -> tomorrow")

# --- 6) your BUSY hours work by themselves (Mon/Wed/Fri 16:00-18:00, Tue/Thu/Sat 17:00-19:30)
r, tg, notes, st = mode_setup(SCHED, at(2, 12, 0))
check(r.effective().kind == "work", "Monday 12:00: you are free")
clock[0] = at(2, 16, 30)
mm = r.effective()
check(mm.kind == "busy" and mm.reason == "hours" and mm.until == at(2, 18, 0), "Monday 16:30: busy by the schedule, until 18:00")
seen.clear()
run(r.on_message(5, tg.add("salom, bir savol bor edi"), bro))
check(len(tg.sent) == 1 and tg.sent[0].startswith("Assalomu alaykum! Zufarbek hozir band. Soat 18:00 dan keyin o'zi javob beradi.") and not seen,
      "busy hours: answered at once (no 15-minute wait, no AI): 'Zufarbek is busy, answers after 18:00'")
run(r.on_message(5, tg.add("hoy"), bro))
check(len(tg.sent) == 1, "busy hours: the same person is told only once")
run(r.on_message(6, tg.add("hello, are you there?"), Sender(name="Random Person", id=61, contact=False)))
check("busy right now" in tg.sent[-1] and "after 18:00" in tg.sent[-1], "busy hours: a stranger is told in English")
run(r.on_message(7, tg.add("", kind="voice"), Sender(name="Otabek Akam", id=62)))
check("hozir band" in tg.sent[-1] and not r.silent_notes, "busy hours: a voice message gets the same sentence, your notes are NOT silent")
run(r.on_message(8, tg.add("o'g'lim?"), dad))
check(len(tg.sent) == 3 and any("Dadajonim" in x and "yozdi" in x for x in notes), "busy hours: Dad still gets nothing from Jarvis, you are told")
clock[0] = at(2, 17, 0)
notes.clear()
run(r.tick())
check(r.effective().kind == "busy", "tick inside the busy hours changes nothing")
clock[0] = at(2, 18, 1)
notes.clear()
run(r.tick())
check(r.effective().kind == "work" and any("Band vaqt tugadi" in x and "Brother" in x and "Otabek Akam" in x for x in notes), "busy hours end by themselves -> back to normal + summary of who wrote")
r, tg, notes, st = mode_setup(SCHED, at(2, 15, 59))
run(r.tick())
clock[0] = at(2, 16, 0)
notes.clear()
run(r.tick())
check(r.effective().kind == "busy" and any("Band vaqt boshlandi" in x and "18:00" in x for x in notes), "busy hours start by themselves -> you are told")
clock[0] = at(8, 17, 0)
check(r.effective().kind == "work", "Sunday: never busy by the schedule")
clock[0] = at(3, 17, 0)
check(r.effective().kind == "busy" and r.effective().until == at(3, 19, 30), "Tuesday 17:00-19:30 is busy")

# «ish vaqtim boshlandi» (= I am free) during busy hours; «uxladim» lasts until you say you are up
r, tg, notes, st = mode_setup(SCHED, at(2, 16, 30))
run(r.apply_mode("work"))
check(r.effective().kind == "work", "'I am free' during busy hours -> available until the busy hours end")
clock[0] = at(2, 18, 30)
check(r.effective().kind == "work", "...and after them you are free anyway")
clock[0] = at(3, 17, 30)
check(r.effective().kind == "busy", "...the next busy window starts by itself")
r, tg, notes, st = mode_setup(SCHED, at(2, 22, 0))
run(r.apply_mode("night"))
clock[0] = at(3, 12, 0)
check(r.effective().kind == "night" and r.effective().reason == "manual", "'uxladim' lasts until you say you are up (not cut off by the schedule)")
clock[0] = at(3, 17, 30)
check(r.effective().kind == "night", "...even inside the next busy window")
run(r.apply_mode("work"))
check(r.effective().kind == "work" or r.effective().kind == "busy", "'ish vaqtim boshlandi' ends the night")

# --- 7) reminders pause at night and restart in the morning
r, tg, notes, st = mode_setup()
run(r.attention(5, "Brother", "xabar", "🙋 Brother kutyapti"))
run(r.apply_mode("night"))
clock[0] += 90 * 60
notes.clear()
run(r.check_reminders())
check(not notes, "night: no reminders")
run(r.apply_mode("work"))
clock[0] += 61
notes.clear()
run(r.check_reminders())
check(any("Javob berasizmi" in x for x in notes), "work again: the reminder about the unanswered person comes within a minute")

# --- 8) the mode survives a restart (kept in Saved Messages)
saved = []


async def save_state(text):
    saved.append(text)


r, tg, notes, st = mode_setup()
tg.save_state = save_state
run(r.apply_mode("night"))
r2, tg2, n2, st2 = mode_setup()
r2.restore(saved[-1])
check(saved and r2.effective().kind == "night", "night mode is restored after a restart")
r2.restore("not json")
check(r2.effective().kind == "night", "damaged saved state is ignored")

# --- 9) Claude understands free wording for modes
r, tg, notes, st, prompts = owner_setup({"action": "set_mode", "mode": "busy", "minutes": 120, "note": "dars", "reply": ""})
run(r.on_owner_message("darsdaman 2 soat"))
check(r.effective().kind == "busy" and "Current local time" in prompts[0][0] and not tg.sent, "'darsdaman 2 soat' (via Claude) -> busy mode")
r, tg, notes, st, prompts = owner_setup({"action": "set_mode", "mode": "teleport"})
run(r.on_owner_message("nimadir"))
check(r.effective().kind == "work", "an unknown mode from Claude is ignored")
check(lite.MODE_NIGHT.match(lite.norm("Uxladim")) and lite.MODE_NIGHT.match(lite.norm("good night")) and lite.MODE_WORK.match(lite.norm("Ish vaqtim boshlandi"))
      and lite.MODE_WORK.match(lite.norm("uyg'ondim")) and not lite.MODE_NIGHT.match(lite.norm("uxlab qoldi")), "quick command words")
check(Settings.from_env({}).busy_hours == modes.DEFAULT_BUSY_HOURS and Settings.from_env({"BUSY_HOURS": "off"}).busy_hours == "off" and Settings.from_env({"TZ_OFFSET": "3"}).tz_hours == 3, "BUSY_HOURS / TZ_OFFSET settings")
check(Settings.from_env({"WORK_HOURS": "mon 10:00-11:00"}).busy_hours == modes.DEFAULT_BUSY_HOURS, "the old WORK_HOURS name is ignored (it meant the opposite)")

# ================= database (SQLite + Turso over HTTP) and scheduled messages =================
import http.server  # noqa: E402
import sqlite3 as _sq  # noqa: E402
import threading as _thr  # noqa: E402
import store  # noqa: E402

db0 = store.SqliteDb(":memory:")
run(db0.init())
run(db0.kv_set("a", "1"))
run(db0.kv_set("a", "2"))
check(run(db0.kv_get("a")) == "2" and run(db0.kv_get("nope")) is None, "SQLite: kv_set overwrites, missing key is None")
check(run(db0.query("INSERT INTO scheduled (chat, name, text, send_at, created_at) VALUES (?,?,?,?,?) RETURNING id", [5, "X", "t", 1, 1]))[0]["id"] == 1, "INSERT ... RETURNING id works")


class FakeTurso(http.server.BaseHTTPRequestHandler):
    """A tiny stand-in for Turso's /v2/pipeline endpoint (backed by sqlite) — checks my client speaks the protocol."""
    conn = _sq.connect(":memory:", check_same_thread=False)
    seen_auth = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = _json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeTurso.seen_auth.append(self.headers.get("Authorization"))
        if self.path != "/v2/pipeline" or self.headers.get("Authorization") != "Bearer SECRET":
            self.send_response(401)
            self.end_headers()
            return
        results = []
        for rq in body["requests"]:
            if rq["type"] != "execute":
                results.append({"type": "ok", "response": {"type": "close"}})
                continue
            args = []
            for a in rq["stmt"].get("args", []):
                args.append(None if a["type"] == "null" else int(a["value"]) if a["type"] == "integer" else a["value"])
            try:
                cur = FakeTurso.conn.execute(rq["stmt"]["sql"], args)
            except Exception as e:
                results.append({"type": "error", "error": {"message": str(e)}})
                continue
            cols = [{"name": d[0]} for d in (cur.description or [])]
            rows = [[({"type": "null"} if v is None else {"type": "integer", "value": str(v)} if isinstance(v, int) else {"type": "text", "value": v}) for v in row]
                    for row in cur.fetchall()]
            FakeTurso.conn.commit()
            results.append({"type": "ok", "response": {"type": "execute", "result": {"cols": cols, "rows": rows, "affected_row_count": max(cur.rowcount, 0)}}})
        out = _json.dumps({"results": results}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


srv = http.server.HTTPServer(("127.0.0.1", 0), FakeTurso)
_thr.Thread(target=srv.serve_forever, daemon=True).start()
turso = store.TursoDb(f"http://127.0.0.1:{srv.server_address[1]}", "SECRET")
run(turso.init())
run(turso.kv_set("k", "väl"))
check(run(turso.kv_get("k")) == "väl" and FakeTurso.seen_auth[0] == "Bearer SECRET", "Turso HTTP client: sends the Bearer token, writes and reads back (also non-ASCII)")
check(run(turso.query("INSERT INTO scheduled (chat, name, text, send_at, created_at) VALUES (?,?,?,?,?) RETURNING id", [6046141246, "Muhammad Akam", "salom", 99, 1]))[0]["id"] == 1
      and run(turso.query("SELECT chat, name FROM scheduled"))[0] == {"chat": 6046141246, "name": "Muhammad Akam"}, "Turso: big integers and rows come back right")
check(run(turso.execute("UPDATE scheduled SET status='x' WHERE id=1")) == 1 and run(turso.execute("UPDATE scheduled SET status='y' WHERE id=99")) == 0, "Turso: affected row count")
try:
    run(store.TursoDb(f"http://127.0.0.1:{srv.server_address[1]}", "WRONG").kv_get("k"))
    check(False, "a wrong token must be an error")
except store.DbError as e:
    check("401" in str(e) and "WRONG" not in str(e), "Turso: wrong token -> clear error that never prints the token")
try:
    run(turso.query("SELECT * FROM no_such_table"))
    check(False, "an SQL error must be an error")
except store.DbError as e:
    check("no such table" in str(e), "Turso: SQL errors come through")
check(store.TursoDb("libsql://my-db-me.turso.io", "t").endpoint == "https://my-db-me.turso.io/v2/pipeline", "libsql:// URL -> https:// endpoint")
check(isinstance(store.make_db({"TURSO_DATABASE_URL": "libsql://x.turso.io", "TURSO_AUTH_TOKEN": "t"}), store.TursoDb)
      and isinstance(store.make_db({}, tempfile.mkdtemp()), store.SqliteDb), "make_db: Turso when configured, else a local file")


def db_setup(**kw):
    r, tg, notes, st = mode_setup(**kw)
    r.db = store.SqliteDb(":memory:")
    run(r.db.init())
    return r, tg, notes, st


# --- time zone: Uzbekistan (UTC+5)
r, tg, notes, st = db_setup(t0=at(3, 14, 20))
check(Settings().tz_hours == 5 and Settings.from_env({}).tz_hours == 5 and r.utc_label() == "UTC+5", "time zone defaults to Uzbekistan, UTC+5")
run(r.say_time())
check("03.11.2026 14:20" in notes[-1] and "UTC+5" in notes[-1], "«/vaqt» tells the bot's time in Tashkent time")
check(lite.TIME_CMD.fullmatch(lite.norm("/vaqt")) and lite.TIME_CMD.fullmatch(lite.norm("Soat")), "«/vaqt» command words")

# --- scheduled messages: /yoz ...
r, tg, notes, st = db_setup(t0=at(3, 14, 20))
r.tg = MultiTG()
run(r.schedule_from_command("/yoz Muhammad Akam | ertaga 10:00 | Assalomu alaykum, aka!\nServer to'lovi haqida eslatma."))
rows = run(r.db.query("SELECT * FROM scheduled"))
check(len(rows) == 1 and rows[0]["chat"] == 6046141246 and rows[0]["send_at"] == at(4, 10, 0) and rows[0]["text"] == "Assalomu alaykum, aka!\nServer to'lovi haqida eslatma.",
      "/yoz: resolved person, 10:00 Tashkent time tomorrow (= 05:00 UTC), text kept exactly (line breaks too)")
check(rows[0]["send_at"] == int(_dt.datetime(2026, 11, 4, 5, 0, tzinfo=_dt.timezone.utc).timestamp()), "10:00 UTC+5 is stored as 05:00 UTC")
check("#1 rejalashtirildi" in notes[-1] and "04.11.2026 10:00" in notes[-1] and "/bekor 1" in notes[-1], "confirmation shows id, person, time and how to cancel")
run(r.run_scheduled())
check(not [m for m in r.tg.chats[6046141246] if m.out], "nothing is sent before its time")
clock[0] = at(4, 10, 0) + 5
notes.clear()
run(r.run_scheduled())
sent = [m for m in r.tg.chats[6046141246] if m.out]
check(len(sent) == 1 and sent[0].text == rows[0]["text"] and "🤖" not in sent[0].text and sent[0].id not in r.our_ids, "at its time: sent as YOUR message, exactly as written, no signature")
check(run(r.db.query("SELECT status FROM scheduled"))[0]["status"] == "sent" and any("#1 yuborildi" in x for x in notes), "marked sent, you are told")
run(r.run_scheduled())
check(len([m for m in r.tg.chats[6046141246] if m.out]) == 1, "never sent twice")

# --- overdue (server was down) / failure / cancel / list
r, tg, notes, st = db_setup(t0=at(3, 14, 20))
r.tg = MultiTG()
run(r.schedule_from_command("/yoz Brother | 15:00 | salom"))
clock[0] = at(3, 15, 0) + 7 * 3600
notes.clear()
run(r.run_scheduled())
check(not [m for m in r.tg.chats[5] if m.out] and any("vaqtida yuborilmadi" in x for x in notes) and run(r.db.query("SELECT status FROM scheduled"))[0]["status"] == "missed",
      "more than 6 hours late -> NOT sent, you are told")
r, tg, notes, st = db_setup(t0=at(3, 14, 20))
r.tg = MultiTG()


async def boom(chat, text):
    raise OSError("network")


run(r.schedule_from_command("/yoz Brother | 15:00 | salom"))
r.tg.send = boom
clock[0] = at(3, 15, 1)
notes.clear()
run(r.run_scheduled())
check(run(r.db.query("SELECT status, note FROM scheduled"))[0] == {"status": "failed", "note": "OSError"} and any("yuborilmadi" in x for x in notes), "send fails -> marked failed, you are told")
r, tg, notes, st = db_setup(t0=at(3, 14, 20))
r.tg = MultiTG()
run(r.schedule_from_command("/yoz Brother | ertaga 09:00 | bir"))
run(r.schedule_from_command("/yoz Muhammad Akam | 2 soatdan keyin | ikki"))
notes.clear()
run(r.list_scheduled())
check("#1" in notes[-1] and "#2" in notes[-1] and "Brother" in notes[-1] and "Muhammad Akam" in notes[-1], "list shows what is waiting")
run(r.cancel_scheduled(1))
clock[0] = at(4, 9, 1)
run(r.run_scheduled())
check(not [m for m in r.tg.chats[5] if m.out] and run(r.db.query("SELECT status FROM scheduled WHERE id=1"))[0]["status"] == "cancelled", "cancelled messages are never sent")
notes.clear()
run(r.cancel_scheduled(77))
check("topilmadi" in notes[-1], "cancel of an unknown / already sent id says so")

# --- mistakes are caught
for bad, why in (("/yoz Brother | ertaga 10:00", "missing text"), ("/yoz Brother | vaqt emas | salom", "bad time"), ("/yoz Brother | bugun 14:00 | salom", "time in the past"),
                 ("/yoz Nonexistent | ertaga 10:00 | salom", "unknown person"), ("/yoz Akam | ertaga 10:00 | salom", "ambiguous person")):
    r, tg, notes, st = db_setup(t0=at(3, 14, 20))
    r.tg = MultiTG()
    run(r.schedule_from_command(bad))
    check(not run(r.db.query("SELECT * FROM scheduled")) and notes, f"/yoz with {why} -> nothing scheduled, you are told")

# --- natural words through Claude: the text must be exactly yours
r, tg, notes, st, prompts = owner_setup({"action": "schedule", "target": "Muhammad Akam", "message": "Aka, ertaga serverga to'lov qilib qo'ying.", "at": "2026-11-04 10:00"})
r.db = store.SqliteDb(":memory:")
run(r.db.init())
r.tg = MultiTG()
clock[0] = at(3, 14, 20)
run(r.on_owner_message("Muhammad Akamga ertaga soat 10 da yoz: Aka, ertaga serverga to'lov qilib qo'ying."))
rows = run(r.db.query("SELECT * FROM scheduled"))
check(len(rows) == 1 and rows[0]["chat"] == 6046141246 and rows[0]["send_at"] == at(4, 10, 0) and "EXACTLY the text" in prompts[0][0] and "2026-11-03" in prompts[0][0],
      "plain words -> Claude fills person/text/time (it is given today's date), exact text scheduled")
r, tg, notes, st, prompts = owner_setup({"action": "schedule", "target": "Brother", "message": "salom", "minutes": 90})
r.db = store.SqliteDb(":memory:")
run(r.db.init())
r.tg = MultiTG()
clock[0] = at(3, 14, 20)
run(r.on_owner_message("brotherga 1.5 soatdan keyin salom de"))
check(run(r.db.query("SELECT send_at FROM scheduled"))[0]["send_at"] == at(3, 15, 50), "'in 90 minutes' via Claude")
r, tg, notes, st, prompts = owner_setup({"action": "schedule", "target": "Brother", "message": "", "at": "2026-11-04 10:00"})
run(r.on_owner_message("brotherga yoz"))
check(not tg.sent, "a schedule plan without text is not accepted")
r, tg, notes, st, prompts = owner_setup({"action": "cancel_scheduled", "id": 5})
r.db = store.SqliteDb(":memory:")
run(r.db.init())
run(r.on_owner_message("5 ni bekor qil"))
check(any("#5" in x for x in notes), "cancel by id through Claude")
check(lite.SCHED_CMD.match("/yoz a | b | c") and lite.LIST_SCHED.fullmatch(lite.norm("/rejalar")) and lite.CANCEL_SCHED.fullmatch(lite.norm("/bekor 12")).group(1) == "12"
      and not lite.CANCEL_SCHED.fullmatch(lite.norm("bekor")), "command words (/yoz, /rejalar, /bekor N)")

# --- everything important survives a restart (kept in the database)
r, tg, notes, st = db_setup(t0=at(3, 20, 0))
run(r.apply_mode("night"))
run(r.attention(5, "Brother", "xabar", "🙋 Brother kutyapti"))
run(r.on_message(6, tg.add("salom"), Sender(name="Otabek Akam", id=62)))
run(r.save())
r2, tg2, n2, st2 = mode_setup(t0=at(3, 20, 5))
r2.db = r.db
run(r2.load())
check(r2.effective().kind == "night" and 5 in r2.pending and r2.pending[5]["text"] == "xabar" and 6 in r2.night_log and r2.names.get(5) == "Brother" and r2.last_chat == 5,
      "mode, who is waiting for your answer, the night list and names are restored after a restart")
check(r2.last_kind == "night", "...and a restart does not trigger a fake 'work started' summary")
n_before = run(r2.db.query("SELECT v FROM kv WHERE k='state'"))
run(r2.save())
check(run(r2.db.query("SELECT v FROM kv WHERE k='state'")) == n_before, "unchanged state is not rewritten")
r3, tg3, n3, st3 = mode_setup()
r3.db = store.SqliteDb(":memory:")
run(r3.db.init())
run(r3.db.kv_set("state", "{broken"))
run(r3.load())
check(r3.effective().kind == "work", "damaged saved state is ignored")


class DownDb(store.Db):
    async def query(self, *a):
        raise store.DbError("Turso unreachable")

    async def execute(self, *a):
        raise store.DbError("Turso unreachable")


r4, tg4, n4, st4 = mode_setup()
r4.db = DownDb()
try:
    run(r4.tick())
    crashed = False
except Exception:
    crashed = True
check(not crashed, "a database outage never crashes the minute loop")
run(r4.attention(5, "Brother", "x", "🙋"))
check(len(r4.pending) == 1 and r4.effective().kind == "work", "...and the bot keeps working in memory while the database is down")

# ================= a greeting only OPENS a conversation =================
g = lite.strip_greeting
check(g("Assalomu alaykum! Zufarbek hozir band.") == "Zufarbek hozir band." and g("Hi! I'm Zufarbek's AI assistant.") == "I'm Zufarbek's AI assistant."
      and g("Здравствуйте! Он занят.") == "Он занят." and g("Assalomu alaykum, dadajon! Zufarbek uxlayapti.") == "Dadajon! Zufarbek uxlayapti."
      and g("Salom, qalaysan?") == "Qalaysan?", "strip_greeting removes the opening greeting and capitalises the rest")
check(g("Zufarbek hozir band.") == "Zufarbek hozir band." and g("Salom!") == "Salom!" and g("") == "" and g("History of hi") == "History of hi", "...and leaves everything else alone")
check(Settings().convo_gap == 4 * 3600 and Settings.from_env({"CONVO_GAP_HOURS": "2"}).convo_gap == 7200, "CONVO_GAP_HOURS setting (default 4)")

r, tg, notes, st = mode_setup(None, at(3, 14, 0))
M = lambda i, out, ts: Msg(i, out, "x", "text", ts)  # noqa: E731
newm = [M(10, False, at(3, 14, 0))]
check(r.is_ongoing([M(9, True, at(3, 13, 30))] + newm, newm), "last message 30 minutes ago -> ongoing")
check(not r.is_ongoing([M(9, True, at(3, 9, 0))] + newm, newm), "last message 5 hours ago -> a new conversation")
check(not r.is_ongoing(newm, newm) and not r.is_ongoing([M(9, False, 0)] + newm, newm), "no earlier message (or unknown time) -> a new conversation")
check(r.is_ongoing([M(8, False, at(3, 11, 0)), M(9, True, at(3, 13, 59))] + newm, newm), "the most recent earlier message counts (either side)")

# AI answers: the prompt says whether to greet
seen.clear()
r, tg, notes, st = mode_setup(None, at(3, 14, 0))
st.grace = 900
tg.add("kecha gaplashgandik", out=True, ts=at(3, 13, 40))
run(r.on_message(5, tg.add("dars soat nechada?", ts=at(3, 14, 0)), bro))
check("CONTINUING conversation" in seen[0][0] and "do NOT start with a greeting" in seen[0][0] and "START of a conversation" not in seen[0][0],
      "ongoing chat: Claude is told NOT to greet and not to repeat that he is busy")
seen.clear()
r, tg, notes, st = mode_setup(None, at(3, 14, 0))
run(r.on_message(5, tg.add("dars soat nechada?", ts=at(3, 14, 0)), bro))
check("START of a conversation" in seen[0][0] and "ONE short, friendly greeting" in seen[0][0] and "CONTINUING" not in seen[0][0], "first message: Claude is told to greet once")
seen.clear()
r, tg, notes, st = mode_setup(None, at(3, 14, 0))
tg.add("ertaga gaplashamiz", out=True, ts=at(3, 8, 0))                                  # 6 hours ago: an old conversation
run(r.on_message(5, tg.add("dars soat nechada?", ts=at(3, 14, 0)), bro))
check("START of a conversation" in seen[0][0], "the last message was 6 hours ago -> greeting is fine again")

# fixed sentences: greeting only when the chat is new
r, tg, notes, st = mode_setup(SCHED, at(2, 16, 30))
tg.add("savol bor edi", ts=at(2, 16, 10))
run(r.on_message(5, tg.add("yana bir narsa so'ramoqchi edim", ts=at(2, 16, 30)), bro))
check(tg.sent[0].startswith("Zufarbek hozir band. Soat 18:00 dan keyin o'zi javob beradi.") and "Assalomu" not in tg.sent[0], "busy hours, ongoing chat: no «Assalomu alaykum», straight to the point")
r, tg, notes, st = mode_setup(SCHED, at(2, 16, 30))
run(r.on_message(5, tg.add("salom, bir savol bor edi", ts=at(2, 16, 30)), bro))
check(tg.sent[0].startswith("Assalomu alaykum! Zufarbek hozir band."), "busy hours, new chat: greeted")
r, tg, notes, st = mode_setup()
run(r.apply_mode("night"))
tg.add("men yozgandim", out=True, ts=clock[0] - 600)
run(r.on_message(5, tg.add("ha, javob berasizmi?", ts=clock[0]), bro))
check(tg.sent[0].startswith("Zufarbek bugungi ish vaqti tugagani uchun") and "Assalomu" not in tg.sent[0], "night, ongoing chat: no greeting")
r, tg, notes, st = mode_setup()
tg.add("o'g'lim, qalaysan", ts=clock[0] - 300)
run(r.apply_mode("night"))
run(r.on_message(5, tg.add("uxladingmi?", ts=clock[0]), dad))
check(tg.sent[0].startswith("Dadajon! Zufarbek hozir uxlayapti."), "night, Dad in an ongoing chat: no «Assalomu alaykum», still respectful")
r, tg, notes, st = mode_setup()
tg.add("hello", ts=clock[0] - 120)
run(r.on_message(5, tg.add("", kind="voice", ts=clock[0]), bro))
check(tg.sent[0].startswith("Zufarbek Jumayev hozir band, ovozli xabarni eshita olmayman.") and "Assalomu" not in tg.sent[0], "voice message in an ongoing chat: no greeting")
r, tg, notes, st = pay_setup()
r.now = lambda: clock[0]
tg.add("salom aka", ts=clock[0] - 200)
run(r.on_message(5, tg.add("karta raqamingiz?", ts=clock[0]), muh))
check("Assalomu" not in tg.sent[0] and CARD in tg.sent[0] and tg.sent[0].startswith("Cefr tys boti serveri uchun to'lov: 13$."), "card number in an ongoing chat: no greeting, still correct")
r, tg, notes, st = make(broken)
r.now = lambda: clock[0]
tg.add("salom", ts=clock[0] - 100)
run(r.on_message(5, tg.add("hello bro how are you", ts=clock[0]), bro))
check(not tg.sent[0].lower().startswith(("hi", "hello")), "AI unavailable + ongoing chat: the fixed sentence is also without a greeting")
r, tg, notes, st = make(fake_claude)
run(r.on_message(5, tg.add("salom, qalaysan", ts=0), Sender(name="Random Person", id=71, contact=False)))
check(tg.sent[0].startswith("Salom! Men Zufarbekning"), "a stranger's first message is greeted")
r, tg, notes, st = make(fake_claude)
r.now = lambda: clock[0]
tg.add("hi", ts=clock[0] - 100)
run(r.on_message(5, tg.add("are you there? hello", ts=clock[0]), Sender(name="Random Person", id=72, contact=False)))
check(not tg.sent[0].startswith(("Hi", "Hello", "Salom")), "a stranger writing again in an ongoing chat gets no new greeting")

# messages you ask Claude to write: told when to greet
r, tg, notes, st, prompts = owner_setup({"action": "send", "target": "Muhammad Akam", "message": "Server to'lovi haqida eslatma.", "reply": ""})
r.tg = MultiTG()
r.now = lambda: clock[0]
clock[0] = at(3, 14, 0)
r.tg.add(6046141246, "salom aka", out=True, ts=at(3, 13, 30))
r.tg.add(6046141246, "ha", ts=at(3, 13, 40))
run(r.attention(6046141246, "Muhammad Akam", "savol", "🙋"))
run(r.on_owner_message("serverga to'lov haqida ayt"))
check("(30 daq. oldin)" in prompts[0][1] and "(20 daq. oldin)" in prompts[0][1] and "ONLY if the recent chat shows no message within the last 4 hours" in prompts[0][0],
      "when you ask for a message, Claude sees how old the last messages are and is told to greet only after a long silence")

print("\nFAILED:", fails) if fails else print("\nALL PASSED")
sys.exit(1 if fails else 0)
