English-only configuration for Postgres, psql, and stored data

Overview
- Goal: Make Postgres server and psql use English messages by default and prevent storing Russian/Cyrillic characters in DB columns.
- This repository now contains:
  - docker-compose.yml configured to initialize Postgres with English-only locales (C locale, UTF-8 encoding).
  - An Alembic migration that enforces ASCII-only characters on selected text columns so non-English symbols are rejected.

1) Re-initialize the Postgres cluster with English-only locale
Important: Changing lc_collate/lc_ctype takes effect only on a newly initialized data directory. Re-initializing removes existing DB data in the volume.

Steps (PowerShell):
- Ensure Docker Desktop is running.
- Stop and remove services and volumes (this deletes DB data):
  docker compose down -v
- Start Postgres again (compose uses postgres:15-alpine):
  docker compose up -d postgres

The compose file sets:
- POSTGRES_INITDB_ARGS: "--encoding=UTF8 --locale=C --lc-messages=C"
- LANG: C.UTF-8, LC_ALL: C.UTF-8, LC_MESSAGES: C

2) Verify Postgres server-side English configuration
Use Docker exec (recommended):
- docker exec -it soc_postgres psql -U app -d app_db -c "SHOW server_encoding;"
- docker exec -it soc_postgres psql -U app -d app_db -c "SHOW lc_collate;"
- docker exec -it soc_postgres psql -U app -d app_db -c "SHOW lc_ctype;"
- docker exec -it soc_postgres psql -U app -d app_db -c "SHOW lc_messages;"
- docker exec -it soc_postgres psql -U app -d app_db -c "SHOW lc_time;"
Expected values (C locale):
- server_encoding: UTF8
- lc_collate: C
- lc_ctype: C
- lc_messages: C
- lc_time: C

3) Make psql client show English messages on Windows (optional but recommended)
For the current PowerShell session:
- $env:LC_ALL = "C"
- $env:LANG = "en_US.UTF-8"
- $env:LC_MESSAGES = "C"
- Optional: chcp 65001  # use UTF-8 code page
Then connect:
- psql "postgresql://app:app_password@localhost:5432/app_db" -c "\\dt"

To persist for new terminals:
- setx LC_ALL "C"
- setx LANG "en_US.UTF-8"
- setx LC_MESSAGES "C"
(Reopen PowerShell afterwards.)

4) Apply DB migrations (creates tables and ASCII-only constraints)
- Install dependencies in your venv (if needed):
  pip install -r requirements.txt
- Run migrations:
  alembic upgrade head

5) What the ASCII-only policy means
- The migration adds CHECK constraints that restrict selected text columns to ASCII-only characters (bytes 0x00-0x7F). This blocks Cyrillic and other non-ASCII characters.
- Affected columns:
  - incidents(source, status, summary[nullable])
  - actions(kind)
  - evidence(kind, path, hash[nullable])
  - tickets(external_id, system, status)
- Example behavior:
  - INSERT INTO incidents(source,status) VALUES ('Source1','new');  -- OK
  - INSERT INTO incidents(source,status) VALUES ('Привет','new');   -- ERROR (violates constraint)

6) Troubleshooting
- If psql still prompts “Пароль пользователя User:” you’re connecting without -U app. Use:
  psql -h localhost -p 5432 -U app -d app_db
- If connection is refused: ensure Docker is running and container soc_postgres is healthy (docker ps).
- If Alembic can’t connect: check .env has DATABASE_URL=postgresql+asyncpg://app:app_password@localhost:5432/app_db and that Docker is up.
- If constraints fail during migration: you may have pre-existing non-ASCII data. Clean it first or recreate the DB volume as in step 1.

7) Quick verification
- docker exec -it soc_postgres psql -U app -d app_db -c "INSERT INTO incidents(source,status) VALUES ('Hello','new');"
- docker exec -it soc_postgres psql -U app -d app_db -c "INSERT INTO incidents(source,status) VALUES ('Привет','new');"  # should fail
- docker exec -it soc_postgres psql -U app -d app_db -c "\dt"

If you prefer en_US.UTF-8 collation instead of C (for more natural sorting), switch the image to postgres:15 (Debian-based) and set POSTGRES_INITDB_ARGS to --locale=en_US.UTF-8 --lc-messages=en_US.UTF-8, then re-initialize the volume again as in step 1.
