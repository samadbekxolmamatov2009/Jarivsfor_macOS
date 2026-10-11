"""Telegram voice call: open the chat, then press the call button for you.
Needs System Settings > Privacy & Security > Accessibility > allow Terminal (or whatever starts Jarvis) — the same
permission "send to this chat" already uses. If the button can't be found, Jarvis tells you to press it."""
import subprocess
import time

# Looks through the Telegram window for a button whose name/description says "call" (Telegram, Telegram Desktop).
FIND_AND_PRESS = r'''
on run
    tell application "System Events"
        if not (exists process "Telegram") then return "no-telegram"
        tell process "Telegram"
            set frontmost to true
            if (count of windows) is 0 then return "no-window"
            try
                set found to (every button of window 1 whose (description contains "call" or title contains "call" or name contains "call") and not (description contains "video") and not (name contains "video"))
            on error
                set found to {}
            end try
            if (count of found) is 0 then
                try
                    set found to (every button of (every group of window 1) whose (description contains "call" or name contains "call") and not (description contains "video") and not (name contains "video"))
                end try
            end if
            if (count of found) is 0 then return "not-found"
            click item 1 of found
            return "pressed"
        end tell
    end tell
end run
'''


def press_call(wait=2.5):
    """-> 'pressed', or the reason it wasn't: 'not-found', 'no-window', 'no-telegram', 'error: ...'"""
    time.sleep(wait)                                  # let the chat open
    try:
        r = subprocess.run(["osascript", "-e", FIND_AND_PRESS], capture_output=True, text=True, timeout=20)
    except Exception as e:
        return f"error: {e}"
    if r.returncode != 0:
        return "error: " + (r.stderr.strip() or "osascript failed")[:200]
    return r.stdout.strip() or "error: empty answer"
