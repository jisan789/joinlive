import asyncio
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

API_ID = 27634392
API_HASH = "c29325ca5de227dc611e54d355f76896"
SESSION_KEY = "1BVtsOGwBuz8vHuPpNuD-zFio1ZhVeIl94gLKDOycaPwrM6mZLyrY8APMQGTSMjMmWw7nU1h8XEyLMybbcrfbhv1kDzvLyiiTu_dqCapqgtwSCD_p6pM0FKWD9Fdg9ZAkgNac0iN_DKa10ECnXSYpzpSOFdWePvDtsy1vGQzFRxT5xbJBF92Wja7w1sMRT8yflFLWWQOSYsMYVAn83ssCPAVGFyEklL5oNgjaxoMMvH7qxB_piEE8rvMws8CFbX2a6zKtF-s_-Tk6S7lsdoDOVuQOItHpclxOpoS36ZAVpH4xb64r5Hgfj5BUjnyMKspKRJ8K8SRY5Cu45Bu09F53nHGtvmi8tSY="
TARGET_ID = 3962785452

async def main():
    client = TelegramClient(StringSession(SESSION_KEY), API_ID, API_HASH)
    await client.start()
    
    print("Fetching all dialogs (limit=None)...")
    dialogs = await client.get_dialogs(limit=None)
    print(f"Total dialogs found: {len(dialogs)}")
    
    found = False
    for d in dialogs:
        d_id = getattr(d, 'id', 0)
        e_id = getattr(d.entity, 'id', 0)
        print(f"Title: '{d.title}' | Dialog ID: {d_id} | Entity ID: {e_id}")
        if TARGET_ID in (abs(d_id), abs(e_id)) or str(TARGET_ID) in str(d_id):
            print(f"🎉 MATCH FOUND: '{d.title}' -> ID: {d_id}")
            found = True

    if not found:
        print(f"\n❌ Target ID {TARGET_ID} is NOT in the user's dialog list.")
        print("To access a private channel, Telethon requires either:")
        print("1. An invite link (e.g. https://t.me/+...)")
        print("2. Or joining the channel first.")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
