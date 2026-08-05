"""
Support tickets Databricks App:
- Serves a small Flask API + single-page UI
- Reads/writes tickets and ticket_messages in Lakebase
  (Databricks-managed Postgres) via lakebase.py

Run locally:
    python app.py
Deploy as a Databricks App using app.yaml.
"""

import logging
import os

from flask import Flask, jsonify, render_template, request

import lakebase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tickets-app")

app = Flask(__name__)

TICKETS_TABLE = os.environ.get("TICKETS_TABLE", "tickets")
MESSAGES_TABLE = os.environ.get("TICKET_MESSAGES_TABLE", "ticket_messages")

VALID_STATUSES = {"open", "in_progress", "resolved", "closed"}
DEFAULT_STATUS = "open"


def _serialize_ticket(row: dict) -> dict:
    """Turn a lakebase row (RealDictRow) into a plain JSON-serializable dict."""
    return {
        "ticket_id": row["ticket_id"],
        "title": row["title"],
        "status": row["status"],
        "priority": row["priority"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
    }


def _serialize_message(row: dict) -> dict:
    return {
        "message_id": row["message_id"],
        "ticket_id": row["ticket_id"],
        "message_text": row["message_text"],
        "author": row["author"],
        "created_at": row["created_at"],
    }


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.errorhandler(Exception)
def handle_exception(err):
    """Ensure all unhandled errors return JSON (not an HTML error page),
    so the frontend's resp.json() call never chokes on HTML."""
    logger.exception("Unhandled exception while processing request")
    status_code = getattr(err, "code", 500)
    if not isinstance(status_code, int):
        status_code = 500
    return jsonify({"error": str(err)}), status_code


@app.route("/")
def index():
    """Single-page UI for managing support tickets."""
    return render_template("index.html")


@app.route("/tickets")
def list_tickets():
    """View all support tickets, newest first."""
    rows = lakebase.run_query(
        f"SELECT ticket_id, title, status, priority, created_by, created_at "
        f"FROM {TICKETS_TABLE} ORDER BY created_at DESC"
    )
    return jsonify([_serialize_ticket(r) for r in rows])


@app.route("/tickets", methods=["POST"])
def create_ticket():
    """Create a new support ticket."""
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400

    priority = (data.get("priority") or "").strip() or None
    created_by = (data.get("created_by") or "").strip() or None
    status = (data.get("status") or DEFAULT_STATUS).strip().lower()
    if status not in VALID_STATUSES:
        return jsonify({"error": f"Invalid status: {status!r}"}), 400

    rows = lakebase.run_query(
        f"INSERT INTO {TICKETS_TABLE} (title, status, priority, created_by) "
        f"VALUES (%s, %s, %s, %s) "
        f"RETURNING ticket_id, title, status, priority, created_by, created_at",
        (title, status, priority, created_by),
    )
    return jsonify(_serialize_ticket(rows[0])), 201


@app.route("/tickets/<int:ticket_id>")
def get_ticket(ticket_id: int):
    """Select a ticket and view its messages."""
    ticket_rows = lakebase.run_query(
        f"SELECT ticket_id, title, status, priority, created_by, created_at "
        f"FROM {TICKETS_TABLE} WHERE ticket_id = %s",
        (ticket_id,),
    )
    if not ticket_rows:
        return jsonify({"error": f"Ticket {ticket_id} not found"}), 404

    message_rows = lakebase.run_query(
        f"SELECT message_id, ticket_id, message_text, author, created_at "
        f"FROM {MESSAGES_TABLE} WHERE ticket_id = %s ORDER BY created_at ASC",
        (ticket_id,),
    )
    ticket = _serialize_ticket(ticket_rows[0])
    ticket["messages"] = [_serialize_message(r) for r in message_rows]
    return jsonify(ticket)


@app.route("/tickets/<int:ticket_id>/messages", methods=["POST"])
def add_message(ticket_id: int):
    """Add a message to an existing ticket."""
    exists = lakebase.run_query(
        f"SELECT 1 FROM {TICKETS_TABLE} WHERE ticket_id = %s", (ticket_id,)
    )
    if not exists:
        return jsonify({"error": f"Ticket {ticket_id} not found"}), 404

    data = request.get_json(silent=True) or {}
    message_text = (data.get("message_text") or "").strip()
    if not message_text:
        return jsonify({"error": "message_text is required"}), 400
    author = (data.get("author") or "").strip() or None

    rows = lakebase.run_query(
        f"INSERT INTO {MESSAGES_TABLE} (ticket_id, message_text, author) "
        f"VALUES (%s, %s, %s) "
        f"RETURNING message_id, ticket_id, message_text, author, created_at",
        (ticket_id, message_text, author),
    )
    return jsonify(_serialize_message(rows[0])), 201


@app.route("/tickets/<int:ticket_id>", methods=["PATCH"])
def update_ticket(ticket_id: int):
    """Update a ticket's status."""
    data = request.get_json(silent=True) or {}
    status = (data.get("status") or "").strip().lower()
    if status not in VALID_STATUSES:
        return jsonify({"error": f"Invalid status: {status!r}"}), 400

    rows = lakebase.run_query(
        f"UPDATE {TICKETS_TABLE} SET status = %s WHERE ticket_id = %s "
        f"RETURNING ticket_id, title, status, priority, created_by, created_at",
        (status, ticket_id),
    )
    if not rows:
        return jsonify({"error": f"Ticket {ticket_id} not found"}), 404
    return jsonify(_serialize_ticket(rows[0]))


if __name__ == '__main__':
    host = os.getenv('FLASK_RUN_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_RUN_PORT', 8000))
    app.run(debug=True, host=host, port=port)
    print(f"Flask app running on http://{host}:{port}")
