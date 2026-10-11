#!/bin/bash
# Jarvis v11.3 for Mac (includes v11.1 + v11.2): battery saver, : smooth reading, Uzbek & Russian voices, "continue reading",
# clear messages when a file can't be read, clean audio, Mac's own microphone.
cd "$HOME/jarvis"
echo "📦 Checking libraries..."
venv/bin/python -m pip install -q edge-tts pypdf
echo "⬇️  Small model for hearing "hello" and "stop" (one time, 74 MB)..."
venv/bin/python -c "import mlx_whisper, numpy as np; mlx_whisper.transcribe(np.zeros(16000, dtype=np.float32), path_or_hf_repo='mlx-community/whisper-tiny.en-mlx', language='en'); print('   ✅ ready')"
echo "🔄 Restarting Jarvis..."
if launchctl print "gui/$(id -u)/com.jarvis.assistant" >/dev/null 2>&1; then
  launchctl kickstart -k "gui/$(id -u)/com.jarvis.assistant"
else
  ./jarvis_toggle.sh >/dev/null 2>&1
fi
echo "✅ Jarvis v11.3 is running (battery saver on)."
