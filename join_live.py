import asyncio
import json
import random
import sys
import time
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.phone import JoinGroupCallRequest, CheckGroupCallRequest
from telethon.tl.types import DataJSON, InputGroupCall
from telethon.errors import RPCError

# Ensure clean UTF-8 console output
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

API_ID = 27634392
API_HASH = "c29325ca5de227dc611e54d355f76896"
SESSION_KEY = "1BVtsOGwBuz8vHuPpNuD-zFio1ZhVeIl94gLKDOycaPwrM6mZLyrY8APMQGTSMjMmWw7nU1h8XEyLMybbcrfbhv1kDzvLyiiTu_dqCapqgtwSCD_p6pM0FKWD9Fdg9ZAkgNac0iN_DKa10ECnXSYpzpSOFdWePvDtsy1vGQzFRxT5xbJBF92Wja7w1sMRT8yflFLWWQOSYsMYVAn83ssCPAVGFyEklL5oNgjaxoMMvH7qxB_piEE8rvMws8CFbX2a6zKtF-s_-Tk6S7lsdoDOVuQOItHpclxOpoS36ZAVpH4xb64r5Hgfj5BUjnyMKspKRJ8K8SRY5Cu45Bu09F53nHGtvmi8tSY="
CHANNEL_ID = -1003962785452

# Random delay range before joining (in seconds): 30s to 180s (3 minutes)
MIN_DELAY_SECONDS = 30
MAX_DELAY_SECONDS = 180

async def live_stream_listener_service():
    print("Starting Live Stream Listener Service...", flush=True)
    client = TelegramClient(StringSession(SESSION_KEY), API_ID, API_HASH)
    await client.start()

    me = await client.get_me()
    print(f"Service running as user: {me.first_name} (ID: {me.id})", flush=True)

    # Resolve target channel
    channel = None
    while not channel:
        try:
            channel = await client.get_entity(CHANNEL_ID)
        except Exception:
            async for dialog in client.iter_dialogs():
                if dialog.id == CHANNEL_ID or str(dialog.id) == str(CHANNEL_ID) or f"-100{dialog.entity.id}" == str(CHANNEL_ID):
                    channel = dialog.entity
                    break
        if not channel:
            print(f"Channel {CHANNEL_ID} not found. Retrying in 10 seconds...", flush=True)
            await asyncio.sleep(10)

    print(f"Monitoring target channel: '{channel.title}' (ID: {channel.id})", flush=True)

    is_in_live = False
    current_call_id = None
    input_call = None
    active_ssrc = None
    ping_counter = 0

    async def try_join_call(input_c, my_peer):
        nonlocal active_ssrc
        for _ in range(10):
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
            try:
                await client(JoinGroupCallRequest(
                    call=input_c,
                    join_as=my_peer,
                    muted=True,
                    video_stopped=True,
                    params=DataJSON(data=json.dumps(webrtc_json))
                ))
                active_ssrc = ssrc
                return True
            except RPCError as e:
                if "SSRC" in str(e).upper():
                    await asyncio.sleep(0.5)
                    continue
                else:
                    return False
            except Exception:
                return False
        return False

    my_input_peer = await client.get_input_entity("me")

    # Infinite Service Loop
    while True:
        try:
            # Check live call status on channel
            full_chat_response = await client(GetFullChannelRequest(channel))
            full_chat = full_chat_response.full_chat
            active_call = full_chat.call

            if active_call:
                # Live stream is RUNNING
                if not is_in_live or (current_call_id != active_call.id):
                    delay = random.randint(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
                    print(f"[{time.strftime('%H:%M:%S')}] Live stream detected! Waiting random delay of {delay} seconds before joining...", flush=True)
                    
                    # Sleep for the random delay
                    await asyncio.sleep(delay)

                    # Verify live stream is still running after delay
                    full_chat_response = await client(GetFullChannelRequest(channel))
                    if not full_chat_response.full_chat.call or full_chat_response.full_chat.call.id != active_call.id:
                        print(f"[{time.strftime('%H:%M:%S')}] Live stream ended during delay period.", flush=True)
                        await asyncio.sleep(5)
                        continue

                    print(f"[{time.strftime('%H:%M:%S')}] Joining live stream now...", flush=True)
                    input_call = InputGroupCall(id=active_call.id, access_hash=active_call.access_hash)
                    current_call_id = active_call.id

                    success = await try_join_call(input_call, my_input_peer)
                    if success:
                        is_in_live = True
                        ping_counter = 0
                        print(f"[{time.strftime('%H:%M:%S')}] Joined live stream successfully! Active on '{channel.title}'", flush=True)
                    else:
                        print(f"[{time.strftime('%H:%M:%S')}] Failed to join live stream. Will retry...", flush=True)
                else:
                    # Already joined - send heartbeat ping
                    ping_counter += 1
                    try:
                        await client(CheckGroupCallRequest(call=input_call, sources=[active_ssrc]))
                    except Exception:
                        pass
                    
                    # Periodic re-confirm join every 30s
                    if ping_counter % 6 == 0:
                        try:
                            await try_join_call(input_call, my_input_peer)
                        except Exception:
                            pass

            else:
                # Live stream is NOT running
                if is_in_live:
                    print(f"[{time.strftime('%H:%M:%S')}] Live stream ENDED/CLOSED. Left the stream.", flush=True)
                    is_in_live = False
                    current_call_id = None
                    input_call = None
                    active_ssrc = None

        except Exception:
            pass

        await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(live_stream_listener_service())
    except KeyboardInterrupt:
        print("Listener Service stopped by user.", flush=True)
