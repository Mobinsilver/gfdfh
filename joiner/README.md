# Telegram Voice Chat Joiner Bot

A powerful Telegram bot for managing multiple accounts and joining voice chats automatically.

## Features

- 🔐 **Account Management**: Add up to 50 Telegram accounts
- 🎤 **Voice Chat Joining**: Join multiple voice chats simultaneously
- 👥 **Group Management**: Join groups and channels automatically
- 🛡️ **Access Control**: Owner and admin permission system
- ⏰ **Auto Leave**: Automatic leave after specified time
- 🔑 **2FA Support**: Full support for two-factor authentication
- 📊 **Real-time Monitoring**: Account status and system monitoring

## Quick Start

### 1. Deploy to Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/deploy)

### 2. Configure Environment Variables

```bash
BOT_TOKEN=8469823668:AAGj7SQBgORsGtJDOhE-sv5A-2wjGU69MC0
API_ID=your_api_id_here
API_HASH=your_api_hash_here
OWNER_ID=5803428693
```

### 3. Get API Credentials

**Method 1: Automatic (Recommended)**
1. Start the bot
2. Send `/getapi +989123456789`
3. Copy the API_ID and API_HASH
4. Set them in Railway environment variables

**Method 2: Manual**
1. Go to https://my.telegram.org/apps
2. Create a new application
3. Copy API_ID and API_HASH
4. Set them in Railway environment variables

## Commands

### Account Management
- `+989123456789` - Add new account
- `/code 12345` - Verify account with code
- `/password mypass` - Verify account with 2FA password
- `/acc` - List all accounts
- `/del +989123456789` - Delete account
- `/logout +989123456789` - Logout account

### Voice Chat Management
- `/join 25` - Join 25 accounts to current group and voice chat
- `/joinall @group` - Join all accounts to group
- `/addvoice +989123456789 @group voice_chat_id` - Add account to voice chat
- `/removevoice +989123456789 @group voice_chat_id` - Remove account from voice chat
- `/listvoice` - List all active voice chats
- `/accountvoice +989123456789` - List voice chats for account

### Settings
- `/time 30` - Set auto-leave time (minutes)
- `/ping` - Check bot status
- `/getapi +989123456789` - Get API credentials
- `/help` - Show complete bot commands

### Admin Management
- `/setowner 123456789` - Set bot owner (once)
- `/promote 123456789` - Promote user to admin
- `/demote 123456789` - Demote admin to user

## Usage Example

1. **Set Owner**: `/setowner 5803428693`
2. **Add Account**: `+989123456789`
3. **Verify**: `/code 12345`
4. **Join Group**: `/join 25`
5. **Check Status**: `/ping`

## Requirements

- Python 3.9+
- Telegram Bot Token
- Telegram API credentials
- Railway account (for deployment)

## Support

For support and questions, contact: [@silverrmb](https://t.me/silverrmb)

## License

This project is for educational purposes only.
