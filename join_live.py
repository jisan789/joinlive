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
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.phone import JoinGroupCallRequest, CheckGroupCallRequest, LeaveGroupCallRequest
from telethon.tl.types import DataJSON, InputGroupCall, GroupCall, GroupCallDiscarded
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
    
    # 3. ICE-CONTROLLED (0x8029) - client acts as controlled agent to Telegram SFU
    controlled_attr = struct.pack("!HH", 0x8029, 8) + os.urandom(8)
    attrs = username_attr + priority_attr + controlled_attr
    
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
            print(f"Channel {CHANNEL_ID} not found. Retrying in 5 seconds...", flush=True)
            await asyncio.sleep(5)

    title = getattr(channel, 'title', str(CHANNEL_ID))
    print(f"Monitoring target channel: '{title}' (ID: {channel.id})", flush=True)

    is_in_live = False
    current_call_id = None
    input_call = None
    active_ssrc = None
    udp_socket = None
    udp_target = None
    server_ufrag = None
    server_pwd = None
    client_ufrag = None
    last_full_check = 0

    my_input_peer = await client.get_input_entity("me")

    # Infinite Service Loop
    while True:
        try:
            if not is_in_live:
                # STATE 1: MONITORING (Wait for live stream to start)
                try:
                    full_chat_response = await client(GetFullChannelRequest(channel))
                    full_chat = full_chat_response.full_chat
                    active_call = getattr(full_chat, 'call', None)

                    if isinstance(active_call, GroupCall):
                        # Live stream detected -> JOIN EXACTLY ONCE!
                        print(f"[{time.strftime('%H:%M:%S')}] Live stream detected! Joining once...", flush=True)

                        input_call = InputGroupCall(id=active_call.id, access_hash=active_call.access_hash)
                        current_call_id = active_call.id
                        active_ssrc = random.randint(100000, 999999999)
                        client_ufrag = f"ufrag{active_ssrc}"
                        client_pwd = f"pwd{active_ssrc}12345678"

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
                                "ufrag": client_ufrag,
                                "pwd": client_pwd
                            },
                            "ssrc": active_ssrc
                        }

                        res = await client(JoinGroupCallRequest(
                            call=input_call,
                            join_as=my_input_peer,
                            muted=True,
                            video_stopped=True,
                            params=DataJSON(data=json.dumps(webrtc_json))
                        ))

                        # Parse WebRTC Gateway IP & credentials
                        server_ufrag = None
                        server_pwd = None
                        udp_target = None

                        for u in res.updates:
                            if hasattr(u, "params"):
                                s_params = json.loads(u.params.data)
                                s_trans = s_params.get("transport", {})
                                server_ufrag = s_trans.get("ufrag")
                                server_pwd = s_trans.get("pwd")
                                for c in s_trans.get("candidates", []):
                                    if c.get("protocol") == "udp" and "." in c.get("ip", ""):
                                        udp_target = (c["ip"], int(c["port"]))
                                        break
                                break

                        if udp_socket:
                            try:
                                udp_socket.close()
                            except Exception:
                                pass
                            udp_socket = None

                        if udp_target and server_ufrag and server_pwd:
                            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                            udp_socket.setblocking(False)
                            print(f"[{time.strftime('%H:%M:%S')}] SUCCESS: Joined live! WebRTC Gateway at {udp_target[0]}:{udp_target[1]}. Staying connected without rejoining.", flush=True)
                        else:
                            print(f"[{time.strftime('%H:%M:%S')}] SUCCESS: Joined live stream! Maintaining MTProto heartbeat session.", flush=True)

                        is_in_live = True
                        last_full_check = time.time()

                except RPCError as ex:
                    print(f"[{time.strftime('%H:%M:%S')}] Monitoring notice: {ex}", flush=True)
                except Exception as ex:
                    print(f"[{time.strftime('%H:%M:%S')}] Monitoring notice: {ex}", flush=True)

                await asyncio.sleep(5)

            else:
                # STATE 2: ACTIVE IN LIVE STREAM
                # Continuous Heartbeat & STUN Maintenance (STAY IN STREAM, NEVER REJOIN)
                stream_ended = False

                # 1. Send STUN Binding Keep-Alive every ~3s if gateway endpoint available
                if udp_socket and udp_target and server_ufrag and server_pwd and client_ufrag:
                    try:
                        stun_pkt = build_stun_binding_request(server_ufrag, client_ufrag, server_pwd)
                        udp_socket.sendto(stun_pkt, udp_target)
                        try:
                            udp_socket.recvfrom(2048)
                        except BlockingIOError:
                            pass
                    except Exception:
                        pass

                # 2. Send MTProto CheckGroupCallRequest every 3.5 seconds (official recommendation is 4s)
                try:
                    await client(CheckGroupCallRequest(call=input_call, sources=[active_ssrc]))
                except RPCError as rpc_err:
                    err_str = str(rpc_err).upper()
                    if any(w in err_str for w in ("DISCARDED", "INVALID", "CLOSED")):
                        print(f"[{time.strftime('%H:%M:%S')}] Live stream closed by host ({rpc_err}). Leaving stream.", flush=True)
                        stream_ended = True
                    elif any(w in err_str for w in ("FORBIDDEN", "JOIN_MISSING")):
                        print(f"[{time.strftime('%H:%M:%S')}] Live session expired on server. Resetting...", flush=True)
                        stream_ended = True
                except Exception:
                    pass

                # 3. Periodically check full channel state every 30s as a background check (NOT every 2.5s)
                if not stream_ended and (time.time() - last_full_check >= 30):
                    last_full_check = time.time()
                    try:
                        fc = await client(GetFullChannelRequest(channel))
                        call_obj = getattr(fc.full_chat, 'call', None)
                        if not isinstance(call_obj, GroupCall) or call_obj.id != current_call_id:
                            print(f"[{time.strftime('%H:%M:%S')}] Live stream ended or changed. Returning to monitoring.", flush=True)
                            stream_ended = True
                    except Exception:
                        pass

                if stream_ended:
                    if udp_socket:
                        try:
                            udp_socket.close()
                        except Exception:
                            pass
                        udp_socket = None
                    is_in_live = False
                    current_call_id = None
                    input_call = None
                    active_ssrc = None
                    continue

                await asyncio.sleep(3.0)

        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] Service error: {e}", flush=True)
            await asyncio.sleep(3.0)

if __name__ == "__main__":
    try:
        asyncio.run(live_stream_listener_service())
    except KeyboardInterrupt:
        print("Listener Service stopped by user.", flush=True)
