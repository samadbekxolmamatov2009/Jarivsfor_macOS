"""Runs anywhere (no Mac needed):  python3 tests/test_v12.py
Modules that only exist on the Mac install (skills.when, telegram_user, config) are replaced by small stand-ins."""
import datetime
import os
import re
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

config = types.ModuleType("config")
config.ADDRESS_AS = "sir"
sys.modules["config"] = config


def parse_when(t):
    """Tiny stand-in for skills/when.py: 'tomorrow', 'friday', 'at 5 pm', '9 pm', '10:30'."""
    out = {"date": None, "has_time": False, "hour": 0, "minute": 0, "minutes": 60, "spans": []}
    today = datetime.date.today()
    if "tomorrow" in t:
        out["date"] = today + datetime.timedelta(days=1)
        out["spans"].append("tomorrow")
    elif "today" in t:
        out["date"] = today
        out["spans"].append("today")
    m = re.search(r"\b(?:at )?(\d{1,2})(?::(\d\d))? ?(am|pm)\b", t)
    if m:
        h = int(m.group(1)) % 12 + (12 if m.group(3) == "pm" else 0)
        out.update(has_time=True, hour=h, minute=int(m.group(2) or 0))
        out["spans"].append(m.group(0))
    return out


when = types.ModuleType("skills.when")
when.parse_when = parse_when
when.say_day = lambda d: "today" if d == datetime.date.today() else "tomorrow" if d == datetime.date.today() + datetime.timedelta(days=1) else d.strftime("on %A")
when.say_time = lambda h, m: f"{h % 12 or 12}:{m:02d} {'PM' if h >= 12 else 'AM'}"
sys.modules["skills.when"] = when
tgu = types.ModuleType("skills.telegram_user")
tgu.speakable = lambda s: s
sys.modules["skills.telegram_user"] = tgu

from skills import tasks, power  # noqa: E402


class Dialog:
    def __init__(self, name):
        self.name = name


class FakeTG:
    sent = []

    def ready(self):
        return True

    def find(self, name):
        return Dialog("Aziz") if "aziz" in name.lower() else None

    def split_name_message(self, words):
        d = self.find(words[0])
        return d, " ".join(words[1:])

    def send(self, d, msg):
        self.sent.append((d.name, msg))


class FakeSkills:
    def __init__(self):
        self.tg = FakeTG()
        self.pending = None
        self.awaiting = None

    def _confirm(self, q, action):
        self.pending = action
        return q + " Say yes to confirm."

    def _ask(self, q, cb):
        self.awaiting = cb
        return q

    def yes(self):
        a, self.pending = self.pending, None
        return a()


def norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[.,!?;]", " ", text.lower())).strip()


tmp = tempfile.mkdtemp()
sk = FakeSkills()
cmds = tasks.TaskCommands(sk, lambda t: None, tasks.TaskStore(os.path.join(tmp, "tasks.json")))


def say(text):
    r = cmds.route(norm(text), text)
    if isinstance(r, dict):
        r = " ".join(t for t, _ in r["say"])
    return r


def check(cond, label):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        check.failed += 1


check.failed = 0

# --- parsing
text, due, prio, rep = tasks.parse_task("call the bank tomorrow at 10 am important")
check(text == "Call the bank" and due.hour == 10 and prio == "high", f"parse due+priority -> {text!r} {due} {prio}")
text, due, prio, rep = tasks.parse_task("water the plants every day at 8 pm")
check(text == "Water the plants" and rep == "daily" and due.hour == 20, f"parse daily -> {text!r} {rep}")
text, due, *_ = tasks.parse_task("stretch in 30 minutes")
check(text == "Stretch" and 29 * 60 < (due - datetime.datetime.now()).total_seconds() < 31 * 60, "parse 'in 30 minutes'")
text, due, *_ = tasks.parse_task("buy milk")
check(text == "Buy milk" and due is None, "parse undated")

