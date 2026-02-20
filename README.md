# Instagram Downloader API

FastAPI service to download Instagram reels/posts.

Developer: `@xoxhunterxd`

## Endpoints

- `GET /health`
- `GET /?url=<instagram_url>` (direct download)
- `GET /api/v1/instagram/download?url=<instagram_url>`
- `POST /api/v1/instagram/download`

## POST Body

```json
{
  "url": "https://www.instagram.com/reel/XXXXXXXXXXX/"
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
