#!/bin/bash
# Shows what Jarvis can "see" in the Telegram window. Open a chat in Telegram first, then run:
#   bash ~/jarvis/tg_call_debug.sh
# and send the output to your developer. (Needs the same Accessibility permission.)
osascript <<'OSA'
tell application "System Events"
    if not (exists process "Telegram") then return "Telegram is not running"
    tell process "Telegram"
        set out to "windows: " & (count of windows) & linefeed
        try
            set els to entire contents of window 1
            set n to 0
            repeat with e in els
                set n to n + 1
                if n > 300 then exit repeat
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
