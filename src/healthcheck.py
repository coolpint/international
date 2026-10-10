from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .monitor.http import fetch_json
from .monitor.config import load_sources
from .monitor.notifier import send_telegram_text, telegram_is_configured


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HISTORY_DIR = REPO_ROOT / "data" / "history"
DEFAULT_RUN_LOG_DIR = REPO_ROOT / "data" / "run_logs"
KST = ZoneInfo("Asia/Seoul")
MONITOR_INTERVAL_HOURS = 8


@dataclass
class HealthReport:
    status: str
    message: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a weekly health check for the international monitor.")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--workflow-file", default="monitor.yml")
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--run-log-dir", default=str(DEFAULT_RUN_LOG_DIR))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_kst(dt: datetime | None) -> str:
    if dt is None:
        return "없음"
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")


def _load_ndjson_since(directory: Path, since: datetime) -> list[dict]:
    rows = []
    if not directory.exists():
        return rows

    for path in sorted(directory.glob("*.ndjson")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            run_at = _parse_iso_datetime(payload.get("run_at"))
            if run_at and run_at >= since:
                rows.append(payload)
    return rows


def _github_headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def load_monitor_runs(repository: str, workflow_file: str, since: datetime, token: str | None) -> list[dict]:
    api_url = (
        f"https://api.github.com/repos/{repository}/actions/workflows/{workflow_file}/runs?per_page=100"
    )
    payload = fetch_json(api_url, headers=_github_headers(token))
    runs = []
    for run in payload.get("workflow_runs", []):
        created_at = _parse_iso_datetime(run.get("created_at"))
        if not created_at or created_at < since:
            continue
        if run.get("event") != "schedule":
            continue
        runs.append(run)
    return runs


def build_health_report(
    runs: list[dict],
    history_rows: list[dict],
    run_logs: list[dict],
    now: datetime,
    days: int,
    source_history: list[dict] | None = None,
    active_source_ids: set[str] | None = None,
) -> HealthReport:
    success_runs = [run for run in runs if run.get("conclusion") == "success"]
    failed_runs = [run for run in runs if run.get("conclusion") not in {"success", None}]
    latest_success = max((_parse_iso_datetime(run.get("updated_at")) for run in success_runs), default=None)
    expected_runs = max(1, int(days * 24 / MONITOR_INTERVAL_HOURS))
    min_expected_successes = max(1, expected_runs - 2)

    source_error_counter = Counter()
    for report in run_logs:
        for source in report.get("sources", []):
            if source.get("status") not in {"error", "partial"} or source.get("enabled") is False:
                continue
            if active_source_ids is not None and source.get("source_id") not in active_source_ids:
                continue
            source_error_counter[source.get("source_id") or "unknown"] += 1

    source_health = {}
    for log in sorted(source_history if source_history is not None else run_logs,
                      key=lambda row: row.get("run_at", "")):
        timestamp = _parse_iso_datetime(log.get("run_at"))
        if timestamp is None or timestamp > now:
            continue
        for source in log.get("sources", []):
            source_id = source.get("source_id")
            if not source_id or source.get("status") == "disabled" or source.get("enabled") is False:
                continue
            if active_source_ids is not None and source_id not in active_source_ids:
                continue
            health = source_health.setdefault(source_id, {"zeros": 0, "last_ok": None, "last_items": None})
            status = source.get("status")
            count = source.get("collected")
            health["zeros"] = health["zeros"] + 1 if count == 0 or status == "error" else 0
            # Legacy ok/0 cannot prove a healthy empty response.
            if status in {"ok", "empty", "filtered"} and (count != 0 or "candidates" in source):
                health["last_ok"] = timestamp
            if count and status in {"ok", "partial"}:
                health["last_items"] = timestamp

    notification_errors = sum(1 for row in history_rows if row.get("notification_error"))
    notified_count = sum(1 for row in history_rows if row.get("notified"))
    new_count = sum(1 for row in history_rows if row.get("event") == "new")
    updated_count = sum(1 for row in history_rows if row.get("event") == "updated")
    source_error_total = sum(source_error_counter.values())
    stale = latest_success is None or now - latest_success > timedelta(hours=18)

    issues = []
    if stale:
        issues.append("최근 성공 실행이 18시간 이상 없습니다")
    if len(success_runs) < min_expected_successes:
        issues.append(f"최근 {days}일 스케줄 성공 횟수가 낮습니다 ({len(success_runs)}/{expected_runs})")
    if failed_runs:
        issues.append(f"최근 {days}일 스케줄 실패가 {len(failed_runs)}회 있습니다")
    if source_error_total:
        issues.append(f"최근 {days}일 소스 에러가 {source_error_total}회 있습니다")
    if notification_errors:
        issues.append(f"최근 {days}일 텔레그램 전송 오류가 {notification_errors}회 있습니다")

    if active_source_ids is not None:
        for source_id in sorted(active_source_ids - source_health.keys()):
            issues.append(f"{source_id}: 정상 수집 로그 없음")
    for source_id, health in sorted(source_health.items()):
        if health["zeros"] >= 3:
            issues.append(f"{source_id}: 연속 0건 {health['zeros']}회 (빈 결과/필터 제외/실패 확인 필요)")
        if health["last_ok"] is None or now - health["last_ok"] > timedelta(hours=18):
            issues.append(f"{source_id}: 마지막 정상 시각 {_format_kst(health['last_ok'])}, 18시간 내 정상 수집 확인 안 됨")

    status = "healthy" if not issues else "warning"
    title = "[국제 모니터 주간 점검] 정상 작동중" if status == "healthy" else "[국제 모니터 주간 점검] 이상 감지"

    lines = [
        title,
        f"점검 시각: {_format_kst(now)}",
        f"점검 기간: {_format_kst(now - timedelta(days=days))} ~ {_format_kst(now)}",
        f"스케줄 실행: 성공 {len(success_runs)}회, 실패 {len(failed_runs)}회",
        f"최근 성공: {_format_kst(latest_success)}",
        f"이벤트: 신규 {new_count}건, 업데이트 {updated_count}건, 실제 전송 {notified_count}건",
    ]

    if run_logs:
        lines.append(f"소스 로그: 에러 {source_error_total}회")
    else:
        lines.append("소스 로그: 아직 주간 점검용 run log가 충분히 쌓이지 않았습니다")

    if source_error_counter:
        top_sources = ", ".join(f"{source_id} {count}회" for source_id, count in source_error_counter.most_common(5))
        lines.append(f"에러 소스: {top_sources}")

    if source_health:
        lines.append("소스별 마지막 정상 시각:")
        for source_id, health in sorted(source_health.items()):
            lines.append(f"- {source_id}: {_format_kst(health['last_ok'])}; 마지막 항목 {_format_kst(health['last_items'])}; 연속 0건 {health['zeros']}회")

    if status == "healthy":
        lines.append("판정: 지난 한 주 기준 이상 징후 없이 정상 작동중입니다.")
    else:
        lines.append("판정: 아래 항목을 확인해 주세요.")
        for issue in issues:
            lines.append(f"- {issue}")

    return HealthReport(status=status, message="\n".join(lines))


def main() -> int:
    args = parse_args()
    now = utc_now()
    since = now - timedelta(days=args.days)

    repository = os.environ.get("GITHUB_REPOSITORY", "coolpint/international")
    github_token = os.environ.get("GITHUB_TOKEN")
    history_rows = _load_ndjson_since(Path(args.history_dir), since)
    run_logs = _load_ndjson_since(Path(args.run_log_dir), since)
    runs = load_monitor_runs(repository, args.workflow_file, since, github_token)
    source_history = _load_ndjson_since(Path(args.run_log_dir), datetime.min.replace(tzinfo=timezone.utc))
    active_source_ids = {source.id for source in load_sources(REPO_ROOT / "config" / "sources.json") if source.enabled}
    report = build_health_report(runs, history_rows, run_logs, now, args.days, source_history, active_source_ids)

    print(report.message)

    if not args.dry_run:
        if not telegram_is_configured():
            print("[error] Telegram secrets not configured.", file=sys.stderr)
            return 1
        send_telegram_text(report.message)

    return 0 if report.status == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
