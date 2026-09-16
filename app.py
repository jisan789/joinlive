import asyncio
import json
import os
import random
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.phone import JoinGroupCallRequest, CheckGroupCallRequest, LeaveGroupCallRequest
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
    "service_enabled": True,
    "status": "initializing",
    "is_in_live": False,
    "current_channel": str(CHANNEL_TARGET),
    "last_live_detected": None,
    "last_joined": None,
    "total_pings_received": 0,
    "error_log": None
}

listener_task = None
telethon_client = None

async def resolve_target_channel(client, target):
    """Resolves target channel by Invite Link, ID, Username, or Pre-loaded Dialogs."""
    if isinstance(target, str) and ("t.me/+" in target or "joinchat/" in target):
        invite_hash = target.split("+")[-1].split("joinchat/")[-1].strip("/")
        try:
            updates = await client(ImportChatInviteRequest(invite_hash))
            if hasattr(updates, 'chats') and updates.chats:
                return updates.chats[0]
        except UserAlreadyParticipantError:
            pass
        except Exception:
            pass

    try:
        dialogs = await client.get_dialogs(limit=None)
        target_str = str(target)
        target_clean = target_str.replace("-100", "").strip()

        for d in dialogs:
            d_id_str = str(getattr(d, 'id', 0))
            e_id_str = str(getattr(d.entity, 'id', 0))
            d_title = getattr(d, 'title', getattr(d.entity, 'first_name', 'Unknown'))

            if (target_str in (d_id_str, e_id_str) or 
                target_clean in (d_id_str, e_id_str) or 
                f"-100{e_id_str}" == target_str or
                (hasattr(d.entity, 'username') and d.entity.username and f"@{d.entity.username}".lower() == target_str.lower())):
                return d.entity
    except Exception:
        pass

    try:
        return await client.get_entity(target)
    except Exception:
        pass

    return None

