# Telegram 4-Account Live Voice Auto-Join & Web Streamer (Render Ready)

An automated 24/7 service that connects to Telegram using **Telethon** and **PyTgCalls** across **4 accounts simultaneously**, continuously monitors a target channel with an **internal self-healing loop**, automatically joins live voice chats / group calls from all 4 accounts with **randomized 90 to 180 second delays**, and restreams audio to the web in real-time.

---

## ⚡ Internal Multi-Account Architecture (24/7 Always Active)
- **Natural Randomized Join (90s to 180s delay)**: When a voice chat / live stream starts in the channel, each of the 4 accounts independently waits for a randomized delay between 90 and 180 seconds before joining to look natural and organic.
- **Audio Broadcaster**: Account 1 acts as the master audio relay ingesting audio to the web MP3 stream.
- **Internal Monitor Loop**: Runs continuously every 5 seconds. Whenever a live broadcast starts in the channel, it immediately detects it and schedules joins for all accounts.
- **Connection Self-Healing**: Automatically reconnects if Telegram disconnects or any account drops.
- **Render Keep-Alive Self-Ping**: Periodically pings `/health` using `RENDER_EXTERNAL_URL` every 8 minutes to prevent Render from idling into sleep mode.

---

## 👥 Configured Accounts Pool
1. **Account 1 (Master / Recorder)**: Sakib (`ID: 8313350444`)
2. **Account 2 (Relay Participant)**: Mahin (`ID: 8958542619`)
3. **Account 3 (Relay Participant)**: Rana (`ID: 8679731255`)
4. **Account 4 (Relay Participant)**: Sevou (`ID: 8857778880`)

---

## ⚙️ Configuration & Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SOURCE_CHANNEL_ID` | `-1003962785452` | Target Telegram channel ID |
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
   git commit -m "Update delay to 90s-180s for 4 accounts"
   git push origin main
   ```
2. In Render dashboard, the Docker web service will auto-deploy.
3. Environment variables can optionally override any account credentials (`SESSION_1`, `SESSION_2`, `SESSION_3`, `SESSION_4`, `MIN_JOIN_DELAY_SECONDS`, `MAX_JOIN_DELAY_SECONDS`).

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
