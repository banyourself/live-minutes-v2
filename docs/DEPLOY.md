# Deploying Live Minutes

Three ways to run the server. All use the same Docker image.

## A. District self-hosting (recommended for school districts)

Data stays on district infrastructure, which simplifies FERPA and procurement review.

```bash
cp .env.production.example .env      # fill in SECRET_KEY, POSTGRES_PASSWORD, PUBLIC_URL, PLATFORM_ADMIN_EMAILS
docker compose up -d --build
```

This starts PostgreSQL, the web/API server on 127.0.0.1:8000, and one drafting worker.
Put it behind the district's HTTPS reverse proxy or load balancer, then make the first
administrator:

```bash
docker compose exec web python -m server.manage make-admin it-admin@yourdistrict.edu
```

That account must exist first (school SSO or an invite), or sign up with an address in
`PLATFORM_ADMIN_EMAILS` and confirm it from the emailed link.

Add workers when drafts queue up: `docker compose up -d --scale worker=3`.

### Without a public IP: Cloudflare Tunnel

This is how https://minutes.kevinle.tech runs. The machine opens no inbound ports.

```bash
cloudflared tunnel login
cloudflared tunnel create live-minutes
cloudflared tunnel route dns live-minutes minutes.yourdomain.edu
```

Put the credentials JSON and a `config.yml` (hostname to `http://web:8000`) in one folder, set
`TUNNEL_DIR` to it in `.env`, set `TRUSTED_PROXY_HOPS=1`, and start with
`docker compose --profile tunnel up -d --build`.

### Free cloud server: Oracle Cloud Always Free

An Always Free Ampere (ARM) VM runs the same Compose stack and tunnel, so nothing changes for users.

1. In Oracle Cloud, pick a home region with several availability domains (US West Phoenix, for example).
   You can't change it later, and free servers only exist there.
2. Create an instance: image **Canonical Ubuntu 24.04**, shape **VM.Standard.A1.Flex** with up to
   4 OCPUs and 24 GB memory, and your SSH public key. Leave the default security list, which only
   allows SSH. The tunnel needs no inbound ports.
