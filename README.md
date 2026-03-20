# OpenEdux.ai

Minimal static landing for **www.openedux.ai** (Slogan + optional visit analytics).

## Local preview

Open `index.html` in a browser, or serve the folder:

```bash
python3 -m http.server 8080
```

## Visit analytics: two options

| | **A — Third-party** | **B — Cloudflare Worker + KV** |
|---|---------------------|----------------------------------|
| **Effort** | Lowest: paste a snippet | Small: KV + Worker + DNS/route |
| **Data** | In vendor dashboard; IP visibility varies by product/plan | You store **visit count** + **recent logs** (IP, UA, country) in KV |
| **Best for** | Quick traffic charts, minimal ops | You need **your own** IP/count records |

### A. Third-party (example: Cloudflare Web Analytics)

1. In Cloudflare dashboard: **Web Analytics** → create a site / beacon token.
2. In `index.html`, uncomment the `beacon.min.js` block at the bottom and set `YOUR_BEACON_TOKEN`.
3. Deploy. Metrics appear in the Cloudflare analytics UI.

Other options (same idea): Umami Cloud, Plausible, etc. **IP** handling and export are defined by each vendor.

### B. Own Worker (this repo)

Prerequisites:

- Domain (e.g. `www.openedux.ai`) on **Cloudflare** with proxy (orange cloud) as needed.
- A route so **`/api/*`** hits this Worker while static HTML still serves from GitHub Pages (or Pages + Worker routing — use a route like `www.openedux.ai/api/*`).

Steps:

1. Create a **KV namespace** in Cloudflare (Workers → KV).
2. Copy `wrangler.toml.example` → `wrangler.toml`, set `kv_namespaces.id`.
3. `npx wrangler deploy` (install `wrangler` or use `npm create cloudflare` flow as you prefer).
4. Attach a **route** `www.openedux.ai/api/*` (or your hostname) to this Worker.
5. Optional: `npx wrangler secret put ADMIN_TOKEN` — random string. Then `GET https://www.openedux.ai/api/visit/stats` with header `Authorization: Bearer <ADMIN_TOKEN>` returns `{ total, recent }` (`recent` caps at 200 entries).
6. On **`index.html`**, add to the `<html>` tag:

   ```html
   <html lang="en" data-visit-endpoint="/api/visit">
   ```

   The page will `sendBeacon`/`fetch` **POST** `/api/visit` on load (same origin once the Worker route is live).

**Note:** Without the Worker route, the browser will get **404** for `/api/visit`; leave `data-visit-endpoint` unset until routing is ready.

### Open Graph image

`index.html` references `https://www.openedux.ai/og-image.png`. Add that asset at the site root or update/remove the `og:image` meta tag.

## Privacy

The footer includes a short privacy notice. Adjust wording or jurisdiction-specific text as needed (not legal advice).

## License

Project content: follow your org policy.
