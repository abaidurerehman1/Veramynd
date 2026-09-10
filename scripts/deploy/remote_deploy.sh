#!/usr/bin/env bash
# Deploy Veramynd under ~/apps/veramynd only. Does not touch other apps or ~/.env.
set -euo pipefail

APP_ROOT="${HOME}/apps/veramynd"
REPO_DIR="${APP_ROOT}/repo"
TOOLS_DIR="${APP_ROOT}/.tools"
VENV_DIR="${APP_ROOT}/.venv"
LOG_DIR="${APP_ROOT}/logs"
PID_FILE="${APP_ROOT}/api.pid"
PORT="${VERAMYND_API_PORT:-8080}"
REPO_URL="${VERAMYND_REPO_URL:-https://github.com/abaidurerehman1/Veramynd.git}"
REPO_REF="${VERAMYND_REPO_REF:-main}"
NODE_VER="${VERAMYND_NODE_VER:-v20.18.1}"

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

echo "==> Write parser .env from CI-provided env (no Qdrant Docker required)"
ENV_FILE="${REPO_DIR}/veramynd/veramynd_parser/.env"
umask 077
cat > "${ENV_FILE}" <<EOF
OPENAI_API_KEY=${OPENAI_API_KEY:-}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
OPENAI_MODEL=${OPENAI_MODEL:-gpt-4.1-mini}
OPENAI_EMBEDDING_MODEL=${OPENAI_EMBEDDING_MODEL:-text-embedding-3-large}
# Path-mode Qdrant — do not set QDRANT_URL on this host.
QDRANT_COLLECTION=${QDRANT_COLLECTION:-veramynd_chunks}
QDRANT_STANDARDS_COLLECTION=${QDRANT_STANDARDS_COLLECTION:-veramynd_standards}
RERANK_MODEL=${RERANK_MODEL:-BAAI/bge-reranker-base}
JUDGE_MODEL=${JUDGE_MODEL:-claude-sonnet-4-5}
JUDGE_ESCALATE_MODEL=${JUDGE_ESCALATE_MODEL:-claude-opus-4-6}
LLM_AUTO_RAISE=${LLM_AUTO_RAISE:-1}
NORMALIZE_ESCALATE_MODEL=${NORMALIZE_ESCALATE_MODEL:-o4-mini}
EOF
chmod 600 "${ENV_FILE}"

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

echo "==> Python venv + deps"
if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv "${VENV_DIR}"
fi
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
pip install -U pip wheel setuptools
pip install -r "${REPO_DIR}/veramynd/backend/requirements.txt"
pip install -e "${REPO_DIR}/veramynd/veramynd_parser[normalize,embed,retrieve,judge]"

echo "==> Build frontend"
cd "${REPO_DIR}/veramynd/frontend"
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
# Stop any prior veramynd uvicorn on this port owned by this user.
pkill -f "uvicorn api.app:app --host 0.0.0.0 --port ${PORT}" 2>/dev/null || true
sleep 1

cd "${REPO_DIR}/veramynd/backend"
export VERAMYND_API_PORT="${PORT}"
nohup "${VENV_DIR}/bin/uvicorn" api.app:app \
  --host 0.0.0.0 \
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

echo "OK: Veramynd listening on http://0.0.0.0:${PORT}/ (pid $(cat "${PID_FILE}"))"
echo "Public URL: http://$(curl -fsS ifconfig.me 2>/dev/null || echo HOST):${PORT}/"
