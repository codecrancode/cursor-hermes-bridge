# Cursor-Hermes Bridge

Build a production-ready Python bridge that lets Hermes monitor and control Cursor from Telegram.

## Architecture

```
Telegram ←→ FastAPI ←→ Adapters ←→ Cursor (local)
              │
              ├─ Session Service
              ├─ Progress Service
              ├─ Summary Service
              ├─ Auth Service
              └─ SQLite Storage
```

## Project Structure (CREATE ALL)

```
cursor-hermes-bridge/
  app/
    __init__.py
    main.py                    # FastAPI app entry, lifespan, startup
    api/
      __init__.py
      routes.py                # /status, /send, /continue, /stop, /new, /sessions, /switch, /summary, /tail
      deps.py                  # FastAPI dependency injection (auth, services)
    adapters/
      __init__.py
      base.py                  # Abstract CursorAdapter with async methods
      cursor_cli.py            # Preferred: Cursor Agent CLI integration
      cursor_logs.py           # Fallback: file/session log watcher
      cursor_cdp.py            # Experimental: Chrome DevTools Protocol (feature-flagged)
    services/
      __init__.py
      telegram_service.py      # Telegram bot (aiogram or python-telegram-bot)
      session_service.py       # Session lifecycle management
      progress_service.py      # Structured progress tracking
      summary_service.py       # Human-readable summaries
      auth_service.py          # Chat ID / user ID whitelist
    models/
      __init__.py
      session.py               # Session dataclass: id, created_at, status, adapter, metadata
      progress_event.py        # ProgressEvent dataclass: session_id, stage, detail, timestamp
      command_request.py       # CommandRequest: session_id, command, params
      command_result.py        # CommandResult: success, output, error, session_id
      alert.py                 # Alert: type, severity, message, session_id, timestamp
    storage/
      __init__.py
      database.py              # SQLite via aiosqlite: sessions, events, alerts, authorized_chats
      jsonl_export.py          # Optional JSONL export for debugging
    watchers/
      __init__.py
      filesystem_watcher.py    # watchdog-based filesystem watcher for Cursor logs
      polling_watcher.py       # Polling fallback when watchdog unavailable
    summarizers/
      __init__.py
      base.py                  # Abstract summarizer interface
      local_summarizer.py      # Simple template-based summarizer
    utils/
      __init__.py
      config.py                # Pydantic Settings
      logging.py               # Logging config (redact secrets)
  tests/
    __init__.py
    conftest.py                # Fixtures: mock adapter, test DB, test app
    test_adapters/
      __init__.py
      test_base.py
      test_cursor_logs.py
    test_services/
      __init__.py
      test_session_service.py
      test_progress_service.py
      test_summary_service.py
      test_auth_service.py
    test_api/
      __init__.py
      test_routes.py
    test_storage/
      __init__.py
      test_database.py
  docs/
    architecture.md
    backends.md
    security.md
  scripts/
    setup.sh
    run.sh
  examples/
    telegram-commands.md
    macos-config.example.yaml
  README.md
  .env.example
  docker-compose.yml
  Makefile
  pyproject.toml
```

## Technical Requirements

### Python & Dependencies
- Python 3.12+
- FastAPI with uvicorn
- aiogram for Telegram bot
- Pydantic v2 for settings/config
- aiosqlite for async SQLite
- watchdog for filesystem watching
- pytest + pytest-asyncio for tests
- httpx for async HTTP testing

### pyproject.toml Config
```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "cursor-hermes-bridge"
version = "0.1.0"
description = "Bridge that lets Hermes monitor and control Cursor from Telegram"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "aiogram>=3.14.0",
    "pydantic>=2.10.0",
    "pydantic-settings>=2.6.0",
    "aiosqlite>=0.20.0",
    "watchdog>=6.0.0",
    "httpx>=0.28.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=6.0",
]
```

### Models (dataclasses, all typed)

```python
# session.py
@dataclass
class SessionStatus(Enum):
    IDLE = "idle"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"

@dataclass
class Session:
    id: str  # UUID
    name: str
    status: SessionStatus
    adapter: str  # which adapter is active
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any]

# progress_event.py
@dataclass
class ProgressEvent:
    id: str
    session_id: str
    stage: str  # "planning", "editing", "testing", "completed", "error"
    detail: str
    timestamp: datetime
    metadata: dict[str, Any]

# command_request.py
@dataclass
class CommandRequest:
    session_id: str
    command: str  # "send", "continue", "stop", "new", "status", "switch"
    params: dict[str, Any]

# command_result.py
@dataclass
class CommandResult:
    success: bool
    output: str | None
    error: str | None
    session_id: str
    command: str

# alert.py
@dataclass
class AlertType(Enum):
    TASK_COMPLETE = "task_complete"
    TASK_ERROR = "task_error"
    APPROVAL_NEEDED = "approval_needed"
    INACTIVITY_TIMEOUT = "inactivity_timeout"
    INFO = "info"

@dataclass
class Alert:
    id: str
    type: AlertType
    severity: str  # "info", "warning", "error"
    message: str
    session_id: str | None
    timestamp: datetime
```

