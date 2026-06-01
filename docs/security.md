# Security

## Threat Model

### Trust Assumptions
- The bridge runs on the user's local machine
- The Telegram bot token is a shared secret between the user and Telegram
- Cursor IDE is a trusted application running on the same machine
- The local API is bound to localhost by default

### Threat: Unauthorized Telegram Access
An attacker who gains access to a user's Telegram account could send commands to the bridge.

**Mitigation:**
- `TELEGRAM_ALLOWED_CHAT_IDS` restricts which chat IDs can send commands
- Only the specific chat IDs listed in the config are authorized
- Unauthorized access attempts are logged with chat ID and timestamp
- The bot token itself is the primary auth mechanism; if compromised, rotate it via BotFather

### Threat: Remote API Access
An attacker on the local network could send commands to the bridge's API.

**Mitigation:**
- API binds to `127.0.0.1` by default (localhost-only)
- Set `API_SECRET_TOKEN` to a strong random value for remote access
- All API requests require `X-API-Key` header matching the secret token
- Rate limiting is recommended for production deployments

### Threat: IDE Remote Control
An attacker who compromises the bridge could control the user's Cursor IDE.

**Mitigation:**
- All API access is gated by authentication
- CDP adapter is disabled by default and requires explicit feature flag
- Command injection is prevented by the typed adapter interface
- All commands are logged with timestamps for audit

### Threat: Secrets Exposure
API keys or tokens could leak through logs or error messages.

**Mitigation:**
- All secrets are redacted in log output as `***REDACTED***`
- `.env` files are gitignored
- Database contents are encrypted at rest on macOS (FileVault) and Linux (LUKS)
- JSONL export files inherit filesystem permissions

## Operational Security Checklist

- [ ] `TELEGRAM_BOT_TOKEN` is set to a valid bot token
- [ ] `TELEGRAM_ALLOWED_CHAT_IDS` contains only authorized chat IDs
- [ ] `API_SECRET_TOKEN` is set to a strong random value (or API is localhost-only)
- [ ] `.env` file has `600` permissions (`chmod 600 .env`)
- [ ] `ENABLE_CDP_ADAPTER` is `false` unless explicitly needed
- [ ] Database file is in a directory with restricted permissions
- [ ] Bot token is rotated via BotFather if compromised
- [ ] Log files are regularly rotated and not publicly accessible

## Default Security Configuration

```ini
# Safe defaults
API_HOST=127.0.0.1
API_PORT=8920
API_SECRET_TOKEN=
ENABLE_CDP_ADAPTER=false
LOG_LEVEL=INFO
```

Report security vulnerabilities by opening a GitHub issue with the label `security`.
