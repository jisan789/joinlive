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
from telethon.tl.functions.phone import JoinGroupCallRequest, CheckGroupCallRequest
from telethon.tl.types import DataJSON, InputGroupCall

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
    magic_cookie = b"\x21\x12\xa4\x42"
    trans_id = os.urandom(12)
    
    username_str = f"{server_ufrag}:{client_ufrag}".encode('utf-8')
    pad_len = (4 - (len(username_str) % 4)) % 4
    username_attr = struct.pack("!HH", 0x0006, len(username_str)) + username_str + (b"\x00" * pad_len)
    
    priority_val = 1845494271
    priority_attr = struct.pack("!HHI", 0x0024, 4, priority_val)
    
    controlling_attr = struct.pack("!HH", 0x802a, 8) + os.urandom(8)
    attrs = username_attr + priority_attr + controlling_attr
    
    header_for_hmac = struct.pack("!HH", 0x0001, len(attrs) + 24) + magic_cookie + trans_id
    hmac_val = hmac.new(server_pwd.encode('utf-8'), header_for_hmac + attrs, hashlib.sha1).digest()
    integrity_attr = struct.pack("!HH", 0x0008, 20) + hmac_val
    
    all_attrs = attrs + integrity_attr
    final_header = struct.pack("!HH", 0x0001, len(all_attrs) + 8) + magic_cookie + trans_id
    crc = zlib.crc32(final_header + all_attrs) ^ 0x5354554e
    fingerprint_attr = struct.pack("!HHI", 0x8028, 4, crc & 0xffffffff)
    
    return final_header + all_attrs + fingerprint_attr

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
        print("Target channel not found")
        return

    full_chat = (await client(GetFullChannelRequest(target_dialog))).full_chat
    if not full_chat.call:
        print("No active call right now")
        return

    call = full_chat.call
    input_call = InputGroupCall(id=call.id, access_hash=call.access_hash)
    my_peer = await client.get_input_entity("me")

    client_ssrc = random.randint(100000, 999999999)
    client_ufrag = f"ufrag{client_ssrc}"
    client_pwd = f"pwd{client_ssrc}12345678"

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
        "ssrc": client_ssrc
    }

    res = await client(JoinGroupCallRequest(
        call=input_call,
        join_as=my_peer,
        muted=True,
        video_stopped=True,
        params=DataJSON(data=json.dumps(webrtc_json))
    ))

    print("[JOIN] Sent JoinGroupCallRequest successfully!")

    server_params = None
    for u in res.updates:
        if hasattr(u, "params"):
            server_params = json.loads(u.params.data)
            break

    if not server_params:
        print("Could not find server RTC params")
        return

    transport = server_params.get("transport", {})
    server_ufrag = transport.get("ufrag")
    server_pwd = transport.get("pwd")
    candidates = transport.get("candidates", [])

    udp_target = None
    for c in candidates:
        if c.get("protocol") == "udp" and "." in c.get("ip", ""):
            udp_target = (c["ip"], int(c["port"]))
            break

    print(f"Target WebRTC Gateway: {udp_target}")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)

    # Long-running loop for 120 seconds (2 full minutes)
    # Sends STUN check every 2 seconds + MTProto CheckGroupCall every 10 seconds
    start_time = time.time()
    last_mtproto_ping = 0

    print("Entering WebRTC Keep-Alive Loop...")
    while time.time() - start_time < 120:
        elapsed = int(time.time() - start_time)
        
        # Send STUN Binding Request
        stun_pkt = build_stun_binding_request(server_ufrag, client_ufrag, server_pwd)
        sock.sendto(stun_pkt, udp_target)
        
        # Check response
        try:
            data, addr = sock.recvfrom(2048)
            msg_type = struct.unpack("!H", data[:2])[0]
            if msg_type == 0x0101 and elapsed % 10 == 0:
                print(f"[{elapsed}s] STUN Heartbeat ACK from WebRTC Gateway (0x0101) - Stream connection alive!")
        except BlockingIOError:
            pass

        # Send MTProto CheckGroupCallRequest every 10 seconds
        if time.time() - last_mtproto_ping >= 10:
            try:
                await client(CheckGroupCallRequest(call=input_call, sources=[client_ssrc]))
            except Exception as e:
                print(f"MTProto ping notice: {e}")
            last_mtproto_ping = time.time()

        await asyncio.sleep(2)

    print("Completed 2 minutes continuous connection test successfully!")
    sock.close()
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
