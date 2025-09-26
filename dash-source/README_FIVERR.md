# SysOps Dashboard Deployment (REMI Media Ventures)

## Setup
```bash
npm ci
npm run build
```

## Deploy
```bash
export S3_BUCKET_URL=s3://sysops.remimediaventures.com
export CF_DISTRIBUTION_ID=XXXXXX
make deploy-all
```

## Modes
- **Bootstrap Mode:** `REPO_BOOTSTRAP=1 node server.js`
- **Normal JIT Mode:** `REPO_BOOTSTRAP=0 REPO_JIT_ENABLED=1 node server.js`

## Pitfalls / Correction
- Ensure ACM cert for `*.remimediaventures.com`
- CloudFront SPA errors mapped (403/404 → /index.html)
- `/healthz.json` must return `{status:"ok"}`
- Approve/revoke only in owner console (not UI)
