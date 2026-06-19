# Deploy The Car Deal CRM On Render

This CRM deploys to Render as a Next.js Node web service. Render gives the app a
public `*.onrender.com` URL after the service is created.

## What Render Will Host

- The CRM website: Home, Dashboard, Admin, Leads, valuation input, and AI report UI.
- The Prisma SQLite schema, created automatically at startup.
- OpenAI-powered evaluation, if `OPENAI_API_KEY` is configured.

The local Python scraper, local n8n instance, and local `dev.db` are not uploaded
automatically. The first Render deploy starts with an empty database unless you
manually migrate data later.

## Important Persistence Note

Render Free web services have an ephemeral filesystem. That means SQLite data can
disappear after restarts or redeploys.

The included `render.yaml` writes the database to:

```text
/var/data/render.db
```

For a quick demo, the Free plan is fine. For a real CRM you care about, upgrade
the service to Starter or above and attach a persistent disk at `/var/data`.

## Step 1: Push This Workspace To GitHub

Render deploys from a Git repository. From the workspace root:

```powershell
git status
git add render.yaml crm/package.json crm/package-lock.json crm/prisma/schema.prisma crm/src crm/RENDER_DEPLOYMENT.md
git commit -m "Prepare CRM for Render deployment"
```

Create a new GitHub repository, then connect this local repo:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git push -u origin master
```

If `git remote add origin` says the remote already exists, run:

```powershell
git remote set-url origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git push -u origin master
```

## Step 2: Create The Render Service

1. Go to [Render](https://dashboard.render.com/).
2. Click `New`.
3. Choose `Blueprint`.
4. Connect your GitHub account if Render asks.
5. Select the repository you just pushed.
6. Render should detect `render.yaml`.
7. Create/sync the Blueprint.

The blueprint uses:

- Root directory: `crm`
- Build command: `npm ci && npm run prisma:generate && npm run build`
- Start command: `npm run start:render`
- Health check path: `/`
- Public URL: `https://car-deal-crm.onrender.com` or similar

## Step 3: Add Environment Variables

Render will ask for `OPENAI_API_KEY` because the blueprint marks it as secret.
Paste your key into Render only, not into GitHub.

Configured defaults:

```text
NODE_VERSION=24
DATABASE_URL=file:/var/data/render.db
OPENAI_MODEL=gpt-4o-mini
OPENAI_RESEARCH_MODEL=gpt-4o-mini
NEXT_TELEMETRY_DISABLED=1
```

## Step 4: Make Data Persistent

For a real CRM, do this after the first deploy:

1. Open the Render service.
2. Upgrade from `Free` to `Starter` or above.
3. Go to the service `Disks` page.
4. Add a disk:
   - Mount path: `/var/data`
   - Size: `1 GB`
5. Redeploy the service.

The app already points SQLite at `/var/data/render.db`, so the database will
survive redeploys once the disk is attached.

## Step 5: Verify

After deploy, open the Render URL and check:

- `/` loads the Admin/Dashboard homepage.
- `/dashboard` loads without a server error.
- `/admin` lets you add a test car.
- Manual valuation save works.
- AI evaluation either works or shows a clear OpenAI key/quota error.

## Current Limitation

The hosted CRM will not receive new Facebook listings until the ingestion path is
moved from local n8n into a hosted API/webhook flow. Treat this first deployment
as publishing the CRM interface; live cloud ingestion can be added next.
