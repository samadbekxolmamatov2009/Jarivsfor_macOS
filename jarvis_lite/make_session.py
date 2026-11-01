"""Run this ONCE, ON YOUR MAC (not on Render). It logs in to Telegram and prints a session string for Render's TG_SESSION.

    ~/jarvis/venv/bin/python make_session.py            (telethon is already in Jarvis's venv; else: pip install telethon)

The string gives full access to your Telegram account: paste it ONLY into Render's environment variables, then clear the
Terminal (Cmd+K). Do not run Jarvis Lite anywhere else with the same string at the same time."""
import asyncio
import getpass

from telethon import TelegramClient
from telethon.sessions import StringSession


async def main():
    api_id = int(input("api_id: ").strip())
    api_hash = getpass.getpass("api_hash (hidden): ").strip()
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.start()                                   # asks for phone number, code, 2-step password
    string = client.session.save()
    await client.disconnect()
    print("\n===== TG_SESSION (copy the ONE long line below, it is a secret) =====")
    print(string)
    print("=====================================================================\n")

asyncio.run(main())
