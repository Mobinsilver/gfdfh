import json
import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from loguru import logger
from config import API_ID, API_HASH, ACCOUNTS_FILE, SESSIONS_DIR

class AccountManager:
    def __init__(self):
        self.accounts = []
        self.clients = {}
        self.load_accounts()
        self.ensure_sessions_dir()
    
    def ensure_sessions_dir(self):
        """Create sessions directory if it doesn't exist"""
        if not os.path.exists(SESSIONS_DIR):
            os.makedirs(SESSIONS_DIR)
            logger.info(f"Created sessions directory: {SESSIONS_DIR}")
    
    def load_accounts(self):
        """Load accounts from JSON file"""
        try:
            if os.path.exists(ACCOUNTS_FILE):
                with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
                    self.accounts = json.load(f)
                logger.info(f"Loaded {len(self.accounts)} accounts from {ACCOUNTS_FILE}")
            else:
                self.accounts = []
                logger.info("No accounts file found, starting with empty list")
        except Exception as e:
            logger.error(f"Error loading accounts: {e}")
            self.accounts = []
    
    def save_accounts(self):
        """Save accounts to JSON file"""
        try:
            with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.accounts, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(self.accounts)} accounts to {ACCOUNTS_FILE}")
        except Exception as e:
            logger.error(f"Error saving accounts: {e}")
    
    def add_account(self, phone_number, session_string=None):
        """Add a new account to the manager"""
        try:
            account_data = {
                'phone': phone_number,
                'session_string': session_string,
                'active': False,
                'joined_groups': []
            }
            self.accounts.append(account_data)
            self.save_accounts()
            logger.info(f"Added account: {phone_number}")
            return True
        except Exception as e:
            logger.error(f"Error adding account {phone_number}: {e}")
            return False
    
    def add_account_with_session(self, phone_number, session_string):
        """Add a new account with session string"""
        try:
            account_data = {
                'phone': phone_number,
                'session_string': session_string,
                'active': True,  # Mark as active since we have session
                'joined_groups': []
            }
            self.accounts.append(account_data)
            self.save_accounts()
            logger.info(f"Added account with session: {phone_number}")
            return True
        except Exception as e:
            logger.error(f"Error adding account with session {phone_number}: {e}")
            return False
    
    def remove_account(self, phone_number):
        """Remove an account from the manager"""
        try:
            self.accounts = [acc for acc in self.accounts if acc['phone'] != phone_number]
            self.save_accounts()
            logger.info(f"Removed account: {phone_number}")
            return True
        except Exception as e:
            logger.error(f"Error removing account {phone_number}: {e}")
            return False
    
    async def create_client(self, account):
        """Create a Telegram client for an account"""
        try:
            phone = account['phone']
            session_string = account.get('session_string')
            
            if session_string:
                session = StringSession(session_string)
            else:
                session = StringSession()
            
            client = TelegramClient(session, API_ID, API_HASH)
            await client.start(phone=phone)
            
            # Save session string
            account['session_string'] = client.session.save()
            self.save_accounts()
            
            self.clients[phone] = client
            account['active'] = True
            
            logger.info(f"Created client for account: {phone}")
            return client
        except Exception as e:
            logger.error(f"Error creating client for {account['phone']}: {e}")
            account['active'] = False
            return None
    
    async def initialize_all_clients(self):
        """Initialize all account clients"""
        logger.info("Initializing all account clients...")
        
        for account in self.accounts:
            if not account['active']:
                await self.create_client(account)
                await asyncio.sleep(1)  # Delay between initializations
        
        active_count = sum(1 for acc in self.accounts if acc['active'])
        logger.info(f"Initialized {active_count} active clients out of {len(self.accounts)} accounts")
    
    async def get_active_clients(self):
        """Get all active clients"""
        return [client for phone, client in self.clients.items() if self.get_account_by_phone(phone)['active']]
    
    def get_account_by_phone(self, phone):
        """Get account data by phone number"""
        for account in self.accounts:
            if account['phone'] == phone:
                return account
        return None
    
    async def close_all_clients(self):
        """Close all active clients"""
        logger.info("Closing all clients...")
        for client in self.clients.values():
            try:
                await client.disconnect()
            except Exception as e:
                logger.error(f"Error closing client: {e}")
        self.clients.clear()
        logger.info("All clients closed")
    
    def get_accounts_info(self):
        """Get information about all accounts"""
        active_count = sum(1 for acc in self.accounts if acc['active'])
        return {
            'total': len(self.accounts),
            'active': active_count,
            'inactive': len(self.accounts) - active_count,
            'accounts': self.accounts
        }
