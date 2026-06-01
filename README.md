# Cursor-Hermes Bridge

A production-ready bridge that lets [Hermes Agent](https://github.com/NousResearch/hermes-agent) monitor and control [Cursor](https://cursor.sh) from Telegram.

## Architecture

```
Telegram ──→ Telegram Bot ──→ FastAPI API ──→ Adapters ──→ Cursor (local)
                │                                      │
                │              ┌────────────────────────┘
                │              │
                └──→ Auth Service → SQLite Storage
```

### Components

- **Telegram Bot** (aiogram): Receives commands, sends progress summaries and alerts
- **FastAPI API**: Local control plane with authenticated endpoints
- **Adapters**: Pluggable backends for Cursor integration
- **Watchers**: Filesystem and polling watchers for Cursor activity
- **Summarizers**: Generate human-readable progress updates
- **SQLite**: Persistent storage for sessions, events, alerts, and auth

## Quick Start

### Prerequisites

- Python 3.12+
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- Cursor installed locally

### Installation

```bash
git clone https://github.com/your-org/cursor-hermes-bridge.git
cd cursor-hermes-bridge
make install
```

### Configuration

Copy `.env.example` to `.env` and fill in your settings:

```bash
cp .env.example .env
```

Required settings:

| Key | Description |
|-----|-------------|
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token from BotFather |
| `TELEGRAM_ALLOWED_CHAT_IDS` | Comma-separated chat IDs authorized to control Cursor |

### Running

```bash
make run
```

### With Docker

```bash
docker-compose up -d
```

## Telegram Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/status` | Show current Cursor status | `/status` |
| `/send <prompt>` | Send a prompt to the active session | `/send Refactor auth.py` |
| `/continue` | Continue the current session | `/continue` |
| `/stop` | Stop the current session | `/stop` |
| `/new` | Start a new session | `/new` |
| `/sessions` | List recent sessions | `/sessions` |
| `/switch <id>` | Switch to a different session | `/switch abc-123` |
| `/summary` | Get summary of active session | `/summary` |
| `/tail [lines]` | Tail recent output | `/tail 50` |

## Example Flow

```
You: /send Build a login page with NextAuth
Bot: ⏳ Starting new session...
Bot: 📝 Session s-abc created. Sending prompt...
Bot: 🔧 Planning: Analyzing project structure...
Bot: 🔧 Editing: Creating pages/api/auth directory
Bot: 🔧 Editing: Writing [...nextauth].ts handler
Bot: ✅ Completed: 4 files changed, tests passing

You: /summary
Bot: 📋 Session s-abc Summary:
     Stage: Completed
     Files changed: 4
     Duration: 3m 42s
     Adapter: cursor_logs
```

## Adapters

| Adapter | Status | Description |
|---------|--------|-------------|
| `cursor_logs` | ✅ MVP | Reads Cursor log/session files. No external dependencies. |
| `cursor_cli` | 🚧 Feature-flagged | Uses Cursor CLI for direct prompt injection. |
| `cursor_cdp` | 🔬 Experimental | Chrome DevTools Protocol for Cursor UI automation. Behind `ENABLE_CDP_ADAPTER` flag. |

### Adapter Comparison

| Feature | cursor_logs | cursor_cli | cursor_cdp |
|---------|-------------|------------|------------|
| Read status | ✅ Full | ✅ Full | ✅ Full |
| Send prompts | ⚠️ Queue only | ✅ Direct | ✅ Direct |
| New session | ⚠️ Signal only | ✅ Full | ✅ Full |
| Stop session | ⚠️ Signal only | ✅ Full | ✅ Full |
| Progress detail | ✅ High | ✅ High | ✅ Medium |
| Reliability | 🟢 High | 🟡 Medium | 🔴 Low |
| Setup complexity | 🟢 None | 🟡 CLI install | 🔴 Complex |

## Configuration

All configuration is via environment variables or `.env` file:

```ini
# Required
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_ALLOWED_CHAT_IDS=123456789,987654321

# API (optional)
API_HOST=127.0.0.1
API_PORT=8920
API_SECRET_TOKEN=

# Storage
DATABASE_PATH=data/cursor-bridge.db

# Watchers
WATCHER_LOG_PATHS=

# Adapters
ADAPTER_PRIMARY=cursor_logs
ENABLE_CDP_ADAPTER=false

# Summarizer
SUMMARIZER_TYPE=local

# Logging
LOG_LEVEL=INFO
```

## Cursor Paths

| OS | Log Directory | Session Directory |
|----|---------------|-------------------|
| macOS | `~/Library/Application Support/Cursor/logs/` | `~/Library/Application Support/Cursor/sessions/` |
| Linux | `~/.config/Cursor/logs/` | `~/.config/Cursor/sessions/` |
| Windows | `%APPDATA%\Cursor\logs\` | `%APPDATA%\Cursor\sessions\` |

## Development

```bash
make install    # Install dependencies
make run        # Start the server
make test       # Run tests
make lint       # Lint code
make clean      # Clean up
```

## Project Structure

```
cursor-hermes-bridge/
  app/
    main.py              # FastAPI entry point
    api/                 # API routes and dependencies
    adapters/            # Cursor backends (logs, CLI, CDP)
    services/            # Business logic services
    models/              # Typed domain models
    storage/             # SQLite + JSONL persistence
    watchers/            # Filesystem + polling watchers
    summarizers/         # Progress summarization
    utils/               # Config, logging
  tests/                 # Test suite
  docs/                  # Documentation
  scripts/               # Setup and run scripts
  examples/              # Configuration examples
```

## Limitations

- **MVP uses log watching** — no direct Cursor API integration yet. Prompt injection works via a command queue that requires Cursor CLI to be installed.
- **macOS first** — default paths target macOS. Linux and Windows paths require manual configuration.
- **CDP adapter is experimental** — Electron automation is fragile and feature-flagged.

## License

MIT
