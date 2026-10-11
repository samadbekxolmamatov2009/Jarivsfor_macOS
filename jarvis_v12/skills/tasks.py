"""Tasks: a to-do list that Jarvis keeps (tasks.json), reminds you about out loud AND on your phone,
and can also act on: "tomorrow at 9 am tell Aziz the lesson is moved" is sent by Jarvis at that time.

Voice examples (they work from the Telegram bot on your phone too):
    add task call the bank tomorrow at 10 am            important / urgent -> high priority
    add task water the plants every day at 8 pm         daily repeat
    what are my tasks / what is on my list today
    task two is done / done with call the bank
    postpone task two to friday at 5 pm / delete task three / clear finished tasks
    remind me at 6 pm to call mom                       (saved, survives restarts)
    at 9 pm tell Aziz I will be late                    (Jarvis sends it for you)
"""
import datetime
import json
import os
import re
import threading
import uuid

import config
from .lang import detect as detect_lang
from .when import parse_when, say_day, say_time

FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tasks.json")
NAG_EVERY = 30 * 60          # not done after a reminder? repeat it after 30 minutes ...
NAG_TIMES = 2                # ... at most twice
DEFAULT_HOUR = 9             # a task with only a date is due at 9:00

NUMS = {"one": 1, "first": 1, "1st": 1, "two": 2, "second": 2, "2nd": 2, "three": 3, "third": 3, "3rd": 3,
        "four": 4, "fourth": 4, "five": 5, "fifth": 5, "six": 6, "sixth": 6, "seven": 7, "seventh": 7,
        "eight": 8, "eighth": 8, "nine": 9, "ninth": 9, "ten": 10, "tenth": 10, "eleven": 11, "twelve": 12}
STOP = {"the", "a", "an", "my", "to", "and", "of", "for", "on", "in", "at", "task", "one", "that", "about", "i"}
WORD_VAL = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
            "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "forty-five": 45,
            "forty five": 45, "fifty": 50, "sixty": 60}
IN_DURATION = re.compile(r"\b(?:in|after)\s+(\d+(?:\.\d+)?|" + "|".join(sorted(WORD_VAL, key=len, reverse=True)) +
                         r")[ -](seconds?|secs?|minutes?|mins?|hours?|hrs?|days?)\b")
PRIORITY_RE = r"(?:very )?(?:important|urgent|high priority|top priority|asap)"
REPEAT_RE = r"(?:every ?day|daily|each day)"

ADD_RES = [
    re.compile(r"^(?:add|create|new|put)(?: a| an| another| one more)?(?: new)? (?:task|to-?do|todo)s?\b[ :,]*"
               r"(?:to |that |called |named |for )?(?P<x>.*)$"),
    re.compile(r"^add (?P<x>.+?) (?:to|on|in|into) (?:my |the )?(?:tasks?|to-?do|todo)(?: list)?$"),
]
BARE_ADD_RE = re.compile(r"^(?:task|todo|to-do)[ :,]+(?P<x>.+)$")        # "task call mom" (checked last)
LIST_RES = [
    re.compile(r"^(?:what(?:'s| is| are)?|show|read|list|tell|give|check|open)(?: me)?(?: all)?(?: of)?"
               r" (?:my |the |today'?s |tomorrow'?s |our )?(?:pending |open |remaining |current )?"
               r"(?:tasks?|to-?do(?: list)?|todos?)(?: list)?(?: for)?(?: (?:today|tomorrow))?$"),
    re.compile(r"^(?:my )?(?:tasks?|to-?do list|todo list)(?: for)?(?: (?:today|tomorrow))?$"),
    re.compile(r"^what do i (?:still |even )?(?:have|need|got) to do(?: (?:today|tomorrow))?$"),
    re.compile(r"^what(?:'s| is) (?:left|next) (?:on my list|to do)$"),
    re.compile(r"^how many tasks(?: do i have| are (?:left|there))?(?: left)?$"),
]
DONE_RES = [
    re.compile(r"^(?:mark )?task (?P<ref>.+?) (?:is |are |as )?(?:done|complete|completed|finished)$"),
    re.compile(r"^mark (?P<ref>.+?) (?:as )?(?:done|complete|completed|finished)$"),
    re.compile(r"^(?:complete|finish|tick off|check off|cross off)(?: the)?(?: task)? (?P<ref>.+)$"),
    re.compile(r"^(?:done with|i(?:'ve| have)? (?:finished|completed|did)) (?P<ref>.+)$"),
]
DELETE_RE = re.compile(r"^(?:delete|remove|cancel|drop) (?:the )?task (?P<ref>.+)$")
POSTPONE_RE = re.compile(r"^(?:postpone|reschedule|snooze|move|push) (?:the )?task (?P<ref>.+?) "
                         r"(?:to|until|till|for|by) (?P<when>.+)$")
