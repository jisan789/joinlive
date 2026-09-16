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

async def main():
    client = TelegramClient(StringSession(SESSION_KEY), API_ID, API_HASH)
    await client.start()
    dialogs = await client.get_dialogs()
    for d in dialogs:
        print(f"Title: {d.title} | ID: {d.id} | Entity ID: {getattr(d.entity, 'id', None)}")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
