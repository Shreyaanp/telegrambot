# 🤖 Rose-Style Telegram Verification Bot

A production-ready Telegram bot with Rose bot-inspired architecture, featuring biometric verification via Mercle SDK, plugin system, and comprehensive group management tools.

## ✨ Features

### 🔐 Verification System
- **Auto-verification on group join** - New members are automatically muted and prompted to verify
- **Manual `/verify` command** - Users can verify in private messages
- **Global verification** - Once verified, users are recognized across all groups
- **Whitelist support** - Bypass verification for trusted users
- **Message cleanup** - All verification messages are deleted to keep chat clean
- **Per-group settings** - Each group can customize timeout, welcome message, etc.

### 👮 Admin Commands
- `/vkick @user` - Kick user from group
- `/vban @user [reason]` - Ban user from group
- `/settings` - View/update group settings
- `/vverify @user` - Manually verify user (bypass Mercle)

### ⚠️ Warning System
- `/warn @user [reason]` - Warn user
- `/warnings @user` - Show user's warnings
- `/resetwarns @user` - Clear warnings
- **Auto-kick at 3 warnings**

### 📋 Whitelist Management
- `/whitelist list` - Show whitelisted users
- `/whitelist add @user [reason]` - Add to whitelist
- `/whitelist remove @user` - Remove from whitelist

### 📜 Rules & Stats
- `/rules` - Display group rules
- `/setrules <text>` - Set group rules (admin only)
- `/stats` - Show verification statistics

### 🚫 Anti-Flood Protection
- Automatic message rate limiting
- Auto-mute users sending too many messages
- Configurable thresholds

## 🏗️ Architecture

### Plugin System
```
Bot Core
├── Plugin Manager (dynamic loading/unloading)
├── Verification Plugin (auto-join + /verify)
├── Admin Plugin (/vkick, /vban, /settings)
├── Warnings Plugin (/warn, /warnings)
├── Whitelist Plugin (/whitelist)
├── Rules Plugin (/rules, /setrules)
├── Stats Plugin (/stats)
└── Anti-Flood Plugin (rate limiting)
```

### Service Layer
```
Services
├── UserService (user CRUD)
├── GroupService (group settings & membership)
├── SessionService (verification sessions)
├── PermissionService (roles, whitelist, warnings)
├── MessageCleanerService (batch deletion)
└── MercleSDK (face verification API)
```

### Database Schema (SQLite with WAL mode)
```
Tables:
├── users (global verified users)
├── groups (group settings)
├── group_members (membership tracking)
├── verification_sessions (active verifications)
├── warnings (warning system)
├── whitelist (bypass verification)
├── permissions (custom admin roles)
└── flood_tracker (anti-flood)
```

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Telegram Bot Token (from @BotFather)
- Mercle SDK API Key
- Domain with SSL certificate (for production)

### Installation

1. **Clone and setup:**
```bash
cd /home/ichiro/telegrambot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. **Configure environment:**
```bash
# Edit .env file
BOT_TOKEN=your_bot_token_here
MERCLE_API_URL=https://newapi.mercle.ai/api/mercle-sdk
MERCLE_API_KEY=your_mercle_api_key_here
VERIFICATION_TIMEOUT=120
WEBHOOK_URL=https://telegram.mercle.ai
WEBHOOK_PATH=/webhook/secure-random-path
```

3. **Test locally (polling mode):**
```bash
# Create a simple test script
python3 << 'EOF'
import asyncio
from bot.core.bot import TelegramBot
from bot.config import Config
from bot.services.mercle_sdk import MercleSDK
from bot.plugins.verification import VerificationPlugin

async def main():
    config = Config()
    bot = TelegramBot(config)
    
    await bot.initialize()
    
    # Register Mercle SDK
    mercle_sdk = MercleSDK(config.mercle_api_url, config.mercle_api_key)
    bot.get_plugin_manager().register_service("mercle_sdk", mercle_sdk)
    
    # Load verification plugin
    await bot.load_plugins([VerificationPlugin])
    
    # Run in polling mode
    await bot.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
EOF
```

4. **Deploy to production (webhook mode):**
```bash
# On EC2 instance
cd /home/ubuntu/telegrambot

# Update code
git pull

# Install dependencies
source venv/bin/activate
pip install -r requirements.txt

# Start with systemd
sudo systemctl restart telegrambot
sudo systemctl status telegrambot
```

## 📦 Deployment

### Systemd Service
```ini
[Unit]
Description=Telegram Verification Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/telegrambot
Environment="PATH=/home/ubuntu/telegrambot/venv/bin"
ExecStart=/home/ubuntu/telegrambot/venv/bin/uvicorn webhook_server:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Nginx Configuration
```nginx
server {
    listen 80;
    server_name telegram.mercle.ai;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name telegram.mercle.ai;
    
    ssl_certificate /etc/letsencrypt/live/telegram.mercle.ai/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/telegram.mercle.ai/privkey.pem;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 🔧 Configuration

### Group Settings
Each group can be configured independently:

```bash
/settings                    # View current settings
/settings timeout 300        # Set 5-minute timeout
/settings autoverify on      # Enable auto-verification
/settings welcome Hello!     # Set custom welcome message
```

### Permission System
Hybrid system: Telegram admins + custom permissions

```python
# Telegram admins: Full access to everything
# Custom permissions: Fine-grained control

