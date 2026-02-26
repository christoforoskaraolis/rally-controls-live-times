# Rally Controls Live Times

Web server for the Rally Control Timer app. One page: live times by TC, reset button.

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
