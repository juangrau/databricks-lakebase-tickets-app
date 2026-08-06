"""
One-time setup script: creates the Databricks secret scope and stores the
Lakebase connection URL as a secret. Run this locally (with the Databricks CLI
configured, so databricks.sdk can authenticate) or from a notebook with
`%sh python setup_secrets.py`. Never commit the secret value anywhere.

The URL is base64-encoded before being stored, matching the decode step in
lakebase.py and the `databricks secrets put` command in the README.

Usage:
    python setup_secrets.py
"""
import base64
import getpass

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import workspace

w = WorkspaceClient()

scope = "database"
key = "lakebase-url"

try:
    w.secrets.create_scope(scope=scope)
except Exception as e:
    print(f"Scope '{scope}' may already exist: {e}")

url = getpass.getpass("Paste your Lakebase connection URL: ")
if not url:
    raise SystemExit("No URL provided; aborting.")

w.secrets.put_secret(
    scope=scope,
    key=key,
    string_value=base64.b64encode(url.encode("utf-8")).decode("ascii"),
)

w.secrets.put_acl(
    scope=scope,
    principal="users",
    permission=workspace.AclPermission.READ,
)

print(f"Stored secret {scope}/{key} and granted READ to 'users'.")