# Backends (Adapters)

## Adapter Overview

The adapter architecture allows the bridge to work with multiple Cursor integration methods. Each adapter implements the same abstract interface, enabling graceful degradation and future-proofing.

## Available Adapters

### 1. `cursor_logs` (MVP Default) ✅

**Status:** Production-ready  
**Type:** Read-only monitoring + command queue

Reads Cursor's local log and session files to infer progress. Uses the filesystem watcher (watchdog) to detect file changes and parse structured progress information.

**Capabilities:**
- ✅ Read current status from log files
- ✅ List sessions from session directory
- ✅ Get progress events from log parsing
- ✅ Tail recent output (last N log lines)
- ⚠️ Send prompts via command queue file (Cursor CLI polls this file)

**Limitations:**
- Cannot directly inject prompts without Cursor CLI
- Progress detection depends on Cursor's logging format
- Session switching requires manual signal files

**When to use:** Always the default. Works with zero configuration.

### 2. `cursor_cli` (Feature-Flagged) 🚧

**Status:** Beta  
**Type:** Direct control via Cursor CLI

Uses the Cursor command-line interface (`cursor --...`) to send prompts, control sessions, and read results.

**Capabilities:**
- ✅ Send prompts directly
- ✅ Start new sessions
- ✅ Stop active sessions
- ✅ Continue sessions
- ✅ Full status reporting

**Limitations:**
- Requires `cursor` CLI to be installed and authenticated
- CLI API may change between Cursor versions
- Not available on all platforms

**When to use:** When direct prompt injection is needed and the Cursor CLI is available.

### 3. `cursor_cdp` (Experimental) 🔬

**Status:** Experimental — feature-flagged behind `ENABLE_CDP_ADAPTER=true`  
**Type:** UI automation via Chrome DevTools Protocol

Connects to Cursor's Electron instance via Chrome DevTools Protocol (CDP) to send commands and read the editor state.

**Capabilities:**
- ✅ Read editor content
- ✅ Send keystrokes and commands
- ✅ Read terminal output
- ✅ Full IDE automation theoretically possible

**Limitations:**
- 🔴 Extremely fragile — Electron/CDP breaks with every Cursor update
- 🔴 Requires matching Cursor's exact CDP endpoint/port
- 🔴 May need accessibility permissions
- 🔴 High latency
- **DO NOT use in production**

**When to use:** Only for experimentation or when no other adapter works.

## Adapter Selection

The primary adapter is configured via `ADAPTER_PRIMARY` in settings. The system falls back gracefully:

```
ADAPTER_PRIMARY=cursor_cli
```

If `cursor_cli` is unavailable, the system falls back to `cursor_logs` automatically.

## Feature Flags

| Flag | Default | Purpose |
|------|---------|---------|
| `ADAPTER_PRIMARY` | `cursor_logs` | Which adapter to use by default |
| `ENABLE_CDP_ADAPTER` | `false` | Enable experimental CDP adapter |

## Adding a New Adapter

1. Create `app/adapters/your_adapter.py`
2. Implement `CursorAdapter` ABC
3. Register with `@adapter_registry.register(...)`
4. Add tests in `tests/test_adapters/`
5. Document in `docs/backends.md`

```python
from .base import CursorAdapter, adapter_registry

@adapter_registry.register("your_adapter")
class YourAdapter(CursorAdapter):
    @property
    def name(self) -> str:
        return "your_adapter"

    async def is_available(self) -> bool:
        return True
    # ... implement all abstract methods
```