CLEAR_DONE_RE = re.compile(r"^(?:clear|remove|delete) (?:all )?(?:the )?(?:finished|done|completed) tasks?$")
CLEAR_ALL_RE = re.compile(r"^(?:clear|delete|remove) (?:all )?(?:of )?(?:my )?(?:tasks|to-?do list)$")
SCHEDULED_MSG = re.compile(r"^(?P<when>(?:at|in|tomorrow|tonight|on|next|this)\b.+?)\s+(?:please\s+)?"
                           r"(?:tell|text|message|send (?:a )?(?:telegram )?(?:message |text )?to)\s+(?P<rest>.+)$", re.I)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M")


def _dt(s):
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M") if s else None


# ------------------------------------------------------------------ storage
class TaskStore:
    def __init__(self, path=FILE):
        self.path = path
        self.lock = threading.RLock()
        self.poke = threading.Event()          # wakes the reminder thread when something changes
        self.items = self._load()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except FileNotFoundError:
            return []
        except Exception:                      # damaged file: keep it aside, start fresh
            try:
                os.replace(self.path, self.path + ".broken")
            except OSError:
                pass
            return []

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.items, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)
        self.poke.set()

    def add(self, text, due=None, priority="normal", repeat=None, kind="todo", **extra):
        with self.lock:
            t = {"id": uuid.uuid4().hex[:8], "text": text, "created": _iso(datetime.datetime.now()),
                 "due": _iso(due) if due else None, "remind_at": _iso(due) if due else None,
                 "priority": priority, "repeat": repeat, "kind": kind, "done": False, "nags": 0}
            t.update(extra)
            self.items.append(t)
            self._save()
            return t

    def pending(self):
        """Open tasks in the order Jarvis reads them: important first, then by due time."""
        with self.lock:
            open_ = [t for t in self.items if not t["done"]]
        return sorted(open_, key=lambda t: (0 if t.get("priority") == "high" else 1,
                                            0 if t.get("due") else 1, t.get("due") or "", t["created"]))

    def _next_day(self, task):
        due = _dt(task["due"])
        while due <= datetime.datetime.now():
            due += datetime.timedelta(days=1)
        task.update(due=_iso(due), remind_at=_iso(due), nags=0)

    def complete(self, task):
        """-> 'done' or 'again' (a daily task that was moved to its next day)."""
        with self.lock:
            if task.get("repeat") == "daily" and task.get("due"):
                self._next_day(task)
                self._save()
                return "again"
            task["done"] = True
            task["remind_at"] = None
            task["done_at"] = _iso(datetime.datetime.now())
            self._save()
            return "done"

    def delete(self, task):
        with self.lock:
            self.items = [t for t in self.items if t["id"] != task["id"]]
            self._save()

    def clear(self, only_done=False):
        with self.lock:
            n = len(self.items)
            self.items = [t for t in self.items if not t["done"]] if only_done else []
            self._save()
            return n - len(self.items)

    def reschedule(self, task, due):
        with self.lock:
            task.update(due=_iso(due), remind_at=_iso(due), nags=0)
            self._save()

    def due_now(self, now=None):
        now = _iso(now or datetime.datetime.now())
        with self.lock:
            return [t for t in self.items if not t["done"] and t.get("remind_at") and t["remind_at"] <= now]

    def fired(self, task):
        """A reminder was delivered: ask again in 30 minutes (twice at most); then stop,
        or move a daily task on to tomorrow."""
        with self.lock:
            task["nags"] = task.get("nags", 0) + 1
            if task["kind"] != "todo":
                task["done"], task["remind_at"] = True, None            # a scheduled message is sent once
            elif task["nags"] <= NAG_TIMES:
                task["remind_at"] = _iso(datetime.datetime.now() + datetime.timedelta(seconds=NAG_EVERY))
            elif task.get("repeat") == "daily" and task.get("due"):
                self._next_day(task)
            else:
                task["remind_at"] = None
            self._save()

    def next_remind(self):
        with self.lock:
            times = [t["remind_at"] for t in self.items if not t["done"] and t.get("remind_at")]
        return _dt(min(times)) if times else None


