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
) -> HealthReport:
    success_runs = [run for run in runs if run.get("conclusion") == "success"]
    failed_runs = [run for run in runs if run.get("conclusion") not in {"success", None}]
    latest_success = max((_parse_iso_datetime(run.get("updated_at")) for run in success_runs), default=None)
    expected_runs = max(1, int(days * 24 / MONITOR_INTERVAL_HOURS))
    min_expected_successes = max(1, expected_runs - 2)

    source_error_counter = Counter()
    latest_source_status = {}
    for report in run_logs:
        report_time = _parse_iso_datetime(report.get("run_at"))
        for source in report.get("sources", []):
            source_id = source.get("source_id") or "unknown"
            if source.get("status") == "error":
                source_error_counter[source_id] += 1

            previous = latest_source_status.get(source_id)
            if previous is None or (report_time is not None and report_time >= previous[0]):
                latest_source_status[source_id] = (
                    report_time or datetime.min.replace(tzinfo=timezone.utc),
                    source.get("status"),
                )

    notification_errors = sum(1 for row in history_rows if row.get("notification_error"))
    notified_count = sum(1 for row in history_rows if row.get("notified"))
    new_count = sum(1 for row in history_rows if row.get("event") == "new")
    updated_count = sum(1 for row in history_rows if row.get("event") == "updated")
    source_error_total = sum(source_error_counter.values())
    currently_failing_sources = sorted(
        source_id for source_id, (_, status) in latest_source_status.items() if status == "error"
    )
    stale = latest_success is None or now - latest_success > timedelta(hours=18)

    issues = []
    if stale:
        issues.append("최근 성공 실행이 18시간 이상 없습니다")
    if len(success_runs) < min_expected_successes:
        issues.append(f"최근 {days}일 스케줄 성공 횟수가 낮습니다 ({len(success_runs)}/{expected_runs})")
    if failed_runs:
        issues.append(f"최근 {days}일 스케줄 실패가 {len(failed_runs)}회 있습니다")
    if currently_failing_sources:
        issues.append(f"현재 실패 중인 소스가 {len(currently_failing_sources)}개 있습니다")
    if notification_errors:
        issues.append(f"최근 {days}일 텔레그램 전송 오류가 {notification_errors}회 있습니다")

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
    if currently_failing_sources:
        lines.append(f"현재 실패: {', '.join(currently_failing_sources)}")

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
    report = build_health_report(runs, history_rows, run_logs, now, args.days)

    print(report.message)

    if not args.dry_run:
        if not telegram_is_configured():
            print("[error] Telegram secrets not configured.", file=sys.stderr)
            return 1
        send_telegram_text(report.message)

    return 0 if report.status == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