### Adapter Interface (base.py)

```python
class CursorAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def get_status(self) -> dict: ...

    @abstractmethod
    async def send_prompt(self, session_id: str, prompt: str) -> CommandResult: ...

    @abstractmethod
    async def continue_session(self, session_id: str) -> CommandResult: ...

    @abstractmethod
    async def stop_session(self, session_id: str) -> CommandResult: ...

    @abstractmethod
    async def new_session(self) -> CommandResult: ...

    @abstractmethod
    async def list_sessions(self) -> list[Session]: ...

    @abstractmethod
    async def switch_session(self, session_id: str) -> CommandResult: ...

    @abstractmethod
    async def get_summary(self, session_id: str) -> str: ...

    @abstractmethod
    async def tail_session(self, session_id: str, lines: int = 20) -> str: ...

    @abstractmethod
    async def get_progress(self, session_id: str) -> list[ProgressEvent]: ...

    @abstractmethod
    def is_available(self) -> bool: ...
```

### Config (config.py)

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Telegram
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_ALLOWED_CHAT_IDS: list[int]

    # API
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8920
    API_SECRET_TOKEN: str = ""  # empty = localhost-only

    # Storage
    DATABASE_PATH: str = "data/cursor-bridge.db"
    JSONL_EXPORT_PATH: str = ""

    # Watchers
    WATCHER_LOG_PATHS: list[str] = []

    # Adapters
    ADAPTER_PRIMARY: str = "cursor_logs"  # "cursor_cli", "cursor_logs"
    ENABLE_CDP_ADAPTER: bool = False

    # Summarizer
    SUMMARIZER_TYPE: str = "local"

    # Logging
    LOG_LEVEL: str = "INFO"

    # macOS default paths
    CURSOR_LOG_DIR: str = os.path.expanduser("~/Library/Application Support/Cursor/logs/")
    CURSOR_SESSION_DIR: str = os.path.expanduser("~/Library/Application Support/Cursor/sessions/")
```

### API Routes (routes.py)

```
GET    /health              → health check
GET    /status              → current Cursor status
POST   /send                → send prompt to active session
POST   /continue            → continue current session
POST   /stop                → stop current session
POST   /new                 → start a new session
GET    /sessions            → list sessions
POST   /switch/{id}         → switch to session
GET    /sessions/{id}       → get session details
GET    /sessions/{id}/summary  → get session summary
GET    /sessions/{id}/tail  → tail session output
GET    /sessions/{id}/progress → get progress events
```

### Storage Schema (database.py)

```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'idle',
    adapter TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata TEXT DEFAULT '{}'
);

