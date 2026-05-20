#!/usr/bin/env bash
set -euo pipefail

# ════════════════════════════════════════════════════════════
# DataLens 制造业路演 - 一键执行脚本
#
# 流程：
#   1. 生成 MySQL 测试数据（需 MySQL 运行中）
#   2. 启动 DataLens 后端 + 前端服务
#   3. 运行 Playwright E2E 测试
#   4. 生成测试报告
#
# 使用：
#   chmod +x scripts/run-all.sh
#   ./scripts/run-all.sh
#
# 环境变量配置：
#   MYSQL_HOST      (默认 127.0.0.1)
#   MYSQL_PORT      (默认 3306)
#   MYSQL_USER      (默认 root)
#   MYSQL_PASSWORD  (默认 空)
# ════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
E2E_DIR="$SCRIPT_DIR/e2e"
SCREENSHOTS_DIR="$E2E_DIR/screenshots"
TEST_RESULTS_DIR="$E2E_DIR/test-results"

# ── 颜色 ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ── 配置 ──
MYSQL_HOST="${MYSQL_HOST:-127.0.0.1}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
MYSQL_USER="${MYSQL_USER:-root}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
BACKEND_PORT="${BACKEND_PORT:-8000}"

step=0

# ── 辅助函数 ──

print_step() {
  step=$((step + 1))
  echo ""
  echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
  echo -e "${CYAN} Step $step: $1${NC}"
  echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
  echo ""
}

print_ok() {
  echo -e "${GREEN}  ✔ $1${NC}"
}

print_warn() {
  echo -e "${YELLOW}  ⚠ $1${NC}"
}

print_fail() {
  echo -e "${RED}  ✘ $1${NC}"
}

check_command() {
  if ! command -v "$1" &>/dev/null; then
    print_fail "需要 $1，请先安装"
    exit 1
  fi
}

wait_for_http() {
  local url="$1"
  local label="$2"
  local timeout="${3:-60}"
  local waited=0
  echo -n "  等待 $label 启动..."
  while ! curl -sf "$url" >/dev/null 2>&1; do
    if [ "$waited" -ge "$timeout" ]; then
      echo ""
      print_fail "$label 启动超时"
      return 1
    fi
    sleep 2
    waited=$((waited + 2))
    echo -n "."
  done
  echo ""
  print_ok "$label 已就绪"
}

cleanup() {
  echo ""
  print_step "清理"
  if [ -f "$PROJECT_DIR/.run/backend.pid" ]; then
    kill "$(cat "$PROJECT_DIR/.run/backend.pid")" 2>/dev/null || true
    print_ok "后端已停止"
  fi
  if [ -f "$PROJECT_DIR/.run/frontend.pid" ]; then
    kill "$(cat "$PROJECT_DIR/.run/frontend.pid")" 2>/dev/null || true
    print_ok "前端已停止"
  fi
}
trap cleanup EXIT

# ════════════════════════════════════════════════════════════
# Step 1: 环境检查
# ════════════════════════════════════════════════════════════
print_step "检查依赖环境"

check_command python3
check_command node
check_command mysql
check_command npx

PYTHON_VERSION=$(python3 --version)
NODE_VERSION=$(node --version)
print_ok "Python: $PYTHON_VERSION"
print_ok "Node: $NODE_VERSION"

# 检查 MySQL 连接
echo ""
echo "  测试 MySQL 连接..."
if mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" ${MYSQL_PASSWORD:+-p"$MYSQL_PASSWORD"} -e "SELECT VERSION()" 2>/dev/null; then
  print_ok "MySQL 连接成功"
else
  print_fail "无法连接 MySQL ($MYSQL_HOST:$MYSQL_PORT)，请确保 MySQL 已启动"
  print_warn "可设置环境变量 MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASSWORD"
  exit 1
fi

# 检查 PostgreSQL
echo ""
echo "  检查 PostgreSQL..."
if command -v psql &>/dev/null; then
  print_ok "PostgreSQL 客户端可用"
else
  print_warn "psql 未安装，将跳过 PostgreSQL 检查"
fi

# 检查 pip 依赖
echo ""
echo "  检查 Python 依赖..."
pip install pymysql -q 2>/dev/null && print_ok "pymysql 已安装" || print_warn "pymysql 安装失败"

# ════════════════════════════════════════════════════════════
# Step 2: 生成并导入测试数据
# ════════════════════════════════════════════════════════════
print_step "生成制造业测试数据"

echo "  正在生成 ~60 万行制造业仿真数据..."
echo "  (如需调整数据量，请修改命令行参数)"

python3 "$SCRIPT_DIR/manufacturing_seed_data.py" \
  --host "$MYSQL_HOST" \
  --port "$MYSQL_PORT" \
  --user "$MYSQL_USER" \
  ${MYSQL_PASSWORD:+--password "$MYSQL_PASSWORD"} \
  --database "manufacturing_demo" \
  --seed 20260501

print_ok "测试数据生成完成"

