"""Busy hours, night mode and timed 'busy' mode for Jarvis Lite — pure logic, no Telegram here.

BUSY_HOURS (env) = the times you are BUSY and cannot answer, e.g. "mon,wed,fri 16:00-18:00; tue,thu,sat 17:00-19:30"
("off" = no schedule; days not listed = no busy time). Outside these hours you are available (people wait 15 minutes, then
get "busy"). Times are in your time zone (TZ_OFFSET hours from UTC, default 5 = Uzbekistan).
"""
import datetime
import re
from dataclasses import dataclass

DAY_KEYS = {"mon": 0, "du": 0, "dush": 0, "tue": 1, "se": 1, "sesh": 1, "wed": 2, "chor": 2, "thu": 3, "pay": 3, "payshanba": 3,
            "fri": 4, "ju": 4, "juma": 4, "sat": 5, "sha": 5, "shan": 5, "sun": 6, "yak": 6, "yakshanba": 6,
            "dushanba": 0, "seshanba": 1, "chorshanba": 2, "shanba": 5}
DAYS_UZ = ["dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba", "yakshanba"]
DAYS_RU_ON = ["в понедельник", "во вторник", "в среду", "в четверг", "в пятницу", "в субботу", "в воскресенье"]
DAYS_EN_ON = ["on Monday", "on Tuesday", "on Wednesday", "on Thursday", "on Friday", "on Saturday", "on Sunday"]
DEFAULT_BUSY_HOURS = "mon,wed,fri 16:00-18:00; tue,thu,sat 17:00-19:30"


