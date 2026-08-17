# Testing Guide — WhatsApp + Mail + Unified Dashboards

Everything below was verified working against your real Homebrew Postgres
(`wa_gateway` db) before this file was written: migrations, both WhatsApp
devices still connected, a real WhatsApp send, the full mail API round-trip
(encrypted password storage, worker call, DB writes, cascade delete), and
all 14 UI pages rendering with no errors.

## 1. Start everything

```bash
cd /Users/charantej/Desktop/wa_gateway
bash run_dev.sh
```

This now starts **three** processes: Django (`:8000`), the WhatsApp worker
(`:3000`), and the new mail worker (`:3002`). First run installs
`worker_mail/node_modules` automatically.

## 2. Health check (all three must return `ok`)

```bash
curl http://localhost:8000/health
curl http://localhost:3000/health
curl http://localhost:3002/health
```

## 3. Log in

Open `http://localhost:8000/app/` → sign in with your existing account (or
`admin` / `admin123` if untouched). You'll see the sidebar grouped into
**Overview / WhatsApp / Mail**.

## 4. Test WhatsApp (unchanged flow, still works)

1. **Unified** → confirms both dashboards show live counts.
2. **WhatsApp → Devices** → your linked numbers should read `Connected`.
   (If not, click **Connect** and scan the QR.)
3. **WhatsApp → Send** → pick a connected device, send yourself a test
   message, confirm it arrives on your phone.
4. **WhatsApp → Messages** → the message appears with status `Process`/`Sent`.
5. **WhatsApp → Inbox** → reply from your phone, refresh — it should appear
   here (and the bell icon should ring).

## 5. Test Mail (new flow)

1. **Mail → Accounts** → **Add a Mail Account**. For Gmail:
   - IMAP Host: `imap.gmail.com`, Port `993`
   - SMTP Host: `smtp.gmail.com`, Port `587`
   - Username/Password: your Gmail address + a 16-char **App Password**
     (Google Account → Security → App Passwords — a normal password will
     be rejected by Gmail).
2. Click **Connect** on the new row → should flip to `Connected`. If it
   fails, the exact IMAP error (auth failed, DNS, etc.) shows in a toast.
3. **Mail → Compose** → send yourself a test email → check it lands in
   your real inbox.
4. **Mail → Sent** → the email shows `Sent`.
5. **Mail → Accounts** → click **Sync** → pulls recent inbox mail into
   Postgres.
6. **Mail → Inbox** → synced emails appear here. Click **Sync** again —
   the list should **not** grow (dedupe on `message_id` is working).

## 6. Test the Unified dashboard

**Overview → Unified** → shows WhatsApp + Mail side by side: device/account
counts, connected counts, messages/emails sent, pending/failed, and one
merged "Recent Activity" feed sorted by time with a WhatsApp/Mail tag on
each row.

## 7. Verify data actually lands in Postgres (optional, for peace of mind)

```bash
psql -U postgres -d wa_gateway -c "select name,status from api_device;"
psql -U postgres -d wa_gateway -c "select name,status from api_mailaccount;"
psql -U postgres -d wa_gateway -c "select to_addr,status from api_email order by created_at desc limit 5;"
psql -U postgres -d wa_gateway -c "select sender,subject from api_incomingemail order by received_at desc limit 5;"
```

## Notes

- Mail passwords are encrypted at rest (Fernet) — `password_enc` in
  `api_mailaccount` is never plaintext.
- Mail sync is on-demand (the **Sync** button) — there's no background
  poller, matching how WhatsApp's QR-connect flow already works.
- Stop all three services with `Ctrl+C` in the `run_dev.sh` terminal.
