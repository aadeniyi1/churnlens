# Deploying the dashboard and API (free)

**Part 1** (Steps 1 to 4) puts the dashboard on the internet. **Part 2** (Step 5) adds the API.

Part 1 puts the dashboard on the internet with a link you can share. It takes about 20 minutes the first time
and costs $0.

```
your laptop                     Supabase (free Postgres)          Streamlit Community Cloud (free)
uv run run.py all    ──publish──▶  dashboard tables      ◀──reads──  dashboard/Home.py
```

Your laptop does the heavy work (1.7M events). Only the small finished tables (about 150k rows) go to Supabase.

---

## Step 1: Create a Supabase project

1. Go to [supabase.com](https://supabase.com), sign in with GitHub, and click **New project**.
2. Name it `churnlens` and pick the region closest to you.
3. For the database password, click **Generate a password**, then copy it somewhere safe.
   A password with only letters and numbers avoids problems in the connection string.
4. Wait about 2 minutes for the project to finish setting up.

## Step 2: Get the connection string

1. In your project, click **Connect** at the top.
2. Choose the **Session pooler** connection string, not "Direct connection".
   The direct one needs IPv6, which many home networks and Streamlit Cloud don't have.
3. Copy it. It looks like this:
   `postgresql://postgres.abcdefghijk:[YOUR-PASSWORD]@aws-0-us-east-1.pooler.supabase.com:5432/postgres`
4. Replace `[YOUR-PASSWORD]` (including the brackets) with your real password.
   If your password contains symbols, they must be "URL-encoded": write `@` as `%40`, `#` as `%23`,
   `/` as `%2F`, `:` as `%3A`, `?` as `%3F`, and `%` as `%25`. Letters and numbers stay as they are.

## Step 3: Publish your data

In the project folder:

```bash
cp .env.example .env          # Windows PowerShell: copy .env.example .env
```

Open `.env` in VS Code and paste your connection string after `SUPABASE_DB_URL=`. Save, then run:

```bash
uv run run.py all             # if you haven't built everything yet
uv run run.py publish
```

You should see each table listed with its row count, then `published to Supabase`.
In Supabase, **Table Editor** now shows the tables.

`.env` is in `.gitignore`, so your password never goes to GitHub. Check with `git status`: `.env` must not appear.

**Optional check:** run the dashboard locally against Supabase instead of DuckDB:

```bash
CHURNLENS_USE_SUPABASE=1 uv run run.py dashboard
# Windows PowerShell: $env:CHURNLENS_USE_SUPABASE=1; uv run run.py dashboard
```

The caption at the bottom of each page should say `Source: Supabase Postgres`.

## Step 4: Deploy on Streamlit Community Cloud

1. Make sure your latest code is merged into `main` on GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with GitHub, and click **Create app** →
   **Deploy a public app from GitHub**.
3. Fill in:
   - Repository: `aadeniyi1/churnlens`
   - Branch: `main`
   - Main file path: `dashboard/Home.py`
   - App URL: something like `churnlens` (gives you `churnlens.streamlit.app` if it's free)
4. Click **Advanced settings**:
   - Python version: **3.12**
   - Secrets: paste this line, using your connection string:
     ```toml
     SUPABASE_DB_URL = "postgresql://postgres.abcdefghijk:YOURPASSWORD@aws-0-us-east-1.pooler.supabase.com:5432/postgres"
     ```
5. Click **Deploy**. The first start takes a few minutes, because it installs the packages in
   `dashboard/requirements.txt`.

Open the link and check that the page captions say `Source: Supabase Postgres`.

---

## Step 5 (Part 2): Deploy the API on Render

Do Part 1 first: the API reads the same Supabase tables as the dashboard.

```
Supabase (free Postgres)  ◀──reads──  Render (free web service): api/main.py  ◀──calls──  CRM, scripts, you
```

**First, try it on your laptop:**

```bash
uv run run.py api
```

Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs), click **Authorize**, type `dev-key`, click
**Authorize** again, then open any endpoint, click **Try it out** and **Execute**. Press Ctrl+C in the
terminal to stop the API.

**Then put it on Render:**

1. Make sure the API code is merged into `main` on GitHub.
2. Go to [render.com](https://render.com) and sign up with GitHub (no credit card needed for the free plan).
3. Click **New +** → **Blueprint**. Connect your GitHub account if asked, and pick `aadeniyi1/churnlens`.
4. Render reads `render.yaml` and shows one service, `churnlens-api`. It asks for one value:
   - `SUPABASE_DB_URL`: paste the same connection string you put in `.env` and in Streamlit's secrets.
5. Click **Apply**. The first build takes about 3 minutes. Watch the **Logs** tab until it says
   `Application startup complete`.
6. Your API's address is at the top of the service page, like `https://churnlens-api.onrender.com`.
   Open `<that address>/status`. You should see `"data_source":"Supabase Postgres"`.
7. Get your API key: in the service, open **Environment**, find `API_KEY`, and click the eye icon to show it.
   Render made it for you. Treat it like a password: only share it with people who should have access.
8. Open `<your address>/docs`, click **Authorize**, paste the key, and try an endpoint.

**If Render asks for a card for Blueprints**, use **New +** → **Web Service** instead, pick the repo, and fill in:

| Setting | Value |
|---|---|
| Language | Python 3 |
| Build command | `pip install -r api/requirements.txt` |
| Start command | `uvicorn api.main:app --host 0.0.0.0 --port $PORT` |
| Instance type | Free |
| Environment variables | `PYTHON_VERSION` = `3.12.8`, `CHURNLENS_DB` = `postgres`, `SUPABASE_DB_URL` = your connection string, `API_KEY` = a long random string you make up |

Health check path (under **Advanced**): `/status`.

**Try the example client against the live API** (it takes up to a minute the first time while Render wakes up):

```bash
# macOS
export CHURNLENS_API_URL=https://churnlens-api.onrender.com   # your address from step 6
export CHURNLENS_API_KEY=paste-your-key
uv run examples/client.py
```

```powershell
# Windows PowerShell
$env:CHURNLENS_API_URL="https://churnlens-api.onrender.com"
$env:CHURNLENS_API_KEY="paste-your-key"
uv run examples/client.py
```

How to connect other systems to the API: [api_integration.md](api_integration.md).

---

## Things to know about the free plans

- **Streamlit apps sleep** after several days without visitors. The first visitor sees a "wake up" button,
  which takes about 30 seconds. Open your app before an interview.
- **Free Supabase projects pause** after about a week with no activity. Phase 6 adds a nightly GitHub Action
  that republishes the data, which also keeps the project awake. Until then, if it pauses, click **Restore**
  in Supabase.
- **Render's free API sleeps** after 15 minutes without requests. The next request takes up to a minute.
  Open `/status` a minute before a demo.
- Free-plan limits change over time, so check the Supabase and Streamlit pricing pages if anything looks off.

## Troubleshooting

| Problem | Fix |
|---|---|
| `SUPABASE_DB_URL is not set` | `.env` is missing, or the line has a typo. It must be in the project folder, next to `run.py`. |
| `password authentication failed` | Wrong password, or `[YOUR-PASSWORD]` is still in the string. Reset the password in Supabase → Project settings → Database. |
| `failed to resolve host '...@aws-...'` | Your password contains `@`. Write it as `%40` in the connection string (see Step 2). |
| `could not translate host name` / timeout | You used the Direct connection string. Use **Session pooler**. |
| Dashboard says `No warehouse found` on Streamlit Cloud | The `SUPABASE_DB_URL` secret is missing. Add it in the app's **Settings → Secrets**, then reboot the app. |
| API returns `401` | Wrong key. On Render, copy `API_KEY` again from **Environment**. On your laptop, use `dev-key` unless you set `API_KEY` in `.env`. |
| API returns `503 Server is missing its API_KEY setting` | On Render, add the `API_KEY` environment variable, then **Manual Deploy** → **Deploy latest commit**. |
| Render logs say `SUPABASE_DB_URL is not set` | Add it under **Environment**, then redeploy. |
| API `/status` is slow or times out the first time | Normal on the free plan: it was asleep. Try again after a minute. |
| Dashboard works but shows old numbers | Data is cached for an hour. Use **⋮ → Clear cache** in the app, or wait. |
