# Deploying ASRA for free

This guide takes the whole app — **two FastAPI engines + the React UI** — live at
**$0**, no credit card, with your source kept **private**.

| Piece | Hosted on | Free tier |
|---|---|---|
| `AI Model/` backend | Hugging Face **private** Docker Space | 2 vCPU / 16 GB RAM, no card |
| `RAG Model/` backend | Hugging Face **private** Docker Space | 2 vCPU / 16 GB RAM, no card |
| `Frontend/` SPA | **Cloudflare Pages** | unlimited bandwidth, no card |
| LLM | Google **Gemini** API | free tier (AI Studio key) |

```
 Browser ──> Cloudflare Pages (static SPA)
                 │  baked-in at build time:
                 │    VITE_AI_API  ─────────────►  HF Space: AI Model   (/evaluate, /status, …)
                 │    VITE_RAG_API ─────────────►  HF Space: RAG Model  (/evaluate, /status, …)
                 ▼                                   each calls Gemini, allows CORS from the Pages URL
```

### The ordering that matters (why this isn't one click)
- The **frontend bakes the two backend URLs at build time** → deploy the **backends first**, get their URLs, *then* build the frontend.
- The **backends only accept browser calls from an allow-listed origin** (`ASRA_CORS_ORIGINS`) → set that to the **Pages URL last**, once you have it.

So the path is: **① Gemini key → ② both HF Spaces → ③ Cloudflare Pages → ④ point CORS back at Pages → ⑤ smoke test.**

---

## ① Prerequisites (all free)

1. **Hugging Face account** — <https://huggingface.co/join>
2. **Cloudflare account** — <https://dash.cloudflare.com/sign-up>
3. **Google AI Studio / Gemini key** — <https://aistudio.google.com/apikey> → *Create API key*. Copy it; you'll paste it into both Spaces.
4. CLI tools on your machine:
   ```bash
   pip install -U "huggingface_hub[cli]"   # provides `huggingface-cli`
   huggingface-cli login                   # paste a HF access token (Settings → Access Tokens, role: write)
   git lfs install                          # HF repos use LFS (you already have git-lfs)
   ```
   > Cloudflare needs **no CLI** — we use its dashboard (connects to your GitHub repo).

---

## ② Deploy the two backends → Hugging Face Spaces

### 2a. Create the two **private** Docker Spaces
```bash
huggingface-cli repo create asra-ai-model  --repo-type space --space-sdk docker --private -y
huggingface-cli repo create asra-rag-model --repo-type space --space-sdk docker --private -y
```
(Or via the UI: **New → Space → SDK: Docker → Visibility: Private**.)

### 2b. Add the secret/variable to **each** Space
Open each Space → **Settings → Variables and secrets**:

| Name | Type | Value | AI | RAG |
|---|---|---|:--:|:--:|
| `GEMINI_API_KEY` | **Secret** | your AI Studio key | ✓ | ✓ (**required**) |
| `ASRA_CORS_ORIGINS` | Variable | leave blank for now — set in Step ④ | ✓ | ✓ |

> **RAG only — bake the index at build:** on the RAG Space, when you add
> `GEMINI_API_KEY`, also tick **"Use as build secret"** (or add it in the Space's
> build-secrets section). That lets the Dockerfile build the Chroma vector store
> *during the image build*, so the Space wakes instantly. If you skip it, the
> Space still works — it builds the index on first boot instead (slower first
> request). The AI Space needs no build secret.

### 2c. Push the code (Hugging Face builds the image)
From the repo root:
```bash
chmod +x deploy/hf/assemble_and_push.sh
HF_USER=<your-hf-username> ./deploy/hf/assemble_and_push.sh
```
This assembles each Space's Docker context from the monorepo (engine source +
shared `sample_data/`) and pushes it. **No `.env` or key is ever shipped** — only
the platform secrets you set in 2b are used.

Open each Space and watch **Build logs**. First build ≈ 3–8 min (RAG is longer —
it installs ChromaDB and embeds the `kb/`).

### 2d. Smoke-test the backends
The "Direct URL" is shown on each Space (format `https://<user>-<space>.hf.space`):
```bash
curl https://<user>-asra-ai-model.hf.space/health
curl https://<user>-asra-ai-model.hf.space/eval/datasets      # → {"datasets":["sample-v1","sample-v2"]}
curl https://<user>-asra-rag-model.hf.space/health
curl "https://<user>-asra-rag-model.hf.space/status"          # RAG should report a live embedding model
```
Note both URLs — they're the `VITE_*` values in the next step.

---

## ③ Deploy the frontend → Cloudflare Pages

