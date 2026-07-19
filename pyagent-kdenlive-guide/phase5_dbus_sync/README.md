# Phase 5 — D-Bus Live Sync

Live-apply three high-frequency edits (`pyagent_import_media`,
`pyagent_append_clip`, `pyagent_apply_effect`) directly to a running
Kdenlive instance over its built-in D-Bus interface. When Kdenlive is not
running, or the change is not live-capable, fall through to the Phase 3
file-mode backend and prompt the user to reopen the project.

## Architecture

```
LLM tool call (pi extension)
  -> callRuntime()
    -> liveApply()   [if PYAGENT_LIVE=1 and tool is LIVE_CAPABLE]
         -> spawnSync: python3 -m phase5_dbus_sync apply   (stdin = JSON)
              -> LiveSync.apply()
                   -> D-Bus (if available)   OR   Phase 3 file backend + notify-and-reload
    -> runRuntime()  [file-mode fallback / non-live tools]
```

`LiveSync.is_live(tool)` returns `True` only when Kdenlive is running
(`pgrep -x kdenlive`), its D-Bus service name can be discovered
(`busctl --user list | grep kdenlive`), and the tool is in `LIVE_CAPABLE`.

When a file-mode edit lands, `LiveSync` records the tool call. If the
cumulative count of file-mode edits since the last reload hits
`RELOAD_AFTER`, the next `reload_if_needed()` triggers
`KdenliveDBus.clean_restart(clean=False)` (the single-bool overload, which
reloads the current open project in place) and a `notify-send` so the
user sees the reload.

## File map (post-2026-07-19 cleanup)

| File | Purpose | Lines |
|---|---|---|
| `dbus_client.py` | The D-Bus client (`KdenliveDBus` wrapper, `LiveSync.apply`) | — |
| `live_sync.py` | Routing logic: live vs file-mode, reload trigger | — |
| `__main__.py` | `python3 -m phase5_dbus_sync {apply,notify}` CLI | — |

Legacy `kdenlive_state.py` (unused wrapper) and `notifier.py`
(`notify-send` subprocess wrapper) were deleted during the
2026-07-19 cleanup — `live_sync.py` calls `notify-send` directly
now (saves a process spawn per reload).

## CLI

```bash
# Apply a single tool call (JSON on stdin, JSON on stdout):
echo '{"tool":"pyagent_add_transition","args":{"duration_sec":1.0},"project":"/tmp/x.kdenlive"}' \
  | python3 -m phase5_dbus_sync apply

# Notify + reload:
python3 -m phase5_dbus_sync notify --file /tmp/x.kdenlive
```

## Enabling live mode

```bash
export PYAGENT_LIVE=1
# (PYAGENT_PROJECT must also be set)
```

Without `PYAGENT_LIVE=1`, the extension is byte-identical to Phase 3
behavior — live sync is opt-in.

## Tests

```bash
cd pyagent-kdenlive-guide
PYTHONPATH=. python3 -m pytest phase5_dbus_sync
# 29 passed
```

Per-test-file:

| File | Tests | Purpose |
|---|---|---|
| `test_dbus_client.py` | 15 | D-Bus method routing, return values, exception path, process discovery |
| `test_live_sync.py` | 11 | Live routing, file fallback, reload trigger, module entry |
| `test_apply_cli.py` | 3 | CLI plumbing end-to-end |
