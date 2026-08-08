"""
Lakebase (Databricks-managed Postgres) connection helper.

Connects using a single LAKEBASE_URL (a standard Postgres connection URL,
e.g. postgresql://role:password@host:5432/databricks_postgres?sslmode=require)
pointing at a native Postgres role with a static, non-expiring password.
This keeps setup to a single secret instead of five separate env vars.

On Databricks Apps the URL comes from a secret scope (set in app.yaml).
Locally, you can set LAKEBASE_URL in a .env file instead.
"""

import base64
import os
from contextlib import contextmanager

import psycopg2
from databricks.sdk import WorkspaceClient
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

load_dotenv()

_SCOPE = os.environ.get("LAKEBASE_SECRET_SCOPE", "database")
_KEY = os.environ.get("LAKEBASE_SECRET_KEY", "lakebase-url")


def _lakebase_url() -> str:
    """Resolve the Lakebase connection URL from env var or Databricks secret scope.
    
    Handles both single and double base64 encoding of the secret value.
    """
    env_url = os.environ.get("LAKEBASE_URL")
    if env_url:
        return env_url
    
    secret = WorkspaceClient().secrets.get_secret(scope=_SCOPE, key=_KEY)
    raw_value = secret.value
    
    # First, check if it's already a valid Postgres URL (not encoded)
    if raw_value.startswith(("postgresql://", "postgres://")):
        return raw_value
    
    # Try first decode
    try:
        first_decode = base64.b64decode(raw_value).decode("utf-8")
        
        # If it's a valid Postgres URL after first decode, return it
        if first_decode.startswith(("postgresql://", "postgres://")):
            return first_decode
        
        # Otherwise, try decoding again (double-encoded case)
        try:
            second_decode = base64.b64decode(first_decode).decode("utf-8")
            if second_decode.startswith(("postgresql://", "postgres://")):
                return second_decode
            else:
                # If second decode doesn't give us a URL, use first decode
                return first_decode
        except Exception:
            # If second decode fails, return first decode
            return first_decode
            
    except Exception as e:
        # If base64 decode fails, the secret might be plain text
        # Return the raw value and let psycopg2 validate it
        raise ValueError(f"Failed to decode Lakebase URL from secret. Raw value starts with: {raw_value[:20]}... Error: {e}")


@contextmanager
def get_connection():
    """Yield a raw psycopg2 connection with a RealDictCursor factory."""
    conn = psycopg2.connect(_lakebase_url(), cursor_factory=RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()


def run_query(sql: str, params: tuple | dict | None = None) -> list[dict]:
    """Run a query against Lakebase and return rows as list[dict].

    Commits after execution so INSERT/UPDATE ... RETURNING statements
    persist. psycopg2 rolls back on close, so without this writes were
    silently discarded.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            conn.commit()
            return rows


def run_write(sql: str, params: tuple | dict | None = None) -> int:
    """Run an INSERT/UPDATE/DELETE against Lakebase, return affected row count."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            conn.commit()
            return cur.rowcount
