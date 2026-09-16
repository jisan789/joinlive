# Telegram Live Stream Listener Web Service (Render Ready)

This repository contains a FastAPI Web Service that runs an automated **Telegram Live Stream Listener Service** powered by Telethon.

---

## Features
- **FastAPI Web Endpoint**: Responds to HTTP GET requests (`/` and `/health`) to allow external cron services (e.g. UptimeRobot, Cron-Job.org) to ping every minute and keep Render free instances awake 24/7.
- **Asynchronous Background Task**: Telethon background listener service runs in memory, continuously monitoring channel `-1003962785452`.
- **Randomized Join Delay**: Waits a randomized delay (30 seconds to 3 minutes) before joining any detected live stream.
- **Auto Reconnect & Heartbeat**: Keeps Telegram group call connection active via 10s pings, auto-cleans state when stream closes, and auto-joins future streams.

---

## File Structure
- `app.py`: FastAPI server + Telethon live listener service logic.
- `requirements.txt`: Python dependencies (`telethon`, `fastapi`, `uvicorn`).
- `Procfile`: Web start command for Render / Heroku.
- `render.yaml`: Render Blueprint configuration file.

---

## How to Deploy on Render

### Step 1: Push to GitHub
Initialize git and push code to your GitHub repository:
```bash
git init
git add .
git commit -m "Deploy Telegram Live Listener Web Service"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.name.git
git push -u origin main
```

### Step 2: Deploy to Render
1. Log into [Render.com](https://render.com).
2. Click **New +** -> **Web Service**.
3. Connect your GitHub repository.
4. Settings:
   - **Environment**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app:app --host 0.0.0.0 --port $PORT`
5. Environment Variables (configured automatically if using `render.yaml`, or add manually):
   - `API_ID`: `27634392`
   - `API_HASH`: `c29325ca5de227dc611e54d355f76896`
   - `SESSION_KEY`: `<YOUR_TELETHON_STRING_SESSION>`
   - `CHANNEL_ID`: `-1003962785452`
   - `MIN_DELAY_SECONDS`: `30`
   - `MAX_DELAY_SECONDS`: `180`

---

## Step 3: Keep Alive via 1-Minute Cron Ping
To prevent Render's free tier instance from sleeping:
1. Go to [cron-job.org](https://cron-job.org) or [UptimeRobot](https://uptimerobot.com).
2. Create a new HTTP monitor / cron job.
3. Set the URL to your Render Web Service domain: `https://YOUR-RENDER-APP.onrender.com/`
4. Set execution interval to **Every 1 minute**.
