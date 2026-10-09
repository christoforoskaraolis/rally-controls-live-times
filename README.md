# Rally Controls Live Times

Web server for the Rally Control Timer app. Tabs:

1. **LIVE TIMES** – times from the marshal app, split by TC  
2. **PENALTY LIST** – add / edit / clear car penalties  
3. **ITINERARY** – event controls / stages list

## Deploy on Railway

1. Push this folder to a **new** GitHub repo (see below).
2. In Railway: **New Project** → **Deploy from GitHub** → select that repo.
3. Do **not** set a Root Directory – leave it empty.
4. Railway will detect the Dockerfile and deploy. You get a URL like `https://xxx.up.railway.app`.

Put that URL in the app: Settings → Sync server URL.

## Run locally

```bash
pip install -r requirements.txt
python server.py
```

Open http://localhost:8765