The repo is already on GitHub (`origin`). Push anything uncommitted first
(this branch includes `Frontend/public/_redirects`, the SPA fallback):
```bash
git add -A && git commit -m "Add deployment config" && git push origin main
```

In the **Cloudflare dashboard → Workers & Pages → Create → Pages → Connect to Git**:
1. Pick the `AI-Strategic-Resource-Allocator-ASRA` repo, branch `main`.
2. Build settings:
   - **Framework preset:** Vite (or "None")
   - **Root directory:** `Frontend`
   - **Build command:** `npm run build`
   - **Build output directory:** `dist`
3. **Environment variables** (Production) — paste the two Space URLs from 2d:
   | Variable | Value |
   |---|---|
   | `VITE_AI_API` | `https://<user>-asra-ai-model.hf.space` |
   | `VITE_RAG_API` | `https://<user>-asra-rag-model.hf.space` |
   > These are read at **build time** (`import.meta.env.VITE_*`). If you change a
   > backend URL later, you must **re-deploy** the Pages project.
4. **Save and Deploy.** You'll get `https://<project>.pages.dev`.

> `Frontend/public/_redirects` ships a `/* /index.html 200` rule so deep links
> like `/compare` and `/dataset` resolve instead of 404-ing.

---

## ④ Point the backends' CORS at your Pages URL

Back in **each** Space → **Settings → Variables and secrets**, set:

```
ASRA_CORS_ORIGINS = https://<project>.pages.dev
```

Add any custom domain too, comma-separated, e.g.
`https://asra.pages.dev,https://asra.example.com`. Each Space restarts (~30 s).

> Why not `*`? The engines handle applicant PII; a wildcard would let *any*
> site drive the API from a visitor's browser. Keep it to your Pages origin.
> (Cloudflare preview deployments use `*.pages.dev` subdomains — if you want
> previews to work too, add your specific preview URL when testing.)

---

## ⑤ Smoke-test the live app

1. Open `https://<project>.pages.dev/compare`.
2. The status bar should show both engines; the dataset picker should list
   `sample-v1` / `sample-v2`.
3. Click **Run** → both panels populate (the first call may take ~1–2 min if a
   Space was asleep — see below).
4. Visit `/dataset` and refresh — it should load (proves the SPA fallback works).

If a panel errors with a CORS or "could not reach" message, re-check Step ④ and
that the `VITE_*` URLs exactly match the Spaces' Direct URLs (no trailing slash).

---

## Operating notes

**Cost.** Everything above stays at **$0**: HF CPU Spaces and Cloudflare Pages are
free with no card; Gemini usage for this demo (a handful of small generate/embed
calls per run) sits inside the free tier.

**Cold starts.** Free HF Spaces **sleep after ~48 h of inactivity** and take
~1–2 min to wake on the next request (baking the RAG index keeps the wake fast).
The UI shows per-panel loading state meanwhile. To keep them warm you can ping
`/health` on a schedule (e.g. a free GitHub Action cron) — optional.

**Updating.**
- Backend code change → re-run `deploy/hf/assemble_and_push.sh` (rebuilds the Spaces).
- KB (`RAG Model/kb/`) change → same; the index re-bakes (idempotent — only
  changed chunks re-embed).
- Frontend change → `git push origin main`; Cloudflare auto-builds.

**Privacy.** Both Spaces are **private** (source not public). The `LICENSE` is
proprietary — keep them private. The assemble script never ships `.env`/keys.

**Optional hardening.** Set `ASRA_API_KEY` (a variable) on the Spaces to require an
`X-API-Key` header on the mutating/LLM routes. The frontend doesn't send one
today, so only enable this if you also add the header client-side.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Space build fails on `pip install` | Re-trigger the build (transient), or check the Build logs for the failing package. The RAG image already includes `build-essential`. |
| RAG `/status` shows no live embedding model / retrieval empty | `GEMINI_API_KEY` missing on the RAG Space, or the build secret wasn't set so the index didn't bake. Add the key (secret **and** build secret) and **Factory rebuild** the Space. |
| Frontend panel: "Could not reach … Is the server running?" | The Space is asleep (wait ~1–2 min and retry) **or** the `VITE_*` URL is wrong → fix env var and re-deploy Pages. |
| Browser console: CORS error | `ASRA_CORS_ORIGINS` on the backend doesn't include the exact Pages origin. Set it (Step ④) and let the Space restart. |
| `/compare` 404s on refresh | `Frontend/public/_redirects` missing from the build — confirm it's committed and the Pages output dir is `dist`. |
| Dataset list empty | Backend can't read `sample_data/` — should be impossible via the script (it copies it); check the Space build logs for the COPY step. |
