import asyncio
import collections
import logging
import os
import random
import sys
import time
from typing import List, Set

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
import uvicorn

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.types import InputGroupCall, UpdateGroupCall, GroupCallDiscarded

from pytgcalls import PyTgCalls
from pytgcalls.types import GroupCallConfig, RecordStream

# ==================== CONFIGURATION ====================
SOURCE_CHANNEL_ID = int(os.environ.get("SOURCE_CHANNEL_ID", -1002325443125))
WEB_HOST = os.environ.get("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.environ.get("PORT", 8000))
STREAM_TCP_PORT = int(os.environ.get("STREAM_TCP_PORT", 9988))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

# Random Delay Configuration (2 to 6 minutes default per account)
MIN_JOIN_DELAY_SECONDS = int(os.environ.get("MIN_JOIN_DELAY_SECONDS", 120))  # 2 minutes
MAX_JOIN_DELAY_SECONDS = int(os.environ.get("MAX_JOIN_DELAY_SECONDS", 360))  # 6 minutes

# 4 Configured Accounts (Account 1 is the Master Audio Streamer, 2-4 join alongside)
ACCOUNTS_CONFIG = [
    {
        "index": 1,
        "name": "Sakib",
        "api_id": int(os.environ.get("API_ID_1", os.environ.get("API_ID", 27634392))),
        "api_hash": os.environ.get("API_HASH_1", os.environ.get("API_HASH", "c29325ca5de227dc611e54d355f76896")),
        "session": os.environ.get(
            "SESSION_1",
            os.environ.get(
                "SESSION",
                "1BVtsOGwBu1N9KLlJxcAJFGzeqvLDS-V27RPGJ3w9Crn4P40Atgq6WKp8rRme_vMwel4Tsgt_0jEVg3ohNqmw78yl99EovYsg0P1"
                "eahpo7f1k0NsTJ7OmKOZldPfJg1JRXHIhZXVl9MsKSzRGaMq2htOkGTevFQ5Kahurj7heaGOhvN8F3qWNPSWjm0xPX9qwju2qXSE"
                "G6eSZNx-QNO2WIyGrf9KvhldqARB4GL6utk2e3usuIqF9QRLyLWgAlVyTGkQPaAnNp0QJfcmVh1fW1JpSt8nnWcOypVslfDyDY9O"
                "376fspGb_Jxve12GKYOBXq94g3KR0jvvmDPIjOeS_7_wb7BIpREw="
            )
        ),
        "is_recorder": True,
    },
    {
        "index": 2,
        "name": "Mahin",
        "api_id": int(os.environ.get("API_ID_2", 32821627)),
        "api_hash": os.environ.get("API_HASH_2", "45a260ea58881b721d909c74e40adcbd"),
        "session": os.environ.get(
            "SESSION_2",
            "1BVtsOGwBuz97tJLwZ_DRPNtA0UNw3aqGbF_1vATiPa2YVhIkF8lon9RqStdX3Q9wqt020r7wplavfqxGEiezhBH8tqkER2B1da591h-TepIsoTNjJPMVGhHAGf9rfnuehnfCO84u8jzun2pxJMN6yCQ1GkQ2LRwGK4Kj0X7rf9RdI2v-TnjQ-sK_ED-fekYQS4BHM80QOHHjyuRhj0SrTHGIzqoHTzV4yeYXXxMlYBpJtEjJoBcCnHnTBo27ARx_mM8Q6ucArrbHKeLd-lCCHirP1f7cxONqUUknZV-ZOIcx31cREKMgOhB4nEBBu-dkfUIolGT2Q9MppVN2LUbekzIrdGG3-pQ="
        ),
        "is_recorder": False,
    },
    {
        "index": 3,
        "name": "Rana",
        "api_id": int(os.environ.get("API_ID_3", 33591633)),
        "api_hash": os.environ.get("API_HASH_3", "a4e0dc8c681a8c6afe6124140b163768"),
        "session": os.environ.get(
            "SESSION_3",
            "1BVtsOGwBuwKDPeuKNy2P6M5z2RWXitz9okHn35hEMdbM4UJqrNjEiQRAIl3TJNpd_1rz6o6Lo_mGOCS04CAon-qmH8vsOedujp7vMxHamJ_er8HO8fKocsoH1RzQSEe4-uPsclEgMrGFgQo1TLbPVmzS8-MhZmMpN5JArFVwVwdQax9X0eDOT66j2R-xxJg705BnfQ3eyiIrGJdmPYn98zmr4uvLOVo8fXmhiYL_w9ElNRZQ2HIMoAcn7yMF21JWoWaf3eRdK_nZULbdDWZivVvmGtIydaOfKW-xX2cEMeu3AUJH6z34z_QFuIq79u0PXqjO16HKz9-tDdA8GxkiHZMGx3lwQWY="
        ),
        "is_recorder": False,
    },
    {
        "index": 4,
        "name": "Sevou",
        "api_id": int(os.environ.get("API_ID_4", 35126153)),
        "api_hash": os.environ.get("API_HASH_4", "a95d613cee72019ccb984d8686c3e592"),
        "session": os.environ.get(
            "SESSION_4",
            "1BVtsOGwBuxTz-8TYWd-9IZVuW-PsEXNzGdrDeb0DoMN0AL9yp_oYb0TRdLW3cqA1JGDradwF4VBpO3Rd_YxPIGuq_Nqg1gkH4bGtMkxhTCEGvNlc5aNXz2Hk5aCJPf2GgjSuKdMTiKFOwGEJt8yjXes0pI5wDSGxl1kjmBK-c9aHZSgFyhVvjoovLLxpzRKJIR4D5GRRQgK-hO1ayfJSIxc1TPqSe6gWnj_8JzRcXt8MvXmCp2umlDn82bfE8OkuwL-uYkO8VkANK6dGi5Udgb41qSKYLhRJ3H8avdlviEz8W-ZInbiJyAFHx8dosnaeaCfoHs6YJ5b7YrAPjI1Qxjpk4_n9S8U="
        ),
        "is_recorder": False,
    },
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("JoinLiveApp")


# ==================== ACCOUNT & APP STATE ====================
class AccountState:
    def __init__(self, index: int, name: str, api_id: int, api_hash: str, session: str, is_recorder: bool):
        self.index = index
        self.name = name
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_str = session
        self.is_recorder = is_recorder
        self.client: TelegramClient | None = None
        self.call_py: PyTgCalls | None = None
        self.user_id: int | None = None
        self.display_name: str = name
        self.is_connected: bool = False
        self.is_joined: bool = False
        self.scheduled_join_time: float | None = None
        self.join_task: asyncio.Task | None = None
        self.error_message: str | None = None


class AppState:
    def __init__(self):
        self.start_time = time.time()
        self.accounts: List[AccountState] = [
            AccountState(
                cfg["index"],
                cfg["name"],
                cfg["api_id"],
                cfg["api_hash"],
                cfg["session"],
                cfg["is_recorder"],
            )
            for cfg in ACCOUNTS_CONFIG
        ]
        self.channel_entity = None
        self.channel_title = "Unknown Channel"
        self.is_call_active = False
        self.current_call_id = None
        self.listeners_count = 0
        self.stream_subscribers: Set[asyncio.Queue] = set()
        self.header_buffer = collections.deque(maxlen=16)
        self.tcp_server = None
        self.recent_logs = collections.deque(maxlen=40)
        self.status_message = "Initializing 4 accounts..."
        self.join_lock = asyncio.Lock()
        self.last_stream_time = 0
        self.consecutive_errors = 0

    def add_log(self, text: str):
        entry = f"{time.strftime('%H:%M:%S')} - {text}"
        self.recent_logs.append(entry)
        logger.info(text)


state = AppState()


# ==================== STREAM BROADCAST SERVER ====================
async def handle_tcp_stream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    state.add_log("FFmpeg audio stream connected to TCP broadcaster.")
    state.last_stream_time = time.time()
    try:
        while True:
            data = await reader.read(4096)
            if not data:
                break
            state.last_stream_time = time.time()
            state.header_buffer.append(data)

            # Broadcast to all connected web clients
            dead_queues = []
            for q in list(state.stream_subscribers):
                try:
                    if q.qsize() > 50:
                        try:
                            q.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    q.put_nowait(data)
                except Exception:
                    dead_queues.append(q)
            for dq in dead_queues:
                state.stream_subscribers.discard(dq)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning(f"TCP stream error: {e}")
    finally:
        state.add_log("Audio stream connection closed.")
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def start_tcp_server():
    server = await asyncio.start_server(handle_tcp_stream, "127.0.0.1", STREAM_TCP_PORT)
    state.tcp_server = server
    state.add_log(f"Audio ingest TCP server ready on 127.0.0.1:{STREAM_TCP_PORT}")


# ==================== TELETHON & PYTGCALLS LOGIC ====================
async def check_channel_call():
    """Checks if the channel currently has an active voice chat."""
    primary_acc = next((acc for acc in state.accounts if acc.client and acc.client.is_connected()), None)
    if not primary_acc or not primary_acc.client:
        return False, None
    try:
        if not primary_acc.client.is_connected():
            state.add_log(f"Reconnecting primary client {primary_acc.display_name}...")
            await primary_acc.client.connect()
            state.add_log("Telegram reconnected successfully.")

        full_chat = await primary_acc.client(GetFullChannelRequest(SOURCE_CHANNEL_ID))
        call = getattr(full_chat.full_chat, "call", None)
        if call and isinstance(call, InputGroupCall):
            return True, call.id
    except Exception as e:
        logger.debug(f"Error checking channel call: {e}")
    return False, None


async def join_account_call(acc: AccountState):
    """Joins an individual account into the live voice chat immediately."""
    if not acc.call_py or not acc.is_connected:
        return False

    try:
        # Check if already in call
        active_calls = await acc.call_py._binding.calls()
        if SOURCE_CHANNEL_ID in active_calls:
            acc.is_joined = True
            acc.scheduled_join_time = None
            return True
    except Exception:
        pass

    try:
        if acc.is_recorder:
            stream_dest = f"tcp://127.0.0.1:{STREAM_TCP_PORT}"
            await acc.call_py.record(
                SOURCE_CHANNEL_ID,
                stream=stream_dest,
                config=GroupCallConfig(auto_start=False),
            )
        else:
            await acc.call_py.play(
                SOURCE_CHANNEL_ID,
                config=GroupCallConfig(auto_start=False),
            )

        try:
            await acc.call_py.mute(SOURCE_CHANNEL_ID)
        except Exception:
            pass

        acc.is_joined = True
        acc.scheduled_join_time = None
        role_label = "Master Streamer" if acc.is_recorder else "Participant"
        state.add_log(f"[{acc.display_name} | {role_label}] Joined voice chat successfully.")
        return True
    except Exception as e:
        acc.is_joined = False
        acc.scheduled_join_time = None
        state.add_log(f"[{acc.display_name}] Failed to join call: {e}")
        return False


async def schedule_account_join(acc: AccountState, delay_seconds: float):
    """Waits for the randomized 2-6 minute delay before joining."""
    acc.scheduled_join_time = time.time() + delay_seconds
    mins = int(delay_seconds // 60)
    secs = int(delay_seconds % 60)
    state.add_log(f"[{acc.display_name}] Live detected! Scheduled to join in {mins}m {secs}s ({int(delay_seconds)}s delay).")

    try:
        await asyncio.sleep(delay_seconds)
        is_active, _ = await check_channel_call()
        if not is_active:
            state.add_log(f"[{acc.display_name}] Live call ended before scheduled join time.")
            return False
        return await join_account_call(acc)
    except asyncio.CancelledError:
        state.add_log(f"[{acc.display_name}] Scheduled join cancelled.")
        return False
    finally:
        acc.scheduled_join_time = None
        acc.join_task = None


def trigger_delayed_joins():
    """Schedules independent 2-6 minute random delays for each unjoined account."""
    for acc in state.accounts:
        if not acc.is_joined and (acc.join_task is None or acc.join_task.done()):
            delay = random.uniform(MIN_JOIN_DELAY_SECONDS, MAX_JOIN_DELAY_SECONDS)
            acc.join_task = asyncio.create_task(schedule_account_join(acc, delay))


async def leave_account_call(acc: AccountState):
    """Leaves the voice chat and cancels any pending delayed join for an account."""
    if acc.join_task and not acc.join_task.done():
        acc.join_task.cancel()
        acc.join_task = None
    acc.scheduled_join_time = None

    if not acc.call_py:
        return
    try:
        await acc.call_py.leave_call(SOURCE_CHANNEL_ID)
    except Exception as e:
        logger.debug(f"[{acc.display_name}] Leave error: {e}")
    finally:
        acc.is_joined = False
        state.add_log(f"[{acc.display_name}] Left voice chat.")


async def join_live_call_immediate():
    """Forces immediate join for all 4 accounts (e.g. from manual trigger)."""
    async with state.join_lock:
        state.add_log("Triggering immediate join for all 4 accounts...")
        state.status_message = "Joining live stream (all accounts)..."

        # Cancel any scheduled delays
        for acc in state.accounts:
            if acc.join_task and not acc.join_task.done():
                acc.join_task.cancel()
                acc.join_task = None
            acc.scheduled_join_time = None

        await asyncio.gather(*[join_account_call(acc) for acc in state.accounts], return_exceptions=True)
        joined_count = sum(1 for acc in state.accounts if acc.is_joined)

        if joined_count > 0:
            state.status_message = f"Live - {joined_count}/4 accounts joined & streaming"
            state.add_log(f"Joined voice chat: {joined_count}/4 accounts active.")
            return True
        else:
            state.status_message = "Join failed for all accounts"
            return False


async def leave_live_call():
    """Leaves the voice chat for all 4 accounts and cancels all scheduled joins."""
    async with state.join_lock:
        state.add_log("Leaving live voice chat for all 4 accounts...")
        await asyncio.gather(*[leave_account_call(acc) for acc in state.accounts], return_exceptions=True)
        state.status_message = "Standby - Waiting for live stream"
        state.add_log("All accounts left call. Waiting for next live session.")


async def auto_join_monitor_loop():
    """Resilient internal loop that continuously monitors the channel, auto-schedules random 2-6 min delayed joins, and heals drops."""
    state.add_log(f"Internal 4-account auto-join loop engaged (Random Delay: {MIN_JOIN_DELAY_SECONDS//60}-{MAX_JOIN_DELAY_SECONDS//60} min).")
    while True:
        try:
            is_active, call_id = await check_channel_call()
            state.is_call_active = is_active
            state.current_call_id = call_id

            if is_active:
                for acc in state.accounts:
                    call_still_connected = False
                    if acc.is_joined and acc.call_py:
                        try:
                            active_calls = await acc.call_py._binding.calls()
                            call_still_connected = SOURCE_CHANNEL_ID in active_calls
                        except Exception:
                            call_still_connected = False

                    if not acc.is_joined or not call_still_connected:
                        if not call_still_connected and acc.is_joined:
                            state.add_log(f"[{acc.display_name}] Dropped connection detected.")
                            acc.is_joined = False

                        # Schedule random 2-6 minute delay if not already scheduled
                        if acc.join_task is None or acc.join_task.done():
                            delay = random.uniform(MIN_JOIN_DELAY_SECONDS, MAX_JOIN_DELAY_SECONDS)
                            acc.join_task = asyncio.create_task(schedule_account_join(acc, delay))

                joined_count = sum(1 for acc in state.accounts if acc.is_joined)
                pending_count = sum(1 for acc in state.accounts if acc.scheduled_join_time and not acc.is_joined)
                if joined_count > 0:
                    state.status_message = f"Live - {joined_count}/4 accounts joined ({pending_count} pending delay)"
                else:
                    state.status_message = f"Live detected - {pending_count}/4 accounts scheduled (2-6m delay)"
            else:
                any_joined = any(acc.is_joined for acc in state.accounts)
                any_pending = any(acc.scheduled_join_time for acc in state.accounts)
                if any_joined or any_pending:
                    state.add_log("Live voice chat has concluded in the channel.")
                    await leave_live_call()
                state.status_message = "Standby - Monitoring for live stream"

            state.consecutive_errors = 0
        except asyncio.CancelledError:
            break
        except Exception as e:
            state.consecutive_errors += 1
            logger.error(f"Internal monitor loop error (#{state.consecutive_errors}): {e}")
            if state.consecutive_errors > 5:
                await asyncio.sleep(10)
            else:
                await asyncio.sleep(3)
            continue

        await asyncio.sleep(5)


async def render_keep_alive_loop():
    """Continuous internal keep-alive loop to prevent Render from idling."""
    state.add_log("Render keep-alive loop active.")
    await asyncio.sleep(20)
    while True:
        try:
            await asyncio.sleep(480)
            target_url = RENDER_EXTERNAL_URL.rstrip("/") if RENDER_EXTERNAL_URL else f"http://127.0.0.1:{WEB_PORT}"
            ping_url = f"{target_url}/health"

            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(ping_url, timeout=15) as resp:
                    if resp.status == 200:
                        logger.info(f"Keep-alive self-ping success: {ping_url}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.debug(f"Keep-alive ping note: {e}")


# ==================== FASTAPI WEB APPLICATION ====================
app = FastAPI(title="Telegram 4-Account Live Voice Relay")


@app.on_event("startup")
async def startup_event():
    # 1. Start TCP audio streamer ingest
    await start_tcp_server()

    # 2. Start Telethon Clients and PyTgCalls engines for all 4 accounts
    for acc in state.accounts:
        try:
            state.add_log(f"Authenticating Account #{acc.index} ({acc.name})...")
            client = TelegramClient(StringSession(acc.session_str), acc.api_id, acc.api_hash)
            await client.start()
            acc.client = client

            me = await client.get_me()
            acc.user_id = me.id
            acc.display_name = f"{me.first_name} (ID: {me.id})"
            acc.is_connected = True
            state.add_log(f"Account #{acc.index} connected as: {acc.display_name}")

            state.add_log(f"Starting PyTgCalls engine for Account #{acc.index}...")
            call_py = PyTgCalls(client)
            await call_py.start()
            acc.call_py = call_py
            state.add_log(f"Account #{acc.index} PyTgCalls engine ready.")
        except Exception as e:
            acc.error_message = str(e)
            state.add_log(f"Account #{acc.index} initialization failed: {e}")

    # 3. Resolve target channel using first available connected client
    primary_client = next((acc.client for acc in state.accounts if acc.client and acc.client.is_connected()), None)
    if primary_client:
        try:
            entity = await primary_client.get_entity(SOURCE_CHANNEL_ID)
            state.channel_entity = entity
            state.channel_title = getattr(entity, "title", str(SOURCE_CHANNEL_ID))
            state.add_log(f"Target channel identified: '{state.channel_title}' ({SOURCE_CHANNEL_ID})")
        except Exception as e:
            state.channel_title = f"Channel {SOURCE_CHANNEL_ID}"
            state.add_log(f"Could not resolve entity title: {e}")

        # Listen to raw Telegram update events for instant detection
        @primary_client.on(events.Raw)
        async def raw_handler(update):
            if isinstance(update, UpdateGroupCall):
                state.add_log("Instant update: Group call state changed in channel.")
                asyncio.create_task(check_and_react())

    async def check_and_react():
        is_active, _ = await check_channel_call()
        if is_active:
            trigger_delayed_joins()
        else:
            await leave_live_call()

    # 4. Start the internal resilient loops
    asyncio.create_task(auto_join_monitor_loop())
    asyncio.create_task(render_keep_alive_loop())


@app.on_event("shutdown")
async def shutdown_event():
    state.add_log("Shutting down application...")
    await leave_live_call()
    for acc in state.accounts:
        if acc.call_py:
            try:
                await acc.call_py.stop()
            except Exception:
                pass
        if acc.client:
            try:
                await acc.client.disconnect()
            except Exception:
                pass
    if state.tcp_server:
        state.tcp_server.close()
        await state.tcp_server.wait_closed()


@app.get("/stream")
async def stream_audio(request: Request):
    """Real-time HTTP chunked MP3 audio stream for web browsers."""
    queue = asyncio.Queue(maxsize=100)
    state.stream_subscribers.add(queue)
    state.listeners_count += 1
    state.add_log(f"New web listener connected. Total listeners: {state.listeners_count}")

    # Preload initial header bytes to make browser playback start immediately
    for chunk in state.header_buffer:
        try:
            queue.put_nowait(chunk)
        except Exception:
            break

    async def audio_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=2.0)
                    yield data
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass
        finally:
            state.stream_subscribers.discard(queue)
            state.listeners_count = max(0, state.listeners_count - 1)
            state.add_log(f"Listener disconnected. Total listeners: {state.listeners_count}")

    return StreamingResponse(
        audio_generator(),
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.get("/health")
async def health_check():
    uptime = int(time.time() - state.start_time)
    connected_accounts = sum(1 for acc in state.accounts if acc.client and acc.client.is_connected())
    joined_accounts = sum(1 for acc in state.accounts if acc.is_joined)
    pending_accounts = sum(1 for acc in state.accounts if acc.scheduled_join_time and not acc.is_joined)
    return JSONResponse({
        "status": "healthy",
        "uptime_seconds": uptime,
        "accounts_connected": f"{connected_accounts}/4",
        "accounts_joined": f"{joined_accounts}/4",
        "accounts_pending_delay": f"{pending_accounts}/4",
        "is_call_active": state.is_call_active,
        "listeners": state.listeners_count,
        "channel_title": state.channel_title,
    })


@app.get("/api/status")
async def get_status():
    joined_accounts = sum(1 for acc in state.accounts if acc.is_joined)
    connected_accounts = sum(1 for acc in state.accounts if acc.client and acc.client.is_connected())
    pending_accounts = sum(1 for acc in state.accounts if acc.scheduled_join_time and not acc.is_joined)
    now = time.time()
    return JSONResponse({
        "channel_title": state.channel_title,
        "channel_id": SOURCE_CHANNEL_ID,
        "is_call_active": state.is_call_active,
        "is_joined": joined_accounts > 0,
        "joined_accounts_count": joined_accounts,
        "connected_accounts_count": connected_accounts,
        "pending_accounts_count": pending_accounts,
        "total_accounts": len(state.accounts),
        "accounts": [
            {
                "index": acc.index,
                "name": acc.name,
                "display_name": acc.display_name,
                "user_id": acc.user_id,
                "is_connected": acc.is_connected,
                "is_joined": acc.is_joined,
                "is_recorder": acc.is_recorder,
                "remaining_delay_seconds": max(0, int(acc.scheduled_join_time - now)) if (acc.scheduled_join_time and not acc.is_joined) else None,
                "error": acc.error_message,
            }
            for acc in state.accounts
        ],
        "current_call_id": str(state.current_call_id) if state.current_call_id else None,
        "listeners_count": state.listeners_count,
        "status_message": state.status_message,
        "streaming_active": (time.time() - state.last_stream_time) < 5 if state.last_stream_time else False,
        "logs": list(state.recent_logs),
    })


@app.post("/api/join")
async def manual_join():
    is_active, _ = await check_channel_call()
    if not is_active:
        return JSONResponse({"success": False, "message": "No active live stream in channel."})
    success = await join_live_call_immediate()
    return JSONResponse({"success": success, "message": "Joined call immediately from 4 accounts" if success else "Failed to join"})


@app.post("/api/leave")
async def manual_leave():
    await leave_live_call()
    return JSONResponse({"success": True, "message": "Left call and cancelled all pending delays"})


# ==================== NEO-BRUTALIST WEB DASHBOARD UI ====================
HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JOINLIVE // 4-ACCOUNT VOICE RELAY</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700;900&family=Space+Mono:ital,wght@0,400;0,700;1,400&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #FFFDF0;
            --main-black: #000000;
            --neo-yellow: #FFDE59;
            --neo-green: #00F59B;
            --neo-pink: #FF5E7E;
            --neo-purple: #9D7BFC;
            --neo-cyan: #38BDF8;
            --neo-orange: #FF9F43;
            --card-white: #FFFFFF;
            --shadow-hard: 5px 5px 0px #000000;
            --shadow-hard-lg: 8px 8px 0px #000000;
            --shadow-hard-sm: 3px 3px 0px #000000;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            min-height: 100vh;
            background-color: var(--bg-color);
            background-image: radial-gradient(var(--main-black) 1.2px, transparent 1.2px);
            background-size: 22px 22px;
            color: var(--main-black);
            font-family: 'Space Grotesk', -apple-system, sans-serif;
            padding: 0 0 40px 0;
            display: flex;
            flex-direction: column;
            align-items: center;
        }

        /* Top Marquee Banner */
        .marquee-banner {
            width: 100%;
            background: var(--neo-yellow);
            border-bottom: 3.5px solid var(--main-black);
            padding: 10px 0;
            overflow: hidden;
            white-space: nowrap;
            display: flex;
            position: sticky;
            top: 0;
            z-index: 100;
            box-shadow: 0 4px 0px rgba(0,0,0,0.15);
        }

        .marquee-content {
            display: inline-block;
            font-family: 'Space Mono', monospace;
            font-size: 0.92rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            animation: marquee 24s linear infinite;
        }

        @keyframes marquee {
            from { transform: translateX(0); }
            to { transform: translateX(-50%); }
        }

        /* Main Container */
        .container {
            width: 94%;
            max-width: 1080px;
            margin-top: 28px;
            display: flex;
            flex-direction: column;
            gap: 24px;
        }

        /* Neo-Brutalist Box Utility */
        .neo-box {
            background: var(--card-white);
            border: 3.5px solid var(--main-black);
            border-radius: 16px;
            box-shadow: var(--shadow-hard);
            transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1);
        }

        /* Header Bar */
        header.neo-box {
            background: var(--card-white);
            padding: 20px 28px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
        }

        .header-title-group {
            display: flex;
            align-items: center;
            gap: 18px;
        }

        .app-badge {
            background: var(--neo-yellow);
            border: 3px solid var(--main-black);
            width: 56px;
            height: 56px;
            border-radius: 14px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.8rem;
            box-shadow: var(--shadow-hard-sm);
            transform: rotate(-3deg);
        }

        .header-text h1 {
            font-size: 1.6rem;
            font-weight: 900;
            text-transform: uppercase;
            letter-spacing: -0.02em;
            line-height: 1.1;
        }

        .header-text p {
            font-family: 'Space Mono', monospace;
            font-size: 0.8rem;
            color: #4b5563;
            margin-top: 4px;
            font-weight: 600;
        }

        /* Status Badge Pill */
        .status-pill {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 20px;
            border: 3px solid var(--main-black);
            border-radius: 9999px;
            font-family: 'Space Mono', monospace;
            font-size: 0.9rem;
            font-weight: 700;
            box-shadow: var(--shadow-hard-sm);
            text-transform: uppercase;
        }

        .status-pill.live {
            background: var(--neo-green);
        }

        .status-pill.standby {
            background: var(--neo-yellow);
        }

        .status-dot {
            width: 13px;
            height: 13px;
            border-radius: 50%;
            background: var(--main-black);
            display: inline-block;
        }

        .status-pill.live .status-dot {
            background: #ffffff;
            border: 2px solid var(--main-black);
            animation: blink 1s infinite alternate;
        }

        @keyframes blink {
            from { transform: scale(0.9); opacity: 0.7; }
            to { transform: scale(1.2); opacity: 1; }
        }

        /* Accounts Pool Strip */
        .accounts-container {
            padding: 22px 24px;
            position: relative;
        }

        .accounts-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 14px;
            margin-top: 8px;
        }

        @media (max-width: 900px) {
            .accounts-grid {
                grid-template-columns: repeat(2, 1fr);
            }
        }

        @media (max-width: 540px) {
            .accounts-grid {
                grid-template-columns: 1fr;
            }
        }

        .account-card {
            background: #FAFAFA;
            border: 3px solid var(--main-black);
            border-radius: 12px;
            padding: 14px 16px;
            box-shadow: var(--shadow-hard-sm);
            display: flex;
            flex-direction: column;
            gap: 8px;
            position: relative;
            transition: all 0.2s ease;
        }

        .account-card.active-joined {
            background: #F0FDF4;
            border-color: #000;
            box-shadow: 4px 4px 0px #00F59B;
        }

        .account-card.active-pending {
            background: #FFFBEB;
            border-color: #000;
            box-shadow: 4px 4px 0px var(--neo-orange);
        }

        .acc-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .acc-role-badge {
            font-family: 'Space Mono', monospace;
            font-size: 0.68rem;
            font-weight: 800;
            padding: 2px 6px;
            border: 2px solid var(--main-black);
            border-radius: 6px;
            text-transform: uppercase;
        }

        .acc-role-master {
            background: var(--neo-pink);
            color: white;
        }

        .acc-role-relay {
            background: var(--neo-cyan);
            color: black;
        }

        .acc-name {
            font-size: 1.05rem;
            font-weight: 800;
        }

        .acc-id {
            font-family: 'Space Mono', monospace;
            font-size: 0.72rem;
            color: #6b7280;
            font-weight: 600;
        }

        .acc-status-tag {
            display: flex;
            align-items: center;
            gap: 6px;
            font-family: 'Space Mono', monospace;
            font-size: 0.72rem;
            font-weight: 700;
            padding: 4px 8px;
            border: 2px solid var(--main-black);
            border-radius: 6px;
            background: #E5E7EB;
            margin-top: 4px;
        }

        .acc-status-tag.joined {
            background: var(--neo-green);
        }

        .acc-status-tag.standby {
            background: var(--neo-yellow);
        }

        .acc-status-tag.delay-pill {
            background: var(--neo-orange);
            color: black;
            animation: pulse-delay 1.5s infinite alternate;
        }

        @keyframes pulse-delay {
            from { opacity: 0.85; }
            to { opacity: 1; }
        }

        /* Layout Grid */
        .layout-grid {
            display: grid;
            grid-template-columns: 1.35fr 1fr;
            gap: 24px;
        }

        @media (max-width: 860px) {
            .layout-grid {
                grid-template-columns: 1fr;
            }
        }

        /* Card Section Styling */
        .section-card {
            padding: 26px;
            position: relative;
        }

        .card-tag {
            position: absolute;
            top: -14px;
            left: 20px;
            background: var(--neo-cyan);
            border: 2.5px solid var(--main-black);
            padding: 3px 12px;
            font-size: 0.75rem;
            font-weight: 900;
            text-transform: uppercase;
            border-radius: 8px;
            box-shadow: 2px 2px 0px #000;
            font-family: 'Space Mono', monospace;
        }

        /* Channel Info Card */
        .channel-strip {
            background: #F3F4F6;
            border: 3px solid var(--main-black);
            border-radius: 12px;
            padding: 14px 18px;
            display: flex;
            align-items: center;
            gap: 16px;
            margin-top: 10px;
            margin-bottom: 22px;
            box-shadow: var(--shadow-hard-sm);
        }

        .channel-avatar {
            width: 48px;
            height: 48px;
            background: var(--neo-purple);
            border: 2.5px solid var(--main-black);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
            font-weight: 900;
            color: white;
            box-shadow: 2px 2px 0px #000;
        }

        .channel-details h2 {
            font-size: 1.2rem;
            font-weight: 800;
            line-height: 1.2;
        }

        .channel-details span {
            font-family: 'Space Mono', monospace;
            font-size: 0.78rem;
            color: #4b5563;
            font-weight: 700;
        }

        /* Brutalist Audio Visualizer Equalizer */
        .visualizer-board {
            background: #121212;
            border: 3px solid var(--main-black);
            border-radius: 14px;
            padding: 18px 24px;
            height: 100px;
            display: flex;
            align-items: flex-end;
            justify-content: space-between;
            gap: 8px;
            box-shadow: inset 0 2px 10px rgba(0,0,0,0.4);
            margin-bottom: 22px;
        }

        .eq-bar {
            flex: 1;
            background: var(--neo-yellow);
            border: 2px solid var(--main-black);
            border-radius: 4px 4px 0 0;
            min-height: 8px;
            height: 10px;
            transition: height 0.08s ease;
        }

        .eq-bar:nth-child(2n) { background: var(--neo-cyan); }
        .eq-bar:nth-child(3n) { background: var(--neo-green); }
        .eq-bar:nth-child(4n) { background: var(--neo-pink); }
        .eq-bar:nth-child(5n) { background: var(--neo-purple); }

        .visualizer-board.playing .eq-bar {
            animation: bounce-eq 0.9s infinite ease-in-out;
        }

        @keyframes bounce-eq {
            0%, 100% { height: 10px; }
            50% { height: 75px; }
        }

        .visualizer-board.playing .eq-bar:nth-child(1) { animation-delay: 0.05s; }
        .visualizer-board.playing .eq-bar:nth-child(2) { animation-delay: 0.25s; }
        .visualizer-board.playing .eq-bar:nth-child(3) { animation-delay: 0.12s; }
        .visualizer-board.playing .eq-bar:nth-child(4) { animation-delay: 0.40s; }
        .visualizer-board.playing .eq-bar:nth-child(5) { animation-delay: 0.18s; }
        .visualizer-board.playing .eq-bar:nth-child(6) { animation-delay: 0.32s; }
        .visualizer-board.playing .eq-bar:nth-child(7) { animation-delay: 0.08s; }
        .visualizer-board.playing .eq-bar:nth-child(8) { animation-delay: 0.45s; }
        .visualizer-board.playing .eq-bar:nth-child(9) { animation-delay: 0.22s; }
        .visualizer-board.playing .eq-bar:nth-child(10) { animation-delay: 0.35s; }
        .visualizer-board.playing .eq-bar:nth-child(11) { animation-delay: 0.15s; }
        .visualizer-board.playing .eq-bar:nth-child(12) { animation-delay: 0.28s; }

        /* Tactile Player Controls */
        .controls-row {
            display: flex;
            align-items: center;
            gap: 16px;
            margin-bottom: 22px;
        }

        .play-btn-brutal {
            flex: 1;
            height: 64px;
            background: var(--neo-yellow);
            border: 3.5px solid var(--main-black);
            border-radius: 14px;
            box-shadow: var(--shadow-hard);
            font-size: 1.15rem;
            font-weight: 900;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 12px;
            cursor: pointer;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            transition: all 0.1s ease;
        }

        .play-btn-brutal:hover {
            transform: translate(-2px, -2px);
            box-shadow: 7px 7px 0px #000;
        }

        .play-btn-brutal:active {
            transform: translate(3px, 3px);
            box-shadow: 2px 2px 0px #000;
        }

        .play-btn-brutal.playing {
            background: var(--neo-pink);
            color: #ffffff;
        }

        /* Volume Box */
        .vol-box {
            background: #F3F4F6;
            border: 3px solid var(--main-black);
            border-radius: 14px;
            padding: 0 16px;
            height: 64px;
            display: flex;
            align-items: center;
            gap: 12px;
            box-shadow: var(--shadow-hard-sm);
        }

        .vol-slider {
            -webkit-appearance: none;
            width: 110px;
            height: 10px;
            background: #e5e7eb;
            border: 2px solid var(--main-black);
            border-radius: 999px;
            outline: none;
        }

        .vol-slider::-webkit-slider-thumb {
            -webkit-appearance: none;
            appearance: none;
            width: 22px;
            height: 22px;
            background: var(--neo-cyan);
            border: 2.5px solid var(--main-black);
            border-radius: 6px;
            cursor: pointer;
            box-shadow: 2px 2px 0px #000;
        }

        .vol-pct {
            font-family: 'Space Mono', monospace;
            font-size: 0.82rem;
            font-weight: 700;
            min-width: 36px;
        }

        /* Action Buttons Grid */
        .action-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 14px;
        }

        .btn-action {
            padding: 14px;
            border: 3px solid var(--main-black);
            border-radius: 12px;
            font-size: 0.92rem;
            font-weight: 800;
            text-transform: uppercase;
            cursor: pointer;
            box-shadow: var(--shadow-hard-sm);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            transition: all 0.1s ease;
        }

        .btn-action:hover {
            transform: translate(-2px, -2px);
            box-shadow: 5px 5px 0px #000;
        }

        .btn-action:active {
            transform: translate(2px, 2px);
            box-shadow: 1px 1px 0px #000;
        }

        .btn-join {
            background: var(--neo-green);
        }

        .btn-leave {
            background: #FFFFFF;
        }

        /* Right Column: Telemetry & Metrics */
        .metric-cards-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 14px;
            margin-bottom: 22px;
            margin-top: 10px;
        }

        .stat-card {
            border: 3px solid var(--main-black);
            border-radius: 14px;
            padding: 16px;
            box-shadow: var(--shadow-hard-sm);
        }

        .stat-card.yellow { background: var(--neo-yellow); }
        .stat-card.purple { background: var(--neo-purple); color: white; }
        .stat-card.cyan { background: var(--neo-cyan); }
        .stat-card.pink { background: var(--neo-pink); color: white; }

        .stat-label {
            font-family: 'Space Mono', monospace;
            font-size: 0.72rem;
            text-transform: uppercase;
            font-weight: 700;
            letter-spacing: 0.05em;
            margin-bottom: 6px;
        }

        .stat-value {
            font-size: 1.5rem;
            font-weight: 900;
            line-height: 1;
        }

        /* Brutalist Dot-Matrix Terminal */
        .terminal-box {
            background: #10141b;
            border: 3px solid var(--main-black);
            border-radius: 14px;
            padding: 16px;
            box-shadow: var(--shadow-hard);
            height: 250px;
            overflow-y: auto;
            display: flex;
            flex-direction: column-reverse;
            gap: 6px;
        }

        .terminal-line {
            font-family: 'Space Mono', monospace;
            font-size: 0.78rem;
            color: #A3E635;
            line-height: 1.4;
            word-break: break-all;
            display: flex;
            align-items: flex-start;
            gap: 8px;
        }

        .terminal-line .t-arrow {
            color: var(--neo-pink);
            font-weight: 700;
        }

        /* Stream URL Share Banner */
        .share-banner {
            background: var(--card-white);
            border: 3px solid var(--main-black);
            border-radius: 14px;
            padding: 14px 18px;
            box-shadow: var(--shadow-hard-sm);
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            flex-wrap: wrap;
        }

        .share-text {
            font-family: 'Space Mono', monospace;
            font-size: 0.82rem;
            font-weight: 700;
        }

        .share-pill {
            background: var(--neo-yellow);
            border: 2px solid var(--main-black);
            padding: 4px 10px;
            border-radius: 6px;
            cursor: pointer;
            font-family: 'Space Mono', monospace;
            font-size: 0.78rem;
            font-weight: 700;
            box-shadow: 2px 2px 0px #000;
            transition: all 0.1s ease;
        }

        .share-pill:hover {
            transform: translate(-1px, -1px);
            box-shadow: 3px 3px 0px #000;
        }

        .share-pill:active {
            transform: translate(1px, 1px);
            box-shadow: 1px 1px 0px #000;
        }

        footer {
            margin-top: 10px;
            text-align: center;
            font-family: 'Space Mono', monospace;
            font-size: 0.8rem;
            font-weight: 700;
            color: #374151;
        }
    </style>
