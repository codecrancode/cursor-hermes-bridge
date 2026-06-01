# Architecture

## Overview

Cursor-Hermes Bridge is a local intermediary that connects Telegram to a running Cursor IDE instance. It uses a pluggable adapter architecture so it can work with multiple Cursor integration backends.

## System Architecture

```
┌──────────────┐     ┌──────────────────────┐     ┌──────────────┐
│   Telegram   │────→│   Telegram Service   │────→│  Auth Service│
│   Client     │←────│   (aiogram Bot)      │←────│  (chat IDs)  │
└──────────────┘     └──────────────────────┘     └──────────────┘
                              │
                              ▼
                     ┌──────────────────┐     ┌──────────────────┐
                     │  FastAPI Server  │────→│  Session Service │
                     │  (port 8920)     │←────│                  │
                     └──────────────────┘     └──────────────────┘
                              │
                              ▼
                     ┌──────────────────┐     ┌──────────────────┐
                     │  Adapter Layer   │────→│  Cursor Instance │
                     │  (pluggable)     │←────│  (local process) │
                     └──────────────────┘     └──────────────────┘
                              │
                              ▼
                     ┌──────────────────┐     ┌──────────────────┐
                     │  Watchers        │────→│  Log/Session     │
                     │  (filesystem)    │     │  Files (local)   │
                     └──────────────────┘     └──────────────────┘
                              │
                              ▼
                     ┌──────────────────┐
                     │  SQLite Storage  │
                     │  + JSONL Export  │
                     └──────────────────┘
```

## Data Flow

### Monitoring Flow
1. Watchers monitor Cursor log/session files for changes
2. Changes are parsed into structured ProgressEvents
3. ProgressService stores events and triggers alerts
4. SummaryService generates human-readable summaries
5. TelegramService sends formatted updates to authorized chats

### Command Flow
1. User sends Telegram command (e.g., `/send Refactor auth.py`)
2. TelegramService dispatches to the appropriate handler
3. Command is validated by AuthService (chat ID check)
4. SessionService routes to the active adapter
5. Adapter executes the command against Cursor
6. Result flows back through the chain to Telegram

## Component Details

### Adapters

Each adapter implements the `CursorAdapter` abstract base class. The adapter registry manages discovery and primary selection:

```python
class CursorAdapter(ABC):
    async def get_status(self) -> dict
    async def send_prompt(self, session_id: str, prompt: str) -> CommandResult
    async def continue_session(self, session_id: str) -> CommandResult
    async def stop_session(self, session_id: str) -> CommandResult
    async def new_session(self) -> CommandResult
    async def list_sessions(self) -> list[Session]
    async def switch_session(self, session_id: str) -> CommandResult
    async def get_summary(self, session_id: str) -> str
    async def tail_session(self, session_id: str, lines: int) -> str
    async def get_progress(self, session_id: str) -> list[ProgressEvent]
    def is_available(self) -> bool
```

### Services

- **TelegramService**: aiogram-based bot. Dispatches commands, sends alerts.
- **SessionService**: Session lifecycle management (create, activate, pause, complete, error).
- **ProgressService**: Structured progress tracking and alert triggering.
- **SummaryService**: Converts progress events to human-readable summaries.
- **AuthService**: Chat ID whitelist validation.

### Storage

SQLite database with four tables:
- `sessions` — session metadata and status
- `progress_events` — structured progress updates
- `alerts` — system alerts (complete, error, approval, timeout)
- `authorized_chats` — Telegram chat ID whitelist

## Security Boundaries

See `docs/security.md` for full threat model.
