#!/usr/bin/env bash
# Apache Jena Fuseki：Docker 容器（推荐）或连接已在运行的本地 Fuseki（FUSEKI_URL 相同）。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
RUNTIME_DIR="$ROOT_DIR/.run"
FUSEKI_DATA_DIR="$RUNTIME_DIR/fuseki-data"

FUSEKI_PORT_DEFAULT=3030
FUSEKI_DATASET_DEFAULT=datalens
FUSEKI_IMAGE_DEFAULT=stain/jena-fuseki:4.10.0
FUSEKI_PORT="${FUSEKI_PORT:-$FUSEKI_PORT_DEFAULT}"
FUSEKI_DATASET="${FUSEKI_DATASET:-$FUSEKI_DATASET_DEFAULT}"
FUSEKI_IMAGE="${FUSEKI_IMAGE:-$FUSEKI_IMAGE_DEFAULT}"
FUSEKI_URL="${FUSEKI_URL:-http://localhost:${FUSEKI_PORT}}"

if [[ -f "$ROOT_DIR/.env" ]]; then
  # shellcheck disable=SC1090
  source "$ROOT_DIR/.env"
  FUSEKI_PORT="${FUSEKI_PORT:-$FUSEKI_PORT_DEFAULT}"
  FUSEKI_DATASET="${FUSEKI_DATASET:-$FUSEKI_DATASET_DEFAULT}"
  FUSEKI_IMAGE="${FUSEKI_IMAGE:-$FUSEKI_IMAGE_DEFAULT}"
  FUSEKI_URL="${FUSEKI_URL:-http://localhost:${FUSEKI_PORT}}"
fi

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

has_docker() {
  command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1
}

compose() {
  docker compose -f "$COMPOSE_FILE" "$@"
}

fuseki_ping() {
  curl -sf "${FUSEKI_URL}/\$/ping" >/dev/null 2>&1
}

fuseki_dataset_ready() {
  curl -sf -o /dev/null -w "%{http_code}" \
    -X POST "${FUSEKI_URL}/${FUSEKI_DATASET}/query" \
    -H "Accept: application/sparql-results+json" \
    --data-urlencode "query=ASK { ?s ?p ?o }" 2>/dev/null | grep -qE '^(200|204)$'
}

wait_fuseki() {
  local timeout="${1:-60}"
  local waited=0
  log "等待 Fuseki 就绪 (${FUSEKI_URL})..."
  while ! fuseki_ping; do
    if (( waited >= timeout )); then
      log "Fuseki 启动超时（${timeout}s）"
      return 1
    fi
    sleep 2
    waited=$((waited + 2))
  done
  waited=0
  while ! fuseki_dataset_ready; do
    if (( waited >= timeout )); then
      return 1
    fi
    sleep 1
    waited=$((waited + 1))
  done
  log "Fuseki 已就绪: ${FUSEKI_URL}/${FUSEKI_DATASET}"
}

start_fuseki() {
  if fuseki_ping && fuseki_dataset_ready; then
    log "Fuseki 已在运行 (${FUSEKI_URL})"
    return 0
  fi

  if ! has_docker; then
    log "未检测到 Docker — 跳过容器启动。"
    log "请在本机安装并启动 Fuseki，或运行: docker compose up -d fuseki"
    log "FUSEKI_URL 应指向: ${FUSEKI_URL}"
    return 1
  fi

  mkdir -p "$FUSEKI_DATA_DIR"
  log "启动 Fuseki 容器 (port=${FUSEKI_PORT}, dataset=${FUSEKI_DATASET}, image=${FUSEKI_IMAGE})..."
  local try max_try
  max_try=3
  for try in 1 2 3; do
    if docker pull "$FUSEKI_IMAGE" >/dev/null 2>&1; then
      break
    fi
    if (( try == max_try )); then
      log "拉取 Fuseki 镜像失败: ${FUSEKI_IMAGE}"
      log "建议: 1) 执行 docker login 2) 配置 Docker 镜像加速器 3) 在 .env 中设置 FUSEKI_IMAGE 为可用镜像地址"
      return 1
    fi
    log "拉取镜像失败，${try}/${max_try}，2 秒后重试..."
    sleep 2
  done
  FUSEKI_PORT="$FUSEKI_PORT" FUSEKI_DATASET="$FUSEKI_DATASET" \
  FUSEKI_IMAGE="$FUSEKI_IMAGE" compose up -d fuseki
  wait_fuseki 90
}

stop_fuseki() {
  if ! has_docker; then
    log "无 Docker / Fuseki 容器；本地 Trig 存储不受影响"
    return 0
  fi
  log "停止 Fuseki 容器..."
  compose stop fuseki 2>/dev/null || true
  log "Fuseki 已停止"
}

restart_fuseki() {
  stop_fuseki || true
  start_fuseki
}

status_fuseki() {
  if fuseki_ping && fuseki_dataset_ready; then
    log "Fuseki: 运行中 (${FUSEKI_URL}, dataset=${FUSEKI_DATASET})"
    return 0
  fi
  if has_docker; then
    log "Fuseki: 未运行 (${FUSEKI_URL})"
  else
    log "Fuseki: 未运行 (${FUSEKI_URL})"
  fi
  return 1
}

logs_fuseki() {
  if ! has_docker; then
    log "无 Docker，无 Fuseki 日志"
    exit 0
  fi
  compose logs -f --tail=100 fuseki
}

usage() {
  cat <<EOF
用法: ./scripts/fuseki.sh <start|stop|restart|status|wait|logs>

通过 Docker 启动 Fuseki，或确保 FUSEKI_URL 已指向本地/远程 Fuseki 实例。

环境变量（.env）:
  FUSEKI_URL=http://localhost:3030
  FUSEKI_DATASET=datalens
  FUSEKI_IMAGE=stain/jena-fuseki:4.10.0
  FUSEKI_AUTO_START=true
  FUSEKI_FALLBACK_MEMORY=false
EOF
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    start) start_fuseki ;;
    stop) stop_fuseki ;;
    restart) restart_fuseki ;;
    status) status_fuseki ;;
    wait) wait_fuseki "${2:-60}" ;;
    logs) logs_fuseki ;;
    *) usage; exit 1 ;;
  esac
}

main "$@"
