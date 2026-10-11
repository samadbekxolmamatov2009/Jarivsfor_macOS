#!/bin/bash
# Shows what Jarvis can "see" when a call doesn't start. Open the chat in Telegram first, then run:
#   bash ~/jarvis/tg_call_debug.sh
# and send the output to your developer. (Needs the same Accessibility permission.)
echo "=== Telegram window (buttons) ==="
osascript <<'OSA'
tell application "System Events"
    if not (exists process "Telegram") then return "Telegram is not running"
    tell process "Telegram"
        set out to "windows: " & (count of windows) & linefeed
        try
            set n to 0
            repeat with e in (entire contents of window 1)
                set n to n + 1
                if n > 400 then exit repeat
                try
                    set out to out & (role of e) & " | " & (description of e) & " | " & (title of e) & " | " & (name of e) & linefeed
                end try
            end repeat
        on error m
            set out to out & "error: " & m
        end try
        return out
    end tell
end tell
OSA
echo "=== Telegram menu bar ==="
osascript <<'OSA'
tell application "System Events"
    if not (exists process "Telegram") then return "Telegram is not running"
    tell process "Telegram"
        set out to ""
        try
            repeat with mb in menu bar items of menu bar 1
                set out to out & "[" & (name of mb) & "] "
                try
                    repeat with mi in menu items of menu 1 of mb
                        try
                            set out to out & (name of mi) & "; "
                        end try
                    end repeat
                end try
                set out to out & linefeed
            end repeat
        on error m
            set out to out & "error: " & m
        end try
        return out
    end tell
end tell
OSA
echo "=== Running apps that could show a Call dialog ==="
osascript -e 'tell application "System Events" to get name of every process whose name is "FaceTime" or name is "UserNotificationCenter" or name is "CallServicesAgent"'
