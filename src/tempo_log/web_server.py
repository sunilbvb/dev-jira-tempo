"""Embedded Web UI and REST API server for Tempo Worklog Console."""

from __future__ import annotations

import hmac
import json
import logging
import mimetypes
import os
import secrets
import urllib.parse
import datetime
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .config import JiraConfig, Settings, load_settings
from .day_report import DayEntry, analyse, render
from .exceptions import TempoLogError, ValidationError
from .export import ExportItem, generate_csv, generate_html, generate_json
from .journal import DEFAULT_SQLITE_PATH, SQLiteJournal
from .journal_analyzer import analyze_day, parse_fixed_blocks, parse_journal
from .keyring_store import (
    get_credential,
    is_keyring_available,
    set_credential,
)
from .schedule import Item, ScheduleConfig, build_day, format_clock, parse_clock, round_up
from .service import TempoService
from .sharing import build_digest_payload, send_webhook
from .ticket_mapper import TicketMapper
from .timer import get_active_timer, start_timer, stop_timer
from .worklog_import import merge_by_issue, parse_blocks

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
            self._send_error("Unauthorized: Server auth token required but not configured", HTTPStatus.UNAUTHORIZED)
            return False

        auth_header = self.headers.get("Authorization", "")
        api_token_header = self.headers.get("X-Auth-Token", "")

        provided_token = None
        if auth_header.startswith("Bearer "):
            provided_token = auth_header[7:].strip()
        elif api_token_header:
            provided_token = api_token_header.strip()

        if not provided_token or not hmac.compare_digest(
            provided_token.encode("utf-8"), expected_token.encode("utf-8")
        ):
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
            if path == "/api/export":
                self._handle_get_export(query)
                return
            if path == "/api/day-report":
                self._handle_get_day_report(query)
                return
            if path == "/api/ticket-map":
                self._handle_get_ticket_map()
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
        if path == "/api/analyze":
            self._handle_api_analyze(body)
            return
        if path == "/api/analyze/submit":
            self._handle_api_analyze_submit(body)
            return
        if path == "/api/schedule":
            self._handle_post_schedule(body)
            return
        if path == "/api/day-report":
            self._handle_post_day_report(body)
            return
        if path == "/api/ticket-map":
            self._handle_post_ticket_map(body)
            return
        if path == "/api/share":
            self._handle_post_share(body)
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

    def _handle_api_analyze(self, body: dict[str, Any]) -> None:
        content = body.get("content", "")
        file_path = body.get("file")
        if not content and file_path:
            p = Path(file_path).expanduser()
            if p.is_file():
                content = p.read_text(encoding="utf-8")
        if not content:
            self._send_error("Provide 'content' or 'file' containing journal markdown.", HTTPStatus.BAD_REQUEST)
            return

        date_val = body.get("date") or datetime.date.today().isoformat()
        service = self._get_service()
        settings = service.settings if service else None

        round_mins = body.get("round_minutes") or (settings.tempo_round_minutes if settings else 15)
        cap = body.get("cap") or (settings.tempo_daily_cap_hours if settings else None)
        consolidate = body.get("consolidate")
        trim = bool(body.get("trim", False))
        sequential = bool(body.get("sequential", False))

        existing: list[dict[str, Any]] = []
        if service and not body.get("offline", False):
            try:
                acc = service.default_account_id
                if not acc and service.jira_client:
                    acc = service.jira_client.get_current_account_id()
                if acc:
                    res = service.list_time(account_id=acc, from_date=date_val, to_date=date_val, limit=1000)
                    existing = res if isinstance(res, list) else res.get("results", res.get("worklogs", []))
            except Exception as exc:
                logger.warning("Could not list worklogs in web analyze: %s", exc)

        entries = parse_journal(
            content,
            heading_time_mode=settings.tempo_heading_time if settings else "start",
            meeting_prefix=settings.tempo_meeting_prefix if settings else "Meeting:",
        )
        report = analyze_day(
            entries,
            date_val,
            round_minutes=round_mins,
            daily_cap_hours=cap,
            resolver=(lambda k: service.jira_client.resolve_issue_id(k)) if (service and service.jira_client) else None,
            existing_worklogs=existing,
            sequential=sequential,
            consolidate=consolidate,
            trim=trim,
            meeting_issue=settings.tempo_meeting_issue if settings else None,
            fixed_blocks=parse_fixed_blocks(settings.tempo_fixed_blocks if settings else None),
            duplicate_window_minutes=settings.tempo_duplicate_window_minutes if settings else 15,
        )

        self._send_json({
            "status": "ok",
            "date": report.date,
            "total_minutes": report.total_minutes,
            "ready_minutes": report.ready_minutes,
            "existing_minutes": report.existing_minutes,
            "cap_hours": report.cap_hours,
            "ready_count": len(report.ready),
            "blocked_count": len(report.blocked),
            "logged_count": len(report.logged),
            "entries": [
                {
                    **asdict(p.entry),
                    "status": p.status,
                    "rounded_minutes": p.rounded_minutes,
                    "planned_start": p.start,
                    "problems": p.problems,
                    "notes": p.notes,
                    "is_logged": p.is_logged,
                }
                for p in report.planned
            ],
            "day_warnings": report.day_warnings,
            "day_info": report.day_info,
            "next_steps": report.next_steps,
        })

    def _handle_api_analyze_submit(self, body: dict[str, Any]) -> None:
        service = self._get_service()
        if not service:
            self._send_error("Cannot submit: Tempo API token not configured.", HTTPStatus.UNAUTHORIZED)
            return

        entries = body.get("entries", [])
        if not entries:
            self._send_error("No entries provided to submit.", HTTPStatus.BAD_REQUEST)
            return

        succeeded, failed, failures = service.batch_log(
            entries,
            stop_on_error=True,
            rollback_on_error=True,
            allow_duplicates=True,
        )
        if failed > 0:
            self._send_error(
                f"Submission failed ({failed} failed, rolled back): {'; '.join(failures)}",
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        self._send_json({
            "status": "ok",
            "succeeded": succeeded,
            "failed": 0,
            "message": f"Successfully uploaded {succeeded} worklog(s) to Tempo.",
        })

    def _collect_export_items(self, from_date: str | None, to_date: str | None) -> list[ExportItem]:
        service = self._get_service()
        items: list[ExportItem] = []
        if service and service.tempo_client:
            try:
                today = datetime.date.today()
                f_d = from_date or (today - datetime.timedelta(days=7)).isoformat()
                t_d = to_date or today.isoformat()
                logs = service.tempo_client.list_worklogs(from_date=f_d, to_date=t_d)
                for w in logs:
                    issue_info = w.get("issue", {})
                    issue_key = issue_info.get("key") or str(issue_info.get("id", "UNKNOWN"))
                    items.append(
                        ExportItem(
                            date=w.get("startDate", ""),
                            issue=issue_key,
                            hours=(w.get("timeSpentSeconds", 0) / 3600),
                            start_time=w.get("startTime", "")[:5],
                            tempo_id=w.get("tempoWorklogId", ""),
                            description=w.get("description", ""),
                        )
                    )
            except Exception as exc:
                logger.warning("Could not fetch remote worklogs: %s", exc)

        if not items:
            j = SQLiteJournal()
            logs = j.query(from_date=from_date, to_date=to_date, limit=200)
            for w in logs:
                items.append(
                    ExportItem(
                        date=w.get("start_date", ""),
                        issue=w.get("issue_key") or str(w.get("issue_id", "UNKNOWN")),
                        hours=float(w.get("hours", 0.0)),
                        start_time=w.get("start_time", "")[:5],
                        tempo_id=w.get("tempo_worklog_id", ""),
                        description=w.get("description", ""),
                    )
                )
        return items

    def _handle_get_export(self, query: dict[str, list[str]]) -> None:
        fmt = (query.get("format", ["csv"])[0]).lower()
        from_date = query.get("from", [None])[0]
        to_date = query.get("to", [None])[0]
        items = self._collect_export_items(from_date, to_date)

        if fmt == "json":
            self._send_json(json.loads(generate_json(items)))
            return
        elif fmt == "html":
            content = generate_html(items).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        else:
            content = generate_csv(items).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="tempo_export.csv"')
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    def _handle_get_day_report(self, query: dict[str, list[str]]) -> None:
        target_date = query.get("date", [datetime.date.today().isoformat()])[0]
        service = self._get_service()
        round_minutes = service.settings.tempo_round_minutes if service and service.settings else 15
        cap_hours = service.settings.tempo_daily_cap_hours if service and service.settings else 12.0

        items = self._collect_export_items(target_date, target_date)
        entries: list[DayEntry] = []
        for idx, item in enumerate(items, 1):
            start_m = parse_clock(item.start_time) if item.start_time else (idx * 30 + 540)
            entries.append(
                DayEntry(
                    worklog_id=idx,
                    start=start_m,
                    minutes=int(round(item.hours * 60)),
                    issue=item.issue,
                    title=item.description.splitlines()[0] if item.description else "",
                )
            )

        report = analyse(entries, round_minutes=round_minutes, max_day_minutes=int(cap_hours * 60))
        rendered = render(report, max_day_minutes=int(cap_hours * 60))
        self._send_json({
            "date": target_date,
            "total_minutes": report["total_minutes"],
            "total_hours": report["total_minutes"] / 60,
            "over_cap": report["over_cap"],
            "overlaps": [f"{a.issue} & {b.issue}" for a, b in report["overlaps"]],
            "gaps": [{"start": format_clock(g[0])[:5], "end": format_clock(g[1])[:5], "minutes": g[1] - g[0]} for g in report["gaps"]],
            "off_step": [e.issue for e in report["off_step"]],
            "rendered": rendered,
        })

    def _handle_get_ticket_map(self) -> None:
        mapper = TicketMapper.load()
        self._send_json({"mappings": mapper.mappings})

    def _handle_post_schedule(self, body: dict[str, Any]) -> None:
        content = body.get("content", "")
        target_date = body.get("date") or datetime.date.today().isoformat()
        step = int(body.get("round_minutes") or 15)
        cap = float(body.get("cap_hours") or 12.0)
        start_time = body.get("start") or "09:00"

        if content:
            blocks = parse_blocks(content, target_date)
            merged = merge_by_issue(blocks)
            items: list[Item] = []
            for m in merged:
                items.append(
                    Item(
                        issue=m.issue or "UNASSIGNED",
                        minutes=round_up(m.minutes, step),
                        description=m.description().strip(),
                        fixed_start=m.fixed_start,
                    )
                )
        else:
            raw_items = body.get("items", [])
            items = [
                Item(
                    issue=i.get("issue", "TASK"),
                    minutes=round_up(float(i.get("minutes") or (float(i.get("hours", 1.0)) * 60)), step),
                    description=i.get("description", ""),
                    fixed_start=parse_clock(i["fixed_start"]) if i.get("fixed_start") else None,
                )
                for i in raw_items
            ]

        config = ScheduleConfig(
            start_candidates=(start_time,),
            round_minutes=step,
            max_day_minutes=int(cap * 60),
            break_issue=body.get("break_issue"),
            break_start=body.get("break_start") or "13:00",
            break_minutes=int(body.get("break_minutes") or 60),
            break_description=body.get("break_desc") or "Lunch:\n- Lunch break",
        )

        reserved: list[tuple[int, int]] = []
        for r in body.get("reserved", []):
            try:
                s_s, e_s = r.split("-", 1)
                reserved.append((parse_clock(s_s.strip()), parse_clock(e_s.strip())))
            except Exception:
                pass

        try:
            scheduled = build_day(items, config, reserved=reserved if reserved else None)
        except Exception as exc:
            self._send_error(str(exc), HTTPStatus.BAD_REQUEST)
            return

        out = {
            "date": target_date,
            "total_minutes": sum(i.minutes for i in scheduled),
            "total_hours": round(sum(i.minutes for i in scheduled) / 60, 2),
            "items": [
                {
                    "issue": str(i.issue),
                    "minutes": i.minutes,
                    "hours": round(i.hours, 2),
                    "start": format_clock(i.start)[:5] if i.start is not None else "--:--",
                    "end": format_clock(i.start + i.minutes)[:5] if i.start is not None else "--:--",
                    "description": i.description,
                }
                for i in scheduled
            ],
        }
        self._send_json(out)

    def _handle_post_day_report(self, body: dict[str, Any]) -> None:
        content = body.get("content", "")
        target_date = body.get("date") or datetime.date.today().isoformat()
        blocks = parse_blocks(content, target_date) if content else []
        entries: list[DayEntry] = []
        for idx, b in enumerate(blocks, 1):
            start_m = b.start_minute if b.start_minute is not None else (idx * 30 + 540)
            entries.append(
                DayEntry(
                    worklog_id=idx,
                    start=start_m,
                    minutes=b.minutes,
                    issue=str(b.issue or "UNASSIGNED"),
                    title=b.title,
                )
            )
        step = int(body.get("round_minutes") or 15)
        cap = float(body.get("cap_hours") or 12.0)
        report = analyse(entries, round_minutes=step, max_day_minutes=int(cap * 60))
        rendered = render(report, max_day_minutes=int(cap * 60))
        self._send_json({
            "date": target_date,
            "total_minutes": report["total_minutes"],
            "total_hours": round(report["total_minutes"] / 60, 2),
            "over_cap": report["over_cap"],
            "rendered": rendered,
        })

    def _handle_post_ticket_map(self, body: dict[str, Any]) -> None:
        kw = (body.get("keyword") or "").strip().lower()
        ticket = (body.get("ticket") or "").strip().upper()
        if not kw or not ticket:
            self._send_error("Provide 'keyword' and 'ticket'", HTTPStatus.BAD_REQUEST)
            return
        mapper = TicketMapper.load()
        mapper.add_mapping(kw, ticket)
        saved = mapper.save()
        self._send_json({"status": "ok", "keyword": kw, "ticket": ticket, "file": str(saved)})

    def _handle_post_share(self, body: dict[str, Any]) -> None:
        target_date = body.get("date") or datetime.date.today().isoformat()
        webhook_url = body.get("webhook") or os.getenv("TEMPO_SHARE_WEBHOOK")
        if not webhook_url:
            self._send_error("Webhook URL required (or set TEMPO_SHARE_WEBHOOK)", HTTPStatus.BAD_REQUEST)
            return
        items = self._collect_export_items(target_date, target_date)
        if not items:
            self._send_error(f"No worklog entries found to share for {target_date}", HTTPStatus.NOT_FOUND)
            return
        payload = build_digest_payload(target_date, items, channel=body.get("channel"))
        success, msg = send_webhook(webhook_url, payload)
        if success:
            self._send_json({"status": "ok", "message": msg})
        else:
            self._send_error(f"Webhook error: {msg}", HTTPStatus.BAD_GATEWAY)

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


def run_server(port: int = 18114, host: str = "127.0.0.1", token: str | None = None) -> None:
    """Start the HTTP server on specified host and port."""
    if token:
        os.environ["TEMPO_WEB_TOKEN"] = token
    elif not os.environ.get("TEMPO_WEB_TOKEN") and not os.environ.get("WEB_AUTH_TOKEN"):
        os.environ["TEMPO_WEB_TOKEN"] = secrets.token_hex(16)

    active_token = os.environ.get("TEMPO_WEB_TOKEN") or os.environ.get("WEB_AUTH_TOKEN")
    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, TempoWebHandler)
    logger.info("Tempo Web Console running on http://%s:%s", host if host != "127.0.0.1" else "localhost", port)
    if active_token:
        logger.info("Auth Token: %s", active_token)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping Tempo Web Console...")
        httpd.server_close()
