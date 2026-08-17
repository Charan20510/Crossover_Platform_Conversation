#!/bin/bash
# ============================================================
# Development startup script — runs Django + Node worker together
# Usage:  bash run_dev.sh
# ============================================================

set -e

echo "============================================"
echo "  WhatsApp Gateway - Dev Startup"
echo "============================================"

# ---- Load .env ----
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

# ---- Defaults ----
export DJANGO_DEBUG=${DJANGO_DEBUG:-True}
export USE_SQLITE=${USE_SQLITE:-true}
export WORKER_BASE_URL=${WORKER_BASE_URL:-http://localhost:3000}
export DJANGO_WEBHOOK_URL=${DJANGO_WEBHOOK_URL:-http://localhost:8000/webhook/incoming}
export WORKER_PORT=${WORKER_PORT:-3000}
export MAIL_WORKER_BASE_URL=${MAIL_WORKER_BASE_URL:-http://localhost:3002}
export DJANGO_MAIL_WEBHOOK_URL=${DJANGO_MAIL_WEBHOOK_URL:-http://localhost:8000/webhook/mail}
export WORKER_MAIL_PORT=${WORKER_MAIL_PORT:-3002}
export DEFAULT_COUNTRY_CODE=${DEFAULT_COUNTRY_CODE:-91}

# ---- Check Python ----
if ! command -v python3 &> /dev/null; then
  echo "ERROR: python3 not found. Install Python 3.12+ first."
  exit 1
fi

# ---- Check Node ----
if ! command -v node &> /dev/null; then
  echo "ERROR: node not found. Install Node.js 20+ first."
  exit 1
fi

echo ""
echo "1. Setting up Python virtual environment..."
cd django
if [ ! -d venv ]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install -q -r requirements.txt

echo ""
echo "2. Running Django migrations..."
python manage.py makemigrations api --noinput 2>/dev/null || true
python manage.py migrate --noinput

echo ""
echo "3. Starting Django dev server (port 8000)..."
python manage.py runserver 0.0.0.0:8000 &
DJANGO_PID=$!

echo ""
echo "4. Setting up Node worker..."
cd ../worker
if [ ! -d node_modules ]; then
  echo "   Installing Node dependencies (first run)..."
  npm install
fi

echo ""
echo "5. Starting Node worker (port 3000)..."
node index.js &
WORKER_PID=$!

echo ""
echo "6. Setting up Node mail worker..."
cd ../worker_mail
if [ ! -d node_modules ]; then
  echo "   Installing Node dependencies (first run)..."
  npm install
fi

echo ""
echo "7. Starting Node mail worker (port 3002)..."
node index.js &
WORKER_MAIL_PID=$!

echo ""
echo "============================================"
echo "  Django:       http://localhost:8000"
echo "  WA Worker:    http://localhost:3000"
echo "  Mail Worker:  http://localhost:3002"
echo "============================================"
echo ""
echo "Press Ctrl+C to stop all services."

# ---- Trap Ctrl+C ----
trap "echo ''; echo 'Shutting down...'; kill $DJANGO_PID $WORKER_PID $WORKER_MAIL_PID 2>/dev/null; exit 0" INT TERM

# Wait for both processes
wait
