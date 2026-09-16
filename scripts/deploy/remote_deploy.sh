#!/usr/bin/env bash
# Deploy Veramynd under ~/apps/veramynd only. Does not touch other apps or ~/.env.
set -euo pipefail

APP_ROOT="${HOME}/apps/veramynd"
REPO_DIR="${APP_ROOT}/repo"
TOOLS_DIR="${APP_ROOT}/.tools"
VENV_DIR="${APP_ROOT}/.venv"
LOG_DIR="${APP_ROOT}/logs"
PID_FILE="${APP_ROOT}/api.pid"
PORT="${VERAMYND_API_PORT:-9102}"
REPO_URL="${VERAMYND_REPO_URL:-https://github.com/abaidurerehman1/Veramynd.git}"
REPO_REF="${VERAMYND_REPO_REF:-main}"
# Vite 8 / rolldown need Node ^20.19 || >=22.12
NODE_VER="${VERAMYND_NODE_VER:-v22.14.0}"

mkdir -p "${APP_ROOT}" "${TOOLS_DIR}" "${LOG_DIR}"

echo "==> Sync repo (${REPO_REF})"
if [[ -d "${REPO_DIR}/.git" ]]; then
  git -C "${REPO_DIR}" fetch --depth 1 origin "${REPO_REF}"
  git -C "${REPO_DIR}" checkout -f "FETCH_HEAD"
  git -C "${REPO_DIR}" clean -fd
else
  rm -rf "${REPO_DIR}"
  git clone --depth 1 --branch "${REPO_REF}" "${REPO_URL}" "${REPO_DIR}"
fi

echo "==> Install parser .env (path-mode Qdrant; no QDRANT_URL)"
ENV_FILE="${REPO_DIR}/veramynd/veramynd_parser/.env"
SRC_ENV="${VERAMYND_ENV_FILE:-${APP_ROOT}/veramynd.env}"
umask 077
if [[ -f "${SRC_ENV}" ]]; then
  # Copy CI-uploaded secrets file — never print contents.
  cp "${SRC_ENV}" "${ENV_FILE}"
else
  cat > "${ENV_FILE}" <<EOF
OPENAI_API_KEY=${OPENAI_API_KEY:-}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
OPENAI_MODEL=${OPENAI_MODEL:-gpt-4.1-mini}
OPENAI_EMBEDDING_MODEL=${OPENAI_EMBEDDING_MODEL:-text-embedding-3-large}
QDRANT_COLLECTION=${QDRANT_COLLECTION:-veramynd_chunks}
QDRANT_STANDARDS_COLLECTION=${QDRANT_STANDARDS_COLLECTION:-veramynd_standards}
RERANK_MODEL=${RERANK_MODEL:-BAAI/bge-reranker-base}
JUDGE_MODEL=${JUDGE_MODEL:-claude-sonnet-4-5}
JUDGE_ESCALATE_MODEL=${JUDGE_ESCALATE_MODEL:-claude-opus-4-6}
LLM_AUTO_RAISE=${LLM_AUTO_RAISE:-1}
NORMALIZE_ESCALATE_MODEL=${NORMALIZE_ESCALATE_MODEL:-o4-mini}
EOF
fi
chmod 600 "${ENV_FILE}"

echo "==> Install backend .env (auth / dashboard)"
BACKEND_ENV_FILE="${REPO_DIR}/veramynd/backend/.env"
SRC_BACKEND_ENV="${VERAMYND_BACKEND_ENV_FILE:-${APP_ROOT}/backend.env}"
if [[ -f "${SRC_BACKEND_ENV}" ]]; then
  cp "${SRC_BACKEND_ENV}" "${BACKEND_ENV_FILE}"
else
  cat > "${BACKEND_ENV_FILE}" <<EOF
