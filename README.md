# Rally Controls Live Times

Web server for the Rally Control Timer app. Tabs:

1. **LIVE TIMES** – times from the marshal app, split by TC  
2. **PENALTY LIST** – manual + automatic early/late penalties  
3. **ITINERARY** – rally time program (TC sequence + target minutes)

## Itinerary & penalties

1. In **ITINERARY**, add controls in order.
2. For each control choose **TC** or **SS**, then the **number** (e.g. TC + `01` → `TC01`).
3. Set **target minutes from previous** (not for the first/start control).
4. Set **Check penalties?**  
   - **Yes** — early/late auto penalties apply at this control  
   - **No** — no auto penalty for this control  
5. Labels must match Live Times names. Click **Recalculate penalties** anytime.

Rules:

- **Late:** 10 seconds penalty per full minute late  
- **Early:** 1 minute penalty per full minute early  
- Less than 1 full minute early/late = on time (no auto penalty)

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
