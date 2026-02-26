# Create new GitHub repo and deploy on Railway

## Step 1: Create a new repo on GitHub

1. Go to https://github.com/new
2. **Repository name:** e.g. `rally-controls-live-times` (or any name you like)
3. **Public**
4. Do **not** check "Add a README" or .gitignore – leave the repo **empty**
5. Click **Create repository**

## Step 2: Push this folder to the new repo

Open a terminal in **this folder** (`website_new_repo`) and run:

```bash
cd C:\Users\chriskar\Downloads\Cursor\website_new_repo

git init
git add .
git commit -m "Rally Controls Live Times - website only"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_NEW_REPO_NAME.git
git push -u origin main
```

Replace:
- **YOUR_USERNAME** with your GitHub username (e.g. `christoforoskaraolis`)
- **YOUR_NEW_REPO_NAME** with the repo you created (e.g. `rally-controls-live-times`)

Example:
```bash
git remote add origin https://github.com/christoforoskaraolis/rally-controls-live-times.git
git push -u origin main
```

## Step 3: Deploy on Railway

1. Go to https://railway.app → **New Project**
2. **Deploy from GitHub repo** → choose your **new** repo (e.g. `rally-controls-live-times`)
3. Railway will build from the Dockerfile (no Root Directory needed).
4. When it’s deployed, open **Settings** → **Networking** → **Generate Domain** to get your URL.
5. In the Rally Control Timer app: **Settings** → paste that URL as the Sync server URL.

Done. This repo has only the website – no Flutter, no monorepo – so Railway should build and run without issues.
