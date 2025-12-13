# Telegram Verification Bot with Mercle SDK

A Telegram bot that verifies new group members using Mercle's biometric face verification.

## Features

- ✅ **Auto-verify new members** when they join Telegram groups
- 📱 **Mobile support** - Deep links open Mercle app directly
- 💻 **Desktop support** - QR codes for scanning
- ⏰ **30-second verification timeout**
- 🔐 **Biometric authentication** via Mercle SDK
- 🤖 **Group moderation** - Auto-mute unverified users

## Project Structure

```
telegrambot/
├── bot/
│   ├── config.py              # Configuration loader
│   ├── main.py                # Bot entry point (polling mode)
│   ├── handlers/              # Command & event handlers
│   │   ├── commands.py        # /start, /verify, /status, /help
│   │   ├── member_events.py   # New member joins
│   │   └── callbacks.py       # Button callbacks
│   ├── services/              # Business logic
│   │   ├── mercle_sdk.py      # Mercle API client
│   │   ├── verification.py    # Verification flow
│   │   └── user_manager.py    # User database operations
│   └── utils/                 # Utilities
│       ├── qr_generator.py    # QR code generation
│       └── messages.py        # Message templates
├── database/
│   ├── models.py              # SQLAlchemy models
│   └── db.py                  # Database connection
├── webhook_app.py             # FastAPI webhook (for production)
├── requirements.txt           # Python dependencies
└── .env                       # Configuration (not in git)
```

## Setup

### 1. Install Dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

The `.env` file is already configured with:

```env
BOT_TOKEN=8015740704:AAEvhfS5UwXOk_dbICe_fC8hmNbm_0RNF-I
MERCLE_API_URL=https://newapi.mercle.ai/api/mercle-sdk
MERCLE_API_KEY=815bb028-825a-414b-96da-fb751ec3c97a
VERIFICATION_TIMEOUT=30
```

### 3. Run Bot (Polling Mode - Development)

```bash
python bot/main.py
```

### 4. Test Commands

Open Telegram and message `@mercleMerci_bot`:

- `/start` - Start the bot
- `/verify` - Start verification flow
- `/status` - Check verification status
- `/help` - Show help message

## How It Works

### User Verification Flow

1. User types `/verify` in bot DM
2. Bot creates Mercle SDK session
3. Bot sends message with:
   - 📱 Button to open Mercle app (mobile)
   - 📥 Button to download app
   - 💻 QR code (desktop)
4. User verifies via Mercle app (face scan)
5. Bot polls Mercle API for status (every 3 seconds)
6. When verified:
   - User saved to database
   - Success message sent
   - User can access groups

### Group Member Verification Flow

1. New user joins Telegram group
2. Bot **immediately restricts** the user (mutes them)
3. Bot sends group message: "Please verify in DM"
4. Bot sends **DM** with verification instructions
5. User verifies (same flow as above)
6. Bot **unrestricts** user in group
7. User can now participate

If user doesn't verify within 30 seconds:
- User stays muted
- Can type `/verify` later to try again

## Database Schema

### Users Table
```sql
telegram_id (PK) | username | mercle_user_id | verified_at
```

### Verification Sessions Table
```sql
session_id (PK) | telegram_id | group_id | created_at | expires_at | status
```

### Group Settings Table
```sql
group_id (PK) | group_name | verification_required | timeout_seconds
```

## API Integration

### Mercle SDK Endpoints

**Create Session:**
```
POST https://newapi.mercle.ai/api/mercle-sdk/session/create
Header: X-API-Key: 815bb028-825a-414b-96da-fb751ec3c97a
Body: { "metadata": {...} }

Response:
{
  "session_id": "abc123",
  "qr_data": "{...}",
  "base64_qr": "eyJ...",
  "deep_link": "mercle://verify?session_id=abc123"
}
```

**Check Status:**
```
GET https://newapi.mercle.ai/api/mercle-sdk/session/status?session_id=abc123
Header: X-API-Key: 815bb028-825a-414b-96da-fb751ec3c97a

Response:
{
  "status": "approved",
  "localized_user_id": "mercle_user_123"
}
```

## Deployment to EC2

### 1. Copy to EC2

```bash
scp -r telegrambot/ telegrambot:~/
```

### 2. Install on EC2

```bash
ssh telegrambot
cd telegrambot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Run with systemd

Create `/etc/systemd/system/telegrambot.service`:

```ini
[Unit]
Description=Telegram Verification Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/telegrambot
Environment="PATH=/home/ubuntu/telegrambot/venv/bin"
EnvironmentFile=/home/ubuntu/telegrambot/.env
ExecStart=/home/ubuntu/telegrambot/venv/bin/python bot/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Start the service:

```bash
sudo systemctl enable telegrambot
sudo systemctl start telegrambot
sudo systemctl status telegrambot
```

## Testing

### Test in Bot DM

1. Open Telegram
2. Search for `@mercleMerci_bot`
3. Click "Start"
4. Type `/verify`
5. Scan QR code or tap button
6. Verify your face in Mercle app

### Test in Group

1. Create a test Telegram group
2. Add `@mercleMerci_bot` to the group
3. Make bot an **admin** with these permissions:
   - ✅ Delete messages
   - ✅ Ban users
   - ✅ Invite users via link
   - ✅ Restrict members
4. Have someone join the group
5. Bot should mute them and send DM
6. After verification, bot unmutes them

## Bot Commands

- `/start` - Welcome message
- `/verify` - Start verification flow
- `/status` - Check verification status
- `/help` - Show help message

## Troubleshooting

### Bot doesn't respond in group

- Make sure bot is **admin** in the group
- Check bot has permission to **restrict members**

### Verification times out

- Check Mercle API is accessible
- Verify API key is correct
- Check user has Mercle app installed

### QR code doesn't work

- Make sure base64_qr is being decoded correctly
- Check QR code image is being sent properly

## Support

- Mercle SDK Docs: https://newapi.mercle.ai/docs
- Telegram Bot API: https://core.telegram.org/bots/api
- Bot: @mercleMerci_bot

## License

MIT