3. Upload `deploy/oracle/setup.sh` as the instance's cloud-init script, or copy it to the VM and
   run `sh setup.sh`. It installs Docker, turns on automatic security updates with a 4 AM reboot,
   allows SSH keys only, and starts fail2ban. The VM needs a public IPv4 address (Networking, then
   the VNIC's IP addresses, then Ephemeral public IP); the script waits until it can reach the internet.
4. From the machine that runs Live Minutes today, run `deploy/oracle/move.sh ubuntu@VM_IP path/to/key`.
   It stops the local stack, copies the code, `.env`, tunnel credentials, database, and files to
   `/opt/live-minutes`, starts everything there, and checks `/api/ready`. The local copy stays
   stopped so only one tunnel serves the site.

To ship a new version, commit it and run `deploy/oracle/update.sh ubuntu@VM_IP path/to/key`. It
keeps `.env`, keeps the last version in `/opt/live-minutes/previous`, rebuilds, and checks
`/api/ready`. Nightly backups land in `/opt/live-minutes/backups`; also set an off-site backup
(Cloudflare R2 has a free tier) from the Console.

## B. Hosted on Render (one shared server for many districts)

1. Push the repo to GitHub, then in Render choose New → Blueprint and select it.
   `render.yaml` creates the database, the web service, and the worker.
2. Set `PUBLIC_URL`, `PLATFORM_ADMIN_EMAILS`, and copy the web service's generated
   `SECRET_KEY` to the worker (they must match).
3. **Configure S3-compatible storage** (`S3_BUCKET`, `AWS_ACCESS_KEY_ID`,
   `AWS_SECRET_ACCESS_KEY`, and `S3_ENDPOINT_URL` for providers like Cloudflare R2).
   Render services do not share disks, so the worker cannot read uploaded templates
   without it.
4. Add a custom domain and keep `SECURE_COOKIES=1`.

Any platform that runs containers (AWS ECS, Azure Container Apps, Google Cloud Run,
Fly.io, Kubernetes) works the same way: one web service, one or more workers running
`python -m server.worker`, a PostgreSQL database, and S3-compatible storage.

## Settings checklist

| Setting | Why |
|---|---|
| `SECRET_KEY` | Signs sessions and links. Changing it signs everyone out. |
| `ENCRYPTION_KEYS` | Encrypts stored AI keys and Zoom tokens. Back it up. To rotate, put the new key first and run `python -m server.manage rotate-keys`. |
| `PUBLIC_URL` | Must be https. Used for links and sign-in redirects, and it is the only host the server answers to (add more with `ALLOWED_HOSTS`). Cookies become Secure automatically. |
| `TRUSTED_PROXY_HOPS` | Number of proxies in front of the app (1 on Azure Container Apps and Render). Leave 0 if clients connect directly. |
| `MAIL_BACKEND=smtp`, `SMTP_*`, `MAIL_FROM` | Invites, address confirmation, and password resets. Works with Microsoft 365, Azure Communication Services, or a district relay. Without it, use `python -m server.manage reset-link`. |
| `PLATFORM_ADMIN_EMAILS` | Granted only after the address is confirmed. |
| `ALLOW_SIGNUP=0`, `ALLOW_DISTRICT_CREATION=0` | Accounts come only from invites or district email domains, and only administrators add districts. |
| `MICROSOFT_ALLOWED_TENANTS` | Entra tenant IDs allowed for Microsoft sign-in. District IT can also add their own tenant IDs in the IT console under School sign-in; with neither, Microsoft sign-in stays off. |
| `GOOGLE_ALLOWED_DOMAINS` | Limits Google sign-in to the district's Workspace domains. |
| `BACKUP_S3_HOSTS` | Extra S3-compatible storage hosts district IT may back up to, such as a district MinIO (`minio.district.edu`). Amazon S3, Cloudflare R2, Backblaze, Wasabi, DigitalOcean, Google Cloud, and Linode are allowed without it. |
| `PASSWORD_BREACH_CHECK`, `EMAIL_DNS_CHECK` | Reject breached passwords and email domains that cannot receive mail. On by default in production. |
| `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` | Optional Cloudflare Turnstile check on sign-up, sign-in, and password reset. In production the token's hostname must match `PUBLIC_URL` and its action must match the form (`signup`, `login`, `forgot`). |
| `GOOGLE_*`, `MICROSOFT_*` | School sign-in. Register `{PUBLIC_URL}/api/auth/sso/google/callback` and `/microsoft/callback`. |
| `ZOOM_APP_CLIENT_ID`, `ZOOM_APP_CLIENT_SECRET`, `ZOOM_APP_SECRET_TOKEN` | Optional Zoom app ([ZOOM-APP-SETUP.md](ZOOM-APP-SETUP.md)). Redirect: `{PUBLIC_URL}/api/zoom/callback`. Event endpoint: `{PUBLIC_URL}/api/zoom/events`, verified with the Secret Token. |
| Backups | Back up PostgreSQL and the file storage on the same schedule. See Backups below. |

## Backups

There are two kinds, for two jobs.

**Server backups (disaster recovery).** With Docker Compose, the `backup` service writes a PostgreSQL
dump (`db-YYYY-MM-DD.dump`) and a copy of the file storage (`files-YYYY-MM-DD.tar.gz`) once a day to
`BACKUP_DIR` (default `./backups` next to `docker-compose.yml`) and keeps `BACKUP_KEEP_DAYS` days
(default 14). Point `BACKUP_DIR` at a folder that is copied off the machine, such as a synced cloud
drive or a network share, and keep `.env` (especially `ENCRYPTION_KEYS` and `SECRET_KEY`) backed up
separately; without them, stored AI keys cannot be decrypted. On Azure, use the managed PostgreSQL
backups and Blob Storage soft delete instead.

To restore: stop `web` and `worker`, then

    docker compose exec -T db pg_restore -U liveminutes -d liveminutes --clean --if-exists < backups/db-YYYY-MM-DD.dump
    docker compose run --rm -v ./backups:/backups worker sh -c "cd /data && tar -xzf /backups/files-YYYY-MM-DD.tar.gz"

and start them again. Test a restore on a spare machine at least once a term.

**Offsite copies of the server backups (free, Cloudflare R2).** The worker uploads the newest
`db-*.dump` and `files-*.tar.gz` once each, encrypted to a public key (X25519 and AES-256-GCM), to
`live-minutes/` in an R2 bucket, and deletes copies older than `OFFSITE_KEEP_DAYS` (default 30). The
server only holds the public key, so neither Cloudflare nor anyone who takes the server can read the
copies. Setup, once:

1. On my own computer: `python deploy/oracle/offsite_keys.py ~/live-minutes-backup.key`. Keep that
   private key file in my password manager, never on the server.
2. In Cloudflare, create the bucket `live-minutes-backups` and an R2 API token with Object Read and
   Write on that bucket only.
3. On the server, run `sh /opt/live-minutes/app/deploy/oracle/set_offsite.sh`. It asks for the R2 endpoint
   (`https://<account id>.r2.cloudflarestorage.com`), the bucket, and the public key the key script printed
   when they are not in `.env` yet, then always for the token's Access Key ID and Secret Access Key without
   showing them. It saves them to `.env`, restarts the containers, and waits for the first upload.
   `sh deploy/oracle/set_offsite.sh status` shows the last upload or error later. Running it again
   replaces the token, for example after rotating it.

The worker checks hourly and records the last upload and any error under the platform setting
`offsite_backup` and in the activity log. To restore from an offsite copy, download the `.lmb` file and
run `python deploy/oracle/decrypt_backup.py ~/live-minutes-backup.key db-YYYY-MM-DD.dump.lmb db-YYYY-MM-DD.dump`,
then restore as above. At this size (well under 1 GB) it stays inside R2's free tier.

**Records copies for districts and colleges.** District IT and college IT can connect their own
S3-compatible storage (Amazon S3, Cloudflare R2, Backblaze B2, Wasabi, MinIO, campus storage) or Azure
Blob Storage in the IT console under Backups, choose which kinds of data go there, and pick daily,
weekly, or manual copies. These are readable ZIP copies of their records in the same format as the full
export, not a way to restore the server.

## Updating

Pull the new version and run `docker compose up -d --build`. The web container applies
database migrations (`alembic upgrade head`) before starting. On platforms with several
web replicas, set `RUN_MIGRATIONS=0` on the web service and run
`python -m alembic -c server/alembic.ini upgrade head` once as a release job instead.

`/api/health` answers when the process is up; `/api/ready` also checks the database.

## Free built-in AI

Every account can draft minutes with an open model that runs on the server itself, through the `ollama` service in
`docker-compose.yml` (tunnel profile, so it only runs on the hosted server). It has no published port; the worker
reaches it at `http://ollama:11434`. Turn it on in `.env`:

```
FREE_AI_URL=http://ollama:11434
FREE_AI_MODELS=gemma4:e4b,qwen3.5:4b
FREE_AI_CONTEXT=32768
```

The first model is the recommended one and the default when an organization has no other AI. The worker downloads the models on start (and retries every minute until Ollama answers), creates one
platform-owned AI connection per model ("Free AI: Gemma 4" and "Free AI: Qwen 3.5"), and runs free requests in their own thread, one at a time, so a
slow free draft never holds up drafts that use someone's own AI. Free drafts skip live redrafting during a
meeting, run once after it ends, and notify the people who run meetings when they are done. Jobs on this lane
are only treated as stuck after 4 hours. On the 4-core Ampere VM the container is capped at 3 cores with a
low CPU weight. In a test on a 45-minute sample meeting (12,000 tokens), `gemma4:e4b` took about 20 minutes and wrote
the cleanest minutes; `qwen3.5:4b` took about 24 minutes and `qwen3:4b` was far slower. Meetings longer than the
context window (about two hours at 32768 tokens) are refused with a message to pick another AI. Removing
`FREE_AI_URL` turns it off; meetings still set to it fail with a clear message.

## Quick translation

The `libretranslate` service in `docker-compose.yml` (tunnel profile, no published port) runs LibreTranslate 1.9.6 with
English, Spanish, Vietnamese, Chinese (Simplified and Traditional), Korean, and Tagalog, capped at 2 cores, a low CPU
weight, and 3 GB of memory. It downloads its language models into the `libretranslate` volume on first start. Turn it on
in `.env` with `LIBRETRANSLATE_URL=http://libretranslate:5000`. The Translations panel then offers "Quick translation"
for the languages the service reports at `/languages`; it finishes in seconds, uses no AI budget, and is rougher than the
AI, so the panel asks the secretary to check names, numbers, and motions. Removing the setting hides the option.

## Downloads page

The site's /download page lists the `.exe` and `.zip` files in `downloads/` inside the files volume
(`/data/files/downloads` in the web container) with their size and SHA-256, and serves them from
`/api/downloads/<name>`. Only names ending in .exe or .zip are listed, and nightly backups skip that folder. To
publish a new build, copy `desktop/release/Live Minutes Setup <version>.exe`, `desktop/release/latest.yml`, and the
extension zip into that folder, and remove the old ones. `latest.yml` is the desktop app's update feed
(`/api/downloads/latest.yml`, sent with `no-cache` and not listed on the page): installed copies read it, download the
new installer, and check its SHA-512 before offering to restart. Upload the installer first and `latest.yml` last, so
no copy reads a feed that points at a file that is not there yet.

## Desktop app

GitHub Actions builds `Live Minutes Setup x.y.z.exe` on every push to check that it builds, but keeps
it only when CI is run by hand (Actions, CI, Run workflow, then the run's artifact, kept for 3 days),
because each copy is about 100 MB of the account's 2 GB of Actions storage. Tag a release (`git tag v1.0.1 && git push --tags`) to attach
the installer to a GitHub Release. People install it and sign in; it connects to
minutes.kevinle.tech unless they choose File, Server settings and enter their district's
`PUBLIC_URL`.

Before distributing widely, buy a Windows code-signing certificate (OV or EV) and set
`CSC_LINK` / `CSC_KEY_PASSWORD` as repository secrets; unsigned installers trigger a
SmartScreen warning.

## Chrome extension

Load `capture-extension/` unpacked for testing. To distribute, zip the folder and
publish it on the Chrome Web Store (one-time developer fee), or have district IT
force-install it through Google Admin.