DATABASE_URL=${DATABASE_URL:-}
JWT_SECRET=${JWT_SECRET:-}
JWT_EXPIRE_HOURS=${JWT_EXPIRE_HOURS:-168}
APP_BASE_URL=${APP_BASE_URL:-http://127.0.0.1:${PORT}}
API_BASE_URL=${API_BASE_URL:-http://127.0.0.1:${PORT}}
SMTP_HOST=${SMTP_HOST:-}
SMTP_PORT=${SMTP_PORT:-587}
SMTP_USER=${SMTP_USER:-}
SMTP_PASSWORD=${SMTP_PASSWORD:-}
SMTP_FROM=${SMTP_FROM:-}
SMTP_USE_TLS=${SMTP_USE_TLS:-true}
GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID:-}
GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET:-}
GOOGLE_REDIRECT_URI=${GOOGLE_REDIRECT_URI:-}
EOF
fi
chmod 600 "${BACKEND_ENV_FILE}"
# If CI still has localhost URLs, rewrite to this server's public host:port.
PUBLIC_HOST="$(curl -fsS ifconfig.me 2>/dev/null || true)"
if [[ -n "${PUBLIC_HOST}" ]]; then
  python3 - "${BACKEND_ENV_FILE}" "${PUBLIC_HOST}" "${PORT}" <<'PY'
import sys
from pathlib import Path
path = Path(sys.argv[1])
host, port = sys.argv[2], sys.argv[3]
public = f"http://{host}:{port}"
text = path.read_text(encoding="utf-8")
lines = []
for line in text.splitlines():
    if line.startswith("APP_BASE_URL=") and ("localhost" in line or "127.0.0.1" in line):
        lines.append(f"APP_BASE_URL={public}")
    elif line.startswith("API_BASE_URL=") and ("localhost" in line or "127.0.0.1" in line):
        lines.append(f"API_BASE_URL={public}")
    elif line.startswith("GOOGLE_REDIRECT_URI=") and ("localhost" in line or "127.0.0.1" in line):
        lines.append(f"GOOGLE_REDIRECT_URI={public}/api/auth/oauth/google/callback")
    else:
        lines.append(line)
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("backend public URL rewrite applied (values redacted)")
PY
fi
# Keep a durable copy outside the repo tree for restarts between deploys.
cp "${BACKEND_ENV_FILE}" "${APP_ROOT}/backend.env"
chmod 600 "${APP_ROOT}/backend.env"

echo "==> Ensure portable Node ${NODE_VER} (user-local only)"
NODE_HOME="${TOOLS_DIR}/node-${NODE_VER}-linux-x64"
if [[ ! -x "${NODE_HOME}/bin/node" ]]; then
  curl -fsSL "https://nodejs.org/dist/${NODE_VER}/node-${NODE_VER}-linux-x64.tar.xz" \
    -o "${TOOLS_DIR}/node.tar.xz"
  tar -xJf "${TOOLS_DIR}/node.tar.xz" -C "${TOOLS_DIR}"
  rm -f "${TOOLS_DIR}/node.tar.xz"
fi
export PATH="${NODE_HOME}/bin:${PATH}"
node -v
npm -v

echo "==> Python venv + deps (legacy-CPU safe wheels)"
if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv "${VENV_DIR}"
fi
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
pip install -U pip wheel setuptools
CONSTRAINTS="${REPO_DIR}/scripts/deploy/constraints-legacy-cpu.txt"
export PIP_CONSTRAINT="${CONSTRAINTS}"
export PIP_PROGRESS_BAR=off
# Drop any X86_V2 NumPy / NumPy-2-only SciPy left from a prior deploy.
pip uninstall -y numpy scipy 2>/dev/null || true
pip install -r "${REPO_DIR}/veramynd/backend/requirements.txt"
# CPU torch first so we do not pull CUDA builds on this host.
pip install --index-url https://download.pytorch.org/whl/cpu torch==2.2.2
pip install "numpy==1.26.4" "scipy==1.11.4" "scikit-learn==1.4.2"
pip install "transformers==4.46.3" "tokenizers==0.20.3" "huggingface-hub==0.26.5"
# Full localhost parity — Docling required (same default engine as local).
pip install -e "${REPO_DIR}/veramynd/veramynd_parser[full]"
# Re-assert CPU-safe pins Docling may have tried to upgrade.
pip install --index-url https://download.pytorch.org/whl/cpu torch==2.2.2 torchvision==0.17.2 || true
pip install --force-reinstall --no-deps "numpy==1.26.4"
pip install "scipy==1.11.4" "scikit-learn==1.4.2"

