# Deploying the web console

The web console (frontend and backend together) runs as a single Docker
container. It needs a host that keeps a server running and supports
WebSockets. **Vercel does not work**: its Python functions stop after each
request, can't hold WebSockets, and wipe the disk.

## Settings

| Variable | Default in Docker | What it does |
|---|---|---|
| `FSOC_PASSWORD` | not set | If set, every page asks for this password (any user name). **Set it for any public URL.** |
| `FSOC_PUBLIC` | `1` | Turns off writing, uploading, checking and deleting algorithm plugins, because a plugin is Python code that runs on the server. Browsing, running and comparing still work. |
| `FSOC_DATA_DIR` | `/data` | Where run logs, comparisons and uploaded videos are saved. Mount a persistent disk here to keep them across restarts. |
| `FSOC_MAX_VIDEO_MB` | `200` | Largest `.mp4` accepted for upload. |
| `PORT` | `8420` | Port the server listens on. Most hosts set this for you. |

## Test locally first

```
docker build -t fsoc-console .
docker run -p 8420:8420 -e FSOC_PASSWORD=choose-one fsoc-console
```

Open `http://127.0.0.1:8420/` and sign in with any user name and the password.

## Option A: Render (keeps the GitHub repo private)

1. Sign up at render.com with GitHub and allow access to the private `SIH26169` repo.
2. **New → Web Service**, pick `SIH26169`. Render detects the `Dockerfile`.
3. Instance type: **Starter** or higher. The free tier has too little CPU for
   real-time 30 FPS tracking and sleeps when idle.
4. Environment: add `FSOC_PASSWORD` (a password you share with the judges).
5. Optional: **Disks → Add disk**, mount path `/data`, 1 GB, to keep run history.
6. Deploy. The URL looks like `https://sih26169.onrender.com`.

## Option B: Hugging Face Spaces (free, 2 CPU cores)

1. Create a Space: SDK **Docker**, hardware **CPU basic** (free).
2. In the Space's `README.md` header, add `app_port: 8420`.
3. Push this repo's files to the Space's git repo.
4. **Settings → Variables and secrets**: add the secret `FSOC_PASSWORD`.
5. Open it at `https://<user>-<space>.hf.space` (the direct URL, not the
   huggingface.co page, so the password prompt works).

A **public** Space shows its source files to anyone. Make the Space private
if the code must stay private, or use Render.

## Limits of a hosted demo

- One shared engine: if two people press **Start run** at once, the second
  sees "a run is already in progress". This is fine for a judged demo.
- Real-time speed depends on the host's CPU. Heavy noise scenarios need
  about 2 cores to hold 30 FPS; the Live page shows the actual rate.
- To let people test their own algorithms, run the console on their own
  computer (`start.bat` or `python web/dashboard_server.py`), where plugin
  editing is on.
