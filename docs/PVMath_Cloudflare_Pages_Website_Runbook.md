# pvmath.com — Cloudflare Pages migration runbook

Marketing site moves from **GitHub Pages** (10 min deploy timeouts) to **Cloudflare Pages** (`pvmath-website` project).

App stays on existing CF Pages project **`pvmath-react`** → `app.pvmath.com`.

---

## 1. Create CF Pages project

1. [Cloudflare Dashboard](https://dash.cloudflare.com) → **Workers & Pages** → **Create** → **Pages** → **Connect to Git**
2. Authorize GitHub → select **`IsmailPVMath/siteiq`**
3. Project name: **`pvmath-website`**
4. Production branch: **`main`**
5. Build settings:

| Setting | Value |
|---|---|
| Framework preset | None |
| Build command | `bash scripts/build-marketing.sh` |
| Build output directory | `website-dist` |
| Root directory | `/` (repo root) |

6. **Save and deploy** — first build should finish in ~30–60 s.

---

## 2. Build watch paths (optional but recommended)

**Settings → Builds → Build watch paths** — only redeploy when marketing files change:

```
index.html
impressum.html
privacy.html
terms.html
sitemap.xml
assets/**
services/**
guides/**
scripts/build-marketing.sh
```

API / frontend / Python commits then skip website rebuilds.

---

## 3. Custom domains

**Custom domains** → add:

- `pvmath.com`
- `www.pvmath.com`

If `pvmath.com` is already on Cloudflare DNS, approve the automatic record updates.

If DNS is still on **Namecheap** (A records → GitHub `185.199.x.x`):

1. Move DNS to Cloudflare (recommended), **or**
2. Delete GitHub A records and set apex + `www` per CF Pages instructions (CNAME `www` → `pvmath-website.pages.dev`; apex via CF proxy or ALIAS)

Remove after cutover:

- A `@` → `185.199.108–111.153`
- CNAME `www` → `ismailpvmath.github.io`

---

## 4. Disable GitHub Pages (stops failure emails)

GitHub → **IsmailPVMath/siteiq** → **Settings** → **Pages**:

- **Source** → **None** / delete build source

Optional: delete root **`CNAME`** file in a follow-up commit (GitHub-only; not used by CF Pages).

---

## 5. Verify

- [https://pvmath.com](https://pvmath.com) — LayoutIQ electrical copy, 6 workflow steps, updated pricing
- [https://pvmath.com/guides/](https://pvmath.com/guides/) — Knowledge Centre
- [https://pvmath.com/services/](https://pvmath.com/services/) — Services page
- Legal: `/impressum.html`, `/privacy.html`, `/terms.html`

---

## Local test

```bash
bash scripts/build-marketing.sh
cd website-dist && python3 -m http.server 8080
# open http://localhost:8080
```

---

## Projects summary

| Domain | CF Pages project | Build output |
|---|---|---|
| `app.pvmath.com` | `pvmath-react` | `frontend/dist` |
| `pvmath.com` | `pvmath-website` | `website-dist` |
