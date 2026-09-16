import asyncio
import hashlib
import hmac
import json
import os
import random
import socket
import struct
import zlib
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.phone import JoinGroupCallRequest
from telethon.tl.types import DataJSON, InputGroupCall

API_ID = 27634392
API_HASH = "c29325ca5de227dc611e54d355f76896"
SESSION_KEY = "1BVtsOGwBuz8vHuPpNuD-zFio1ZhVeIl94gLKDOycaPwrM6mZLyrY8APMQGTSMjMmWw7nU1h8XEyLMybbcrfbhv1kDzvLyiiTu_dqCapqgtwSCD_p6pM0FKWD9Fdg9ZAkgNac0iN_DKa10ECnXSYpzpSOFdWePvDtsy1vGQzFRxT5xbJBF92Wja7w1sMRT8yflFLWWQOSYsMYVAn83ssCPAVGFyEklL5oNgjaxoMMvH7qxB_piEE8rvMws8CFbX2a6zKtF-s_-Tk6S7lsdoDOVuQOItHpclxOpoS36ZAVpH4xb64r5Hgfj5BUjnyMKspKRJ8K8SRY5Cu45Bu09F53nHGtvmi8tSY="
CHANNEL_ID = -1003962785452

def build_stun_binding_request(server_ufrag: str, client_ufrag: str, server_pwd: str) -> bytes:
    """Constructs a standard RFC 5389 / ICE STUN Binding Request packet."""
    magic_cookie = b"\x21\x12\xa4\x42"
    trans_id = os.urandom(12)
    
    # 1. USERNAME attribute (0x0006): server_ufrag:client_ufrag
    username_str = f"{server_ufrag}:{client_ufrag}".encode('utf-8')
    pad_len = (4 - (len(username_str) % 4)) % 4
    username_attr = struct.pack("!HH", 0x0006, len(username_str)) + username_str + (b"\x00" * pad_len)
    
    # 2. PRIORITY attribute (0x0024): ICE priority
    priority_val = 1845494271 # Type host priority
    priority_attr = struct.pack("!HHI", 0x0024, 4, priority_val)
    
    # 3. ICE-CONTROLLING (0x802a)
    tie_breaker = os.urandom(8)
    controlling_attr = struct.pack("!HH", 0x802a, 8) + tie_breaker
    
    attrs = username_attr + priority_attr + controlling_attr
    
    # Header before HMAC (add 24 bytes for MESSAGE-INTEGRITY attribute)
    msg_len_for_hmac = len(attrs) + 24
    header_for_hmac = struct.pack("!HH", 0x0001, msg_len_for_hmac) + magic_cookie + trans_id
    
    # 4. MESSAGE-INTEGRITY attribute (0x0008)
    key = server_pwd.encode('utf-8')
    hmac_val = hmac.new(key, header_for_hmac + attrs, hashlib.sha1).digest()
    integrity_attr = struct.pack("!HH", 0x0008, 20) + hmac_val
    
    all_attrs = attrs + integrity_attr
    
    # 5. FINGERPRINT attribute (0x8028)
    msg_len_final = len(all_attrs) + 8
    final_header = struct.pack("!HH", 0x0001, msg_len_final) + magic_cookie + trans_id
    
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

    print("Joined Group Call via MTProto!")

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

    print(f"Server ufrag: {server_ufrag}, pwd: {server_pwd}")
    print(f"Candidates found: {len(candidates)}")

    udp_target = None
    for c in candidates:
        if c.get("protocol") == "udp" and "." in c.get("ip", ""):
            udp_target = (c["ip"], int(c["port"]))
            break

    if not udp_target:
        print("No IPv4 UDP candidate found")
        return

    print(f"Targeting Telegram WebRTC Gateway: {udp_target}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)

    stun_pkt = build_stun_binding_request(server_ufrag, client_ufrag, server_pwd)
    print(f"Sending STUN Binding Request ({len(stun_pkt)} bytes)...")
    sock.sendto(stun_pkt, udp_target)

    # Listen for STUN Binding Response
    for _ in range(20):
        await asyncio.sleep(0.2)
        try:
            data, addr = sock.recvfrom(2048)
            msg_type = struct.unpack("!H", data[:2])[0]
            print(f"Received UDP response from {addr}! Type: 0x{msg_type:04x}, Size: {len(data)} bytes")
            if msg_type == 0x0101:
                print("🎉 SUCCESS! Received STUN Binding Response (Success) from Telegram WebRTC Gateway!")
                break
        except BlockingIOError:
            sock.sendto(stun_pkt, udp_target)

    sock.close()
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
