# Backend Setup

## Install and run

From this directory, create a virtual environment and install the pinned dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env`, set a unique `SECRET_KEY`, then start the API:

```bash
cp .env.example .env
uvicorn app.main:app --reload
```

The default database is local SQLite. To use MySQL, set `DATABASE_URL` in `.env` and make sure the database exists. The MySQL driver is included in `requirements.txt`.

To generate a signing key, run `python -c 'import secrets; print(secrets.token_urlsafe(48))'` and put its output in `.env`. Set `APP_ENV=production` in production; the API rejects a missing or short `SECRET_KEY` in that mode.

## SMTP password reset

For Gmail, enable 2-Step Verification and create an App Password in the Google Account security settings. Use that App Password as `SMTP_PASSWORD`, not the regular Google account password. Set `SMTP_USER` and `SMTP_FROM` to the sending address, `SMTP_HOST=smtp.gmail.com`, and `SMTP_PORT=587` for STARTTLS. Port `465` uses implicit TLS. Never commit `.env` or paste its values into source code.

`FRONTEND_RESET_URL` is the frontend page that reads the `token` query parameter from the reset email. `FRONTEND_VERIFY_URL` is the page that reads the token from the registration email. The verification page submits it to `POST /api/v1/auth/verify-email?token=...`; after verification, the user can log in. The reset page submits the token and new password to `POST /api/v1/auth/reset-password`. The API returns the same response for registered and unregistered addresses from `POST /api/v1/auth/forgot-password` to avoid revealing which emails have accounts.

## Authentication routes

- `POST /api/v1/auth/login`: public accounts only.
- `POST /api/v1/auth/verify-email`: activate a public account using its one-time email token.
- `POST /api/v1/auth/resend-verification`: resend a verification email for an unverified public account.
- `POST /api/v1/auth/login/admin-pemda`: Admin Pemda only.
- `POST /api/v1/auth/login/admin-pemprov`: Admin Pemprov only.
- `POST /api/v1/auth/logout`: revoke the current bearer token.
- `POST /api/v1/auth/forgot-password` and `POST /api/v1/auth/reset-password`: email recovery flow.

## Report attachments

Submit report attachments as `multipart/form-data` to `POST /api/v1/reports`.
Use `foto_bukti_awal` (or the legacy alias `foto_bukti`) for the initial
evidence photo, and `dokumen_pendukung_lain` (or `dokumen_pendukung`) for a
supporting document. The API saves the paths separately as
`foto_bukti_awal` and `dokumen_pendukung` on the report. Existing databases
gain the nullable `foto_bukti_awal` column automatically when the API starts.
Uploaded images are served inline at `/uploads/{filename}`; other files are
served as downloads.

## Tests

Run isolated authentication tests without connecting to the configured database or SMTP server:

```bash
python -m unittest tests.test_auth_flow
```

Run the full API integration suite in an isolated temporary database and port:

```bash
bash run_test.sh
```