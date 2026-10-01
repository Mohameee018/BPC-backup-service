# BPC Backup Service

Server-side backup service for the BPC Clothes System.

## Architecture

- bpc-backup-api: normal web service for administrator Google OAuth setup.
- bpc-backup-worker: Railway cron service running every 5 minutes.
- Google Drive: compressed PostgreSQL recovery dumps.
- Google Sheets: human-readable backup history and status.
- Supabase/PostgreSQL: primary database.

The worker checks PostgreSQL cumulative table statistics before dumping. If nothing changed, it records a skipped run instead of creating another full dump. It also forces at least one full dump every 24 hours.

## Required Railway variables

API:
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI
OAUTH_STATE_SECRET
BACKUP_SETUP_PASSWORD

Worker:
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
GOOGLE_REFRESH_TOKEN
DATABASE_URL
BACKUP_RETENTION_DAYS (default 30)
GOOGLE_SHEET_NAME (default BPC Backup Monitor)

Do not commit these values.

## Google setup

Deploy the API and generate its Railway domain. Then set GOOGLE_REDIRECT_URI to the exact URL ending in /oauth2/callback and add that same URI to the Google Cloud OAuth Web Application client.

Open /setup on the API, enter the setup password, authorize the dedicated BPC Google account, and copy the one-time refresh token into the worker's GOOGLE_REFRESH_TOKEN variable.

The service never logs or stores the refresh token in GitHub.