CREATE TABLE progress_events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    detail TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE alerts (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    session_id TEXT,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE authorized_chats (
    chat_id INTEGER PRIMARY KEY,
    name TEXT,
    added_at TEXT NOT NULL
);
```

### Telegram Bot Commands

```
/status          → show Cursor status
/send <prompt>   → send prompt to active session
/continue        → continue current session
/stop            → stop current session
/new             → start a new session
/sessions        → list recent sessions
/switch <id>     → switch to a different session
/summary         → get summary of active session
/tail [lines]    → tail recent output
```

### Services

**telegram_service.py**: aiogram-based bot. Dispatches commands, sends alerts asynchronously. Falls back gracefully on connection errors with retries.

**session_service.py**: Manages session lifecycle. CRUD on SQLite. Tracks active session. Handles status transitions (idle→active→completed/paused/error).

**progress_service.py**: Receives updates from adapters, stores events, manages alert triggers (task complete, error, approval-needed, inactivity).

**summary_service.py**: Uses the summarizer to produce human-readable summaries from progress events.

**auth_service.py**: Checks message.chat.id against ALLOWED_CHAT_IDS. Logs unauthorized attempts. Simple, fast, no tokens needed for Telegram side (the bot token itself is the secret).

### Watchers

**filesystem_watcher.py**: Uses watchdog to monitor Cursor log/session directories. Emits ProgressEvents on file changes.

**polling_watcher.py**: Timer-based polling fallback when watchdog is unavailable.

### Summarizers

**base.py**: Abstract interface: `async def summarize(events: list[ProgressEvent]) -> str`

**local_summarizer.py**: Template-based summarizer. Takes the last N events, groups by stage, produces concise messages like:
- "Planning complete."
- "Editing auth middleware."
- "Paused: needs approval for terminal command."
- "Completed: 14 files changed, tests passing."

## Implementation Order (MVP first, then optional)

1. **Log/session watcher backend** (`cursor_logs.py`, `filesystem_watcher.py`)
2. **Telegram notifications** (`telegram_service.py`, bot commands)
3. **Local API** (`api/routes.py` + services)
4. **Command queue abstraction** (`adapters/base.py`, command routing)
5. **CLI adapter** (`cursor_cli.py`) — behind feature flag
6. **CDP adapter** (`cursor_cdp.py`) — behind `ENABLE_CDP_ADAPTER` flag

## Known Cursor Paths (macOS default)

```
Logs:             ~/Library/Application Support/Cursor/logs/
Sessions:         ~/Library/Application Support/Cursor/sessions/
Settings:         ~/Library/Application Support/Cursor/User/settings.json
```

For Linux: `~/.config/Cursor/`
For Windows: `%APPDATA%\Cursor\`

## Security Model

- Telegram bot token is the primary auth mechanism
- ALLOWED_CHAT_IDS restricts who can send commands
- API_SECRET_TOKEN protects local API (empty = localhost-only)
- All secrets redacted from logs
- CDP adapter requires explicit feature flag
- Clear warnings in docs about remote IDE control risks

## File-by-File Implementation Guide

### app/__init__.py
Empty.

### app/main.py
FastAPI app with lifespan that initializes all services. Connects Telegram bot. Registers routes. Health check at /health.

### app/api/__init__.py
Empty.

### app/api/deps.py
FastAPI dependency functions:
- `verify_auth(request)`: Checks X-API-Key header matches API_SECRET_TOKEN (or allows localhost without it)
- `get_session_service()`, `get_telegram_service()`: Inject services

### app/adapters/cursor_logs.py
Read Cursor's local log/session files. Parse structured data. Fallback pattern: try reading `.json` / `.log` files, parse timestamps and stages.

### app/services/telegram_service.py
Initialize aiogram Bot and Dispatcher. Register command handlers. Send formatted messages. Retry with exponential backoff on failures.

### app/services/session_service.py
CRUD for Session in SQLite. Track active session ID. Handle transitions.

### app/services/progress_service.py
Create, query, summarize ProgressEvents. Trigger alerts on thresholds.

### app/services/summary_service.py
Use summarizer to produce human-readable Telegram messages.

### app/services/auth_service.py
Check chat_id against allowed list. Log unauthorized access.

### app/storage/database.py
Async SQLite via aiosqlite. Create tables on init. CRUD methods for all tables.

### README.md
Full setup instructions, architecture diagram, command reference, adapter comparison, security notes, troubleshooting.

### docs/architecture.md
System architecture, component diagram, data flow.

### docs/backends.md
Adapter comparison table, when to use each, limitations.

### docs/security.md
Threat model, operational security, configuration checklist.

### .env.example
All config keys with placeholder values.

### Makefile
- `make install` — pip install
- `make run` — start uvicorn
- `make test` — run tests
- `make lint` — ruff check
- `make clean` — remove cache/data

### docker-compose.yml
Simple single-service compose file.

### tests/conftest.py
Fixtures: in-memory SQLite, mock adapter, test FastAPI app, test aiogram bot.

## CRITICAL RULES

1. All Python MUST be typed (mypy strict-compatible).
2. All async functions must have proper error handling.
3. SQLite operations use aiosqlite, NOT sqlite3 directly.
4. Telegram failures retry with exponential backoff (max 3 retries).
5. Log ALL secrets as `***REDACTED***`.
6. The MVP must work with ZERO external dependencies on Cursor internals — log watching only.
7. Every adapter MUST implement graceful degradation.
8. Feature flags for ALL experimental features.
9. README must have working `pip install` / `make install` instructions.
10. Test coverage: at least 80% on services/, adapters/, storage/.

## BUILD THIS NOW

Build the COMPLETE project. Every file listed above. Every class, every method, every test. Do NOT leave stubs. Do NOT leave TODO markers unless truly blocked by an unavailable external detail. Make reasonable assumptions about Cursor's local file layout and proceed.

After building, run `make test` to verify everything works.

Start with pyproject.toml and work down the file list. Build every file in full.