echo "==> Verify pipeline imports (localhost parity)"
python - <<'PY'
import importlib
import importlib.util
mods = [
    "numpy",
    "openpyxl",
    "fitz",  # pymupdf
    "docx",
    "openai",
    "anthropic",
    "qdrant_client",
    "sentence_transformers",
    "torch",
    "docling",
    "veramynd_parser",
]
for m in mods:
    importlib.import_module(m)
    print(f"OK {m}")
print("numpy", __import__("numpy").__version__)
print("torch", __import__("torch").__version__)
from veramynd_parser.standards.spreadsheet import parse_standards  # noqa: F401
print("OK parse_standards_import")
assert importlib.util.find_spec("docling") is not None, "docling required for localhost parity"
print("OK docling (Parse will use engine=docling)")
PY

echo "==> Build frontend"
cd "${REPO_DIR}/veramynd/frontend"
rm -rf node_modules
npm ci
npm run build

echo "==> Restart API on 0.0.0.0:${PORT}"
if [[ -f "${PID_FILE}" ]]; then
  old_pid="$(cat "${PID_FILE}" || true)"
  if [[ -n "${old_pid}" ]] && kill -0 "${old_pid}" 2>/dev/null; then
    kill "${old_pid}" || true
    sleep 2
    kill -9 "${old_pid}" 2>/dev/null || true
  fi
  rm -f "${PID_FILE}"
fi
# Stop any prior Veramynd uvicorn (any port) owned by this user.
pkill -f "uvicorn api.app:app --host " 2>/dev/null || true
sleep 1

cd "${REPO_DIR}/veramynd/backend"
umask 077
printf '%s\n' "VERAMYND_API_PORT=${PORT}" "VERAMYND_PDF_ENGINE=docling" > "${APP_ROOT}/runtime.env"
chmod 600 "${APP_ROOT}/runtime.env"
# Ensure backend .env is present even if repo clean wiped an earlier copy.
if [[ ! -f "${REPO_DIR}/veramynd/backend/.env" && -f "${APP_ROOT}/backend.env" ]]; then
  cp "${APP_ROOT}/backend.env" "${REPO_DIR}/veramynd/backend/.env"
  chmod 600 "${REPO_DIR}/veramynd/backend/.env"
fi
# Do NOT bash-source backend/.env (SMTP_FROM etc. can break the shell).
# Python dotenv loads it inside the API process.
set -a
# shellcheck disable=SC1091
source "${APP_ROOT}/runtime.env"
set +a
nohup "${VENV_DIR}/bin/uvicorn" api.app:app \
  --host 127.0.0.1 \
  --port "${PORT}" \
  --workers 1 \
  > "${LOG_DIR}/api.log" 2>&1 &
echo $! > "${PID_FILE}"
sleep 3

if ! kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
  echo "API failed to start. Last log lines:"
  tail -n 80 "${LOG_DIR}/api.log" || true
  exit 1
fi

echo "OK: Veramynd API on 127.0.0.1:${PORT}/ (pid $(cat "${PID_FILE}"))"

DOMAIN="${VERAMYND_DOMAIN:-}"
LIVE_URL=""

echo "==> Configure public HTTPS front door"
CLOUDFLARED_BIN="${TOOLS_DIR}/cloudflared"
CADDY_BIN="${TOOLS_DIR}/caddy"
mkdir -p "${TOOLS_DIR}" "${LOG_DIR}"

if [[ -n "${DOMAIN}" ]]; then
  # Prefer Caddy + Let's Encrypt for a clean https://domain URL.
  if [[ ! -x "${CADDY_BIN}" ]]; then
    echo "Downloading Caddy..."
    curl -fsSL "https://caddyserver.com/api/download?os=linux&arch=amd64" -o "${CADDY_BIN}"
    chmod +x "${CADDY_BIN}"
  fi
  cat > "${APP_ROOT}/Caddyfile" <<EOF
