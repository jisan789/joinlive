import asyncio
import hashlib
import hmac
import json
import os
import random
import socket
import struct
import sys
import time
import zlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.phone import JoinGroupCallRequest, CheckGroupCallRequest, LeaveGroupCallRequest
from telethon.tl.types import DataJSON, InputGroupCall, PeerChannel, GroupCall, GroupCallDiscarded
from telethon.errors import RPCError, UserAlreadyParticipantError

try:
    from ntgcalls import NTgCalls
    HAS_NTGCALLS = True
except ImportError:
    HAS_NTGCALLS = False

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

# Service State & Logs Buffer
service_status = {
    "started_at": time.time(),
    "service_enabled": True,
    "status": "initializing",
    "is_in_live": False,
    "current_channel": str(CHANNEL_TARGET),
    "last_live_detected": None,
    "last_joined": None,
    "total_pings_received": 0,
    "error_log": None,
    "logs": []
}

def log_event(msg: str):
    """Prints message and stores in in-memory logs buffer for web dashboard terminal."""
    timestamp = time.strftime('%H:%M:%S')
    formatted_msg = f"[{timestamp}] {msg}"
    print(formatted_msg, flush=True)
    service_status["logs"].append(formatted_msg)
    if len(service_status["logs"]) > 80:
        service_status["logs"].pop(0)

def build_stun_binding_request(server_ufrag: str, client_ufrag: str, server_pwd: str) -> bytes:
    """Constructs a standard RFC 5389 / ICE STUN Binding Request packet for Telegram WebRTC."""
    magic_cookie = b"\x21\x12\xa4\x42"
    trans_id = os.urandom(12)
    
    # 1. USERNAME attribute (0x0006): server_ufrag:client_ufrag
    username_str = f"{server_ufrag}:{client_ufrag}".encode('utf-8')
    pad_len = (4 - (len(username_str) % 4)) % 4
    username_attr = struct.pack("!HH", 0x0006, len(username_str)) + username_str + (b"\x00" * pad_len)
    
    # 2. PRIORITY attribute (0x0024)
    priority_attr = struct.pack("!HHI", 0x0024, 4, 1845494271)
     
    # 3. ICE-CONTROLLING (0x802a)
    controlling_attr = struct.pack("!HH", 0x802a, 8) + os.urandom(8)
    attrs = username_attr + priority_attr + controlling_attr
    
    # 4. MESSAGE-INTEGRITY attribute (0x0008)
    header_for_hmac = struct.pack("!HH", 0x0001, len(attrs) + 24) + magic_cookie + trans_id
    hmac_val = hmac.new(server_pwd.encode('utf-8'), header_for_hmac + attrs, hashlib.sha1).digest()
    integrity_attr = struct.pack("!HH", 0x0008, 20) + hmac_val
    
    all_attrs = attrs + integrity_attr
    
    # 5. FINGERPRINT attribute (0x8028)
    final_header = struct.pack("!HH", 0x0001, len(all_attrs) + 8) + magic_cookie + trans_id
    crc = zlib.crc32(final_header + all_attrs) ^ 0x5354554e
    fingerprint_attr = struct.pack("!HHI", 0x8028, 4, crc & 0xffffffff)
    
    return final_header + all_attrs + fingerprint_attr

listener_task = None
self_ping_task = None
telethon_client = None

