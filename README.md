# Support Tickets App on Lakebase

A small [Flask](https://flask.palletsprojects.com/) API + single-page UI for managing support tickets, backed by [Lakebase](https://docs.databricks.com/en/lakeformats/lakebase.html) (Databricks-managed Postgres). Built as a Databricks Bootcamp homework project.

## Features

- Create support tickets with title, priority, and author
- Add threaded messages to a ticket
- Update ticket status (`open` → `in_progress` → `resolved` → `closed`)
- Single-page UI rendering ticket list and per-ticket message history

## Project layout

```
app.py            Flask app (routes, JSON API, error handling)
lakebase.py       Lakebase / Postgres connection helper (psycopg2)
create_tables.sql Schema for tickets and ticket_messages
app.yaml          Databricks App deployment manifest
setup_secrets.py  One-time script to create the secret scope + store the URL
templates/        Single-page UI (index.html)
```

## Prerequisites

- Python 3.10+
- A Lakebase (managed Postgres) instance with a native Postgres role using a static, non-expiring password

## Local setup

1. Create the tables:

   ```bash
   psql "$LAKEBASE_URL" -f create_tables.sql
   ```

2. Configure the connection. Create a `.env` file from the template:

   ```bash
   cp .env.example .env
   ```

   Then edit `.env` and set:

   ```
   LAKEBASE_URL=postgresql://<role>:<password>@<host>:5432/databricks_postgres?sslmode=require
   ```

   `LAKEBASE_URL` is a standard Postgres URL. See `.env.example` for the shape.

3. Install dependencies and run:

   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   python app.py
   ```

   Open http://localhost:8000 (overridable via `FLASK_RUN_HOST` / `FLASK_RUN_PORT`).

## Deployment as a Databricks App

`app.yaml` deploys the app on Databricks Apps. The connection URL is injected from the `database/lakebase-url` secret scope rather than an env var:

```yaml
command: ["python", "app.py"]
env:
  - name: LAKEBASE_SECRET_SCOPE
    value: "database"
  - name: LAKEBASE_SECRET_KEY
    value: "lakebase-url"
```

Create the secret beforehand by running the one-time setup script (from a terminal
with the Databricks CLI configured, or in a notebook with `%sh python setup_secrets.py`):

```bash
python setup_secrets.py
```

It creates the `database` scope, stores the base64-encoded `lakebase-url`
secret (prompted via `getpass`, never committed), and grants `users` read
access so the app can resolve it at runtime.

Equivalent CLI form, if you prefer doing it manually:

```bash
databricks secrets put --scope database --key lakebase-url \
  --string-value "$(base64 <<< "$LAKEBASE_URL")"
databricks secrets update-acl --scope database --principal users --permission READ
```

## Schema

```sql
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title       VARCHAR(255) NOT NULL,
    status      VARCHAR(50)  NOT NULL,
    priority    VARCHAR(50),
    created_by  VARCHAR(100),
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ticket_messages (
    message_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ticket_id    BIGINT NOT NULL REFERENCES tickets(ticket_id),
    message_text TEXT NOT NULL,
    author       VARCHAR(100),
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## API reference

| Method | Path                                      | Description                          |
|--------|-------------------------------------------|--------------------------------------|
| GET    | `/healthz`                                | Liveness check                       |
| GET    | `/tickets`                                | List all tickets, newest first       |
| POST   | `/tickets`                                | Create a ticket                      |
| GET    | `/tickets/<ticket_id>`                    | Get a ticket + its messages          |
| POST   | `/tickets/<ticket_id>/messages`           | Add a message to a ticket            |
| PATCH  | `/tickets/<ticket_id>`                    | Update a ticket's status             |

## Configuration

| Variable                | Default               | Description                            |
|-------------------------|-----------------------|----------------------------------------|
| `LAKEBASE_URL`          | *(required)*          | Postgres connection URL                |
| `LAKEBASE_SECRET_SCOPE` | `database`            | Secret scope holding the URL (App)     |
| `LAKEBASE_SECRET_KEY`   | `lakebase-url`        | Secret key holding the URL (App)       |
| `TICKETS_TABLE`         | `tickets`             | Tickets table name                     |
| `TICKET_MESSAGES_TABLE` | `ticket_messages`     | Ticket messages table name             |