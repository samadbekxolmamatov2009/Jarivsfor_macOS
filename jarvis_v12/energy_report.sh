#!/bin/bash
# Finds out WHAT is eating the battery. Run it for ~20 seconds while Jarvis is idle ("sleeping"):
#   bash ~/jarvis/energy_report.sh
# and send the whole output to your developer.
echo "=== Battery ==="; pmset -g batt | head -2
echo; echo "=== Jarvis-related processes (CPU % averaged over 10 s, memory) ==="
top -l 2 -s 10 -n 40 -stats pid,command,cpu,mem,power 2>/dev/null | awk '/^PID/{n++} n==2' | grep -i -E "PID|python|jarvis|ollama|mlx|hud|whisper|telegram|afplay|say|kokoro" | head -15
echo; echo "=== Top 8 energy users on the whole Mac ==="
top -l 2 -s 5 -o power -n 8 -stats pid,command,cpu,power 2>/dev/null | awk '/^PID/{n++} n==2' | head -10
echo; echo "=== Things that keep the Mac awake ==="
pmset -g assertions | grep -E "PreventUserIdleSystemSleep|PreventSystemSleep|NoDisplaySleep|PreventUserIdleDisplaySleep" | head -6
echo; echo "=== Jarvis settings ==="
grep -E "ECO_MODE|IDLE_PAUSE|QUIET_HOURS|PAUSE_WHEN|WHISPER_MODEL|TTS_ENGINE|BRAIN|MODEL" "$HOME/jarvis/config.py" 2>/dev/null | head -12
ls "$HOME/jarvis/.eco_mode" "$HOME/jarvis/autoreply.json" 2>/dev/null
echo; echo "Ollama models loaded in memory:"; (command -v ollama >/dev/null && ollama ps) || echo "(ollama not found)"