# --- voice commands
check(say("add task buy milk").startswith("Added: Buy milk"), "add task")
check("tomorrow at 10:00 AM" in say("add task call the bank tomorrow at 10 am urgent"), "add dated task")
check(say("create a task to study algebra").startswith("Added: Study algebra"), "create a task to ...")
check(say("add eggs to my to-do list").startswith("Added: Eggs"), "add X to my to-do list")
out = say("what are my tasks")
check(out.startswith("You have 4 tasks") and out.index("Call the bank") < out.index("Buy milk"), "list: important first")
check(say("how many tasks do I have").startswith("You have 4 tasks"), "count")
check(say("make 10 problems on fractions") is None, "worksheet requests are NOT tasks")
check(say("what time is it") is None, "unrelated sentence ignored")
check(say("task two is done").startswith("Done:"), "done by number")
check(say("done with study algebra").startswith("Done: Study algebra"), "done by words")
check(say("i finished my homework") is None, "chit-chat 'i finished' ignored")
check("couldn't tell" in say("task nine is done"), "unknown task number")
r = say("delete task one")
check(r.startswith("Delete the task") and sk.yes() == "Deleted.", "delete asks, then deletes")
check(say("postpone task one to tomorrow at 5 pm").startswith("Moved to tomorrow at 5:00 PM"), "postpone")
check(say("clear finished tasks").startswith("Cleared 2"), "clear finished")
check(say("remind me at 6 pm to call mom").startswith("Added: Call mom"), "saved reminder")
check(say("remind me in ten minutes to call mom") is None, "short reminders stay timers")
check(re.match(r"You have \d+ open tasks?\.? ?.*Today: Call mom", cmds.briefing_line()) is not None, "briefing line")

# --- Jarvis sends a message later
r = say("tomorrow at 9 am tell Aziz the lesson is moved")
check("Say yes" in r and "Aziz" in r and "lesson is moved" in r, f"scheduled message asks first -> {r}")
sk.yes()
msg_task = [t for t in cmds.store.pending() if t["kind"] == "message"][0]
check(msg_task["msg"] == "the lesson is moved", "scheduled message stored")
check(cmds.fire(msg_task).startswith("I sent your scheduled message") and sk.tg.sent == [("Aziz", "the lesson is moved")], "message sent at due time")
check(say("tell Aziz the lesson is at 5 pm") is None, "'tell X ... 5 pm' without a leading time is NOT scheduled")

# --- reminders & repeat
t = cmds.store.add("Overdue thing", datetime.datetime.now() - datetime.timedelta(minutes=1))
check(t in cmds.store.due_now(), "due task is found")
cmds.store.fired(t)
check(t["nags"] == 1 and t["remind_at"] > tasks._iso(datetime.datetime.now()), "nag again in 30 minutes")
cmds.store.fired(t); cmds.store.fired(t)
check(t["remind_at"] is None, "stops nagging after 2 repeats")
d = cmds.store.add("Daily", datetime.datetime.now() - datetime.timedelta(minutes=1), repeat="daily")
check(cmds.store.complete(d) == "again" and tasks._dt(d["due"]) > datetime.datetime.now(), "daily task comes back tomorrow")
cmds2 = tasks.TaskStore(cmds.store.path)
check(len(cmds2.items) == len(cmds.store.items), "tasks survive a restart")
open(cmds.store.path, "w").write("{not json")
check(tasks.TaskStore(cmds.store.path).items == [] and os.path.exists(cmds.store.path + ".broken"), "damaged file is set aside")

# --- battery saver
p = power.Power()
p._checked = 1e18                      # don't call pmset here
p.on_battery = False
os.environ.pop("X", None)
power.MODE_FILE = os.path.join(tmp, ".eco_mode")
check(p.mode() == "auto" and not p.eco(), "plugged in -> eco off")
p.on_battery = True
check(p.eco() and abs(p.wake_level(0.025) - 0.0325) < 1e-9, "on battery -> eco, higher sound gate")
p.set_mode("off"); p._checked = 1e18
check(not p.eco() and p.mode() == "off", "manual off")
p.set_mode("on")
check(p.eco() and p.barge_gap(1.0) == 1.6, "manual on")
for _ in range(6):
    p.note_miss()
check(p.noisy() and p.check_gap() > 0.8 and p.wake_level(0.025) > 0.05, "noisy room -> back off")
check(p.screen_off() is False, "no Quartz here -> never pauses")
check(power.set_qos("utility") is False, "QoS call is harmless off-Mac")

print("\nFAILED:", check.failed) if check.failed else print("\nALL PASSED")
sys.exit(1 if check.failed else 0)
