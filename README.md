# Smart Automation Orchestrator

Visual, dependency-aware orchestration timeline on top of Hermes cron.

## What it is
A unified Hermes plugin (Python tools/hooks + `desktop/plugin.js` + `dashboard/plugin_api.py`) that lets the agent create multi-step automations that respect dependency chains and optional calendar constraints. The user sees the chain on a Desktop timeline pane.

**Manual chain-runner design (honest):** There is no cron-completion hook in Hermes. Chains advance **only** when `orchestrator_trigger_chain` is called after verified success. `post_tool_call` is observer-only.

## Tools
- `orchestrator_create` — create a chain + steps (cycle detection)
- `orchestrator_status` — list jobs / status
- `orchestrator_graph` — nodes + edges for rendering
- `orchestrator_trigger_chain` — advance a job after verified success (validates deps + calendar)

## Hooks
- `post_tool_call` — observer logging of cron tool calls (fail-open)
- `on_session_start` — ensure DB exists

## Desktop
- Timeline pane (read-only)
- Status-bar chip
- Backend: `GET /api/plugins/smart-automation/status` and `/graph` — read-only. All mutations go through agent tools so Hermes approvals fire.

## Storage
SQLite in `ctx.state.data_dir` (`plugin-data/smart-automation/smart_automation.db`), WAL mode, schema v1.

## Disclosure —
- Reads a user-selected local `.ics` file if configured (never network calendars)
- Stores chain metadata locally in plugin data dir
- Creates metadata for underlying cron jobs via the agent (cron jobs themselves are managed by Hermes cron; this plugin only stores dependency metadata); no core Hermes files are modified
- No external network calls required. Slack/Calendar in demo are stubbed/mock and labelled as such.
- Nearest catalog neighbour: `cron-bulletin` (cron report inbox). Differentiation: this plugin ships a visual dependency graph + manual chain advancement, not a report inbox.

## Validation
```bash
python3 tests/test_smart_automation.py
hermes plugins validate --json .
```

## Demo (90s)
1. Prompt: "Create a weekday morning automation that only runs when my calendar shows a free block after 8am. First summarize overnight AI news, then post a short digest to Slack (mocked). Make the second job depend on the first succeeding. Show me the timeline."
2. Agent creates chain; Desktop timeline appears.
3. Manually trigger first job via `orchestrator_trigger_chain`; it completes.
4. Second job unlocks (status `ready`).
5. Status chip reflects state.

## License
MIT