${DOMAIN} {
  encode gzip
  reverse_proxy 127.0.0.1:${PORT}
  header {
    Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
    X-Content-Type-Options nosniff
    Referrer-Policy strict-origin-when-cross-origin
  }
}
EOF
  pkill -f "${CADDY_BIN} run --config" 2>/dev/null || true
  sleep 1
  nohup "${CADDY_BIN}" run --config "${APP_ROOT}/Caddyfile" --adapter caddyfile \
    > "${LOG_DIR}/caddy.log" 2>&1 &
  echo $! > "${APP_ROOT}/caddy.pid"
  LIVE_URL="https://${DOMAIN}"
  # Point auth links at the HTTPS domain.
  python3 - "${BACKEND_ENV_FILE}" "${LIVE_URL}" <<'PY'
import sys
from pathlib import Path
path = Path(sys.argv[1])
base = sys.argv[2].rstrip("/")
text = path.read_text(encoding="utf-8")
out = []
for line in text.splitlines():
    if line.startswith("APP_BASE_URL="):
        out.append(f'APP_BASE_URL="{base}"')
    elif line.startswith("API_BASE_URL="):
        out.append(f'API_BASE_URL="{base}"')
    elif line.startswith("GOOGLE_REDIRECT_URI="):
        out.append(f'GOOGLE_REDIRECT_URI="{base}/api/auth/oauth/google/callback"')
    else:
        out.append(line)
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
  cp "${BACKEND_ENV_FILE}" "${APP_ROOT}/backend.env"
  chmod 600 "${APP_ROOT}/backend.env"
else
  # No custom domain: Cloudflare quick tunnel → stable-enough https://*.trycloudflare.com
  if [[ ! -x "${CLOUDFLARED_BIN}" ]]; then
    echo "Downloading cloudflared..."
    curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" \
      -o "${CLOUDFLARED_BIN}"
    chmod +x "${CLOUDFLARED_BIN}"
  fi
  pkill -f "${CLOUDFLARED_BIN} tunnel --url" 2>/dev/null || true
  sleep 1
  rm -f "${LOG_DIR}/cloudflared.log" "${APP_ROOT}/LIVE_URL"
  nohup "${CLOUDFLARED_BIN}" tunnel --url "http://127.0.0.1:${PORT}" \
    > "${LOG_DIR}/cloudflared.log" 2>&1 &
  echo $! > "${APP_ROOT}/cloudflared.pid"
  # Wait for trycloudflare URL
  for _ in $(seq 1 30); do
    LIVE_URL="$(grep -oE 'https://[a-zA-Z0-9.-]+\.trycloudflare\.com' "${LOG_DIR}/cloudflared.log" | tail -n1 || true)"
    if [[ -n "${LIVE_URL}" ]]; then
      break
    fi
    sleep 1
  done
  if [[ -z "${LIVE_URL}" ]]; then
    PUBLIC_HOST="$(curl -fsS ifconfig.me 2>/dev/null || echo HOST)"
    LIVE_URL="http://${PUBLIC_HOST}:${PORT}"
    echo "WARN: Cloudflare tunnel URL not ready; falling back to ${LIVE_URL}"
  else
    python3 - "${BACKEND_ENV_FILE}" "${LIVE_URL}" <<'PY'
import sys
from pathlib import Path
path = Path(sys.argv[1])
base = sys.argv[2].rstrip("/")
text = path.read_text(encoding="utf-8")
out = []
for line in text.splitlines():
    if line.startswith("APP_BASE_URL="):
        out.append(f'APP_BASE_URL="{base}"')
    elif line.startswith("API_BASE_URL="):
        out.append(f'API_BASE_URL="{base}"')
    elif line.startswith("GOOGLE_REDIRECT_URI="):
        out.append(f'GOOGLE_REDIRECT_URI="{base}/api/auth/oauth/google/callback"')
    else:
        out.append(line)
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
    cp "${BACKEND_ENV_FILE}" "${APP_ROOT}/backend.env"
    chmod 600 "${APP_ROOT}/backend.env"
  fi
fi

printf '%s\n' "${LIVE_URL}" > "${APP_ROOT}/LIVE_URL"
chmod 644 "${APP_ROOT}/LIVE_URL"
echo "==============================================="
echo "LIVE_URL=${LIVE_URL}"
echo "==============================================="
