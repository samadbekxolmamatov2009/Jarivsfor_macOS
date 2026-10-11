"""Battery saver. Jarvis listens all day, so every wasted wake-up costs charge. What this does:

* runs the idle listening at "utility" priority -> macOS keeps it on the efficiency cores
* pauses the microphone while the screen is locked or the display is asleep (you are not there)
* "eco" mode (automatic on battery / Low Power Mode): fewer and stricter speech checks
* backs off when the room is noisy (TV, people) instead of running Whisper on every sound

Voice: "battery saver on / off / auto / status".  Config (all optional):
    ECO_MODE = "auto"                 # auto | on | off
    PAUSE_WHEN_SCREEN_OFF = True
"""
import ctypes
import os
import re
import subprocess
import time
from collections import deque

import config

MODE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".eco_mode")
QOS = {"interactive": 0x21, "initiated": 0x19, "default": 0x15, "utility": 0x11, "background": 0x09}
_libc = None


def set_qos(level):
    """Sets the priority class of the calling thread (threads it starts afterwards inherit it)."""
    global _libc
    try:
        if _libc is None:
            _libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
        return _libc.pthread_set_qos_class_self_np(QOS[level], 0) == 0
    except Exception:
        return False


def _run(cmd, timeout=4):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


class Power:
    def __init__(self):
        self._checked = 0.0
        self.on_battery, self.percent, self.low_power = False, None, False
        self._screen_checked, self._screen_off = 0.0, False
        self._misses = deque(maxlen=30)          # times of wake checks that were not "hello" (noise)

    # ---- power source ----
    def refresh(self, max_age=30):
        if time.time() - self._checked < max_age:
            return
        self._checked = time.time()
        out = _run(["pmset", "-g", "batt"])
        if out:
            self.on_battery = "Battery Power" in out
            m = re.search(r"(\d+)%", out)
            self.percent = int(m.group(1)) if m else None
        self.low_power = bool(re.search(r"lowpowermode\s+1", _run(["pmset", "-g"])))

    # ---- eco mode ----
    def mode(self):
        try:
            with open(MODE_FILE, encoding="utf-8") as f:
                v = f.read().strip().lower()
            if v in ("on", "off", "auto"):
                return v
        except OSError:
            pass
        v = str(getattr(config, "ECO_MODE", "auto")).lower()
        return v if v in ("on", "off", "auto") else "auto"

    def set_mode(self, v):
        with open(MODE_FILE, "w", encoding="utf-8") as f:
            f.write(v)
        self._checked = 0.0

    def eco(self):
        m = self.mode()
        if m != "auto":
            return m == "on"
        self.refresh()
        return self.on_battery or self.low_power

    def describe(self):
        self.refresh(max_age=0)
        m, pct = self.mode(), f" ({self.percent} percent)" if self.percent is not None else ""
        if m == "on":
            return "Battery saver is on."
        if m == "off":
            return "Battery saver is off."
        if self.eco():
            why = "Low Power Mode is on" if self.low_power and not self.on_battery else "you're on battery power"
            return f"Battery saver is on automatically, because {why}{pct}."
        return f"Battery saver is automatic. It's off now because you're plugged in{pct}."

    # ---- screen ----
    def screen_off(self):
        """True while the screen is locked or the display is asleep (cached for 4 s)."""
        if not getattr(config, "PAUSE_WHEN_SCREEN_OFF", True):
            return False
        if time.time() - self._screen_checked < 4:
            return self._screen_off
        self._screen_checked = time.time()
        try:
            import Quartz
            session = Quartz.CGSessionCopyCurrentDictionary() or {}
            self._screen_off = bool(session.get("CGSSessionScreenIsLocked")) or \
                bool(Quartz.CGDisplayIsAsleep(Quartz.CGMainDisplayID()))
        except Exception:
            self._screen_off = False                  # no Quartz installed -> never pause
        return self._screen_off

    # ---- speech checks ----
    def note_miss(self):
        """A sound was heard that turned out not to be 'hello'."""
        self._misses.append(time.time())

    def noisy(self):
        """Many false alarms in the last minute = TV or people talking nearby."""
        now = time.time()
        return sum(1 for t in self._misses if now - t < 60) >= 6

    def wake_level(self, base):
        """Quietest sound (0..1) that is worth a Whisper check."""
        level = base
        if self.eco():
            level *= 1.3
        if self.noisy():
            level *= 1.6
        return level

    def check_gap(self):
        """Seconds to rest between two speech checks while sleeping."""
        return (0.4 if self.eco() else 0.0) + (0.8 if self.noisy() else 0.0)

    def barge_gap(self, base):
        return base * 1.6 if self.eco() else base
