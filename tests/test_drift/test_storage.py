from __future__ import annotations

import time

import pytest

from memorylens._exporters.sqlite import SQLiteExporter


@pytest.fixture
def exporter(tmp_path):
    db_path = str(tmp_path / "test.db")
    exp = SQLiteExporter(db_path=db_path)
    yield exp
    exp.shutdown()


class TestVersionStorage:
    def test_save_and_get_version(self, exporter):
        version = {
            "memory_key": "user_42_prefs",
            "version": 1,
            "span_id": "span-001",
            "operation": "memory.write",
            "content": "User prefers vegetarian meals.",
            "embedding": [0.1, 0.2, 0.3],
            "agent_id": "agent-1",
            "session_id": "sess-1",
            "timestamp": time.time(),
        }
        exporter.save_version(version)
        rows = exporter.get_versions("user_42_prefs")
        assert len(rows) == 1
        assert rows[0]["memory_key"] == "user_42_prefs"
        assert rows[0]["version"] == 1
        assert rows[0]["content"] == "User prefers vegetarian meals."
        assert rows[0]["embedding"] == [0.1, 0.2, 0.3]

    def test_get_versions_ordered(self, exporter):
        base_time = time.time()
        for v in range(3):
            exporter.save_version({
                "memory_key": "key_a",
                "version": v + 1,
                "span_id": f"span-{v}",
                "operation": "memory.write",
                "content": f"Version {v + 1}",
                "embedding": None,
                "agent_id": None,
                "session_id": None,
                "timestamp": base_time + v,
            })
        rows = exporter.get_versions("key_a")
        assert len(rows) == 3
        assert [r["version"] for r in rows] == [1, 2, 3]

    def test_get_all_versions(self, exporter):
        for mk in ["key_a", "key_b"]:
            exporter.save_version({
                "memory_key": mk,
                "version": 1,
                "span_id": f"span-{mk}",
                "operation": "memory.write",
                "content": f"Content for {mk}",
                "embedding": None,
                "agent_id": None,
                "session_id": None,
                "timestamp": time.time(),
            })
        all_versions = exporter.get_all_versions()
        assert len(all_versions) == 2
        keys = {r["memory_key"] for r in all_versions}
        assert keys == {"key_a", "key_b"}

    def test_version_without_embedding(self, exporter):
        exporter.save_version({
            "memory_key": "no_embed",
            "version": 1,
            "span_id": "s1",
            "operation": "memory.write",
            "content": "text",
            "embedding": None,
            "agent_id": None,
            "session_id": None,
            "timestamp": time.time(),
        })
        rows = exporter.get_versions("no_embed")
        assert rows[0]["embedding"] is None

    def test_get_versions_unknown_key_returns_empty(self, exporter):
        rows = exporter.get_versions("nonexistent_key")
        assert rows == []


class TestDriftReportStorage:
    def _make_report(self, key="user_42", report_type="entity", grade="B"):
        return {
            "report_type": report_type,
            "key": key,
            "drift_score": 0.2,
            "contradiction_score": 0.1,
            "staleness_score": 0.3,
            "volatility_score": 0.15,
            "grade": grade,
            "details": {"version_count": 3},
            "created_at": time.time(),
        }

    def test_save_and_get_report(self, exporter):
        report = self._make_report()
        exporter.save_drift_report(report)
        result = exporter.get_drift_report("entity", "user_42")
        assert result is not None
        assert result["key"] == "user_42"
        assert result["grade"] == "B"
        assert isinstance(result["details"], dict)
        assert result["details"]["version_count"] == 3

    def test_upsert_replaces_existing(self, exporter):
        exporter.save_drift_report(self._make_report(grade="C"))
        exporter.save_drift_report(self._make_report(grade="F"))
        result = exporter.get_drift_report("entity", "user_42")
        assert result["grade"] == "F"

    def test_get_report_not_found_returns_none(self, exporter):
        result = exporter.get_drift_report("entity", "does_not_exist")
        assert result is None

    def test_list_drift_reports_no_filter(self, exporter):
        for i, grade in enumerate(["A", "B", "C"]):
            exporter.save_drift_report(self._make_report(key=f"key_{i}", grade=grade))
        rows, total = exporter.list_drift_reports()
        assert total == 3
        assert len(rows) == 3

    def test_list_drift_reports_filter_by_type(self, exporter):
        exporter.save_drift_report(self._make_report(key="e1", report_type="entity"))
        exporter.save_drift_report(self._make_report(key="s1", report_type="session"))
        rows, total = exporter.list_drift_reports(report_type="entity")
        assert total == 1
        assert rows[0]["report_type"] == "entity"

    def test_list_drift_reports_filter_by_min_grade_d(self, exporter):
        """min_grade=D should return D and F reports only."""
        for key, grade in [("a", "A"), ("b", "B"), ("c", "C"), ("d", "D"), ("f", "F")]:
            exporter.save_drift_report(self._make_report(key=key, grade=grade))
        rows, total = exporter.list_drift_reports(min_grade="D")
        grades_returned = {r["grade"] for r in rows}
        assert grades_returned == {"D", "F"}
        assert total == 2

    def test_list_drift_reports_pagination(self, exporter):
        for i in range(5):
            exporter.save_drift_report(self._make_report(key=f"key_{i}"))
        rows, total = exporter.list_drift_reports(limit=2, offset=0)
        assert total == 5
        assert len(rows) == 2
        rows2, _ = exporter.list_drift_reports(limit=2, offset=2)
        assert len(rows2) == 2
        # No overlap between pages
        keys1 = {r["key"] for r in rows}
        keys2 = {r["key"] for r in rows2}
        assert not keys1.intersection(keys2)
