# Instagram Downloader API

FastAPI service to download Instagram reels/posts.

Developer: `@xoxhunterxd`

## Endpoints

- `GET /health`
- `GET /?url=<instagram_url>` (direct download)
- `GET /api/v1/instagram/download?url=<instagram_url>`
- `POST /api/v1/instagram/download`
  - optional `delivery=link` for R2 link response

## POST Body

```json
{
  "url": "https://www.instagram.com/reel/XXXXXXXXXXX/",
  "delivery": "link"
}
```

## Local Run

```bash
pip install -r requirements.txt
python main.py
```

## Quick Test

```bash
curl "http://127.0.0.1:8000/?url=https://www.instagram.com/reel/XXXXXXXXXXX/" --output media.mp4
```

## Cloudflare R2 (Zip + Link)

Set these env vars on Railway/Replit/etc:

- `R2_ENDPOINT` (example: `https://<accountid>.r2.cloudflarestorage.com`)
- `R2_BUCKET`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_PUBLIC_BASE` (optional, public base URL for direct links)
- `R2_SIGNED_URL_TTL` (optional, seconds for signed URLs; default `3600`)

Use `delivery=link`:

```bash
curl "http://127.0.0.1:8000/api/v1/instagram/download?url=https://www.instagram.com/reel/XXXXXXXXXXX/&delivery=link"
```

Response:

```json
{
  "download_url": "https://.../instagram/<id>/file.zip",
  "filename": "file.mp4.zip",
  "delivery": "link",
  "developer": "@xoxhunterxd",
  "expires_in": 3600
}
```

## Railway Deploy

1. Push repo to GitHub.
2. Railway -> New Project -> Deploy from GitHub.
3. Select repo and deploy.
4. Generate public domain.
5. Test:
   - `/health`
   - `/?url=<instagram_url>`

Live URL example:

`https://instagram-downloader-api-production.up.railway.app/`