# 验证数据
echo ""
echo "  验证数据..."
TABLE_COUNT=$(mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" ${MYSQL_PASSWORD:+-p"$MYSQL_PASSWORD"} -N -e "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='manufacturing_demo'" 2>/dev/null)
print_ok "manufacturing_demo 数据库已就绪，$TABLE_COUNT 张表"

# ════════════════════════════════════════════════════════════
# Step 3: 检查 .env 配置
# ════════════════════════════════════════════════════════════
print_step "检查服务配置"

if [ ! -f "$PROJECT_DIR/.env" ]; then
  print_warn ".env 文件不存在，从 .env.example 创建"
  cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
  print_warn "请编辑 .env 文件配置 DATABASE_URL 和 DEEPSEEK_API_KEY/OPENAI_API_KEY"
  echo ""
  echo "  按 Enter 继续（或 Ctrl+C 中止编辑）..."
  read -r
fi

# 提示配置 API Key
if grep -q "DEEPSEEK_API_KEY=$" "$PROJECT_DIR/.env" || grep -q "OPENAI_API_KEY=$" "$PROJECT_DIR/.env"; then
  print_warn "LLM API Key 未配置！"
  print_warn "问答功能将使用 fallback 模式，效果会显著下降"
  print_warn "路演前建议配置 DEEPSEEK_API_KEY 或 OPENAI_API_KEY"
  echo ""
  echo "  按 Enter 继续..."
  read -r
fi

# ════════════════════════════════════════════════════════════
# Step 4: 安装 Node 依赖
# ════════════════════════════════════════════════════════════
print_step "安装依赖"

echo "  检查 Playwright 依赖..."
cd "$E2E_DIR"
if [ ! -d "node_modules" ]; then
  npm install
  print_ok "Playwright 依赖安装完成"
else
  print_ok "Playwright 依赖已安装"
fi

# 安装浏览器（不输出太多信息）
npx playwright install chromium 2>/dev/null || npx playwright install chromium
print_ok "Chromium 浏览器已就绪"

# ════════════════════════════════════════════════════════════
# Step 5: 启动后端和前端服务
# ════════════════════════════════════════════════════════════
print_step "启动 DataLens 服务"

cd "$PROJECT_DIR"

# 启动后端
echo "  启动后端 (端口 $BACKEND_PORT)..."
mkdir -p "$PROJECT_DIR/.run/logs"
cd backend
uvicorn main:app --host 0.0.0.0 --port "$BACKEND_PORT" >"$PROJECT_DIR/.run/logs/backend.log" 2>&1 &
echo $! >"$PROJECT_DIR/.run/backend.pid"
cd "$PROJECT_DIR"

# 等待后端就绪
wait_for_http "http://127.0.0.1:$BACKEND_PORT/health" "后端服务" 60

# 启动前端
echo ""
echo "  启动前端 (端口 $FRONTEND_PORT)..."
cd frontend
npm run dev -- -p "$FRONTEND_PORT" >"$PROJECT_DIR/.run/logs/frontend.log" 2>&1 &
echo $! >"$PROJECT_DIR/.run/frontend.pid"
cd "$PROJECT_DIR"

# 等待前端就绪
wait_for_http "http://127.0.0.1:$FRONTEND_PORT" "前端服务" 120

# ════════════════════════════════════════════════════════════
# Step 6: 运行 E2E 测试
# ════════════════════════════════════════════════════════════
print_step "运行 Playwright E2E 自动化测试"

export MYSQL_HOST MYSQL_PORT MYSQL_USER MYSQL_PASSWORD
export NEXT_PUBLIC_API_URL="http://127.0.0.1:$BACKEND_PORT"
export FRONTEND_URL="http://localhost:$FRONTEND_PORT"

mkdir -p "$SCREENSHOTS_DIR" "$TEST_RESULTS_DIR"
cd "$E2E_DIR"

echo "  Report: $TEST_RESULTS_DIR/report/index.html"
echo "  Screenshots: $SCREENSHOTS_DIR/"
echo ""

# 逐场景执行
for spec in scenario-1-datasource scenario-2-domain scenario-3-knowledgebase scenario-4-copilot scenario-5-search; do
  echo ""
  echo -e "${CYAN}── 测试: $spec ──${NC}"
  if npx playwright test "${spec}.spec.ts" --config playwright.config.ts; then
    print_ok "$spec 通过"
  else
    print_warn "$spec 部分失败（详见报告）"
  fi
done

# ════════════════════════════════════════════════════════════
# Step 7: 生成报告
# ════════════════════════════════════════════════════════════
print_step "测试完成"

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}  路演测试完成！${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo ""
echo "  测试报告:"
echo "    HTML:  file://$TEST_RESULTS_DIR/report/index.html"
echo "    截图:  $SCREENSHOTS_DIR/"
echo ""
echo "  服务仍在运行："
echo "    后端: http://127.0.0.1:$BACKEND_PORT"
echo "    前端: http://localhost:$FRONTEND_PORT"
echo ""
echo "  手动停止服务: ./scripts/service.sh stop"
echo ""
echo "  查看截图: open $SCREENSHOTS_DIR/"
echo ""
