#!/usr/bin/env bash
#
# assemble_and_push.sh — build each Hugging Face Space's Docker context from the
# monorepo and push it. Hugging Face then builds the image and starts the Space.
#
# What it does, per backend:
#   1. clone the (already-created) private Space repo into a temp dir
#   2. replace its contents with: Dockerfile + README.md (Space card) +
#      .dockerignore [+ start.py for RAG], the engine source (renamed to drop
#      the space in "AI Model" → ai_model/), and the shared sample_data dirs
#   3. commit + push → triggers the Hugging Face build
#
# Secrets and venvs/caches are filtered out (see RSYNC_EXCLUDES) so no local
# .env / API key is ever shipped into a Space.
#
# ── Prerequisites ────────────────────────────────────────────────────────────
#   • pip install -U "huggingface_hub[cli]"   (gives `huggingface-cli`)
#   • huggingface-cli login                   (stores a git credential)
#   • git-lfs installed                       (HF repos use it; already present)
#   • the two PRIVATE Docker Spaces created (see DEPLOY.md), e.g.
#       huggingface-cli repo create asra-ai-model  --repo-type space --space-sdk docker --private -y
#       huggingface-cli repo create asra-rag-model --repo-type space --space-sdk docker --private -y
#
# ── Usage ────────────────────────────────────────────────────────────────────
#   HF_USER=<your-hf-username> ./deploy/hf/assemble_and_push.sh
#   # optional overrides:
#   HF_USER=me AI_SPACE=asra-ai-model RAG_SPACE=asra-rag-model ./deploy/hf/assemble_and_push.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # repo root
HF_USER="${HF_USER:?set HF_USER to your Hugging Face username}"
AI_SPACE="${AI_SPACE:-asra-ai-model}"
RAG_SPACE="${RAG_SPACE:-asra-rag-model}"

RSYNC_EXCLUDES=(
  --exclude '.git'           --exclude '.env'        --exclude '.env.*'
  --exclude '__pycache__'    --exclude '*.pyc'
  --exclude '.venv'          --exclude 'venv'        --exclude 'env'
  --exclude '.pytest_cache'  --exclude '.ruff_cache' --exclude '*.egg-info'
  --exclude 'chroma_db'      --exclude '.asra_cache'
  --exclude 'logs/*.jsonl'   --exclude 'intake_sessions/*.json'
  --exclude 'node_modules'   --exclude '.DS_Store'
)

push_space() {
  local kind="$1" space="$2" model_src="$3" dest_pkg="$4"
  local repo="https://huggingface.co/spaces/${HF_USER}/${space}"
  local work; work="$(mktemp -d)"
  trap 'rm -rf "$work"' RETURN

  echo "──────────────────────────────────────────────────────────────"
  echo "→ [$kind] cloning $repo"
  if ! git clone --quiet "$repo" "$work"; then
    echo "✗ [$kind] could not clone $repo" >&2
    echo "  Create it first:  huggingface-cli repo create ${space} --repo-type space --space-sdk docker --private -y" >&2
    return 1
  fi

  echo "→ [$kind] assembling build context"
  # Wipe tracked content (keep .git) so deletions propagate to the Space.
  find "$work" -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +

  cp "$ROOT/deploy/hf/$kind/Dockerfile"     "$work/Dockerfile"
  cp "$ROOT/deploy/hf/$kind/README.md"      "$work/README.md"
  cp "$ROOT/deploy/hf/$kind/.dockerignore"  "$work/.dockerignore"
  [ -f "$ROOT/deploy/hf/$kind/start.py" ] && cp "$ROOT/deploy/hf/$kind/start.py" "$work/start.py"

  mkdir -p "$work/$dest_pkg"
  rsync -a "${RSYNC_EXCLUDES[@]}" "$ROOT/$model_src/"     "$work/$dest_pkg/"
  rsync -a "${RSYNC_EXCLUDES[@]}" "$ROOT/sample_data/"    "$work/sample_data/"
  rsync -a "${RSYNC_EXCLUDES[@]}" "$ROOT/sample_data_v2/" "$work/sample_data_v2/"

  echo "→ [$kind] committing + pushing (Hugging Face will build the image)"
  (
    cd "$work"
    git add -A
    if git diff --cached --quiet; then
      echo "  nothing changed — skipping commit"
    else
      git commit --quiet -m "Deploy ASRA ${kind} backend"
    fi
    git push --quiet origin HEAD:main
  )
  echo "✓ [$kind] pushed → ${repo}  (open it and watch the build logs)"
}

push_space ai  "$AI_SPACE"  "AI Model"  "ai_model"
push_space rag "$RAG_SPACE" "RAG Model" "rag_model"

cat <<EOF

──────────────────────────────────────────────────────────────
Both Spaces pushed. Once their builds go green, the API URLs are:
  AI : https://${HF_USER}-${AI_SPACE}.hf.space
  RAG: https://${HF_USER}-${RAG_SPACE}.hf.space
(HF lowercases the subdomain; copy the exact "Direct URL" shown on each Space.)

Next:
  • Smoke-test:  curl https://${HF_USER}-${AI_SPACE}.hf.space/health
  • Build the frontend on Cloudflare Pages with those two URLs as
    VITE_AI_API / VITE_RAG_API  (see deploy/DEPLOY.md, Step 3).
EOF
