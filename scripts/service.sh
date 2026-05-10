#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
RUNTIME_DIR="$ROOT_DIR/.run"
LOG_DIR="$RUNTIME_DIR/logs"

BACKEND_PID_FILE="$RUNTIME_DIR/backend.pid"
FRONTEND_PID_FILE="$RUNTIME_DIR/frontend.pid"
BACKEND_LOG_FILE="$LOG_DIR/backend.log"
FRONTEND_LOG_FILE="$LOG_DIR/frontend.log"

BACKEND_PORT_DEFAULT=8000
FRONTEND_PORT_DEFAULT=3000
BACKEND_PORT="$BACKEND_PORT_DEFAULT"
FRONTEND_PORT="$FRONTEND_PORT_DEFAULT"

if [[ -f "$ROOT_DIR/.env" ]]; then
  # shellcheck disable=SC1090
  source "$ROOT_DIR/.env"
  BACKEND_PORT="${BACKEND_PORT:-$BACKEND_PORT_DEFAULT}"
  FRONTEND_PORT="${FRONTEND_PORT:-$FRONTEND_PORT_DEFAULT}"
fi

mkdir -p "$LOG_DIR"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

# 优先使用项目虚拟环境里的 Python（与 README / 日常开发一致）
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3 || true)"
fi
if [[ -z "$PYTHON_BIN" ]]; then
  log "错误: 未找到可执行的 Python（请先: python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt）"
  exit 1
fi
if [[ "$PYTHON_BIN" != "$ROOT_DIR/.venv/bin/python" ]]; then
  log "警告: 未使用 .venv，当前 Python 为: ${PYTHON_BIN} (若缺依赖请先创建虚拟环境并 pip install -r backend/requirements.txt)"
fi

is_pid_running() {
  local pid="$1"
  if [[ -z "$pid" ]]; then
    return 1
  fi
  kill -0 "$pid" >/dev/null 2>&1
}

read_pid_file() {
  local file="$1"
  if [[ -f "$file" ]]; then
    tr -d '[:space:]' <"$file"
    return 0
  fi
  return 1
}

remove_pid_file_if_stale() {
  local file="$1"
  local pid
  pid="$(read_pid_file "$file" || true)"
  if [[ -n "${pid:-}" ]] && ! is_pid_running "$pid"; then
    rm -f "$file"
  fi
}

port_pids() {
  local port="$1"
  # 每行一个 PID，去重（reload 时父/子进程可能同时出现在 LISTEN）
  lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | tr ' ' '\n' | awk 'NF' | sort -u || true
}

stop_pid() {
  local pid="$1"
  if ! is_pid_running "$pid"; then
    return 0
  fi

  kill "$pid" >/dev/null 2>&1 || true
  sleep 1

  if is_pid_running "$pid"; then
    kill -9 "$pid" >/dev/null 2>&1 || true
  fi
}

start_backend() {
  remove_pid_file_if_stale "$BACKEND_PID_FILE"
  local pid
  pid="$(read_pid_file "$BACKEND_PID_FILE" || true)"
  if [[ -n "${pid:-}" ]] && is_pid_running "$pid"; then
    log "后端已在运行 (pid=$pid)"
    return 0
  fi

  local occupied
  occupied="$(port_pids "$BACKEND_PORT")"
  if [[ -n "$occupied" ]]; then
    log "检测到后端端口 $BACKEND_PORT 被占用，先清理: $occupied"
    while IFS= read -r p; do
      [[ -n "$p" ]] && stop_pid "$p"
    done <<<"$occupied"
  fi

  log "启动后端服务: http://localhost:${BACKEND_PORT} (Python: ${PYTHON_BIN})"
  (
    cd "$BACKEND_DIR"
    nohup "$PYTHON_BIN" -m uvicorn main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT" >>"$BACKEND_LOG_FILE" 2>&1 &
    echo $! >"$BACKEND_PID_FILE"
  )
  sleep 2
  # nohup 的 $! 多为 uvicorn 父进程；以端口上实际 LISTEN 的 PID 为准，便于 stop/restart 杀干净
  local listen_pid
  listen_pid="$(port_pids "$BACKEND_PORT" | head -n1 || true)"
  if [[ -n "$listen_pid" ]]; then
    echo "$listen_pid" >"$BACKEND_PID_FILE"
  fi
  pid="$(read_pid_file "$BACKEND_PID_FILE" || true)"
  if [[ -n "${pid:-}" ]] && is_pid_running "$pid"; then
    log "后端启动成功 (pid=$pid, log=$BACKEND_LOG_FILE)"
  else
    log "后端启动失败，请检查日志: $BACKEND_LOG_FILE"
    return 1
  fi
}

