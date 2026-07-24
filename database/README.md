# Database

Local development uses the ignored `phishing_defense.db` SQLite file created automatically by FastAPI. Apply `migrations/001_email_open_vertical_slice.sql` to a Supabase PostgreSQL project after reviewing Row Level Security and retention needs. The backend must own privileged database access. Do not put the service-role key in either browser application.