</head>
<body>
    <!-- Top Running Marquee -->
    <div class="marquee-banner">
        <div class="marquee-content">
            ⚡ 4-ACCOUNT TELEGRAM VOICE RELAY // RANDOM 2-6 MIN DELAY ACTIVE &nbsp;&bull;&nbsp; 🚀 PYTGCALLS v3.0 MULTI-CLIENT &nbsp;&bull;&nbsp; 📻 DIRECT WEB STREAM (PORT 8000) &nbsp;&bull;&nbsp; ⚡ NATURAL DELAYED VOICE JOIN &nbsp;&bull;&nbsp; ⚡ 4-ACCOUNT TELEGRAM VOICE RELAY // RANDOM 2-6 MIN DELAY ACTIVE &nbsp;&bull;&nbsp; 🚀 PYTGCALLS v3.0 MULTI-CLIENT &nbsp;&bull;&nbsp; 
        </div>
    </div>

    <div class="container">
        <!-- Top App Bar -->
        <header class="neo-box">
            <div class="header-title-group">
                <div class="app-badge">🎙️</div>
                <div class="header-text">
                    <h1>JOINLIVE // 4-ACCOUNT STUDIO</h1>
                    <p>TELETHON + PYTGCALLS VOICE RELAY (2-6 MIN RANDOM DELAY)</p>
                </div>
            </div>
            <div id="liveBadge" class="status-pill standby">
                <span class="status-dot"></span>
                <span id="liveBadgeText">WAITING FOR LIVE</span>
            </div>
        </header>

        <!-- 4-Accounts Status Pool -->
        <div class="neo-box accounts-container">
            <div class="card-tag" style="background: var(--neo-yellow);">ACCOUNT POOL // 04 ACCOUNTS (2-6M DELAY)</div>
            <div class="accounts-grid" id="accountsGrid">
                <!-- Injected via JS -->
            </div>
        </div>

        <!-- Main Body Grid -->
        <div class="layout-grid">
            <!-- Left Column: Audio Station -->
            <div class="neo-box section-card">
                <div class="card-tag">AUDIO STATION // 01</div>

                <!-- Channel Info Strip -->
                <div class="channel-strip">
                    <div class="channel-avatar" id="channelInitial">T</div>
                    <div class="channel-details">
                        <h2 id="channelName">Loading Channel...</h2>
                        <span id="channelId">ID: Loading...</span>
                    </div>
                </div>

                <!-- Neo-Brutalist Visualizer -->
                <div class="visualizer-board" id="visualizer">
                    <div class="eq-bar"></div>
                    <div class="eq-bar"></div>
                    <div class="eq-bar"></div>
                    <div class="eq-bar"></div>
                    <div class="eq-bar"></div>
                    <div class="eq-bar"></div>
                    <div class="eq-bar"></div>
                    <div class="eq-bar"></div>
                    <div class="eq-bar"></div>
                    <div class="eq-bar"></div>
                    <div class="eq-bar"></div>
                    <div class="eq-bar"></div>
                </div>

                <!-- Big Tactile Play & Volume Controls -->
                <div class="controls-row">
                    <button class="play-btn-brutal" id="playBtn" onclick="togglePlay()">
                        <span id="playIcon">▶</span>
                        <span id="playLabel">START LISTENING</span>
                    </button>
                    <div class="vol-box">
                        <span>🔊</span>
                        <input type="range" class="vol-slider" id="volSlider" min="0" max="1" step="0.05" value="0.9" oninput="setVolume(this.value)">
                        <span class="vol-pct" id="volPct">90%</span>
                    </div>
                </div>

                <!-- Manual Trigger Buttons -->
                <div class="action-grid">
                    <button class="btn-action btn-join" onclick="triggerManualJoin()">
                        ⚡ FORCE JOIN ALL NOW
                    </button>
                    <button class="btn-action btn-leave" onclick="triggerManualLeave()">
                        ✖ DISCONNECT ALL
                    </button>
                </div>
            </div>

            <!-- Right Column: Telemetry & Activity -->
            <div class="neo-box section-card">
                <div class="card-tag" style="background: var(--neo-pink); color: white;">TELEMETRY // 02</div>

                <!-- Metrics Grid -->
                <div class="metric-cards-grid">
                    <div class="stat-card purple">
                        <div class="stat-label">LISTENERS</div>
                        <div class="stat-value" id="metricListeners">0</div>
                    </div>
                    <div class="stat-card yellow">
                        <div class="stat-label">JOINED ACCOUNTS</div>
                        <div class="stat-value" id="metricJoined">0 / 4</div>
                    </div>
                    <div class="stat-card cyan">
                        <div class="stat-label">DELAY RANGE</div>
                        <div class="stat-value" style="font-size:1.15rem; margin-top:4px;">2 - 6 MIN</div>
                    </div>
                    <div class="stat-card pink">
                        <div class="stat-label">AUDIO INGEST</div>
                        <div class="stat-value" id="metricAudio" style="font-size:1.15rem; margin-top:4px;">IDLE</div>
                    </div>
                </div>

                <!-- Activity Log Terminal -->
                <div style="font-weight: 800; font-size: 0.82rem; text-transform: uppercase; margin-bottom: 8px; font-family: 'Space Mono', monospace;">
                    📟 LIVE CONSOLE LOGS
                </div>
                <div class="terminal-box" id="terminalLogs">
                    <div class="terminal-line"><span class="t-arrow">&gt;</span> Initializing logs...</div>
                </div>
            </div>
        </div>

        <!-- Stream Direct Link Share Strip -->
        <div class="share-banner">
            <div class="share-text">
                🔗 DIRECT LIVE STREAM URL: <code>http://localhost:8000/stream</code>
            </div>
            <button class="share-pill" onclick="copyStreamUrl()">
                📋 COPY STREAM LINK
            </button>
        </div>

        <footer>
            JOINLIVE STUDIO &bull; 4-ACCOUNT TELEGRAM LIVE RELAY &bull; TELETHON & PYTGCALLS
        </footer>
    </div>

    <!-- Hidden HTML5 Audio Element -->
    <audio id="audioElement" preload="none"></audio>

    <script>
        const audio = document.getElementById('audioElement');
        const playBtn = document.getElementById('playBtn');
        const playIcon = document.getElementById('playIcon');
        const playLabel = document.getElementById('playLabel');
        const visualizer = document.getElementById('visualizer');
        const volSlider = document.getElementById('volSlider');
        const volPct = document.getElementById('volPct');
        let isPlaying = false;

        function togglePlay() {
            if (!isPlaying) {
                audio.src = '/stream?t=' + Date.now();
                audio.play().then(() => {
                    isPlaying = true;
                    playBtn.classList.add('playing');
                    visualizer.classList.add('playing');
                    playIcon.textContent = '⏸';
                    playLabel.textContent = 'STOP LISTENING';
                }).catch(err => {
                    console.error('Playback error:', err);
                    alert('Connecting to live stream... If the live voice chat just started, please wait a moment.');
                });
            } else {
                audio.pause();
                audio.src = '';
                isPlaying = false;
                playBtn.classList.remove('playing');
                visualizer.classList.remove('playing');
                playIcon.textContent = '▶';
                playLabel.textContent = 'START LISTENING';
            }
        }

        function setVolume(val) {
            audio.volume = val;
            volPct.textContent = Math.round(val * 100) + '%';
        }

        function copyStreamUrl() {
            const url = window.location.origin + '/stream';
            navigator.clipboard.writeText(url).then(() => {
                alert('Stream URL copied to clipboard: ' + url);
            });
        }

        async function triggerManualJoin() {
            try {
                const res = await fetch('/api/join', { method: 'POST' });
                await res.json();
                fetchStatus();
            } catch (e) {
                console.error(e);
            }
        }

        async function triggerManualLeave() {
            try {
                const res = await fetch('/api/leave', { method: 'POST' });
                await res.json();
                fetchStatus();
            } catch (e) {
                console.error(e);
            }
        }

        async function fetchStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();

                // Channel Info
                document.getElementById('channelName').textContent = data.channel_title;
                document.getElementById('channelId').textContent = 'CHANNEL ID: ' + data.channel_id;
                document.getElementById('channelInitial').textContent = data.channel_title ? data.channel_title[0].toUpperCase() : 'T';

                // Status Badges
                const badge = document.getElementById('liveBadge');
                const badgeText = document.getElementById('liveBadgeText');
                if (data.is_joined) {
                    badge.className = 'status-pill live';
                    badgeText.textContent = `STREAMING (${data.joined_accounts_count}/4 ACCOUNTS)`;
                } else if (data.is_call_active) {
                    badge.className = 'status-pill standby';
                    badgeText.textContent = `LIVE ACTIVE (${data.pending_accounts_count} IN 2-6M DELAY)`;
                } else {
                    badge.className = 'status-pill standby';
                    badgeText.textContent = 'WAITING FOR LIVE';
                }

                // Metrics
                document.getElementById('metricListeners').textContent = data.listeners_count;
                document.getElementById('metricJoined').textContent = `${data.joined_accounts_count} / ${data.total_accounts}`;
                document.getElementById('metricAudio').textContent = data.streaming_active ? 'STREAMING' : (data.is_joined ? 'CONNECTED' : 'STANDBY');

                // Accounts Grid Rendering
                const accGrid = document.getElementById('accountsGrid');
                if (data.accounts && data.accounts.length) {
                    accGrid.innerHTML = data.accounts.map(acc => {
                        const isJoined = acc.is_joined;
                        const roleClass = acc.is_recorder ? 'acc-role-master' : 'acc-role-relay';
                        const roleText = acc.is_recorder ? 'MASTER / REC' : 'RELAY';
                        
                        let statusClass = '';
                        let statusText = '🔴 OFFLINE';
                        let cardClass = '';

                        if (isJoined) {
                            statusClass = 'joined';
                            statusText = '🟢 IN VOICE CHAT';
                            cardClass = 'active-joined';
                        } else if (acc.remaining_delay_seconds !== null && acc.remaining_delay_seconds > 0) {
                            const mins = Math.floor(acc.remaining_delay_seconds / 60);
                            const secs = acc.remaining_delay_seconds % 60;
                            statusClass = 'delay-pill';
                            statusText = `⏳ IN ${mins}m ${secs}s`;
                            cardClass = 'active-pending';
                        } else if (acc.is_connected) {
                            statusClass = 'standby';
                            statusText = '🟡 READY';
                        }

                        return `
                            <div class="account-card ${cardClass}">
                                <div class="acc-top">
                                    <span class="acc-role-badge ${roleClass}">${roleText}</span>
                                    <span style="font-size:0.75rem; font-weight:800; font-family:'Space Mono'">#0${acc.index}</span>
                                </div>
                                <div class="acc-name">${acc.name}</div>
                                <div class="acc-id">ID: ${acc.user_id || 'Connecting...'}</div>
                                <div class="acc-status-tag ${statusClass}">
                                    <span>${statusText}</span>
                                </div>
                            </div>
                        `;
                    }).join('');
                }

                // Terminal Logs
                if (data.logs && data.logs.length) {
                    const term = document.getElementById('terminalLogs');
                    term.innerHTML = data.logs.slice().reverse().map(l => 
                        `<div class="terminal-line"><span class="t-arrow">&gt;</span><span>${l}</span></div>`
                    ).join('');
                }
            } catch (e) {
                console.error('Status fetch error:', e);
            }
        }

        setInterval(fetchStatus, 2500);
        fetchStatus();
    </script>
</body>
</html>
"""


@app.get("/")
async def index():
    return HTMLResponse(content=HTML_PAGE)


# ==================== ENTRYPOINT ====================
if __name__ == "__main__":
    uvicorn.run(app, host=WEB_HOST, port=WEB_PORT, log_level="info")