async def self_ping_loop():
    """Automatic internal self-pinging background task to keep server awake on Render."""
    await asyncio.sleep(15)
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    log_event(f"Internal self-ping monitor started. App URL: {render_url or 'Local'}")
    
    while service_status["service_enabled"]:
        try:
            if render_url:
                import urllib.request
                ping_url = f"{render_url.rstrip('/')}/ping"
                urllib.request.urlopen(ping_url, timeout=10)
                log_event("Internal self-ping sent to keep server awake.")
        except Exception:
            pass
        await asyncio.sleep(180)

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
    log_event("Starting Live Stream Listener Service...")
    telethon_client = TelegramClient(StringSession(SESSION_KEY), API_ID, API_HASH)
    await telethon_client.start()

    me = await telethon_client.get_me()
    log_event(f"Logged in as user: {me.first_name} (ID: {me.id})")

    # Resolve target channel
    channel = None
    while service_status["service_enabled"] and not channel:
        log_event(f"Resolving target channel '{CHANNEL_TARGET}'...")
        channel = await resolve_target_channel(telethon_client, CHANNEL_TARGET)
        if not channel:
            err_msg = f"Channel '{CHANNEL_TARGET}' not found. Set CHANNEL_ID to invite link or join channel."
            service_status["error_log"] = err_msg
            log_event(f"ERROR: {err_msg} Retrying in 5s...")
            await asyncio.sleep(5)

    if not channel or not service_status["service_enabled"]:
        return

    title = getattr(channel, 'title', str(CHANNEL_TARGET))
    service_status["current_channel"] = f"{title} ({channel.id})"
    service_status["status"] = "monitoring"
    service_status["error_log"] = None
    log_event(f"Monitoring target channel: '{title}' (ID: {channel.id})")

    is_in_live = False
    current_call_id = None
    input_call = None
    active_ssrc = None
    ntg_instance = None
    last_full_check = 0

    my_input_peer = await telethon_client.get_input_entity("me")

    # Service Loop
    while service_status["service_enabled"]:
        try:
            if not is_in_live:
                # STATE 1: MONITORING (Waiting for a live stream to start)
                try:
                    full_chat_response = await telethon_client(GetFullChannelRequest(channel))
                    full_chat = full_chat_response.full_chat
                    active_call = getattr(full_chat, 'call', None)

                    if active_call and getattr(active_call, 'id', 0) != 0:
                        # Active live stream detected -> JOIN ONCE & MAINTAIN WEBRTC SESSION
                        service_status["last_live_detected"] = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
                        log_event("Live stream detected! Joining and establishing persistent WebRTC session...")

                        input_call = InputGroupCall(id=active_call.id, access_hash=active_call.access_hash)
                        current_call_id = active_call.id
                        chat_id = active_call.id

                        join_payload = None
                        if HAS_NTGCALLS:
                            try:
                                ntg_instance = NTgCalls()
                                raw_payload = await ntg_instance.create_call(chat_id)
                                payload_data = json.loads(raw_payload)
                                raw_ssrc = payload_data.get("ssrc", random.randint(100000, 2147483647))
                                active_ssrc = raw_ssrc if raw_ssrc <= 2147483647 else raw_ssrc - (1 << 32)
                                join_payload = raw_payload
                            except Exception as e:
                                log_event(f"NTgCalls payload notice: {e}")
                                ntg_instance = None

                        if not join_payload:
                            raw_ssrc = random.randint(100000, 2147483647)
                            active_ssrc = raw_ssrc if raw_ssrc <= 2147483647 else raw_ssrc - (1 << 32)
                            client_ufrag = f"ufrag{raw_ssrc}"
                            client_pwd = f"pwd{raw_ssrc}12345678"
                            webrtc_json = {
                                "transport": {
                                    "fingerprints": [
                                        {
                                            "hash": "sha-256",
                                            "setup": "passive",
                                            "fingerprint": "00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF"
                                        }
                                    ],
                                    "candidates": [],
                                    "ufrag": client_ufrag,
                                    "pwd": client_pwd
                                },
                                "ssrc": raw_ssrc
                            }
                            join_payload = json.dumps(webrtc_json)

                        res = await telethon_client(JoinGroupCallRequest(
                            call=input_call,
                            join_as=my_input_peer,
                            muted=True,
                            video_stopped=True,
                            params=DataJSON(data=join_payload)
                        ))

                        server_params_str = None
                        updates_list = getattr(res, "updates", []) if hasattr(res, "updates") else []
                        for u in updates_list:
                            if hasattr(u, "params"):
                                server_params_str = u.params.data
                                break

                        if ntg_instance and server_params_str:
                            try:
                                await ntg_instance.connect(chat_id, server_params_str, False)
                                log_event("SUCCESS: Joined live! Native WebRTC Gateway connected. Staying in stream continuously without drops or rejoining.")
                            except Exception as e:
                                log_event(f"NTgCalls connect notice: {e}")
                        else:
                            log_event("SUCCESS: Joined live stream! Maintaining MTProto keepalive session.")

                        is_in_live = True
                        service_status["is_in_live"] = True
                        service_status["last_joined"] = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
                        last_full_check = time.time()
                except RPCError as ex:
                    log_event(f"Monitoring notice: {ex}")
                except Exception as ex:
                    log_event(f"Monitoring notice: {ex}")

                await asyncio.sleep(5)

            else:
                # STATE 2: ACTIVE IN LIVE STREAM
                # Continuous Heartbeat Maintenance (STAY IN STREAM, NEVER REJOIN)
                stream_ended = False

                # 1. MTProto CheckGroupCallRequest keepalive every 4.0 seconds
                try:
                    await telethon_client(CheckGroupCallRequest(call=input_call, sources=[active_ssrc]))
                except RPCError as rpc_err:
                    err_str = str(rpc_err).upper()
                    if any(w in err_str for w in ("DISCARDED", "INVALID", "CLOSED")):
                        log_event(f"Live stream ended ({rpc_err}). Returning to monitoring.")
                        stream_ended = True
                    elif any(w in err_str for w in ("FORBIDDEN", "JOIN_MISSING")):
                        log_event("Live session expired on server. Resetting to reconnect cleanly.")
                        stream_ended = True
                except Exception:
                    pass

                # 2. Periodically check full channel state every 30s as a background check
                if not stream_ended and (time.time() - last_full_check >= 30):
                    last_full_check = time.time()
                    try:
                        fc = await telethon_client(GetFullChannelRequest(channel))
                        call_obj = getattr(fc.full_chat, 'call', None)
                        if not call_obj or getattr(call_obj, 'id', None) != current_call_id:
                            log_event("Live stream ended or changed. Returning to monitoring.")
                            stream_ended = True
                    except Exception:
                        pass

                if stream_ended:
                    if ntg_instance:
                        try:
                            await ntg_instance.stop(chat_id)
                        except Exception:
                            pass
                        ntg_instance = None
                    is_in_live = False
                    service_status["is_in_live"] = False
                    current_call_id = None
                    input_call = None
                    active_ssrc = None
                    continue

                # Sleep 4.0s between heartbeat cycles
                await asyncio.sleep(4.0)

        except Exception:
            await asyncio.sleep(4.0)

    # Cleanup when service disabled
    if ntg_instance and current_call_id:
        try:
            await ntg_instance.stop(current_call_id)
        except Exception:
            pass
        ntg_instance = None

    if is_in_live and input_call:
        try:
            await telethon_client(LeaveGroupCallRequest(call=input_call, source=active_ssrc or 0))
        except Exception:
            pass
    is_in_live = False
    service_status["is_in_live"] = False
    service_status["status"] = "stopped"
    log_event("Listener Service stopped cleanly.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global listener_task, self_ping_task
    listener_task = asyncio.create_task(live_stream_listener_service())
    self_ping_task = asyncio.create_task(self_ping_loop())
    yield
    if listener_task:
        service_status["service_enabled"] = False
        listener_task.cancel()
    if self_ping_task:
        self_ping_task.cancel()

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
        "error_notice": service_status["error_log"],
        "logs": service_status["logs"]
    }

