import unittest
from datetime import datetime, timedelta, timezone

from src.healthcheck import build_health_report


class HealthcheckTests(unittest.TestCase):
    def test_build_health_report_marks_healthy_when_runs_are_clean(self) -> None:
        now = datetime(2026, 3, 26, 6, 45, tzinfo=timezone.utc)
        runs = [
            {"conclusion": "success", "updated_at": (now - timedelta(hours=8)).isoformat().replace("+00:00", "Z")},
            {"conclusion": "success", "updated_at": (now - timedelta(hours=16)).isoformat().replace("+00:00", "Z")},
        ]
        history_rows = [
            {"event": "new", "notified": True},
            {"event": "updated", "notified": False},
        ]
        run_logs = [
            {"run_at": now.isoformat().replace("+00:00", "Z"), "sources": [{"source_id": "adb_news", "status": "ok"}]}
        ]

        report = build_health_report(runs, history_rows, run_logs, now, days=1)

        self.assertEqual(report.status, "healthy")
        self.assertIn("정상 작동중", report.message)

    def test_build_health_report_marks_warning_on_failures(self) -> None:
        now = datetime(2026, 3, 26, 6, 45, tzinfo=timezone.utc)
        runs = [
            {"conclusion": "failure", "updated_at": (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z")},
        ]
        history_rows = [{"event": "new", "notified": False, "notification_error": "telegram failed"}]
        run_logs = [
            {
                "run_at": now.isoformat().replace("+00:00", "Z"),
                "sources": [{"source_id": "adb_news", "status": "error"}],
            }
        ]

        report = build_health_report(runs, history_rows, run_logs, now, days=1)

        self.assertEqual(report.status, "warning")
        self.assertIn("이상 감지", report.message)
        self.assertIn("adb_news", report.message)


if __name__ == "__main__":
    unittest.main()