await permission_service.grant_permission(
    group_id=group_id,
    telegram_id=user_id,
    role="moderator",
    granted_by=admin_id,
    can_verify=True,
    can_kick=False,
    can_ban=False,
    can_warn=True,
    can_settings=False
)
```

## 📊 Monitoring

### Health Check
```bash
curl https://telegram.mercle.ai/health
```

### Status & Metrics
```bash
curl https://telegram.mercle.ai/status
```

### Logs
```bash
# Systemd logs
sudo journalctl -u telegrambot -f

# Or application logs
tail -f /var/log/telegrambot/bot.log
```

## 🧪 Testing

### Create Test Group
1. Create a new Telegram group
2. Add the bot to the group
3. Make bot an admin with permissions:
   - Delete messages
   - Ban users
   - Restrict members

### Test Scenarios

**Auto-Verification Flow:**
1. Join the group with a test account
2. Bot should mute you immediately
3. Bot sends verification message in group
4. Tap "Open Mercle App" or scan QR
5. Complete face verification
6. Bot unmutes you and deletes verification messages

**Manual Verification:**
1. Send `/verify` to bot in private message
2. Complete verification
3. Bot confirms success

**Admin Commands:**
```bash
/vkick @testuser          # Kick user
/vban @testuser spam      # Ban user
/warn @testuser rule5     # Warn user
/whitelist add @testuser  # Add to whitelist
/settings timeout 180     # Change timeout
/rules                    # Show rules
/stats                    # Show statistics
```

## 📁 Project Structure

```
telegrambot/
├── bot/
│   ├── core/
│   │   ├── bot.py                 # Main bot class
│   │   ├── plugin_manager.py      # Plugin system
│   │   └── __init__.py
│   ├── plugins/
│   │   ├── base.py                # Base plugin interface
│   │   ├── verification.py        # Verification plugin
│   │   ├── admin.py               # Admin commands
│   │   ├── warnings.py            # Warning system
│   │   ├── whitelist.py           # Whitelist management
│   │   ├── rules.py               # Rules system
│   │   ├── stats.py               # Statistics
│   │   ├── antiflood.py           # Anti-flood
│   │   └── __init__.py
│   ├── services/
│   │   ├── user_service.py        # User operations
│   │   ├── group_service.py       # Group operations
│   │   ├── session_service.py     # Session management
│   │   ├── permission_service.py  # Permissions
│   │   ├── message_cleaner.py     # Message deletion
│   │   ├── mercle_sdk.py          # Mercle API client
│   │   └── __init__.py
│   ├── utils/
│   │   ├── qr_generator.py        # QR code generation
│   │   ├── messages.py            # Message templates
│   │   ├── decorators.py          # Permission decorators
│   │   └── __init__.py
│   ├── config.py                  # Configuration
│   └── __init__.py
├── database/
│   ├── models.py                  # SQLAlchemy models
│   ├── db.py                      # Database connection
│   └── __init__.py
├── static/
│   └── verify.html                # Deep link redirect
├── webhook_server.py              # FastAPI webhook server
├── requirements.txt               # Dependencies
├── .env                           # Environment variables
├── .gitignore
├── README.md                      # This file
└── IMPLEMENTATION_PROGRESS.md     # Development progress
```

## 🔑 Environment Variables

```bash
# Telegram Bot
BOT_TOKEN=your_bot_token_from_botfather

# Mercle SDK
MERCLE_API_URL=https://newapi.mercle.ai/api/mercle-sdk
MERCLE_API_KEY=your_api_key
MERCLE_API_SECRET=your_api_secret
MERCLE_APP_ID=your_app_id

# Verification Settings
VERIFICATION_TIMEOUT=120  # seconds (2 minutes)

# Webhook Configuration
WEBHOOK_URL=https://telegram.mercle.ai
WEBHOOK_PATH=/webhook/secure-random-path-here
```

## 🛠️ Development

### Adding a New Plugin

```python
from bot.plugins.base import BasePlugin
from aiogram.filters import Command
from aiogram.types import Message

class MyPlugin(BasePlugin):
    @property
    def name(self) -> str:
        return "myplugin"
    
    @property
    def description(self) -> str:
        return "My custom plugin"
    
    async def on_load(self):
        await super().on_load()
        self.router.message.register(self.cmd_mycommand, Command("mycommand"))
    
    def get_commands(self):
        return [{"command": "/mycommand", "description": "My command"}]
    
    async def cmd_mycommand(self, message: Message):
        await message.answer("Hello from my plugin!")
```

### Database Migrations

```python
# Add migration script in database/migrations/
# Run manually or via CLI tool

async def migrate_add_column():
    async with db.session() as session:
        await session.execute(text("ALTER TABLE users ADD COLUMN new_field TEXT"))
        await session.commit()
```

## 📚 API Documentation

### FastAPI Endpoints

- `POST /webhook/secure-path` - Telegram webhook
- `GET /verify?session_id=...` - Deep link redirect
- `GET /health` - Health check
- `GET /status` - Status & metrics
- `GET /` - API information

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

MIT License - See LICENSE file for details

## 🙏 Acknowledgments

- **Rose Bot** - Inspiration for architecture and features
- **Mercle SDK** - Biometric verification system
- **aiogram** - Telegram Bot API framework
- **FastAPI** - Modern web framework

## 📞 Support

- **Issues**: Create an issue on GitHub
- **Documentation**: See `/help` in the bot
- **Email**: support@mercle.ai

---

**Built with ❤️ using Python, aiogram, FastAPI, and Mercle SDK**
