# MemoryLens Phase 3b — Alerting Design

**Date:** 2026-04-08
**Scope:** Threshold-based alerting on drift, cost, retrieval, compression loss, and error rate
**Status:** Approved
**Depends on:** Phase 1 SDK, Phase 2a-c, Phase 3a Drift Detection

---

## Overview

Alerting watches memory trace data and fires notifications when conditions exceed configured thresholds. Five built-in alert types cover drift health degradation, cost spikes, retrieval failures, compression loss, and error rates. Rules are CLI-managed and stored in SQLite. Alerts deliver via webhook (Slack, PagerDuty, etc.) and CLI log. A dedicated `memorylens alerts monitor` command runs the evaluation loop.

---

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Delivery | Webhook + CLI log | Webhook covers all production systems; CLI log for local dev |
| Rule definition | CLI-managed, SQLite storage | Fits existing pattern, no file editing |
| Alert types | 5: drift, cost, retrieval, compression_loss, error_rate | Covers PRD + two practical additions |
| Monitor | Separate `memorylens alerts monitor` | Clean separation from drift watch |

---

## Alert Rules Table

```sql
CREATE TABLE IF NOT EXISTS alert_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    alert_type TEXT NOT NULL,
    threshold REAL NOT NULL,
    webhook_url TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
)
```

## Alert History Table

```sql
CREATE TABLE IF NOT EXISTS alert_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL,
    alert_type TEXT NOT NULL,
    message TEXT NOT NULL,
    details TEXT NOT NULL,
    fired_at REAL NOT NULL
)
```

Both created lazily.

---

## Five Alert Types

| Type | Data Source | Threshold Meaning | Example |
|---|---|---|---|
| `drift` | drift_reports table | Grade as number: A=1,B=2,C=3,D=4,F=5. Alert when grade >= threshold | `--threshold 4` = alert on D or F |
| `cost` | span attributes (cost_usd) | Dollar amount per session | `--threshold 0.05` = alert when session costs > $0.05 |
| `retrieval` | READ spans | Proportion of reads with error or all scores < 0.5 | `--threshold 0.10` = alert at 10% failure rate |
| `compression_loss` | compression_audits table | Loss score | `--threshold 0.6` = alert on high loss |
| `error_rate` | all spans | Proportion with status=error | `--threshold 0.05` = alert at 5% error rate |

---

## AlertEvaluator

```python
@dataclass(frozen=True)
class AlertEvent:
    rule_name: str
    alert_type: str
    message: str
    details: dict

class AlertEvaluator:
    def __init__(self, exporter: SQLiteExporter): ...
    def evaluate_rule(self, rule: dict) -> list[AlertEvent]: ...
    def fire_alert(self, event: AlertEvent, rule: dict) -> None: ...
```

Each `evaluate_rule` call:
1. Queries relevant data based on alert_type
2. Checks threshold condition
3. Checks alert_history for cooldown (1 hour default) to avoid re-firing
4. Returns list of AlertEvents

`fire_alert` sends webhook (if configured) and saves to alert_history.

### Webhook Payload

```json
{
    "alert": "drift_threshold_exceeded",
    "rule_name": "critical-drift",
    "message": "Entity user_42_diet_prefs has grade F (drift: 0.82)",
    "details": {"memory_key": "user_42_diet_prefs", "grade": "F", "drift_score": 0.82},
    "timestamp": "2026-04-08T12:00:00Z"
}
```

Webhook uses `urllib.request` (stdlib) — no new dependencies. Timeout 10 seconds, no retries in v1.

---

## SQLiteExporter Extensions

```python
class SQLiteExporter:
    # Rule CRUD
    def save_alert_rule(self, rule: dict) -> None: ...
    def get_alert_rule(self, name: str) -> dict | None: ...
    def list_alert_rules(self, enabled_only: bool = False) -> list[dict]: ...
    def delete_alert_rule(self, name: str) -> None: ...
    def update_alert_rule(self, name: str, updates: dict) -> None: ...

    # History
    def save_alert_event(self, event: dict) -> None: ...
    def list_alert_history(self, alert_type: str | None = None,
                           limit: int = 50) -> list[dict]: ...
    def get_last_alert_time(self, rule_id: int) -> float | None: ...
```

---

## CLI Commands

```bash
# Manage rules
memorylens alerts add "critical-drift" --type drift --threshold 4 --webhook https://hooks.slack.com/...
memorylens alerts add "cost-spike" --type cost --threshold 0.05
memorylens alerts add "retrieval-failures" --type retrieval --threshold 0.10
memorylens alerts add "high-compression-loss" --type compression_loss --threshold 0.6
memorylens alerts add "error-spike" --type error_rate --threshold 0.05

memorylens alerts list
memorylens alerts remove "critical-drift"
memorylens alerts enable "cost-spike"
memorylens alerts disable "cost-spike"

# History
memorylens alerts history
memorylens alerts history --type drift

# Monitor
memorylens alerts monitor
memorylens alerts monitor --interval 30

# Live tail
memorylens alerts tail
```

---

## UI Integration

Minimal — visibility into alert state:

- `GET /alerts` — page with two tables: active rules + recent alert history
- Nav bar gets "Alerts" link in `base.html`
- No complex views or htmx interactions in v1

---

## File Structure

### New Files

```
src/memorylens/
├── _alerts/
│   ├── __init__.py
│   ├── evaluator.py        # AlertEvaluator, AlertEvent, 5 check functions
│   ├── webhook.py           # send_webhook() via urllib
│   └── monitor.py           # monitor loop
├── _ui/api/
│   └── alerts.py            # alerts page route
├── _ui/templates/
│   └── alerts.html          # alerts page
├── cli/commands/
│   └── alerts.py            # CLI alert commands
```

### Modified Files

| File | Change |
|---|---|
| `src/memorylens/_exporters/sqlite.py` | Add rule + history CRUD, lazy tables |
| `src/memorylens/_ui/server.py` | Register alert routes |
| `src/memorylens/_ui/templates/base.html` | Add "Alerts" nav link |
| `src/memorylens/cli/main.py` | Register alerts command group |

---

## Testing

```
tests/
├── test_alerts/
│   ├── __init__.py
│   ├── test_evaluator.py     # 5 alert type evaluations, cooldown logic
│   ├── test_webhook.py        # webhook payload format (mock HTTP)
│   └── test_storage.py        # rule + history CRUD
├── test_ui/
│   └── test_api_alerts.py     # alerts page route
├── test_cli/
│   └── test_alerts_commands.py # CLI commands
```

Webhook tested by mocking `urllib.request.urlopen`. Monitor tested by running one iteration, not the loop.
