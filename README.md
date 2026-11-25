# Invitation Studio

Customised digital invitation cards (envelope-open animation, arch photo, functions, RSVP) with a full admin panel and tracker.
Stack: Flask · SQLAlchemy · PostgreSQL (Neon) · Vercel.

## Features
- Admin: sign up / sign in / change password; each admin only sees their own invitations
- Design editor: names, messages, colours + 6 theme presets, fonts, header / hero (arch) / background image uploads, photo gallery
- Functions (Nikah, Reception…) with date, venue, map link, dress code, "Add to calendar"
- Guests: add one by one or bulk import (paste/CSV), unique personal link per guest, max seats per guest, groups
- Tracker: sent / opened (with count) / replied / attending / declined, headcount per function, live activity, "needs a nudge" list, filters, CSV export
- WhatsApp share + reminder buttons with editable message templates (auto-marks guest as "sent")
- Per function: Google Maps + Apple Maps directions, Add to Calendar for Android (Google Calendar) and iPhone (Apple .ics with reminders), plus one-tap "add all functions"
- Main location/venue on the card (name, address, pinned map link) with Google/Apple Maps directions
- "People invited" banner above the RSVP (uses the "Persons invited" number you set per guest)
- Countdown timer, wishes box with quick-wish chips (shown to you in Tracker > Wishes), confetti on RSVP
- Guest page: tap envelope -> card -> per-function +/- attendance -> note -> thank you, can change reply, replies lock option, reply-by date
- Uploaded images are stored in PostgreSQL (works on Vercel's read-only filesystem)

## Run locally (Windows / Mac / Linux)
```
python -m venv .venv
.venv\Scripts\activate          # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
python run.py
```
Open http://127.0.0.1:5000 -> "Create an account".
With no DATABASE_URL it uses a local SQLite file (instance/invites.db), so you can test everything offline.
Optional: copy `.env.example` to `.env` to change settings.

To test against Neon locally, put your Neon connection string in `.env` as DATABASE_URL.

## Go live: Neon + GitHub + Vercel
1. Neon: create a project -> copy the connection string (keep `?sslmode=require`). Tables are created automatically on first request.
2. GitHub: `git init && git add . && git commit -m "Invitation Studio" ` then push to a new repo.
3. Vercel: Import the repo (framework: Other). Add Environment Variables:
   - `DATABASE_URL` = Neon connection string
   - `SECRET_KEY` = long random string (e.g. `python -c "import secrets;print(secrets.token_hex(32))"`)
   - `BASE_URL` = your final URL, e.g. `https://your-app.vercel.app` (used in guest links / WhatsApp messages)
   - `ALLOW_SIGNUP` = `true` for first deploy; after creating your account set it to `false` and redeploy
   - `TIMEZONE` = `Asia/Kolkata`
4. Deploy, open the site, create your account.

## Notes
- Vercel quirk: never name a folder `public` inside the app - Vercel treats it as static files and leaves it out of the Python function (that caused "TemplateNotFound"). Guest pages live in `app/templates/guest/`.
- After deploying, open **System** (top bar) to confirm the app is connected to your Neon PostgreSQL database and to see how many invitations/guests are stored.
- Upgrading from an older version: new columns are added to your existing database automatically on first start (SQLite or Neon).
- Vercel serverless request bodies are limited to ~4.5 MB; the admin page shrinks large photos in the browser before upload, and the server re-encodes to WebP.
- Create an admin from terminal: `flask --app run create-admin`
- Guest links look like `/i/<name>-<random>`; they are unguessable and marked noindex.
- "Opened" is counted only when the guest taps the envelope (link-preview bots are not counted).
