"""
Run locally in Termux or on a computer. It logs into Telegram and prints a
Telethon StringSession. Never paste the session string into a chat or commit it.
"""
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

def main():
    api_id_text = input("Telegram API ID from https://my.telegram.org: ").strip()
    api_hash = input("Telegram API HASH: ").strip()
    api_id = int(api_id_text)

    with TelegramClient(StringSession(), api_id, api_hash) as client:
        print("\nLogin succeeded.")
        print("Add the following as GitHub Actions secret TELEGRAM_SESSION.")
        print("Treat it like your Telegram account password; do not share it.\n")
        print(client.session.save())

if __name__ == "__main__":
    main()
