import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', '8469823668:AAGj7SQBgORsGtJDOhE-sv5A-2wjGU69MC0')
API_ID = int(os.getenv('API_ID', '0'))
API_HASH = os.getenv('API_HASH')

# Owner Configuration
OWNER_ID = int(os.getenv('OWNER_ID', '5803428693'))

# Account Configuration
ACCOUNTS_FILE = 'accounts.json'
SESSIONS_DIR = 'sessions'

# Voice Chat Configuration
MAX_ACCOUNTS = 50
JOIN_DELAY = 1  # seconds between joins

# Logging Configuration
LOG_LEVEL = 'INFO'
LOG_FILE = 'bot.log'
