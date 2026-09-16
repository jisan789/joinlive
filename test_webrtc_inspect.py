import asyncio
import json
import random
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.phone import JoinGroupCallRequest
from telethon.tl.types import DataJSON, InputGroupCall

API_ID = 27634392
API_HASH = "c29325ca5de227dc611e54d355f76896"
SESSION_KEY = "1BVtsOGwBuz8vHuPpNuD-zFio1ZhVeIl94gLKDOycaPwrM6mZLyrY8APMQGTSMjMmWw7nU1h8XEyLMybbcrfbhv1kDzvLyiiTu_dqCapqgtwSCD_p6pM0FKWD9Fdg9ZAkgNac0iN_DKa10ECnXSYpzpSOFdWePvDtsy1vGQzFRxT5xbJBF92Wja7w1sMRT8yflFLWWQOSYsMYVAn83ssCPAVGFyEklL5oNgjaxoMMvH7qxB_piEE8rvMws8CFbX2a6zKtF-s_-Tk6S7lsdoDOVuQOItHpclxOpoS36ZAVpH4xb64r5Hgfj5BUjnyMKspKRJ8K8SRY5Cu45Bu09F53nHGtvmi8tSY="
CHANNEL_ID = -1003962785452

async def main():
    client = TelegramClient(StringSession(SESSION_KEY), API_ID, API_HASH)
    await client.start()
    
    dialogs = await client.get_dialogs()
    target_dialog = None
    for d in dialogs:
        if str(d.id) == str(CHANNEL_ID) or f"-100{getattr(d.entity, 'id', '')}" == str(CHANNEL_ID):
            target_dialog = d.entity
            break
    
    if not target_dialog:
        print("Channel not found in dialogs")
        return

    full_chat = (await client(GetFullChannelRequest(target_dialog))).full_chat
    if not full_chat.call:
        print("No active call")
        return

    call = full_chat.call
    input_call = InputGroupCall(id=call.id, access_hash=call.access_hash)
    my_peer = await client.get_input_entity("me")

    ssrc = random.randint(100000, 999999999)
    webrtc_json = {
        "transport": {
            "fingerprints": [
                {
                    "hash": "sha-256",
                    "setup": "actpass",
                    "fingerprint": "00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF"
                }
            ],
            "candidates": [],
            "ufrag": f"liveufrag{ssrc}",
            "pwd": f"livepwd{ssrc}12345678"
        },
        "ssrc": ssrc
    }

    res = await client(JoinGroupCallRequest(
        call=input_call,
        join_as=my_peer,
        muted=True,
        video_stopped=True,
        params=DataJSON(data=json.dumps(webrtc_json))
    ))

    print("Updates count:", len(res.updates))
    for u in res.updates:
        print("Update type:", type(u).__name__)
        if hasattr(u, "params"):
            print("Server RTC Params JSON:", u.params.data)
        if hasattr(u, "call"):
            print("Call object:", u.call)

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
