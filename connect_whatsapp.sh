#!/bin/bash

DEVICE_TOKEN="${1:-YOUR_DEVICE_TOKEN}"
PHONE="${2:-91XXXXXXXXXX}"

echo "============================="
echo "  WhatsApp Connection Helper"
echo "============================="

echo ""
echo "0. Disconnecting existing session..."
curl -s -X POST http://localhost:8000/disconnect \
  -H "Authorization: $DEVICE_TOKEN" \
  -H "Content-Type: application/json" > /dev/null
sleep 2

echo ""
echo "1. Fetching QR code..."
QR_RESP=$(curl -s -X POST http://localhost:8000/qr \
  -H "Authorization: $DEVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"type\": \"qr\", \"whatsapp\": \"$PHONE\"}")

QR=$(echo "$QR_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('url',''))" 2>/dev/null)

if [ -n "$QR" ]; then
  echo "$QR" | base64 -d > /tmp/wa_qr.png
  open /tmp/wa_qr.png
  echo "   QR code opened in Preview — scan it with WhatsApp"
else
  echo "   QR failed: $(echo "$QR_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('reason','unknown'))" 2>/dev/null)"
fi

echo ""
echo "2. Fetching pairing code..."
CODE_RESP=$(curl -s -X POST http://localhost:8000/qr \
  -H "Authorization: $DEVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"type\": \"code\", \"whatsapp\": \"$PHONE\"}")

CODE=$(echo "$CODE_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('code',''))" 2>/dev/null)

if [ -n "$CODE" ]; then
  echo "   Pairing code: $CODE"
else
  echo "   Code failed: $(echo "$CODE_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('reason','unknown'))" 2>/dev/null)"
fi

echo ""
echo "============================="
echo "  How to connect:"
echo "  Option A (QR):   WhatsApp > Settings > Linked Devices > Link a Device > Scan QR"
echo "  Option B (Code): WhatsApp > Settings > Linked Devices > Link a Device > Use phone number instead"
echo "============================="