start_frontend() {
  remove_pid_file_if_stale "$FRONTEND_PID_FILE"
  local pid
  pid="$(read_pid_file "$FRONTEND_PID_FILE" || true)"
  if [[ -n "${pid:-}" ]] && is_pid_running "$pid"; then
    log "前端已在运行 (pid=$pid)"
    return 0
  fi

  local occupied
  occupied="$(port_pids "$FRONTEND_PORT")"
  if [[ -n "$occupied" ]]; then
    log "检测到前端端口 $FRONTEND_PORT 被占用，先清理: $occupied"
    while IFS= read -r p; do
      [[ -n "$p" ]] && stop_pid "$p"
    done <<<"$occupied"
  fi

  log "启动前端服务: http://localhost:$FRONTEND_PORT"
  (
    cd "$FRONTEND_DIR"
    # 直接启动 next，避免 nohup 记录到 npx 壳进程 PID（stop 时杀不掉仍在监听的 node）
    nohup npx --yes next dev -H 0.0.0.0 -p "$FRONTEND_PORT" >>"$FRONTEND_LOG_FILE" 2>&1 &
    echo $! >"$FRONTEND_PID_FILE"
  )
  sleep 3
  local listen_pid
  listen_pid="$(port_pids "$FRONTEND_PORT" | head -n1 || true)"
  if [[ -n "$listen_pid" ]]; then
    echo "$listen_pid" >"$FRONTEND_PID_FILE"
  fi
  pid="$(read_pid_file "$FRONTEND_PID_FILE" || true)"
  if [[ -n "${pid:-}" ]] && is_pid_running "$pid"; then
    log "前端启动成功 (pid=$pid, log=$FRONTEND_LOG_FILE)"
  else
    log "前端启动失败，请检查日志: $FRONTEND_LOG_FILE"
    return 1
  fi
}

stop_backend() {
  local pid
  pid="$(read_pid_file "$BACKEND_PID_FILE" || true)"
  if [[ -n "${pid:-}" ]]; then
    log "停止后端进程 pid=$pid"
    stop_pid "$pid"
    rm -f "$BACKEND_PID_FILE"
  fi

  local occupied
  occupied="$(port_pids "$BACKEND_PORT")"
  if [[ -n "$occupied" ]]; then
    log "清理后端端口残留进程: $occupied"
    while IFS= read -r p; do
      [[ -n "$p" ]] && stop_pid "$p"
    done <<<"$occupied"
  fi
}

stop_frontend() {
  local pid
  pid="$(read_pid_file "$FRONTEND_PID_FILE" || true)"
  if [[ -n "${pid:-}" ]]; then
    log "停止前端进程 pid=$pid"
    stop_pid "$pid"
    rm -f "$FRONTEND_PID_FILE"
  fi

  local occupied
  occupied="$(port_pids "$FRONTEND_PORT")"
  if [[ -n "$occupied" ]]; then
    log "清理前端端口残留进程: $occupied"
    while IFS= read -r p; do
      [[ -n "$p" ]] && stop_pid "$p"
    done <<<"$occupied"
  fi
}

status() {
  local bpid fpid
  bpid="$(read_pid_file "$BACKEND_PID_FILE" || true)"
  fpid="$(read_pid_file "$FRONTEND_PID_FILE" || true)"

  if [[ -n "${bpid:-}" ]] && is_pid_running "$bpid"; then
    log "后端: 运行中 (pid=$bpid, port=$BACKEND_PORT)"
  else
    log "后端: 未运行 (port=$BACKEND_PORT)"
  fi

  if [[ -n "${fpid:-}" ]] && is_pid_running "$fpid"; then
    log "前端: 运行中 (pid=$fpid, port=$FRONTEND_PORT)"
  else
    log "前端: 未运行 (port=$FRONTEND_PORT)"
  fi
}

usage() {
  cat <<EOF
用法: ./scripts/service.sh <start|stop|restart|status>

命令:
  start    启动前后端服务
  stop     停止前后端服务
  restart  重启前后端服务
  status   查看服务状态
EOF
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    start)
      start_backend
      start_frontend
      status
      ;;
    stop)
      stop_frontend
      stop_backend
      status
      ;;
    restart)
      stop_frontend
      stop_backend
      start_backend
      start_frontend
      status
      ;;
    status)
      status
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