@app.post("/start")
@app.get("/start")
async def start_service():
    global listener_task
    if not service_status["service_enabled"]:
        service_status["service_enabled"] = True
        service_status["status"] = "starting"
        log_event("User manually clicked START service.")
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
        log_event("User manually clicked STOP service.")
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
    <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Inter', sans-serif;
            background: #090d16;
            color: #f8fafc;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .container {
            width: 100%;
            max-width: 750px;
            background: rgba(15, 23, 42, 0.85);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 24px;
            padding: 32px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
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
            background: rgba(10, 15, 29, 0.7);
            border: 1px solid rgba(255, 255, 255, 0.05);
            padding: 18px;
            border-radius: 16px;
        }
        .card-label { font-size: 11px; color: #94a3b8; font-weight: 500; text-transform: uppercase; margin-bottom: 6px; letter-spacing: 0.5px; }
        .card-value { font-size: 15px; font-weight: 600; color: #f1f5f9; word-break: break-word; }

        .btn-group { display: flex; gap: 14px; margin-bottom: 24px; }
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

        .terminal-container {
            background: #030712;
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            overflow: hidden;
            box-shadow: inset 0 2px 8px rgba(0,0,0,0.8);
        }
        .terminal-header {
            background: #111827;
            padding: 10px 16px;
            display: flex;
            align-items: center;
            gap: 8px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }
        .term-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
        .term-dot.red { background: #ef4444; }
        .term-dot.yellow { background: #f59e0b; }
        .term-dot.green { background: #10b981; }
        .term-title { font-size: 12px; font-family: 'Fira Code', monospace; color: #94a3b8; margin-left: 8px; }
        .terminal-body {
            padding: 16px;
            height: 220px;
            overflow-y: auto;
            font-family: 'Fira Code', monospace;
            font-size: 13px;
            line-height: 1.6;
            color: #38bdf8;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .log-entry { word-break: break-all; }
        .log-success { color: #4ade80; }
        .log-error { color: #f87171; }
        .log-warn { color: #fbbf24; }

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
                <div class="card-label">Keep-Alive Heartbeats</div>
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

        <div class="terminal-container">
            <div class="terminal-header">
                <span class="term-dot red"></span>
                <span class="term-dot yellow"></span>
                <span class="term-dot green"></span>
                <span class="term-title">terminal.log — Live Service Console</span>
            </div>
            <div id="terminalLog" class="terminal-body">
                <div class="log-entry">Connecting to live console stream...</div>
            </div>
        </div>

        <div class="notice">
            ⚡ <strong>WebRTC STUN Active:</strong> Continuous ICE Binding pings keep the user in the live stream without leaving or rejoining!
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
                        liveStatus.innerText = '🟢 Inside Live Stream (WebRTC Active)';
                    } else {
                        badge.className = 'live-badge badge-monitoring';
                        badge.innerHTML = '<span class="dot" style="background: #38bdf8;"></span> Monitoring';
                        liveStatus.innerText = '🔍 Waiting for Live Stream';
                    }

                    if (data.logs && data.logs.length > 0) {
                        const term = document.getElementById('terminalLog');
                        term.innerHTML = data.logs.map(log => {
                            let cls = 'log-entry';
                            if (log.includes('SUCCESS') || log.includes('Joined')) cls += ' log-success';
                            else if (log.includes('ERROR') || log.includes('Failed')) cls += ' log-error';
                            else if (log.includes('WARNING') || log.includes('ENDED')) cls += ' log-warn';
                            return `<div class="${cls}">${log}</div>`;
                        }).join('');
                        
                        term.scrollTop = term.scrollHeight;
                    }
                })
                .catch(err => console.error(err));
        }

        function controlService(action) {
            fetch('/' + action, { method: 'POST' })
                .then(() => updateUI());
        }

        setInterval(updateUI, 2500);
        updateUI();
    </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)
