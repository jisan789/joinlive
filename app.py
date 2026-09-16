import asyncio
import json
import os
import random
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.phone import JoinGroupCallRequest, CheckGroupCallRequest
from telethon.tl.types import DataJSON, InputGroupCall
from telethon.errors import RPCError

# Ensure UTF-8 console output for logs
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Environment Variables with default fallback credentials
API_ID = int(os.getenv("API_ID", "27634392"))
API_HASH = os.getenv("API_HASH", "c29325ca5de227dc611e54d355f76896")
SESSION_KEY = os.getenv("SESSION_KEY", "1BVtsOGwBuz8vHuPpNuD-zFio1ZhVeIl94gLKDOycaPwrM6mZLyrY8APMQGTSMjMmWw7nU1h8XEyLMybbcrfbhv1kDzvLyiiTu_dqCapqgtwSCD_p6pM0FKWD9Fdg9ZAkgNac0iN_DKa10ECnXSYpzpSOFdWePvDtsy1vGQzFRxT5xbJBF92Wja7w1sMRT8yflFLWWQOSYsMYVAn83ssCPAVGFyEklL5oNgjaxoMMvH7qxB_piEE8rvMws8CFbX2a6zKtF-s_-Tk6S7lsdoDOVuQOItHpclxOpoS36ZAVpH4xb64r5Hgfj5BUjnyMKspKRJ8K8SRY5Cu45Bu09F53nHGtvmi8tSY=")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1003962785452"))

# Service State
service_status = {
    "started_at": time.time(),
    "status": "initializing",
    "is_in_live": False,
    "current_channel": None,
    "last_live_detected": None,
    "last_joined": None,
    "total_pings_received": 0
}

async def live_stream_listener_service():
    print("[SERVICE] Starting Live Stream Listener Service...", flush=True)
    client = TelegramClient(StringSession(SESSION_KEY), API_ID, API_HASH)
    await client.start()

    me = await client.get_me()
    print(f"[SERVICE] Logged in as: {me.first_name} (ID: {me.id})", flush=True)

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
            print(f"[SERVICE] Channel {CHANNEL_ID} not found. Retrying in 10s...", flush=True)
            await asyncio.sleep(10)

    service_status["current_channel"] = f"{channel.title} ({channel.id})"
    service_status["status"] = "monitoring"
    print(f"[SERVICE] Monitoring target channel: '{channel.title}' (ID: {channel.id})", flush=True)

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

    # Infinite Monitoring Loop
    while True:
        try:
            full_chat_response = await client(GetFullChannelRequest(channel))
            full_chat = full_chat_response.full_chat
            active_call = full_chat.call

            if active_call:
                # Live stream is RUNNING -> Join Instantly!
                if not is_in_live or (current_call_id != active_call.id):
                    service_status["last_live_detected"] = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
                    print(f"[{time.strftime('%H:%M:%S')}] Live stream detected! Joining instantly...", flush=True)

                    input_call = InputGroupCall(id=active_call.id, access_hash=active_call.access_hash)
                    current_call_id = active_call.id

                    success = await try_join_call(input_call, my_input_peer)
                    if success:
                        is_in_live = True
                        service_status["is_in_live"] = True
                        service_status["last_joined"] = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
                        ping_counter = 0
                        print(f"[{time.strftime('%H:%M:%S')}] Joined live stream successfully! Active on '{channel.title}'", flush=True)
                    else:
                        print(f"[{time.strftime('%H:%M:%S')}] Failed to join live stream. Will retry...", flush=True)
                else:
                    # Heartbeat
                    ping_counter += 1
                    try:
                        await client(CheckGroupCallRequest(call=input_call, sources=[active_ssrc]))
                    except Exception:
                        pass

                    if ping_counter % 6 == 0:
                        try:
                            await try_join_call(input_call, my_input_peer)
                        except Exception:
                            pass

            else:
                # Live stream is NOT running
                if is_in_live:
                    print(f"[{time.strftime('%H:%M:%S')}] Live stream ENDED/CLOSED. Left stream.", flush=True)
                    is_in_live = False
                    service_status["is_in_live"] = False
                    current_call_id = None
                    input_call = None
                    active_ssrc = None

        except Exception:
            pass

        await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start Telethon background listener service task
    listener_task = asyncio.create_task(live_stream_listener_service())
    yield
    # Shutdown: Cancel listener task cleanly
    listener_task.cancel()

app = FastAPI(title="LiveJoin Web Service", lifespan=lifespan)

@app.get("/")
async def root():
    service_status["total_pings_received"] += 1
    return {
        "status": "online",
        "service": "Telegram Live Listener Service",
        "uptime_seconds": int(time.time() - service_status["started_at"]),
        "monitoring_channel": service_status["current_channel"],
        "is_in_live": service_status["is_in_live"],
        "last_live_detected": service_status["last_live_detected"],
        "last_joined": service_status["last_joined"],
        "total_cron_pings": service_status["total_pings_received"]
    }

@app.get("/health")
async def health_check():
    return {"status": "ok"}
