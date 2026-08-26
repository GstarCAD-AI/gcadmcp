# Troubleshooting

## First step

```powershell
gstarcad-mcp validate-env --json
```

It reports OS/architecture, Python version, `pywin32`, registered
`GStarCAD.Application.*` ProgIDs, workspace writability, screenshot
prerequisites, dependency versions, and `gcadclaw_assets` availability.

## Common failures

| Symptom | Likely cause | Fix |
|---|---|---|
| `GSTARCAD_NOT_INSTALLED` / `COM_NOT_REGISTERED` | No registered ProgID | Install/repair GstarCAD; verify `validate-env` sees a ProgID |
| `CAD_STARTUP_TIMEOUT` | GstarCAD slow to launch or blocked by dialog | Increase `[cad] startup_wait_seconds`; clear modal dialogs |
| `CAD_CONNECTION_FAILED` | COM activation denied | Run as the interactive user; check one-server-per-instance rule |
| `SCREENSHOT_UNAVAILABLE` / blank screenshot | Session 0, minimized/hidden window, remote desktop quirks | Run in an interactive session; keep GstarCAD visible |
| `DOCUMENT_CONFLICT` | Stale `expected_revision` | Re-read document state and re-plan the edit |
| `IDEMPOTENCY_CONFLICT` | Same `operation_id` reused with different arguments | Generate a new `operation_id` per logical operation |
| `PATH_DENIED` | Path outside workspace / disallowed extension | Use workspace-relative paths under `inputs/` or `outputs/` |
| Host sees no tools | stdout contamination or bad launch command | Check host logs; run `gstarcad-mcp list-tools` locally |
| `CAD_QUEUE_FULL` | Backlog of operations | Reduce concurrency; check for a hung CAD dialog |
| Runtime `DEGRADED` after crash | GstarCAD exited/crashed | Restart GstarCAD or the server; document IDs from the old runtime are invalid (`runtime_id` changed) |

## Logs

- stderr from the server process (host log).
- Rotating file log under `workspace/logs/`.
- Append-only audit trail `workspace/logs/audit.jsonl`.

## Known limitations

- External-edit detection is `not_available`/`best_effort` in the MVP;
  prefer server-owned documents for unattended automation.
- Transaction mode is `best_effort` until undo grouping is verified per
  GstarCAD version.
- Screenshots require an interactive desktop; Session 0 is unsupported.
- Document IDs are valid only for the current server runtime.
