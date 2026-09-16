import asyncio
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = 27634392
API_HASH = "c29325ca5de227dc611e54d355f76896"
SESSION_KEY = "1BVtsOGwBuz8vHuPpNuD-zFio1ZhVeIl94gLKDOycaPwrM6mZLyrY8APMQGTSMjMmWw7nU1h8XEyLMybbcrfbhv1kDzvLyiiTu_dqCapqgtwSCD_p6pM0FKWD9Fdg9ZAkgNac0iN_DKa10ECnXSYpzpSOFdWePvDtsy1vGQzFRxT5xbJBF92Wja7w1sMRT8yflFLWWQOSYsMYVAn83ssCPAVGFyEklL5oNgjaxoMMvH7qxB_piEE8rvMws8CFbX2a6zKtF-s_-Tk6S7lsdoDOVuQOItHpclxOpoS36ZAVpH4xb64r5Hgfj5BUjnyMKspKRJ8K8SRY5Cu45Bu09F53nHGtvmi8tSY="
CHANNEL_ID = -1003962785452

async def main():
    client = TelegramClient(StringSession(SESSION_KEY), API_ID, API_HASH)
    await client.start()
    try:
        e = await client.get_entity(CHANNEL_ID)
        print("Success:", e)
    except Exception as ex:
        print("Failed get_entity:", ex)
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