async def live_stream_listener_service():
    global telethon_client
    print("[SERVICE] Starting Live Stream Listener Service...", flush=True)
    telethon_client = TelegramClient(StringSession(SESSION_KEY), API_ID, API_HASH)
    await telethon_client.start()

    me = await telethon_client.get_me()
    print(f"[SERVICE] Logged in as: {me.first_name} (ID: {me.id})", flush=True)

    # Resolve target channel
    channel = None
    while service_status["service_enabled"] and not channel:
        channel = await resolve_target_channel(telethon_client, CHANNEL_TARGET)
        if not channel:
            err_msg = f"Channel '{CHANNEL_TARGET}' not found. Set CHANNEL_ID to invite link or join channel."
            service_status["error_log"] = err_msg
            await asyncio.sleep(5)

    if not channel or not service_status["service_enabled"]:
        return

    title = getattr(channel, 'title', str(CHANNEL_TARGET))
    service_status["current_channel"] = f"{title} ({channel.id})"
    service_status["status"] = "monitoring"
    service_status["error_log"] = None
    print(f"[SERVICE] Monitoring channel: '{title}' (ID: {channel.id})", flush=True)

    is_in_live = False
    current_call_id = None
    input_call = None
    active_ssrc = None

    async def join_call_once(input_c, my_peer):
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
                await telethon_client(JoinGroupCallRequest(
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

    my_input_peer = await telethon_client.get_input_entity("me")

    # Service Loop
    while service_status["service_enabled"]:
        try:
            full_chat_response = await telethon_client(GetFullChannelRequest(channel))
            full_chat = full_chat_response.full_chat
            active_call = full_chat.call

            if active_call:
                # Live stream is RUNNING
                if not is_in_live or (current_call_id != active_call.id):
                    # Join ONLY ONCE when stream starts!
                    service_status["last_live_detected"] = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
                    print(f"[{time.strftime('%H:%M:%S')}] Live stream detected! Joining...", flush=True)

                    input_call = InputGroupCall(id=active_call.id, access_hash=active_call.access_hash)
                    current_call_id = active_call.id

                    success = await join_call_once(input_call, my_input_peer)
                    if success:
                        is_in_live = True
                        service_status["is_in_live"] = True
                        service_status["last_joined"] = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
                        print(f"[{time.strftime('%H:%M:%S')}] Joined live stream successfully! Staying connected on '{title}'.", flush=True)
                    else:
                        print(f"[{time.strftime('%H:%M:%S')}] Failed to join. Retrying in 5s...", flush=True)
                else:
                    # STAY IN LIVE STREAM WITHOUT RE-JOINING!
                    # Only send 10s heartbeat check to keep connection alive
                    try:
                        await telethon_client(CheckGroupCallRequest(call=input_call, sources=[active_ssrc]))
                    except Exception:
                        pass
            else:
                # Live stream is NOT running
                if is_in_live:
                    print(f"[{time.strftime('%H:%M:%S')}] Live stream ENDED/CLOSED. Reset state.", flush=True)
                    is_in_live = False
                    service_status["is_in_live"] = False
                    current_call_id = None
                    input_call = None
                    active_ssrc = None

        except Exception as e:
            pass

        await asyncio.sleep(5)

    # Cleanup when service disabled
    if is_in_live and input_call:
        try:
            await telethon_client(LeaveGroupCallRequest(call=input_call, source=active_ssrc or 0))
        except Exception:
            pass
    is_in_live = False
    service_status["is_in_live"] = False
    service_status["status"] = "stopped"
    print("[SERVICE] Listener Service Stopped cleanly.", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global listener_task
    listener_task = asyncio.create_task(live_stream_listener_service())
    yield
    if listener_task:
        service_status["service_enabled"] = False
        listener_task.cancel()

app = FastAPI(title="LiveJoin Web Service", lifespan=lifespan)

@app.get("/status")
@app.get("/ping")
async def get_ping_status():
    service_status["total_pings_received"] += 1
    return {
        "status": "online",
        "service": "Telegram Live Listener Service",
        "service_enabled": service_status["service_enabled"],
        "uptime_seconds": int(time.time() - service_status["started_at"]),
        "monitoring_channel": service_status["current_channel"],
        "is_in_live": service_status["is_in_live"],
        "last_live_detected": service_status["last_live_detected"],
        "last_joined": service_status["last_joined"],
        "total_cron_pings": service_status["total_pings_received"],
        "error_notice": service_status["error_log"]
    }

@app.post("/start")
@app.get("/start")
async def start_service():
    global listener_task
    if not service_status["service_enabled"]:
        service_status["service_enabled"] = True
        service_status["status"] = "starting"
        listener_task = asyncio.create_task(live_stream_listener_service())
        return {"status": "ok", "message": "Service started successfully."}
    return {"status": "ok", "message": "Service is already running."}

@app.post("/stop")
@app.get("/stop")
async def stop_service():
    global listener_task
    if service_status["service_enabled"]:
        service_status["service_enabled"] = False
        service_status["status"] = "stopping"
        if listener_task:
            listener_task.cancel()
            listener_task = None
        service_status["is_in_live"] = False
        return {"status": "ok", "message": "Service stopped."}
    return {"status": "ok", "message": "Service is already stopped."}

@app.get("/health")
async def ping_health():
    service_status["total_pings_received"] += 1
    return {"status": "ok", "is_in_live": service_status["is_in_live"]}

# HTML Dashboard Interface
@app.get("/", response_class=HTMLResponse)
async def dashboard_ui():
    service_status["total_pings_received"] += 1
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Telegram Live Stream Manager</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Inter', sans-serif;
            background: #0f172a;
            color: #f8fafc;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .container {
            width: 100%;
            max-width: 650px;
            background: rgba(30, 41, 59, 0.8);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 24px;
            padding: 32px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }
        .title { font-size: 22px; font-weight: 700; color: #38bdf8; display: flex; align-items: center; gap: 10px; }
        .live-badge {
            padding: 6px 14px;
            border-radius: 50px;
            font-size: 13px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
            text-transform: uppercase;
        }
        .badge-live { background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid #22c55e; }
        .badge-monitoring { background: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1px solid #0284c7; }
        .badge-stopped { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #ef4444; }
        .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; animation: pulse 1.5s infinite; }
        @keyframes pulse { 0% { opacity: 0.4; } 50% { opacity: 1; } 100% { opacity: 0.4; } }
        
        .grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin-bottom: 24px; }
        .card {
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.05);
            padding: 18px;
            border-radius: 16px;
        }
        .card-label { font-size: 12px; color: #94a3b8; font-weight: 500; text-transform: uppercase; margin-bottom: 6px; }
        .card-value { font-size: 16px; font-weight: 600; color: #f1f5f9; word-break: break-word; }

        .btn-group { display: flex; gap: 14px; margin-top: 10px; }
        .btn {
            flex: 1;
            padding: 14px;
            border: none;
            border-radius: 14px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 8px;
        }
        .btn-start { background: linear-gradient(135deg, #10b981, #059669); color: white; box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3); }
        .btn-start:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(16, 185, 129, 0.4); }
        .btn-stop { background: linear-gradient(135deg, #ef4444, #dc2626); color: white; box-shadow: 0 4px 15px rgba(239, 68, 68, 0.3); }
        .btn-stop:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(239, 68, 68, 0.4); }

        .notice {
            margin-top: 20px;
            padding: 12px 16px;
            background: rgba(56, 189, 248, 0.1);
            border-left: 4px solid #38bdf8;
            border-radius: 8px;
            font-size: 13px;
            color: #cbd5e1;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="title">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 18a8 8 0 1 1 8-8 8 8 0 0 1-8 8z"/><path d="M12 6v6l4 2"/></svg>
                Live Join Manager
            </div>
            <div id="statusBadge" class="live-badge badge-monitoring">
                <span class="dot" style="background: #38bdf8;"></span> Monitoring
            </div>
        </div>

        <div class="grid">
            <div class="card">
                <div class="card-label">Target Channel</div>
                <div id="targetChannel" class="card-value">Loading...</div>
            </div>
            <div class="card">
                <div class="card-label">Live Stream Status</div>
                <div id="liveStatus" class="card-value">Checking...</div>
            </div>
            <div class="card">
                <div class="card-label">Server Uptime</div>
                <div id="serverUptime" class="card-value">0s</div>
            </div>
            <div class="card">
                <div class="card-label">Cron Heartbeats (/ping)</div>
                <div id="cronPings" class="card-value">0</div>
            </div>
        </div>

        <div class="btn-group">
            <button class="btn btn-start" onclick="controlService('start')">
                ▶ Start Listener
            </button>
            <button class="btn btn-stop" onclick="controlService('stop')">
                ⏹ Stop Listener
            </button>
        </div>

        <div class="notice">
            💡 <strong>Cron Ping Target:</strong> Point your external 1-minute cron job to <code>https://YOUR-APP.onrender.com/ping</code> to keep Render awake.
        </div>
    </div>

    <script>
        function updateUI() {
            fetch('/status')
                .then(res => res.json())
                .then(data => {
                    document.getElementById('targetChannel').innerText = data.monitoring_channel || 'Configuring...';
                    document.getElementById('serverUptime').innerText = Math.floor(data.uptime_seconds / 60) + 'm ' + (data.uptime_seconds % 60) + 's';
                    document.getElementById('cronPings').innerText = data.total_cron_pings;

                    const badge = document.getElementById('statusBadge');
                    const liveStatus = document.getElementById('liveStatus');

                    if (!data.service_enabled) {
                        badge.className = 'live-badge badge-stopped';
                        badge.innerHTML = '<span class="dot" style="background: #ef4444;"></span> Stopped';
                        liveStatus.innerText = 'Service Paused';
                    } else if (data.is_in_live) {
                        badge.className = 'live-badge badge-live';
                        badge.innerHTML = '<span class="dot" style="background: #4ade80;"></span> Active In Live';
                        liveStatus.innerText = '🟢 Inside Live Stream (No Rejoin)';
                    } else {
                        badge.className = 'live-badge badge-monitoring';
                        badge.innerHTML = '<span class="dot" style="background: #38bdf8;"></span> Monitoring';
                        liveStatus.innerText = '🔍 Waiting for Live Stream';
                    }
                })
                .catch(err => console.error(err));
        }

        function controlService(action) {
            fetch('/' + action, { method: 'POST' })
                .then(() => updateUI());
        }

        setInterval(updateUI, 3000);
        updateUI();
    </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)
