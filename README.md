# WhatsApp Gateway — Fonnte Clone (Django + Node.js + Baileys)

A complete, runnable WhatsApp API gateway that replicates Fonnte's functionality.
The main codebase is **Django (Python)**; the WhatsApp WebSocket layer runs on a
small **Node.js + Baileys** worker microservice.

---

## What This Project Does

- Link any WhatsApp number by scanning a QR code (just like Fonnte)
- Send single + bulk messages via REST API
- Receive inbound messages via webhooks
- Auto-reply / chatbot support
- Validate numbers (check if registered on WhatsApp)
- Multi-device, multi-tenant (one account → many devices)
- Packages, quotas, rate limiting (matching Fonnte's model)

---

## Architecture Overview

```
  Your Client App                    Django Backend                Node.js Worker
  (cURL / code)                      (Python)                      (Baileys)
                                                
  POST /send ───────────────────────▶ api/views.py                 
                                      │ validates token            
                                      │ checks quota                
                                      │ enqueues to worker ───────▶ worker/index.js
                                      │                              │ sessionManager.js
                                      │                              │ Baileys WASocket
                                      │                              │   │
                                      │                              │   ▼
                                      │                              │ WhatsApp servers
                                      │                              │ (WebSocket)
                                      │                              │   │
                                      │   ◀──── webhook ◀───────────┤   │ inbound msgs
                                      │   views.webhook_receiver()       │ status updates
                                      │   → stores in DB                 │ device status
                                      │   → forwards to user webhook     
```

**Why two services?** Django is the API gateway, auth, billing, dashboard. The
Node.js worker handles the WhatsApp WebSocket protocol via Baileys (which is a
TypeScript/JS library with no Python equivalent). They talk to each other over
HTTP — Django calls the worker to send messages / get QR; the worker calls
Django's webhook endpoint to deliver inbound messages and statuses.

---

## Prerequisites

Install these on your machine before starting:

1. **Python 3.12+** — https://www.python.org/downloads/
2. **Node.js 20+** — https://nodejs.org/
3. **Git** (optional, for cloning)

Verify they are installed:
```bash
python3 --version    # should show 3.12 or higher
node --version       # should show v20 or higher
npm --version        # comes with Node.js
```

---

## Quick Start (Two Options)

### OPTION A: Docker (easiest — everything in containers)

```bash
# 1. Unzip the project
unzip wa_gateway.zip
cd wa_gateway

# 2. Start everything (Django + Worker + PostgreSQL)
docker compose up --build

# 3. In a new terminal, run migrations + create admin
docker compose exec django python manage.py migrate
docker compose exec django python manage.py createsuperuserauto
```

Done! Skip to the "Testing the API" section below.

---

### OPTION B: Local Development (no Docker)

#### Step 1: Unzip and enter the project

```bash
unzip wa_gateway.zip
cd wa_gateway
```

#### Step 2: Copy the environment file

```bash
cp .env.example .env
```

The defaults in `.env` use SQLite (no PostgreSQL needed) and are ready for
local development. If you want PostgreSQL, set `USE_SQLITE=false` and fill in
the DB credentials.

#### Step 3: Set up the Django backend (Python)

```bash
cd django

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run database migrations
python manage.py makemigrations api
python manage.py migrate

# Create default superuser + demo account
python manage.py createsuperuserauto

# Start the Django server (leave this terminal running)
python manage.py runserver 0.0.0.0:8000
```

You should see:
```
Starting development server at http://0.0.0.0:8000/
```

**Keep this terminal open.** Open a new terminal for Step 4.

#### Step 4: Set up the Node.js worker (Baileys)

```bash
cd wa_gateway/worker

# Install dependencies
npm install

# Start the worker (leave this terminal running)
node index.js
```

You should see:
```
========================================
  WhatsApp Gateway Worker (Baileys)
  Listening on port 3000
========================================
```

**Keep this terminal open too.** Both Django (port 8000) and the worker
(port 3000) must be running simultaneously.

#### Step 5: One-command startup (optional, for future runs)

Instead of Steps 3+4 manually, you can use the dev script:

```bash
cd wa_gateway
bash run_dev.sh
```

This script sets up venv, installs deps, runs migrations, and starts both
Django and the worker in one terminal.

---

## Testing the API — Step by Step

Now that both services are running, follow these steps to send your first
WhatsApp message.

### Step 1: Get your tokens

When you ran `createsuperuserauto`, it printed two tokens:

- **Account token** — for creating devices (e.g. `abc123...`)
- **Device token** — for sending messages (e.g. `xyz789...`)

You can also find tokens at:
- Django admin: http://localhost:8000/admin/ (login: admin / admin123)
- Dashboard: http://localhost:8000/dashboard

Set them as shell variables for convenience:

```bash
# Replace these with your actual tokens
ACCOUNT_TOKEN="your_account_token_here"
DEVICE_TOKEN="your_device_token_here"
```

### Step 2: Add a device (if not already created)

```bash
curl -X POST http://localhost:8000/add-device \
  -H "Authorization: $ACCOUNT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "My WhatsApp", "device": "919876543210"}'
```

Replace `919876543210` with your actual phone number (country code + number,
no + or spaces). Note the `token` in the response — that is your device token.

### Step 3: Get the QR code and link WhatsApp

```bash
curl -X POST http://localhost:8000/qr \
  -H "Authorization: $DEVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type": "qr"}'
```

The response contains a base64-encoded PNG QR code:
```json
{"status": true, "url": "iVBORw0KGgoAAAANSUhEUgAA..."}
```

To view the QR code, save it to an HTML file and open in your browser:

```bash
# Save QR to an HTML file
echo '<img src="data:image/png;base64,'$(curl -s -X POST http://localhost:8000/qr -H "Authorization: $DEVICE_TOKEN" -H "Content-Type: application/json" -d '{"type":"qr"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['url'])")'" />' > qr.html

# Open in browser
open qr.html        # macOS
xdg-open qr.html    # Linux
start qr.html       # Windows
```

Now open WhatsApp on your phone → Settings → Linked Devices → Link a Device →
scan the QR code. Once linked, the device status changes to "connect".

### Step 4: Verify the device is connected

```bash
curl -X POST http://localhost:8000/device \
  -H "Authorization: $DEVICE_TOKEN"
```

Response:
```json
{
  "status": true,
  "device": "919876543210",
  "device_status": "connect",
  "package": "free",
  "quota": 1000
}
```

### Step 5: Send your first message

```bash
curl -X POST http://localhost:8000/send \
  -H "Authorization: $DEVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "target": "919812345678",
    "message": "Hello! This is a test from my WhatsApp gateway."
  }'
```

Replace `919812345678` with the recipient's number. The message should arrive
on their WhatsApp within seconds.

Response:
```json
{
  "status": true,
  "id": ["<message-uuid>"],
  "target": ["919812345678"],
  "process": "process"
}
```

### Step 6: Send bulk messages with variables

```bash
curl -X POST http://localhost:8000/send \
  -H "Authorization: $DEVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "target": "919812345678|John|Admin,919876543210|Jane|User",
    "message": "Hi {name}! You are registered as {var1}.",
    "delay": "1-5"
  }'
```

This sends two personalized messages with a random 1-5 second delay between
them (anti-ban feature, same as Fonnte).

### Step 7: Validate numbers

```bash
curl -X POST http://localhost:8000/validate \
  -H "Authorization: $DEVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target": "919812345678,919876543210", "countryCode": "91"}'
```

Response:
```json
{
  "status": true,
  "registered": ["919812345678"],
  "not_registered": ["919876543210"]
}
```

### Step 8: Send an image/file (requires super/advanced/ultra package)

First upgrade the device in Django admin (set package to "super"), then:

```bash
curl -X POST http://localhost:8000/send \
  -H "Authorization: $DEVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "target": "919812345678",
    "message": "Check this image!",
    "url": "https://via.placeholder.com/600x400"
  }'
```

### Step 9: Set up a webhook (receive incoming messages)

1. Edit your device in Django admin → set `webhook_url` to your server URL
   (e.g. `https://yourapp.com/webhook`). Set `autoread` to ON.

2. On your server, create an endpoint that accepts POST requests. Example
   in Flask/Python:

```python
from flask import Flask, request
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    print(f"Incoming from {data.get('sender')}: {data.get('message')}")

    # Auto-reply example
    if data.get('message', '').lower() == 'hi':
        # Send reply via the gateway API
        import requests
        requests.post('http://localhost:8000/send', json={
            'target': data['sender'].split('@')[0],
            'message': 'Hello! How can I help you?'
        }, headers={'Authorization': 'YOUR_DEVICE_TOKEN'})
    return '', 200
```

3. Any WhatsApp message sent to your linked number will now arrive at your
   webhook URL as a JSON POST.

---

## API Endpoints Reference

| Endpoint | Method | Auth | Purpose |
|---|---|---|---|
| `/send` | POST | device token | Send message (single/bulk) |
| `/qr` | POST | device token | Get QR code / pairing code |
| `/validate` | POST | device token | Check if numbers are on WhatsApp |
| `/device` | POST | device token | Get device info (quota, status) |
| `/disconnect` | POST | device token | Disconnect WhatsApp |
| `/typing` | POST | device token | Send typing indicator |
| `/delete-message` | POST | device token | Cancel a queued message |
| `/reschedule` | POST | device token | Reschedule a pending message |
| `/add-device` | POST | account token | Create a new device |
| `/webhook/incoming` | POST | internal | Worker → Django webhook |
| `/dashboard` | GET | none | HTML dashboard |
| `/admin/` | GET | Django admin | Admin panel |

---

## /send Parameters

| Parameter | Required | Description |
|---|---|---|
| `target` | Yes | Phone number(s), comma-separated. Supports `\|` for variables. |
| `message` | No | Text message (max 6000 chars). Supports `{name}`, `{var1}`, `{var2}`. |
| `url` | No | Public URL of attachment (super/advanced/ultra only). |
| `file` | No | Binary file upload (multipart form). |
| `schedule` | No | Unix timestamp to schedule the message. |
| `delay` | No | Delay between messages: `"2"` or `"1-10"` for random. |
| `countryCode` | No | Replace leading 0 with this code. Default: 91 (India). |
| `location` | No | `latitude,longitude` to send a location pin. |
| `typing` | No | `true` to show typing indicator before sending. |
| `followup` | No | Seconds to wait before sending (follow-up delay). |
| `inboxid` | No | Message ID to reply to (threaded reply). |
| `preview` | No | `true` to generate link previews (default true). |
| `connectOnly` | No | `true` to fail if device disconnected (instead of queueing). |

---

## Project Structure

```
wa_gateway/
├── django/                          ← Main backend (Python)
│   ├── manage.py
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── wa_gateway/                   ← Django project config
│   │   ├── __init__.py
│   │   ├── settings.py
│   │   ├── urls.py
│   │   ├── wsgi.py
│   │   └── asgi.py
│   ├── api/                          ← API app
│   │   ├── __init__.py
│   │   ├── models.py                ← Device, Message, Contact, Account...
│   │   ├── views.py                 ← All API endpoint logic
│   │   ├── urls.py                   ← URL routing
│   │   ├── auth.py                  ← Token authentication
│   │   ├── utils.py                 ← Phone normalization, variables, etc.
│   │   ├── admin.py                 ← Django admin config
│   │   ├── apps.py
│   │   ├── migrations/
│   │   └── management/
│   │       └── commands/
│   │           └── createsuperuserauto.py
│   └── templates/
│       └── dashboard.html           ← Simple HTML dashboard
├── worker/                           ← Node.js Baileys worker
│   ├── package.json
│   ├── index.js                     ← Express HTTP server
│   ├── sessionManager.js            ← Baileys WhatsApp session management
│   └── Dockerfile
├── docker-compose.yml               ← Docker setup (Django + Worker + Postgres)
├── .env.example                     ← Environment variables template
├── .gitignore
├── run_dev.sh                       ← One-command dev startup script
└── README.md                        ← This file
```

---

## Troubleshooting

**Q: The QR code endpoint returns `"device already connect"`**
A: The device is already linked. To re-link, first call `/disconnect`, then `/qr`.

**Q: Messages are not being sent**
A: Check that:
1. Django is running (http://localhost:8000/health → `{"status":"ok"}`)
2. Worker is running (http://localhost:3000/health → `{"status":"ok"}`)
3. Device status is "connect" (call `/device` to check)
4. You have quota remaining

**Q: Worker shows "Device not connected" error**
A: The WhatsApp session was lost. Call `/qr` again and re-scan the QR code.

**Q: `npm install` fails for Baileys**
A: Make sure you have Node.js 20+. Run `node --version` to check. If the
install still fails, try: `npm install --legacy-peer-deps`

**Q: Django migration error "No module named api"**
A: Make sure you are in the `django/` directory when running `manage.py`.

**Q: Port already in use**
A: Kill the process using the port:
```bash
# Find and kill process on port 8000
lsof -ti:8000 | xargs kill -9     # macOS/Linux
netstat -ano | findstr :8000      # Windows

# Or use a different port
python manage.py runserver 0.0.0.0:8080
```
Remember to update `WORKER_BASE_URL` and `DJANGO_WEBHOOK_URL` in `.env` if you
change ports.

---

## Important Legal & Safety Notes

This is an **unofficial** WhatsApp gateway. It uses the WhatsApp Web linked-device
protocol via the Baileys library — NOT Meta's official WhatsApp Business API.

- **WhatsApp can ban numbers** that use unofficial automation. Use a secondary
  number, not your primary personal number.
- Use random delays (`delay=1-10`) for bulk sending to reduce ban risk.
- Only message people who have opted in. Spam triggers bans fastest.
- For regulated/commercial use (healthcare, finance, large-scale marketing),
  use Meta's official WhatsApp Cloud API instead.
- The authors of this code are not responsible for any WhatsApp account bans.

---

## Tech Stack Summary

| Layer | Technology |
|---|---|
| API Gateway | Django 4.2 + Django REST Framework |
| WhatsApp Engine | Node.js 20 + Baileys (@whiskeysockets/baileys) |
| Database | PostgreSQL 16 (or SQLite for dev) |
| Worker comms | Express.js (HTTP) |
| Auth | Token-based (per-device + per-account) |
| Containerization | Docker + Docker Compose |
| WhatsApp protocol | Multi-device WebSocket (same as WhatsApp Web) |
