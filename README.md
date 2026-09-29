# Telegram Live Voice Auto-Join & Web Streamer (Render Ready)

An automated 24/7 service that connects to Telegram using **Telethon** and **PyTgCalls**, continuously monitors a target channel with an **internal self-healing loop**, automatically joins live voice chats / group calls, and restreams audio to the web in real-time.

---

## ⚡ Internal Loop Architecture (24/7 Always Active)
- **Automatic Live Join Loop**: Runs continuously every 5 seconds. Whenever a live broadcast starts in the channel, it immediately detects it and joins as a listener.
- **Connection Self-Healing**: Automatically reconnects if Telegram disconnects or network drops.
- **Stream Dropout Watchdog**: If the stream connection drops while the live broadcast is still active, it automatically recovers and rejoins without manual intervention.
- **Render Keep-Alive Self-Ping**: Periodically pings `/health` using `RENDER_EXTERNAL_URL` every 8 minutes to prevent Render from idling into sleep mode.

---

## 🚀 How to Deploy on Render

### Method 1: Deploy with Git / GitHub (Recommended)
1. Push this folder to a GitHub repository:
   ```bash
   git init
   git add .
   git commit -m "JoinLive Telethon Relay Ready for Render"
   git branch -M main
   git remote add origin https://github.com/your-username/your-repo.git
   git push -u origin main
   ```
2. Go to **[dashboard.render.com](https://dashboard.render.com)**.
3. Click **New +** -> **Web Service**.
4. Connect your GitHub repository.
5. In **Environment**, select **Docker** (Render will automatically detect `Dockerfile`).
6. Under **Environment Variables**, you can optionally override:
   - `API_ID`: `27634392`
   - `API_HASH`: `c29325ca5de227dc611e54d355f76896`
   - `SESSION`: `<Your StringSession>`
   - `SOURCE_CHANNEL_ID`: `-1003962785452`
   - `RENDER_EXTERNAL_URL`: `https://your-service-name.onrender.com` (for self-ping keep-alive)
7. Click **Create Web Service**. Render will build the container with FFmpeg and Python, and run 24/7!

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
