#!/usr/bin/env bash
# Apache Jena Fuseki：Docker 容器（推荐）或连接已在运行的本地 Fuseki（FUSEKI_URL 相同）。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
RUNTIME_DIR="$ROOT_DIR/.run"
FUSEKI_DATA_DIR="$RUNTIME_DIR/fuseki-data"
FUSEKI_PID_FILE="$RUNTIME_DIR/fuseki.pid"
FUSEKI_LOG_FILE="$RUNTIME_DIR/fuseki.log"
FUSEKI_HOME_DEFAULT="$RUNTIME_DIR/apache-jena-fuseki-6.1.0"

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

FUSEKI_HOME="${FUSEKI_HOME:-$FUSEKI_HOME_DEFAULT}"
# native | docker | auto — auto 优先使用本机已解压的 Fuseki，否则回退 Docker
FUSEKI_LAUNCHER="${FUSEKI_LAUNCHER:-auto}"

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

native_fuseki_available() {
  [[ -x "${FUSEKI_HOME}/fuseki-server" ]]
}

read_native_fuseki_pid() {
  if [[ -f "$FUSEKI_PID_FILE" ]]; then
    cat "$FUSEKI_PID_FILE"
  fi
}

native_fuseki_running() {
  local pid
  pid="$(read_native_fuseki_pid || true)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

start_fuseki_native() {
  if ! native_fuseki_available; then
    log "未找到本机 Fuseki: ${FUSEKI_HOME}/fuseki-server"
    log "请将 Apache Jena Fuseki 解压到 ${FUSEKI_HOME_DEFAULT}，或设置 FUSEKI_HOME"
    return 1
  fi

  if fuseki_ping && fuseki_dataset_ready; then
    log "Fuseki 已在运行 (${FUSEKI_URL})"
    return 0
  fi

  if native_fuseki_running; then
    log "Fuseki 进程已在运行 (pid=$(read_native_fuseki_pid))，等待就绪..."
    wait_fuseki 60
    return $?
  fi

  mkdir -p "$FUSEKI_DATA_DIR"
  local dataset_dir="${FUSEKI_DATA_DIR}/${FUSEKI_DATASET}"
  mkdir -p "$dataset_dir"

  log "启动本机 Fuseki (port=${FUSEKI_PORT}, dataset=${FUSEKI_DATASET}, home=${FUSEKI_HOME})..."
  (
    cd "$FUSEKI_HOME"
    nohup env FUSEKI_HOME="$FUSEKI_HOME" FUSEKI_BASE="$FUSEKI_DATA_DIR" \
      ./fuseki-server --port="$FUSEKI_PORT" --update --loc="$dataset_dir" "/${FUSEKI_DATASET}" \
      >>"$FUSEKI_LOG_FILE" 2>&1 &
    echo $! >"$FUSEKI_PID_FILE"
  )
  wait_fuseki 90
}

stop_fuseki_native() {
  local pid
  pid="$(read_native_fuseki_pid || true)"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    log "停止本机 Fuseki (pid=${pid})..."
    kill "$pid" 2>/dev/null || true
    sleep 1
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$FUSEKI_PID_FILE"
}

should_use_docker() {
  case "$FUSEKI_LAUNCHER" in
    docker) return 0 ;;
    native) return 1 ;;
    auto)
      if native_fuseki_available; then
        return 1
      fi
      return 0
      ;;
    *) return 0 ;;
  esac
}

start_fuseki() {
  if fuseki_ping && fuseki_dataset_ready; then
    log "Fuseki 已在运行 (${FUSEKI_URL})"
    return 0
  fi

  if ! should_use_docker; then
    start_fuseki_native
    return $?
  fi

  if ! has_docker; then
    if native_fuseki_available; then
      start_fuseki_native
      return $?
    fi
    log "未检测到 Docker，且未找到本机 Fuseki (${FUSEKI_HOME}/fuseki-server)"
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
  stop_fuseki_native
  if has_docker; then
    log "停止 Fuseki 容器..."
    compose stop fuseki 2>/dev/null || true
  fi
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
  if [[ -f "$FUSEKI_LOG_FILE" ]]; then
    tail -f -n 100 "$FUSEKI_LOG_FILE"
    exit 0
  fi
  if has_docker; then
    compose logs -f --tail=100 fuseki
    exit 0
  fi
  log "无 Fuseki 日志 (${FUSEKI_LOG_FILE})"
  exit 0
}

usage() {
  cat <<EOF
用法: ./scripts/fuseki.sh <start|stop|restart|status|wait|logs>

优先使用本机 Fuseki（.run/apache-jena-fuseki-*），否则回退 Docker。

环境变量（.env）:
  FUSEKI_URL=http://localhost:3030
  FUSEKI_DATASET=datalens
  FUSEKI_HOME=.run/apache-jena-fuseki-6.1.0
  FUSEKI_LAUNCHER=auto|native|docker
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
