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
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.phone import JoinGroupCallRequest, CheckGroupCallRequest
from telethon.tl.types import DataJSON, InputGroupCall, PeerChannel
from telethon.errors import RPCError, UserAlreadyParticipantError

# Ensure UTF-8 console output for logs
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Environment Variables
API_ID = int(os.getenv("API_ID", "27634392"))
API_HASH = os.getenv("API_HASH", "c29325ca5de227dc611e54d355f76896")
SESSION_KEY = os.getenv("SESSION_KEY", "1BVtsOGwBuz8vHuPpNuD-zFio1ZhVeIl94gLKDOycaPwrM6mZLyrY8APMQGTSMjMmWw7nU1h8XEyLMybbcrfbhv1kDzvLyiiTu_dqCapqgtwSCD_p6pM0FKWD9Fdg9ZAkgNac0iN_DKa10ECnXSYpzpSOFdWePvDtsy1vGQzFRxT5xbJBF92Wja7w1sMRT8yflFLWWQOSYsMYVAn83ssCPAVGFyEklL5oNgjaxoMMvH7qxB_piEE8rvMws8CFbX2a6zKtF-s_-Tk6S7lsdoDOVuQOItHpclxOpoS36ZAVpH4xb64r5Hgfj5BUjnyMKspKRJ8K8SRY5Cu45Bu09F53nHGtvmi8tSY=")

RAW_CHANNEL = os.getenv("CHANNEL_ID", "-1003962785452")

try:
    CHANNEL_TARGET = int(RAW_CHANNEL)
except ValueError:
    CHANNEL_TARGET = RAW_CHANNEL

# Service State
service_status = {
    "started_at": time.time(),
    "status": "initializing",
    "is_in_live": False,
    "current_channel": str(CHANNEL_TARGET),
    "last_live_detected": None,
    "last_joined": None,
    "total_pings_received": 0,
    "error_log": None
}

async def resolve_target_channel(client, target):
    """
    Populates Telethon's entity cache in memory by fetching dialogs, 
    and resolves the target channel by ID, Username, or Invite Link.
    """
    # 1. Handle Invite Links (e.g. https://t.me/+... or joinchat)
    if isinstance(target, str) and ("t.me/+" in target or "joinchat/" in target):
        invite_hash = target.split("+")[-1].split("joinchat/")[-1].strip("/")
        try:
            print(f"[SERVICE] Importing chat invite hash: '{invite_hash}'...", flush=True)
            updates = await client(ImportChatInviteRequest(invite_hash))
            if hasattr(updates, 'chats') and updates.chats:
                print(f"[SERVICE] Joined private channel '{updates.chats[0].title}' via invite link!", flush=True)
                return updates.chats[0]
        except UserAlreadyParticipantError:
            pass
        except Exception as e:
            print(f"[SERVICE] Invite link import notice: {e}", flush=True)

    # 2. Fetch all dialogs to populate Telethon's RAM entity cache
    try:
        dialogs = await client.get_dialogs(limit=None)
        
        target_str = str(target)
        target_clean = target_str.replace("-100", "").strip()

        for d in dialogs:
            d_id = getattr(d, 'id', 0)
            e_id = getattr(d.entity, 'id', 0)
            d_id_str = str(d_id)
            e_id_str = str(e_id)
            d_title = getattr(d, 'title', getattr(d.entity, 'first_name', 'Unknown'))

            if (target_str in (d_id_str, e_id_str) or 
                target_clean in (d_id_str, e_id_str) or 
                f"-100{e_id_str}" == target_str or
                (hasattr(d.entity, 'username') and d.entity.username and f"@{d.entity.username}".lower() == target_str.lower())):
                print(f"[SERVICE] Successfully matched channel '{d_title}' in dialogs!", flush=True)
                return d.entity
    except Exception as e:
        print(f"[SERVICE] Dialog fetch notice: {e}", flush=True)

    # 3. Direct entity lookup fallback
    try:
        return await client.get_entity(target)
    except Exception:
        pass

    if isinstance(target, int):
        clean_id = int(str(target).replace("-100", ""))
        for try_peer in [clean_id, PeerChannel(clean_id)]:
            try:
                return await client.get_entity(try_peer)
            except Exception:
                pass

    return None

async def live_stream_listener_service():
    print("[SERVICE] Starting Live Stream Listener Service...", flush=True)
    client = TelegramClient(StringSession(SESSION_KEY), API_ID, API_HASH)
    await client.start()

    me = await client.get_me()
    print(f"[SERVICE] Logged in as: {me.first_name} (ID: {me.id})", flush=True)

    # Resolve target channel
    channel = None
    while not channel:
        print(f"[SERVICE] Resolving target channel '{CHANNEL_TARGET}'...", flush=True)
        channel = await resolve_target_channel(client, CHANNEL_TARGET)
        if not channel:
            err_msg = f"Channel '{CHANNEL_TARGET}' not found in account dialogs. Please set CHANNEL_ID on Render to your channel invite link (e.g. https://t.me/+...) or correct channel ID."
            service_status["error_log"] = err_msg
            print(f"[SERVICE] {err_msg} Retrying in 10s...", flush=True)
            await asyncio.sleep(10)

    title = getattr(channel, 'title', str(CHANNEL_TARGET))
    service_status["current_channel"] = f"{title} ({channel.id})"
    service_status["status"] = "monitoring"
    service_status["error_log"] = None
    print(f"[SERVICE] Monitoring target channel: '{title}' (ID: {channel.id})", flush=True)

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
                        print(f"[{time.strftime('%H:%M:%S')}] Joined live stream successfully! Active on '{title}'", flush=True)
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

        except Exception as e:
            print(f"[SERVICE] Loop check notice: {e}", flush=True)

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
        "total_cron_pings": service_status["total_pings_received"],
        "error_notice": service_status["error_log"]
    }

@app.get("/health")
async def health_check():
    return {"status": "ok"}
