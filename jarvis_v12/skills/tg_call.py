"""Calls for Jarvis on the Mac.

press_call()        Telegram voice call: after the chat is open, finds Telegram's call button (in the window, then in the
                    menu bar) and presses it.
press_call_dialog() After an iPhone call is started (tel: link) macOS asks "Call?" — this presses that button for you.

Both need System Settings > Privacy & Security > Accessibility > allow Terminal (or whatever starts Jarvis).
The first time, macOS also asks "Terminal wants to control System Events / Telegram" — press Allow, then say the
command again. Run `bash ~/jarvis/tg_call_debug.sh` to see what Jarvis can see when something doesn't work."""
import subprocess
import time

# Words that mark a voice-call control in English / Uzbek / Russian UIs. Video calls are skipped.
WORDS = '{"call", "phone", "qo\'ng\'iroq", "qong\'iroq", "qo‘ng‘iroq", "zvon", "звон", "вызов", "позвон"}'

FIND_AND_PRESS = r'''
on isCall(txt)
    set t to txt as text
    ignoring case
        if t contains "video" or t contains "видео" then return false
        repeat with w in ''' + WORDS + r'''
            if t contains (w as text) then return true
        end repeat
    end ignoring
    return false
end isCall

on labelOf(e)
    set s to ""
    tell application "System Events"
        try
            set s to s & " " & (description of e as text)
        end try
        try
            set s to s & " " & (title of e as text)
        end try
        try
            set s to s & " " & (name of e as text)
        end try
        try
            set s to s & " " & (help of e as text)
        end try
    end tell
    return s
end labelOf

on run
    tell application "System Events"
        if not (exists process "Telegram") then return "no-telegram"
        tell process "Telegram"
            set frontmost to true
            delay 0.3
            if (count of windows) is 0 then return "no-window"
            -- 1) a button in the chat window (deep search)
            try
                set els to entire contents of window 1
                set n to 0
                repeat with e in els
                    set n to n + 1
                    if n > 700 then exit repeat
                    try
                        if (role of e) is "AXButton" then
                            if my isCall(my labelOf(e)) then
                                click e
                                return "pressed"
                            end if
                        end if
                    end try
                end repeat
            end try
            -- 2) a menu item in the menu bar ("Call", "Start voice call", ...)
            try
                repeat with mb in menu bar items of menu bar 1
                    try
                        repeat with mi in menu items of menu 1 of mb
                            try
                                if my isCall(name of mi as text) then
                                    if enabled of mi then
                                        click mi
                                        return "pressed-menu"
                                    end if
                                end if
                            end try
                        end repeat
                    end try
                end repeat
            end try
            return "not-found"
        end tell
    end tell
end run
'''

# macOS shows a sheet/dialog with a "Call" button after opening a tel: link (FaceTime / iPhone Cellular Calls).
PRESS_DIALOG = r'''
tell application "System Events"
    repeat with pname in {"FaceTime", "UserNotificationCenter", "CallServicesAgent", "NotificationCenter", "Dock"}
        try
            if exists process (pname as text) then
                tell process (pname as text)
                    repeat with w in windows
                        try
                            click (first button of w whose name is "Call" or name is "Qo'ng'iroq" or name is "Позвонить")
                            return "pressed"
                        end try
                        try
                            click (first button of (first group of w) whose name is "Call")
                            return "pressed"
                        end try
                    end repeat
                end tell
            end if
        end try
    end repeat
end tell
return "not-found"
'''


def _osa(script, timeout=25):
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        return f"error: {e}"
    if r.returncode != 0:
        return "error: " + (r.stderr.strip() or "osascript failed")[:200]
    return r.stdout.strip() or "error: empty answer"


def press_call(wait=2.5):
    """-> 'pressed' / 'pressed-menu', or the reason it wasn't: 'not-found', 'no-window', 'no-telegram', 'error: ...'"""
    time.sleep(wait)                                  # let the chat open
    return _osa(FIND_AND_PRESS)


def press_call_dialog(wait=2.0):
    """After `open tel:...`: presses 'Call' in the confirmation dialog. -> 'pressed' / 'not-found' / 'error: ...'"""
    time.sleep(wait)
    res = "not-found"
    for _ in range(3):                                # the dialog can take a moment to appear
        res = _osa(PRESS_DIALOG)
        if res == "pressed":
            break
        time.sleep(1.0)
    return res
