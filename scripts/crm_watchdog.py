"""Five-minute self-healing watchdog for the local Marketplace CRM pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CRM_ROOT = ROOT / "crm"
WORK_DIR = ROOT / "work"
CRM_WORK_DIR = CRM_ROOT / "work"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
N8N_DATABASE = Path.home() / ".n8n" / "database.sqlite"
CRM_DATABASE = CRM_ROOT / "prisma" / "dev.db"
REPORT_PATH = WORK_DIR / "system-health.json"
INCIDENT_LOG = WORK_DIR / "automation-incidents.jsonl"
INCIDENT_STATE = WORK_DIR / "automation-incident-state.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime_health import heartbeat_age_seconds, read_heartbeat, utc_iso  # noqa: E402
from scripts.valuation_quality_audit import cancel_inactive_jobs, quarantine_unsafe  # noqa: E402


def http_status(url: str, timeout: float = 5) -> int | None:
    try:
        with urlopen(Request(url, headers={"User-Agent": "CRM-Watchdog/1.0"}), timeout=timeout) as response:
            return int(response.status)
    except Exception:
        return None


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def lock_pid(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return None


def command_line(pid: int) -> str:
    if os.name != "nt":
        return ""
    script = (
        f"$p=Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\" -ErrorAction SilentlyContinue;"
        "if($p){[Console]::Out.Write($p.CommandLine)}"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return result.stdout.strip()


def stop_verified_pid(pid: int | None, expected: str) -> bool:
    if not pid or not pid_running(pid):
        return False
    if expected.lower() not in command_line(pid).lower():
        return False
    subprocess.run(["taskkill.exe", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=20, check=False)
    return not pid_running(pid)


def start_detached(name: str, command: list[str], cwd: Path) -> dict[str, Any]:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    stdout_path = WORK_DIR / f"{name}.stdout.log"
    stderr_path = WORK_DIR / f"{name}.stderr.log"
    creation_flags = 0
    if os.name == "nt":
        creation_flags = 0x00000008 | 0x00000200 | 0x08000000
    with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            creationflags=creation_flags,
            close_fds=True,
        )
    return {"action": "started", "pid": process.pid, "command": command[0]}


def start_scheduled_task(name: str, *, restart: bool = False) -> dict[str, Any]:
    escaped = name.replace("'", "''")
    statements = []
    if restart:
        statements.append(f"Stop-ScheduledTask -TaskName '{escaped}' -ErrorAction SilentlyContinue")
    statements.append(f"Start-ScheduledTask -TaskName '{escaped}' -ErrorAction Stop")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", ";".join(statements)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    return {
        "action": "restarted_task" if restart else "started_task",
        "task": name,
        "ok": result.returncode == 0,
        "error": result.stderr.strip()[:500] or None,
    }


def workflow_health() -> dict[str, Any]:
    if not N8N_DATABASE.exists():
        return {"healthy": False, "error": "n8n database is missing"}
    try:
        with sqlite3.connect(N8N_DATABASE, timeout=10) as connection:
            row = connection.execute(
                "SELECT id, name, active FROM workflow_entity WHERE name='Auckland Car Listing Monitor' LIMIT 1"
            ).fetchone()
            webhook = connection.execute(
                "SELECT COUNT(*) FROM webhook_entity WHERE workflowId=?", (row[0],)
            ).fetchone()[0] if row else 0
        return {
            "healthy": bool(row and row[2] and webhook),
            "id": row[0] if row else None,
            "name": row[1] if row else None,
            "active": bool(row and row[2]),
            "webhooks": int(webhook),
        }
    except sqlite3.Error as error:
        return {"healthy": False, "error": str(error)}


def listing_health() -> dict[str, Any]:
    result = {"n8nRows": 0, "crmRows": 0, "matchedUrls": 0, "missingUrls": 0}
    if not N8N_DATABASE.exists() or not CRM_DATABASE.exists():
        return result
    with sqlite3.connect(N8N_DATABASE, timeout=10) as n8n:
        table_row = n8n.execute("SELECT id FROM data_table WHERE name='car_listings'").fetchone()
        if not table_row:
            return result
        table = f"data_table_user_{table_row[0]}"
        urls = {str(row[0]) for row in n8n.execute(f'SELECT url FROM "{table}" WHERE url IS NOT NULL')}
        result["n8nRows"] = len(urls)
        latest = n8n.execute(f'SELECT MAX(COALESCE(lastSeen, firstSeen)) FROM "{table}"').fetchone()[0]
        result["latestMonitorRowAt"] = latest
        if latest:
            try:
                latest_time = datetime.fromisoformat(str(latest).replace("Z", "+00:00"))
                if latest_time.tzinfo is None:
                    latest_time = latest_time.replace(tzinfo=timezone.utc)
                result["latestMonitorAgeSeconds"] = round(
                    max(0.0, (datetime.now(timezone.utc) - latest_time).total_seconds()), 1
                )
            except ValueError:
                result["latestMonitorAgeSeconds"] = None
    with sqlite3.connect(CRM_DATABASE, timeout=10) as crm:
        crm_urls = {str(row[0]) for row in crm.execute("SELECT facebookUrl FROM Listing")}
        result["crmRows"] = int(crm.execute("SELECT COUNT(*) FROM Listing").fetchone()[0])
    result["matchedUrls"] = len(urls & crm_urls)
    result["missingUrls"] = len(urls - crm_urls)
    return result


def valuation_queue_health() -> dict[str, Any]:
    path = CRM_WORK_DIR / "vehicle-valuation.db"
    if not path.exists():
        return {"counts": {}, "oldestRunnableAt": None}
    with sqlite3.connect(path, timeout=10) as connection:
        counts = {str(row[0]): int(row[1]) for row in connection.execute("SELECT status, COUNT(*) FROM valuation_jobs GROUP BY status")}
        oldest = connection.execute(
            "SELECT MIN(created_at) FROM valuation_jobs WHERE status IN ('PENDING','RETRY','EXPANDING_SEARCH','AWAITING_SAFE_EVIDENCE')"
        ).fetchone()[0]
        publication_failures = int(connection.execute(
            "SELECT COUNT(*) FROM valuation_publications WHERE status IN ('RETRY','FAILED')"
        ).fetchone()[0])
        sources = [
            {
                "name": str(row[0]),
                "health": str(row[1]),
                "lastSuccessAt": row[2],
                "lastError": row[3],
            }
            for row in connection.execute(
                "SELECT name, health, last_success_at, last_error FROM sources WHERE enabled=1 ORDER BY name"
            )
        ]
    return {
        "counts": counts,
        "oldestRunnableAt": oldest,
        "publicationFailures": publication_failures,
        "sources": sources,
    }


def process_health(name: str, max_age: int) -> dict[str, Any]:
    heartbeat = read_heartbeat(name)
    age = heartbeat_age_seconds(name)
    heartbeat_status = str((heartbeat or {}).get("status") or "").lower()
    responsive = age is not None and age <= max_age
    reported_healthy = heartbeat_status in {"healthy", "running"} and not (heartbeat or {}).get("error")
    return {
        "healthy": responsive and reported_healthy,
        "responsive": responsive,
        "reportedHealthy": reported_healthy,
        "ageSeconds": round(age, 1) if age is not None else None,
        "heartbeat": heartbeat,
    }


def openai_vision_health() -> dict[str, Any]:
    failure_path = CRM_WORK_DIR / "openai-vision-auth-failure.json"
    if failure_path.exists():
        return {
            "healthy": False,
            "status": "auth_blocked",
            "message": "Vision identity is disabled after HTTP 401; ambiguous listings remain quarantined.",
        }
    return {"healthy": True, "status": "available_or_not_needed"}


def import_missing_listings() -> dict[str, Any]:
    result = subprocess.run(
        [str(PYTHON), str(CRM_ROOT / "scripts" / "import_n8n_listings.py"), "--skip-images"],
        cwd=CRM_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    return {"ok": result.returncode == 0, "output": result.stdout.strip()[-1000:], "error": result.stderr.strip()[-1000:]}


def write_report(payload: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = REPORT_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, default=str, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, REPORT_PATH)


def record_incidents(issues: list[str], payload: dict[str, Any]) -> None:
    fingerprint = hashlib.sha256("\n".join(sorted(issues)).encode("utf-8")).hexdigest() if issues else ""
    try:
        previous = json.loads(INCIDENT_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    if issues and fingerprint != previous.get("fingerprint"):
        INCIDENT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with INCIDENT_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"createdAt": utc_iso(), "issues": issues, "health": payload}, default=str) + "\n")
    temporary = INCIDENT_STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"fingerprint": fingerprint, "updatedAt": utc_iso()}), encoding="utf-8")
    os.replace(temporary, INCIDENT_STATE)


def run_watchdog(*, repair: bool) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    issues: list[str] = []

    crm_http = http_status("http://127.0.0.1:3001/")
    if crm_http != 200:
        issues.append("CRM localhost:3001 is not responding")
        if repair:
            actions.append(start_detached("crm-app", ["C:\\Program Files\\nodejs\\npm.cmd", "run", "dev"], CRM_ROOT))

    n8n_http = http_status("http://127.0.0.1:5678/")
    if n8n_http != 200:
        issues.append("n8n localhost:5678 is not responding")
        if repair:
            actions.append(start_scheduled_task("Auckland Facebook Monitor n8n"))

    monitor = process_health("marketplace-monitor", 1_200)
    if not monitor["healthy"]:
        if monitor["responsive"]:
            issues.append("Marketplace collector source scan is degraded")
        else:
            issues.append("Marketplace collector heartbeat is stale")
        if repair and not monitor["responsive"]:
            pid = lock_pid(WORK_DIR / "monitor.lock")
            stop_verified_pid(pid, "main.py")
            actions.append(start_detached("marketplace-monitor", [str(PYTHON), "main.py"], ROOT))

    sync = process_health("crm-sync", 900)
    if not sync["healthy"]:
        issues.append("CRM sync heartbeat is stale" if not sync["responsive"] else "CRM sync reported a failure")
        if repair and not sync["responsive"]:
            pid = lock_pid(CRM_WORK_DIR / "crm-sync.lock")
            stop_verified_pid(pid, "sync_n8n_to_crm.py")
            actions.append(start_scheduled_task("Car Deal CRM Cloud Sync", restart=True))

    valuation_http = http_status("http://127.0.0.1:8010/health")
    valuation_worker = process_health("valuation-worker", 120)
    if valuation_http != 200:
        issues.append("Valuation API is not healthy")
        if repair:
            actions.append(start_scheduled_task("Car Deal CRM Valuation Service", restart=True))
    if not valuation_worker["healthy"]:
        issues.append("Valuation worker heartbeat is stale or degraded")
        if repair:
            heartbeat_pid = int((valuation_worker.get("heartbeat") or {}).get("pid") or 0)
            stopped = stop_verified_pid(heartbeat_pid, "vehicle_valuation.worker")
            actions.append({
                "action": "restart_stale_valuation_worker",
                "pid": heartbeat_pid or None,
                "stopped": stopped,
                "supervisorWillRestart": stopped,
            })

    workflow = workflow_health()
    if not workflow.get("healthy"):
        issues.append("Auckland n8n workflow is inactive or missing its webhook")

    listings = listing_health()
    if listings.get("missingUrls", 0):
        issues.append(f"{listings['missingUrls']} n8n listing URL(s) are missing from the CRM")
        if repair:
            actions.append({"action": "reconcile_listings", **import_missing_listings()})
            listings = listing_health()
    if (listings.get("latestMonitorAgeSeconds") or 0) > 86_400:
        issues.append("No new source listings have reached n8n in the last 24 hours")

    quality = quarantine_unsafe(dry_run=not repair)
    if quality.get("quarantined", 0):
        issues.append(f"{quality['quarantined']} published valuation(s) failed current safety checks")
        if repair:
            from vehicle_valuation.service import queue_existing_crm

            cancelled = cancel_inactive_jobs()
            queued = queue_existing_crm(
                force=True,
                listing_ids=list(quality.get("listingIds") or []),
            )
            quality["cancelledInactiveJobs"] = cancelled
            quality["queued"] = queued
            actions.append({"action": "requeue_safe_valuations", "queued": queued, "cancelledInactiveJobs": cancelled})

    if repair:
        cancelled = cancel_inactive_jobs()
        if cancelled:
            actions.append({"action": "cancel_inactive_valuation_jobs", "cancelled": cancelled})

    queue_health = valuation_queue_health()
    oldest = queue_health.get("oldestRunnableAt")
    if oldest:
        try:
            oldest_time = datetime.fromisoformat(str(oldest).replace("Z", "+00:00"))
            if oldest_time.tzinfo is None:
                oldest_time = oldest_time.replace(tzinfo=timezone.utc)
            queue_age = (datetime.now(timezone.utc) - oldest_time).total_seconds()
            queue_health["oldestRunnableAgeSeconds"] = round(max(0, queue_age), 1)
            if queue_age > 3600:
                issues.append("Valuation queue contains runnable work older than one hour")
        except ValueError:
            pass

    checked_at = utc_iso()
    try:
        previous_report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        previous_report = {}
    recent_repairs = previous_report.get("recentRepairs", [])
    if not isinstance(recent_repairs, list):
        recent_repairs = []
    if actions:
        recent_repairs = [{"at": checked_at, "actions": actions}, *recent_repairs][:10]

    report = {
        "checkedAt": checked_at,
        "overall": "healthy" if not issues else ("repairing" if repair and actions else "degraded"),
        "services": {
            "crm": {"healthy": crm_http == 200, "httpStatus": crm_http, "port": 3001},
            "n8n": {"healthy": n8n_http == 200, "httpStatus": n8n_http, "port": 5678},
            "marketplaceMonitor": monitor,
            "crmSync": sync,
            "valuation": {"healthy": valuation_http == 200 and valuation_worker["healthy"], "httpStatus": valuation_http, "port": 8010, "worker": valuation_worker},
            "openaiVision": openai_vision_health(),
        },
        "workflow": workflow,
        "listings": listings,
        "valuationQueue": queue_health,
        "qualityAudit": quality,
        "actions": actions,
        "recentRepairs": recent_repairs,
        "issues": issues,
    }
    write_report(report)
    record_incidents(issues, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    report = run_watchdog(repair=not args.check_only)
    print(json.dumps(report, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
