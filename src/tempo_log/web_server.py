"""Embedded Web UI and REST API server for Tempo Worklog Console."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .config import JiraConfig, Settings, load_settings
from .exceptions import TempoLogError, ValidationError
from .journal import DEFAULT_SQLITE_PATH, SQLiteJournal
from .keyring_store import (
    get_credential,
    is_keyring_available,
    set_credential,
)
from .service import TempoService
from .timer import get_active_timer, start_timer, stop_timer

logger = logging.getLogger(__name__)

# Web static paths: single canonical frontend/ directory
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"


def get_static_dir() -> Path:
    return FRONTEND_DIR


class TempoWebHandler(BaseHTTPRequestHandler):
    server_version = "TempoLogWeb/0.2.0"

    def _check_token_auth(self) -> bool:
        expected_token = os.environ.get("TEMPO_WEB_TOKEN") or os.environ.get("WEB_AUTH_TOKEN")
        if not expected_token:
            return True

        auth_header = self.headers.get("Authorization", "")
        api_token_header = self.headers.get("X-Auth-Token", "")
        parsed = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed.query)
        token_param = query_params.get("token", [None])[0]

        provided_token = None
        if auth_header.startswith("Bearer "):
            provided_token = auth_header[7:].strip()
        elif api_token_header:
            provided_token = api_token_header.strip()
        elif token_param:
            provided_token = token_param.strip()

        if provided_token != expected_token:
            self._send_error("Unauthorized: Invalid or missing token", HTTPStatus.UNAUTHORIZED)
            return False
        return True

    def _send_json(self, data: Any, status: int = HTTPStatus.OK) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_error(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
        self._send_json({"error": message, "status": status}, status=status)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. API Endpoints
        if path.startswith("/api/"):
            if not self._check_token_auth():
                return
            if path == "/api/health":
                self._handle_health()
                return
            if path == "/api/config":
                self._handle_get_config()
                return
            if path == "/api/timer":
                self._handle_get_timer()
                return
            if path == "/api/summary":
                self._handle_summary(query)
                return
            if path == "/api/worklogs":
                self._handle_get_worklogs(query)
                return
            if path == "/api/export-csv":
                self._handle_export_csv()
                return

        # 2. Static File Serving
        self._serve_static(path)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/"):
            if not self._check_token_auth():
                return

        try:
            body = self._read_json_body()
        except Exception as exc:
            self._send_error(f"Invalid JSON body: {exc}", HTTPStatus.BAD_REQUEST)
            return

        if path == "/api/config":
            self._handle_post_config(body)
            return
        if path == "/api/timer/start":
            self._handle_timer_start(body)
            return
        if path == "/api/timer/stop":
            self._handle_timer_stop(body)
            return
        if path == "/api/timer/discard":
            self._handle_timer_discard()
            return
        if path == "/api/worklog":
            self._handle_post_worklog(body)
            return

        self._send_error("Endpoint not found", HTTPStatus.NOT_FOUND)

    # --- Handlers ---

    def _get_service(self) -> TempoService | None:
        try:
            settings = load_settings()
            return TempoService.from_settings(settings)
        except Exception as exc:
            logger.debug("Cannot initialize service from settings: %s", exc)
            return None

    def _handle_health(self) -> None:
        service = self._get_service()
        keyring_ok = is_keyring_available()
        if not service:
            self._send_json(
                {
                    "tempo_ok": False,
                    "tempo_message": "Tempo API token not configured.",
                    "jira_ok": None,
                    "jira_message": "Jira not configured.",
                    "keyring_available": keyring_ok,
                }
            )
            return

        report = service.check_health()
        report["keyring_available"] = keyring_ok
        self._send_json(report)

    def _handle_get_config(self) -> None:
        tempo_token = os.environ.get("TEMPO_API_TOKEN") or get_credential("TEMPO_API_TOKEN")
        jira_base = os.environ.get("JIRA_BASE_URL") or get_credential("JIRA_BASE_URL")
        jira_email = os.environ.get("JIRA_EMAIL") or get_credential("JIRA_EMAIL")
        jira_token = os.environ.get("JIRA_API_TOKEN") or get_credential("JIRA_API_TOKEN")
        jira_acc = os.environ.get("JIRA_ACCOUNT_ID") or get_credential("JIRA_ACCOUNT_ID")
        is_server = os.environ.get("JIRA_SERVER", "").lower() in ("1", "true", "yes")

        data = {
            "tempo_token_set": bool(tempo_token),
            "tempo_token_preview": (tempo_token[:4] + "..." + tempo_token[-4:]) if tempo_token and len(tempo_token) > 8 else ("Set" if tempo_token else ""),
            "jira_base_url": jira_base or "",
            "jira_email": jira_email or "",
            "jira_token_set": bool(jira_token),
            "jira_account_id": jira_acc or "",
            "is_server": is_server,
            "keyring_available": is_keyring_available(),
        }
        self._send_json(data)

    def _handle_post_config(self, body: dict[str, Any]) -> None:
        use_keyring = body.get("use_keyring", False) and is_keyring_available()

        tempo_token = body.get("tempo_token", "").strip()
        jira_base = body.get("jira_base_url", "").strip()
        jira_email = body.get("jira_email", "").strip()
        jira_token = body.get("jira_token", "").strip()
        jira_acc = body.get("jira_account_id", "").strip()
        is_server = bool(body.get("is_server", False))

        if use_keyring:
            if tempo_token:
                set_credential("TEMPO_API_TOKEN", tempo_token)
            if jira_base:
                set_credential("JIRA_BASE_URL", jira_base)
            if jira_email:
                set_credential("JIRA_EMAIL", jira_email)
            if jira_token:
                set_credential("JIRA_API_TOKEN", jira_token)
            if jira_acc:
                set_credential("JIRA_ACCOUNT_ID", jira_acc)
        else:
            # Write to local .env
            env_file = Path(".env")
            lines = [
                "# Configured via Tempo Web Console",
                f"TEMPO_API_TOKEN={tempo_token or os.environ.get('TEMPO_API_TOKEN', '')}",
                f"JIRA_BASE_URL={jira_base or os.environ.get('JIRA_BASE_URL', '')}",
                f"JIRA_EMAIL={jira_email or os.environ.get('JIRA_EMAIL', '')}",
                f"JIRA_API_TOKEN={jira_token or os.environ.get('JIRA_API_TOKEN', '')}",
                f"JIRA_ACCOUNT_ID={jira_acc or os.environ.get('JIRA_ACCOUNT_ID', '')}",
                f"JIRA_SERVER={'true' if is_server else 'false'}",
            ]
            env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Also update live process environment
        if tempo_token:
            os.environ["TEMPO_API_TOKEN"] = tempo_token
        if jira_base:
            os.environ["JIRA_BASE_URL"] = jira_base
        if jira_email:
            os.environ["JIRA_EMAIL"] = jira_email
        if jira_token:
            os.environ["JIRA_API_TOKEN"] = jira_token
        if jira_acc:
            os.environ["JIRA_ACCOUNT_ID"] = jira_acc
        os.environ["JIRA_SERVER"] = "true" if is_server else "false"

        self._send_json({"status": "ok", "message": "Configuration saved successfully."})

    def _handle_get_timer(self) -> None:
        active = get_active_timer()
        if not active:
            self._send_json({"active": False})
            return

        self._send_json(
            {
                "active": True,
                "issue": active.issue,
                "issue_id": active.issue_id,
                "description": active.description,
                "started_at": active.started_at,
                "elapsed_seconds": round(active.elapsed_seconds, 1),
                "elapsed_hours": active.elapsed_hours,
                "formatted_duration": active.formatted_duration,
            }
        )

    def _handle_timer_start(self, body: dict[str, Any]) -> None:
        issue = body.get("issue")
        issue_id = body.get("issue_id")
        desc = body.get("description", "")

        try:
            state = start_timer(issue=issue, issue_id=issue_id, description=desc)
            self._send_json(
                {
                    "status": "started",
                    "issue": state.issue,
                    "issue_id": state.issue_id,
                    "started_at": state.started_at,
                }
            )
        except ValidationError as exc:
            self._send_error(str(exc), HTTPStatus.BAD_REQUEST)

    def _handle_timer_stop(self, body: dict[str, Any]) -> None:
        active = get_active_timer()
        if not active:
            self._send_error("No active timer running.", HTTPStatus.BAD_REQUEST)
            return

        service = self._get_service()
        if not service:
            self._send_error("Cannot log to Tempo: API token not configured.", HTTPStatus.UNAUTHORIZED)
            return

        hrs = active.elapsed_hours
        try:
            stopped = stop_timer()
            res = service.log_time(
                hours=hrs,
                issue=stopped.issue,
                issue_id=stopped.issue_id,
                account_id=body.get("account_id"),
                description=body.get("description") or stopped.description,
            )
            self._send_json(
                {
                    "status": "logged",
                    "hours": hrs,
                    "issue": stopped.issue or stopped.issue_id,
                    "result": res,
                }
            )
        except Exception as exc:
            self._send_error(f"Failed to stop/log timer: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_timer_discard(self) -> None:
        try:
            stop_timer(discard=True)
            self._send_json({"status": "discarded"})
        except ValidationError as exc:
            self._send_error(str(exc), HTTPStatus.BAD_REQUEST)

    def _handle_post_worklog(self, body: dict[str, Any]) -> None:
        service = self._get_service()
        if not service:
            self._send_error("Tempo credentials not configured.", HTTPStatus.UNAUTHORIZED)
            return

        try:
            hours = float(body["hours"])
            res = service.log_time(
                hours=hours,
                issue=body.get("issue"),
                issue_id=int(body["issue_id"]) if body.get("issue_id") else None,
                account_id=body.get("account_id"),
                date=body.get("date"),
                time=body.get("time"),
                description=body.get("description", ""),
            )
            self._send_json({"status": "ok", "result": res})
        except Exception as exc:
            self._send_error(str(exc), HTTPStatus.BAD_REQUEST)

    def _handle_summary(self, query: dict[str, list[str]]) -> None:
        j = SQLiteJournal()
        from_date = query.get("from", [None])[0]
        to_date = query.get("to", [None])[0]
        summary = j.weekly_summary(from_date=from_date, to_date=to_date)
        self._send_json(summary)

    def _handle_get_worklogs(self, query: dict[str, list[str]]) -> None:
        j = SQLiteJournal()
        limit = int(query.get("limit", [30])[0])
        from_date = query.get("from", [None])[0]
        to_date = query.get("to", [None])[0]
        issue = query.get("issue", [None])[0]
        records = j.query(from_date=from_date, to_date=to_date, issue_key=issue, limit=limit)
        self._send_json({"worklogs": records, "count": len(records)})

    def _handle_export_csv(self) -> None:
        j = SQLiteJournal()
        tmp_csv = Path("/tmp/tempo_export.csv")
        j.export_csv(tmp_csv)
        if not tmp_csv.exists():
            self._send_error("No audit data available", HTTPStatus.NOT_FOUND)
            return

        content = tmp_csv.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", "attachment; filename=\"tempo_worklogs.csv\"")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _serve_static(self, path: str) -> None:
        static_dir = get_static_dir()
        clean_path = path.lstrip("/")
        if not clean_path or clean_path == "index.html":
            target = static_dir / "index.html"
        else:
            target = static_dir / clean_path

        # Avoid path traversal
        try:
            target = target.resolve()
            if not str(target).startswith(str(static_dir.resolve())):
                self._send_error("Forbidden", HTTPStatus.FORBIDDEN)
                return
        except Exception:
            self._send_error("Not Found", HTTPStatus.NOT_FOUND)
            return

        if not target.exists() or target.is_dir():
            # Fallback to index.html for SPA routing
            target = static_dir / "index.html"

        if not target.exists():
            self._send_error(f"File not found: {path}", HTTPStatus.NOT_FOUND)
            return

        ctype, _ = mimetypes.guess_type(str(target))
        if not ctype:
            ctype = "application/octet-stream"

        content = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def run_server(port: int = 18114, host: str = "127.0.0.1") -> None:
    """Start the HTTP server on specified host and port."""
    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, TempoWebHandler)
    logger.info("Tempo Web Console running on http://%s:%s", host if host != "127.0.0.1" else "localhost", port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping Tempo Web Console...")
        httpd.server_close()
