#!/bin/bash
# REAL measurement of what Jarvis costs your battery.
#   1. Unplug the charger.  2. Close other apps, leave the Mac alone (screen on, don't type) for ~3 minutes.
#   3. bash ~/jarvis/battery_report.sh            (optional: PHASE=90 bash ... for a longer, more exact test)
# It measures the Mac's power draw (watts) with Jarvis running, then with Jarvis paused, then running again,
# and prints Jarvis's share, your battery's real capacity/health, and what that means per hour.
PY="$HOME/jarvis/venv/bin/python"; [ -x "$PY" ] || PY=python3
exec "$PY" - "$@" <<'PYEOF'
import os, re, signal, statistics, subprocess, sys, time

PHASE = int(os.environ.get("PHASE", "60"))
STEP = 3


def sh(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return ""


def field(txt, key):
    m = re.search(r'"%s" = (-?\d+|Yes|No)' % key, txt)
    return m.group(1) if m else None


def signed(v):
    v = int(v)
    return v - (1 << 64) if v >= (1 << 63) else v


def battery():
    t = sh("ioreg", "-rn", "AppleSmartBattery")
    need = {k: field(t, k) for k in ("Amperage", "Voltage", "ExternalConnected", "AppleRawMaxCapacity",
                                     "DesignCapacity", "CycleCount", "AppleRawCurrentCapacity")}
    if None in (need["Amperage"], need["Voltage"]):
        return None
    return {"amp": signed(need["Amperage"]), "volt": int(need["Voltage"]), "ext": need["ExternalConnected"] == "Yes",
            "max": int(need["AppleRawMaxCapacity"] or 0), "design": int(need["DesignCapacity"] or 0),
            "cycles": int(need["CycleCount"] or 0), "cur": int(need["AppleRawCurrentCapacity"] or 0)}


def jarvis_pids():
    out = sh("launchctl", "print", "gui/%d/com.jarvis.assistant" % os.getuid())
    m = re.search(r"\bpid = (\d+)", out)
    cands = [int(m.group(1))] if m else []
    if not cands:
        for pid in sh("pgrep", "-f", "main.py").split():
            cwd = sh("lsof", "-a", "-p", pid, "-d", "cwd", "-Fn")
            if "/jarvis" in cwd:
                cands.append(int(pid))
    pids = list(cands)
    for p in cands:
        pids += [int(x) for x in sh("pgrep", "-P", str(p)).split()]      # the HUD etc.
    return pids


def cpu(pids):
    tot = 0.0
    for p in pids:
        try:
            tot += float(sh("ps", "-o", "%cpu=", "-p", str(p)).strip() or 0)
        except ValueError:
            pass
    return tot


def phase(label, pids):
    watts, cpus = [], []
    end = time.time() + PHASE
    while time.time() < end:
        b = battery()
        if b and b["amp"] < 0:
            watts.append(-b["amp"] * b["volt"] / 1e6)
        cpus.append(cpu(pids) if label != "paused" else 0.0)
        time.sleep(STEP)
    w = statistics.median(watts) if watts else float("nan")
    print(f"   {label:<9} {w:5.2f} W   (Jarvis CPU {statistics.mean(cpus):.1f}%)", flush=True)
    return w, (statistics.mean(cpus) if cpus else 0.0)


b = battery()
if not b:
    sys.exit("Can't read the battery (is this a Mac laptop?).")
if b["ext"]:
    sys.exit("Unplug the charger first — the test measures what the battery gives.")
pids = jarvis_pids()
if not pids:
    sys.exit("Jarvis isn't running. Start it, wait 1 minute, run this again.")

wh_full = b["max"] * b["volt"] / 1e6
health = 100.0 * b["max"] / b["design"] if b["design"] else float("nan")
print(f"Battery: {wh_full:.1f} Wh now holds, health {health:.0f}% of design, {b['cycles']} cycles")
print(f"Jarvis processes: {pids}\nMeasuring 3 x {PHASE}s — don't touch the Mac...\n", flush=True)


def stop(sig):
    for p in pids:
        try:
            os.kill(p, sig)
        except ProcessLookupError:
            pass


signal.signal(signal.SIGINT, lambda *a: (stop(signal.SIGCONT), sys.exit(1)))
try:
    w1, c1 = phase("running", pids)
    stop(signal.SIGSTOP)
    time.sleep(3)
    w0, _ = phase("paused", pids)
finally:
    stop(signal.SIGCONT)                                  # Jarvis always continues
time.sleep(3)
w2, c2 = phase("running", pids)

with_j = (w1 + w2) / 2
j = with_j - w0
print("\n================ REPORT ================")
print(f"Mac with Jarvis:    {with_j:.2f} W   -> battery lasts ~{wh_full / with_j:.1f} h from full")
print(f"Mac without Jarvis: {w0:.2f} W   -> battery lasts ~{wh_full / w0:.1f} h from full")
print(f"Jarvis costs:       {j:.2f} W  = {100 * j / wh_full:.2f}% of the battery per hour"
      f"  = {100 * j * 8 / wh_full:.1f}% over 8 hours")
print("(Accuracy about ±0.3 W. Run twice, at different times, for a trustworthy number. "
      "While Jarvis was idle; talking to him costs more.)")
PYEOF
