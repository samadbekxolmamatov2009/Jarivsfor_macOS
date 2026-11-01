#!/bin/bash
# REAL measurement of what Jarvis costs your battery.
#   1. Unplug the charger.  2. Close other apps, leave the Mac alone (screen on, don't type) for ~5 minutes.
#   3. bash ~/jarvis/battery_report.sh            (optional: PHASE=90 bash ... for a longer, more exact test)
# It measures the Mac's power draw (watts) with Jarvis running and paused, 3 times each in a balanced order,
# and prints Jarvis's share, your battery's real capacity/health, and what that means per hour.
PY="$HOME/jarvis/venv/bin/python"; [ -x "$PY" ] || PY=python3
exec "$PY" - "$@" <<'PYEOF'
import os, re, signal, statistics, subprocess, sys, time

PHASE = int(os.environ.get("PHASE", "45"))
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
print(f"Jarvis processes: {pids}\nMeasuring 6 x {PHASE}s — don't touch the Mac...\n", flush=True)


def stop(sig):
    for p in pids:
        try:
            os.kill(p, sig)
        except ProcessLookupError:
            pass


signal.signal(signal.SIGINT, lambda *a: (stop(signal.SIGCONT), sys.exit(1)))
# running/paused alternate in a balanced order (R P | P R | R P) so slow drifts of the Mac's own load cancel out
ORDER = ["running", "paused", "paused", "running", "running", "paused"]
res = []
try:
    for label in ORDER:
        stop(signal.SIGSTOP if label == "paused" else signal.SIGCONT)
        time.sleep(3)
        res.append((label,) + phase(label, pids))
finally:
    stop(signal.SIGCONT)                                  # Jarvis always continues

deltas = []
for k in range(0, 6, 2):
    (l1, w1, _), (l2, w2, _) = res[k][:3], res[k + 1][:3]
    deltas.append((w1 - w2) if l1 == "running" else (w2 - w1))
run_w = [w for l, w, _ in res if l == "running"]
off_w = [w for l, w, _ in res if l == "paused"]
spread = max(w for _, w, _ in res) - min(w for _, w, _ in res)
j = statistics.median(deltas)
cpu_avg = statistics.mean(c for l, _, c in res if l == "running")
print("\n================ REPORT ================")
print(f"Jarvis running:  {statistics.median(run_w):.2f} W     Jarvis paused: {statistics.median(off_w):.2f} W")
print(f"Pair differences (running - paused): " + ", ".join(f"{d:+.2f}" for d in deltas) + " W")
print(f"The Mac's own power moved by {spread:.1f} W during the test; Jarvis CPU averaged {cpu_avg:.1f}%.")
if spread > 1.0 or max(deltas) - min(deltas) > 0.8:
    print("RESULT: NOT TRUSTWORTHY — the Mac's other load changed more than Jarvis can. Close browsers/Spotlight "
          "indexing/updates, keep the screen brightness fixed, and run again.")
elif abs(j) < 0.3:
    print(f"RESULT: Jarvis is below what this test can see (< 0.3 W = < {100 * 0.3 / wh_full:.1f}% battery per hour). "
          "While idle it is not what drains your battery.")
else:
    print(f"RESULT: Jarvis costs about {j:.2f} W = {100 * j / wh_full:.2f}% of the battery per hour "
          f"= {100 * j * 8 / wh_full:.1f}% over 8 hours.")
print(f"(Battery holds {wh_full:.1f} Wh. Idle only — talking to Jarvis or a busy room costs more.)")
PYEOF