def hhmm(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


class Schedule:
    def __init__(self, windows, tz_hours=5.0):
        self.windows = windows                                   # weekday (0=Mon) -> [(start_min, end_min)]
        self.tz = datetime.timezone(datetime.timedelta(hours=tz_hours))

    def local(self, ts):
        return datetime.datetime.fromtimestamp(ts, self.tz)

    def is_open(self, dt):
        m = dt.hour * 60 + dt.minute
        return any(a <= m < b for a, b in self.windows.get(dt.weekday(), []))

    def _bounds(self, dt, days=8):
        """All window starts/ends from the start of dt's day on (aware datetimes), sorted."""
        base = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        out = []
        for d in range(days):
            day = base + datetime.timedelta(days=d)
            for a, b in self.windows.get(day.weekday(), []):
                out.append((day + datetime.timedelta(minutes=a), "start"))
                out.append((day + datetime.timedelta(minutes=b), "end"))
        return sorted(out)

    def next_change(self, dt):
        """The next moment the schedule switches between open and closed (None if there are no windows at all)."""
        for t, _ in self._bounds(dt):
            if t > dt:
                return t
        return None

    def next_open(self, dt):
        for t, kind in self._bounds(dt):
            if kind == "start" and t > dt:
                return t
        return None

    def describe(self):
        groups = {}
        for wd, wins in sorted(self.windows.items()):
            for a, b in wins:
                groups.setdefault((a, b), []).append(wd)
        return "; ".join("/".join(DAYS_UZ[d] for d in days) + f" {hhmm(a)}–{hhmm(b)}" for (a, b), days in groups.items())


def parse_schedule(spec, tz_hours=5.0):
    """'mon,wed,fri 16:00-18:00; tue 17:00-19:30' -> Schedule, or None for '' / 'off'."""
    if not spec or spec.strip().lower() in ("off", "none", "no", "0"):
        return None
    windows = {}
    for part in spec.split(";"):
        m = re.match(r"\s*([a-zA-Z,\s]+?)\s+(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*$", part)
        if not m:
            continue
        days = [DAY_KEYS.get(x.strip().lower()) for x in m.group(1).split(",") if x.strip()]
        a, b = int(m.group(2)) * 60 + int(m.group(3)), int(m.group(4)) * 60 + int(m.group(5))
        if b <= a:
            continue
        for d in days:
            if d is not None:
                windows.setdefault(d, []).append((a, b))
    return Schedule(windows, tz_hours) if windows else None


@dataclass
class Mode:
    kind: str = "work"        # work (you are available) | night (you said «uxladim») | busy (your busy hours, or you said so)
    reason: str = ""          # "manual" (you said so) | "hours" (the busy schedule)
    note: str = ""            # busy: what you are doing
    until: float = None       # busy: timestamp


# ---------------------------------------------------------------- texts (what other people receive)
NIGHT_MANUAL = {
    "uz": "Assalomu alaykum! {owner} bugungi ish vaqti tugagani uchun hozir javob bera olmaydi. Ertaga o'zi sizga javob beradi.",
    "ru": "Здравствуйте! Рабочее время {owner} на сегодня закончилось, сейчас он не может ответить. Завтра он ответит вам сам.",
    "en": "Hi! {owner}'s working hours are over for today, so he can't reply right now. He will answer you himself tomorrow.",
}
BUSY = {
    "uz": "Assalomu alaykum! {owner} hozir band{note}. {until}",
    "ru": "Здравствуйте! {owner} сейчас занят{note}. {until}",
    "en": "Hi! {owner} is busy right now{note}. {until}",
}
BUSY_UNTIL = {"uz": "Soat {t} dan keyin o'zi javob beradi.", "ru": "После {t} он ответит сам.", "en": "He will answer you himself after {t}."}
BUSY_OPEN = {"uz": "Bo'sh bo'lgach o'zi javob beradi.", "ru": "Освободится и ответит сам.", "en": "He will answer you himself when he is free."}


def mode_reply(mode, lang, owner, now_dt=None):
    lang = lang if lang in ("uz", "ru", "en") else "en"
    if mode.kind == "busy":
        note = f" ({mode.note})" if mode.note else ""
        if mode.until and now_dt is not None:
            until = BUSY_UNTIL[lang].format(t=datetime.datetime.fromtimestamp(mode.until, now_dt.tzinfo).strftime("%H:%M"))
        else:
            until = BUSY_OPEN[lang]
        return BUSY[lang].format(owner=owner, note=note, until=until)
    return NIGHT_MANUAL[lang].format(owner=owner)


def parent_reply(name, owner):
    """For Dad / Mom at night: polite, third person (the message is marked as written by the assistant)."""
    n = (name or "").lower()
    voc = ", dadajon" if "dada" in n else ", ayajon" if "aya" in n else ""
    return f"Assalomu alaykum{voc}! {owner} hozir uxlayapti. Ertalab o'zi sizga yozadi."


# ---------------------------------------------------------------- time words for scheduled messages
MONTHS_UZ = {"yanvar": 1, "fevral": 2, "mart": 3, "aprel": 4, "may": 5, "iyun": 6, "iyul": 7, "avgust": 8,
             "sentabr": 9, "sentyabr": 9, "oktabr": 10, "oktyabr": 10, "noyabr": 11, "dekabr": 12}


def parse_when(text, now_dt):
    """'ertaga 10:00' | 'bugun 18:30' | '18:30' | 'soat 10' | '05.11 10:00' | '5-noyabr 10:00' | '2026-11-05 10:00' |
    '2 soatdan keyin' | '30 daqiqadan keyin'  ->  aware datetime (in now_dt's zone), or None if it can't be understood.
    A time with no day means today, or tomorrow if it has already passed."""
    t = re.sub(r"[’‘ʻʼ`]", "'", (text or "").lower()).strip()
    if not t:
        return None
    tz = now_dt.tzinfo

    def at(day, h, mi):
        if not (0 <= h < 24 and 0 <= mi < 60):
            return None
        return datetime.datetime(day.year, day.month, day.day, h, mi, tzinfo=tz)

    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(daqiqa|minut|min|soat|hour|h)\w*\s*(?:dan\s*)?keyin|in\s+(\d+)\s*(min|hour|h)", t)
    if m:
        n = float((m.group(1) or m.group(3)).replace(",", "."))
        unit = m.group(2) or m.group(4)
        return now_dt + datetime.timedelta(minutes=n * (60 if unit.startswith(("soat", "hour", "h")) else 1))

    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2})[:.](\d{2})", t)
    if m:
        try:
            return at(datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))), int(m.group(4)), int(m.group(5)))
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\s+(?:soat\s*)?(\d{1,2})[:.](\d{2})", t)
    if m:
        year = int(m.group(3)) if m.group(3) else now_dt.year
        year += 2000 if year < 100 else 0
        try:
            return at(datetime.date(year, int(m.group(2)), int(m.group(1))), int(m.group(4)), int(m.group(5)))
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})[- ]?(" + "|".join(MONTHS_UZ) + r")\w*\s+(?:soat\s*)?(\d{1,2})[:.](\d{2})", t)
    if m:
        try:
            return at(datetime.date(now_dt.year, MONTHS_UZ[m.group(2)], int(m.group(1))), int(m.group(3)), int(m.group(4)))
        except ValueError:
            return None

    day = None
    if re.search(r"\b(?:bugun|today)\b", t):
        day = now_dt.date()
    elif re.search(r"\b(?:ertaga|tomorrow)\b", t):
        day = now_dt.date() + datetime.timedelta(days=1)
    elif re.search(r"\bindin\w*|\bday after tomorrow\b", t):
        day = now_dt.date() + datetime.timedelta(days=2)
    m = re.search(r"(?:soat\s*)?(\d{1,2})[:.](\d{2})", t) or re.search(r"soat\s*(\d{1,2})(?![\d:.])", t)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2)) if m.lastindex and m.lastindex >= 2 else 0
    when = at(day or now_dt.date(), h, mi)
    if when and day is None and when <= now_dt:
        when += datetime.timedelta(days=1)                   # "18:30" said at 19:00 means tomorrow
    return when
