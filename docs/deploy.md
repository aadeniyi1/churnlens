# Deploying the dashboard (free)

This puts the dashboard on the internet with a link you can share. It takes about 20 minutes the first time
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

## Things to know about the free plans

- **Streamlit apps sleep** after several days without visitors. The first visitor sees a "wake up" button,
  which takes about 30 seconds. Open your app before an interview.
- **Free Supabase projects pause** after about a week with no activity. Phase 6 adds a nightly GitHub Action
  that republishes the data, which also keeps the project awake. Until then, if it pauses, click **Restore**
  in Supabase.
- Free-plan limits change over time, so check the Supabase and Streamlit pricing pages if anything looks off.

## Troubleshooting

| Problem | Fix |
|---|---|
| `SUPABASE_DB_URL is not set` | `.env` is missing, or the line has a typo. It must be in the project folder, next to `run.py`. |
| `password authentication failed` | Wrong password, or `[YOUR-PASSWORD]` is still in the string. Reset the password in Supabase → Project settings → Database. |
| `failed to resolve host '...@aws-...'` | Your password contains `@`. Write it as `%40` in the connection string (see Step 2). |
| `could not translate host name` / timeout | You used the Direct connection string. Use **Session pooler**. |
| Dashboard says `No warehouse found` on Streamlit Cloud | The `SUPABASE_DB_URL` secret is missing. Add it in the app's **Settings → Secrets**, then reboot the app. |
| Dashboard works but shows old numbers | Data is cached for an hour. Use **⋮ → Clear cache** in the app, or wait. |
