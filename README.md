# Telegram Multi-Account Live Voice Auto-Join & Web Streamer (Render Ready)

An automated 24/7 service that connects to Telegram using **Telethon** and **PyTgCalls** across **dynamic multiple accounts**, continuously monitors a target channel with an **internal self-healing loop**, automatically joins live voice chats / group calls from all accounts with **randomized 90 to 180 second delays**, and restreams audio to the web in real-time.

---

## ⚡ Internal Multi-Account Architecture (24/7 Always Active)
- **Dynamic Account Pool**: No fixed account limit. The system automatically detects how many session keys you configure (1, 3, 5, 10, or more) and adjusts the account pool seamlessly. Adding a session adds an account; removing a session removes it.
- **Natural Randomized Join (90s to 180s delay)**: When a voice chat / live stream starts in the channel, each account independently waits for a randomized delay between 90 and 180 seconds before joining to look natural and organic.
- **Audio Broadcaster**: Account 1 acts as the master audio relay ingesting audio to the web MP3 stream.
- **Internal Monitor Loop**: Runs continuously every 5 seconds. Whenever a live broadcast starts in the channel, it immediately detects it and schedules joins for all accounts.
- **Connection Self-Healing**: Automatically reconnects if Telegram disconnects or any account drops.
- **Render Keep-Alive Self-Ping**: Periodically pings `/health` using `RENDER_EXTERNAL_URL` every 8 minutes to prevent Render from idling into sleep mode.

---

## 👥 How to Add / Remove Telegram Accounts Dynamically

You can configure any number of accounts using **any** of the following methods:

1. **Numbered Environment Variables**:
   Add `SESSION_1`, `SESSION_2`, `SESSION_3`, `SESSION_4`, ... (add or remove keys anytime).
   Optional display name overrides: `ACCOUNT_NAME_1`, `ACCOUNT_NAME_2`, etc.

2. **Bulk Environment Variable (`SESSIONS` or `SESSION_KEYS`)**:
   Add a single environment variable with sessions separated by commas or newlines:
   ```env
   SESSIONS="1BVtsOGwBu...
   1BVtsOGwBu...
   1BVtsOGwBu..."
   ```

3. **Single Session (`SESSION`)**:
   Provide `SESSION="1BVts..."` for single-account mode.

4. **Local `sessions.txt` file**:
   Place a `sessions.txt` file in the project folder with one session string per line.

> If no custom session variables are set, the app falls back to the default demo accounts pool.

---

## ⚙️ Configuration & Environment Variables

| Variable | Default | Description |
|---|---|---|
| `API_ID` | `27634392` | Standard Telegram API ID (shared across all accounts) |
| `API_HASH` | `c29325ca5de227dc611e54d355f76896` | Standard Telegram API Hash (shared across all accounts) |
| `SOURCE_CHANNEL_ID` | `-1002325443125` | Target Telegram channel ID |
| `SESSION_1`, `SESSION_2`, ... | Dynamic | Individual session keys per account |
| `SESSIONS` | `""` | Bulk multi-line or comma-separated session keys |
| `RECORDER_ACCOUNT_INDEX` | `1` | Which account acts as the master audio streamer (default: 1) |
| `MIN_JOIN_DELAY_SECONDS` | `90` | Minimum join delay (90 seconds / 1.5 min) |
| `MAX_JOIN_DELAY_SECONDS` | `180` | Maximum join delay (180 seconds / 3 min) |
| `PORT` | `8000` | Web dashboard & streaming port |
| `RENDER_EXTERNAL_URL` | `""` | Render service URL for keep-alive ping |

---

## 🚀 How to Deploy on Render

### Deploy with Git / GitHub:
1. Push to GitHub:
   ```bash
   git add .
   git commit -m "Dynamic multi-account handler with automatic session count detection"
   git push origin main
   ```
2. In Render dashboard, the Docker web service will auto-deploy.
3. In Render Environment settings, add `SESSION_1`, `SESSION_2`, etc. or a single `SESSIONS` variable with your session keys. The service will automatically detect the exact count and launch them accordingly.

---

## 💻 Local Execution

To run locally:
```bash
pip install -r requirements.txt
python app.py
```

- **Dashboard**: `http://localhost:8000`
- **Live MP3 Stream**: `http://localhost:8000/stream`
- **Health Check**: `http://localhost:8000/health`
- **API Status**: `http://localhost:8000/api/status`