# ------------------------------------------------------------------ parsing
def parse_task(x, now=None):
    """'call the bank tomorrow at 10 am, important' -> (text, due|None, priority, repeat)"""
    now = now or datetime.datetime.now()
    t = x.strip()
    priority = "high" if re.search(r"\b" + PRIORITY_RE + r"\b", t) else "normal"
    repeat = "daily" if re.search(r"\b" + REPEAT_RE + r"\b", t) else None
    t = re.sub(r"\b(?:" + PRIORITY_RE + "|" + REPEAT_RE + r")\b", " ", t)
    due = None
    m = IN_DURATION.search(t)
    if m:
        raw = m.group(1)
        n = float(raw) if raw[0].isdigit() else WORD_VAL[raw]
        due = now + datetime.timedelta(seconds=n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)[0]])
        t = t.replace(m.group(0), " ")
    else:
        w = parse_when(t)
        for piece in w.get("spans", []):
            t = t.replace(piece, " ")
        day = w.get("date")
        if w.get("has_time"):
            due = datetime.datetime.combine(day or now.date(), datetime.time(w["hour"], w["minute"]))
            if not day and due <= now:
                due += datetime.timedelta(days=1)
        elif day:
            due = datetime.datetime.combine(day, datetime.time(DEFAULT_HOUR, 0))
            if due <= now:
                due = None                      # "today" but 9:00 has passed: keep it on the list, no reminder
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\b(?:at|on|by|for|due|before|and)\s*$", " ", t).strip(" ,.")
    t = re.sub(r"^(?:to|that|called|named|for)\s+", "", t).strip(" ,.")
    return (t[:1].upper() + t[1:] if t else ""), due, priority, repeat


def when_phrase(due):
    return f"{say_day(due.date())} at {say_time(due.hour, due.minute)}"


def spoken(task, now=None):
    """What follows the task text when it is read out: 'tomorrow at 5 PM', 'overdue ...', 'important'."""
    now = now or datetime.datetime.now()
    bits = []
    if task.get("due"):
        due = _dt(task["due"])
        bits.append(("overdue, it was " if due < now - datetime.timedelta(minutes=1) else "") + when_phrase(due))
    if task.get("repeat") == "daily":
        bits.append("every day")
    if task.get("priority") == "high":
        bits.append("important")
    return ", ".join(bits)


