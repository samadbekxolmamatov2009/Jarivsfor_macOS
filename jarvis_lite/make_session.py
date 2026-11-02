"""Run this ONCE, ON YOUR MAC (not on Render). It logs in to Telegram and prints a session string for Render's TG_SESSION.

    ~/jarvis/venv/bin/python make_session.py            (telethon is already in Jarvis's venv; else: pip install telethon)

The string gives full access to your Telegram account: paste it ONLY into Render's environment variables, then clear the
Terminal (Cmd+K). Do not run Jarvis Lite anywhere else with the same string at the same time."""
import asyncio
import getpass
import subprocess

from telethon import TelegramClient
from telethon.sessions import StringSession


async def main():
    api_id = int(input("api_id: ").strip())
    api_hash = getpass.getpass("api_hash (hidden): ").strip()
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.start()                                   # asks for phone number, code, 2-step password
    string = client.session.save()
    await client.disconnect()
    try:                                                   # macOS: put it on the clipboard, so nothing can be cut off while copying
        subprocess.run(["pbcopy"], input=string.encode(), check=True)
        copied = True
    except Exception:
        copied = False
    print(f"\n✅ Session made ({len(string)} characters; a good one is 353).")
    if copied:
        print("📋 It is ALREADY COPIED to your clipboard: go to Render → Environment → TG_SESSION and press Cmd+V.")
        print("   (Nothing else should be in the box. Don't copy anything else before you paste.)")
    else:
        print("===== TG_SESSION (the ONE long line below, it is a secret) =====")
        print(string)
        print("================================================================")
    print("Afterwards clear this Terminal (Cmd+K).\n")

asyncio.run(main())