# ------------------------------------------------------------------ voice commands
class TaskCommands:
    """Plugs into Skills: route(t, orig) returns a reply, or None if the sentence is not about tasks."""

    def __init__(self, skills, parse_duration=None, store=None):
        self.s = skills
        self.parse_duration = parse_duration
        self.store = store or TaskStore()

    # ----- finding a task from "two", "the last one", "call the bank" -----
    def resolve(self, ref):
        items = self.store.pending()
        ref = ref.strip(" .").replace("number ", "").replace("task ", "")
        if not items:
            return None
        if ref in ("last", "the last one", "last one"):
            return items[-1]
        m = re.fullmatch(r"(\d+)(?:st|nd|rd|th)?", ref)
        n = int(m.group(1)) if m else NUMS.get(ref)
        if n:
            return items[n - 1] if 1 <= n <= len(items) else None
        words = {w for w in re.findall(r"[a-z']+", ref) if w not in STOP}
        if not words:
            return None
        scored = sorted(((len(words & {w for w in re.findall(r"[a-z']+", t["text"].lower()) if w not in STOP})
                          / len(words), i, t) for i, t in enumerate(items)), key=lambda p: (-p[0], p[1]))
        if scored[0][0] >= 0.5 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
            return scored[0][2]
        return None

    def _missing(self, strict):
        if not strict:
            return None                          # not clearly about a task: let other skills answer
        n = len(self.store.pending())
        if n == 0:
            return "You have no open tasks."
        return f"I couldn't tell which task you mean. Say its number, from one to {n}, or a few words from it."

    # ----- the router -----
    def route(self, t, orig):
        s = self.s
        m = SCHEDULED_MSG.match(orig)            # a timed message that Jarvis sends for you
        if m and s.tg.ready():
            r = self._scheduled_message(m.group("when").lower(), m.group("rest"))
            if r:
                return r

        # reminders with a clock time are saved on disk ("in ten minutes" stays an ordinary timer)
        m = re.match(r"^(?:hey |ok |okay )?(?:jarvis )?(?:please )?remind me (?:to )?(?P<x>.+)$", t)
        if m and not IN_DURATION.search(t) and not (self.parse_duration and self.parse_duration(t)):
            w = parse_when(t)
            if w.get("has_time") or w.get("date"):
                return self._add(m.group("x"))

        for rx in ADD_RES:
            m = rx.match(t)
            if m:
                x = m.group("x").strip()
                return self._add(x) if x else s._ask("What is the task?", lambda ans, t2: self._add(ans))

        if any(rx.match(t) for rx in LIST_RES):
            return self._list(t)
        if CLEAR_DONE_RE.match(t):
            n = self.store.clear(only_done=True)
            return f"Cleared {n} finished task{'s' if n != 1 else ''}." if n else "There are no finished tasks."
        if CLEAR_ALL_RE.match(t):
            if not self.store.items:
                return "Your task list is already empty."
            return s._confirm(f"Delete all {len(self.store.items)} tasks?",
                              lambda: (self.store.clear(), "Your task list is empty now.")[1])

        m = POSTPONE_RE.match(t)
        if m:
            return self._postpone(m.group("ref"), m.group("when"))
        m = DELETE_RE.match(t)
        if m:
            task = self.resolve(m.group("ref"))
            if not task:
                return self._missing(True)
            return s._confirm(f"Delete the task: {task['text']}?", lambda: (self.store.delete(task), "Deleted.")[1])
        for rx in DONE_RES:
            m = rx.match(t)
            if m:
                ref = m.group("ref")
                task = self.resolve(ref)
                if not task:
                    return self._missing("task" in t.split() or bool(re.fullmatch(r"\d+|" + "|".join(NUMS), ref)))
                return self._complete(task)
        m = BARE_ADD_RE.match(t)
        return self._add(m.group("x")) if m else None

    # ----- actions -----
    def _add(self, x):
        text, due, priority, repeat = parse_task(x)
        if not text:
            return self.s._ask("What is the task?", lambda ans, t2: self._add(ans + " " + x))
        self.store.add(text, due, priority, repeat)
        out = f"Added: {text}"
        if due:
            out += f", {when_phrase(due)}"
        if repeat:
            out += ", every day"
        if priority == "high":
            out += ", marked important"
        return out + (". I'll remind you." if due else ".")

    def _list(self, t):
        items = self.store.pending()
        now = datetime.datetime.now()
        if re.search(r"\btoday\b", t):
            items = [x for x in items if x.get("due") and _dt(x["due"]).date() <= now.date()]
            label = " for today"
        elif re.search(r"\btomorrow\b", t):
            tomorrow = (now + datetime.timedelta(days=1)).date()
            items = [x for x in items if x.get("due") and _dt(x["due"]).date() == tomorrow]
            label = " for tomorrow"
        else:
            label = ""
        if not items:
            return f"You have no tasks{label}. Nice and clear." if label else "Your task list is empty."
        count = f"You have {len(items)} task{'s' if len(items) != 1 else ''}{label}."
        if t.startswith("how many"):
            return count
        say = [(count, "en")]
        for n, task in enumerate(items[:6], 1):
            say += [(f"Number {n}:", "en"), (task["text"], detect_lang(task["text"]))]
            tail = spoken(task, now)
            if tail:
                say.append((tail + ".", "en"))
        if len(items) > 6:
            say.append((f"And {len(items) - 6} more.", "en"))
        return {"say": say}

    def _complete(self, task):
        if self.store.complete(task) == "again":
            return f"Done. {task['text']} comes back {when_phrase(_dt(task['due']))}."
        left = len(self.store.pending())
        return f"Done: {task['text']}. " + (f"{left} left." if left else f"That was the last one. Well done, {config.ADDRESS_AS}.")

    def _postpone(self, ref, when):
        task = self.resolve(ref)
        if not task:
            return self._missing(True)
        _, due, _, _ = parse_task("x " + when)
        if not due:
            return "Sorry, I didn't catch when. For example: postpone task two to tomorrow at five pm."
        self.store.reschedule(task, due)
        return f"Moved to {when_phrase(due)}."

    def _scheduled_message(self, when_text, rest):
        s = self.s
        w = parse_when(when_text)
        if w.get("date") and not w.get("has_time") and not IN_DURATION.search(when_text):
            return s._ask("At what time should I send it?",
                          lambda ans, t2: self._scheduled_message(when_text + " at " + ans.lower(), rest))
        _, due, _, _ = parse_task("x " + when_text)
        if not due or due <= datetime.datetime.now():
            return None                           # not a timed message after all
        try:
            d, msg = s.tg.split_name_message(rest.split())
        except Exception as e:
            return f"I couldn't reach Telegram: {e}."
        if not d:
            return f"I couldn't find {rest.split()[0]} in your Telegram chats."
        from .telegram_user import speakable
        who = speakable(d.name)
        if not msg:
            return f"What should I tell {who}? Say it in one go, for example: at nine pm tell {who.split()[0]} I'll be late."
        shown = msg if msg[-1:] in ".!?" else msg + "."
        return s._confirm(f"{when_phrase(due).capitalize()}, I'll send {who}: {shown}",
                          lambda: (self.store.add(f"Message to {who}: {msg}", due, kind="message", who=d.name, msg=msg),
                                   f"Scheduled. I'll send it {when_phrase(due)}.")[1])

    # ----- used by the reminder thread and the briefing -----
    def fire(self, task):
        """Does what a due task asks for; returns the sentence to say and send to your phone."""
        if task["kind"] == "message":
            from .telegram_user import speakable
            try:
                d = self.s.tg.find(task["who"])
                if not d:
                    return f"I couldn't send your scheduled message: {speakable(task['who'])} wasn't found in Telegram."
                self.s.tg.send(d, task["msg"])
                return f"I sent your scheduled message to {speakable(task['who'])}."
            except Exception as e:
                return f"I couldn't send your scheduled message to {speakable(task['who'])}: {e}."
        return f"Task reminder, {config.ADDRESS_AS}: {task['text']}."

    def briefing_line(self):
        items = self.store.pending()
        if not items:
            return ""
        now = datetime.datetime.now()
        late = [x for x in items if x.get("due") and _dt(x["due"]) < now]
        today = [x for x in items if x.get("due") and _dt(x["due"]).date() == now.date() and x not in late]
        out = f"You have {len(items)} open task{'s' if len(items) != 1 else ''}"
        if late:
            out += f", {len(late)} overdue"
        if today:
            out += ". Today: " + ", ".join(x["text"] for x in today[:3])
        return out + "."


class TaskRunner(threading.Thread):
    """Sleeps until the next reminder is due (no ticking every second), then calls deliver(text, task)."""

    def __init__(self, commands, deliver, log=print):
        super().__init__(daemon=True)
        self.c, self.deliver, self.log = commands, deliver, log

    def run(self):
        store = self.c.store
        while True:
            store.poke.clear()                             # (clear first, so a change during the next lines is not lost)
            nxt = store.next_remind()
            wait = 300.0 if not nxt else max(1.0, min(300.0, (nxt - datetime.datetime.now()).total_seconds()))
            if store.poke.wait(wait):
                continue                                   # the list changed: work out the next wake-up again
            for task in store.due_now():
                try:
                    text = self.c.fire(task)
                    self.deliver(text, task)
                except Exception as e:
                    self.log(f"❌ Task reminder failed: {e}")
                finally:
                    store.fired(task)
