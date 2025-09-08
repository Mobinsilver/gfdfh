#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Voice Chat Joiner Bot - Start Script
"""

import asyncio
import sys
import os
import time
from loguru import logger

def check_requirements():
    """Check if all requirements are installed"""
    try:
        import telethon
        import aiofiles
        import dotenv
        import requests
        import bs4
        import psutil
        logger.info("✅ All requirements are installed")
        return True
    except ImportError as e:
        logger.error(f"❌ Missing requirement: {e}")
        logger.error("Please install requirements: pip install -r requirements.txt")
        return False

def check_config():
    """Check if configuration is valid"""
    try:
        from config import BOT_TOKEN, API_ID, API_HASH, OWNER_ID
        
        if not BOT_TOKEN or BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
            logger.error("❌ BOT_TOKEN not configured")
            return False
            
        if not API_ID or API_ID == 0:
            logger.warning("⚠️ API_ID not configured - use /getapi command")
            
        if not API_HASH or API_HASH == 'YOUR_API_HASH_HERE':
            logger.warning("⚠️ API_HASH not configured - use /getapi command")
            
        if not OWNER_ID or OWNER_ID == 0:
            logger.warning("⚠️ OWNER_ID not configured - use /setowner command")
            
        logger.info("✅ Configuration is valid")
        return True
        
    except Exception as e:
        logger.error(f"❌ Configuration error: {e}")
        return False

def create_directories():
    """Create necessary directories"""
    try:
        os.makedirs('sessions', exist_ok=True)
        os.makedirs('logs', exist_ok=True)
        logger.info("✅ Directories created")
        return True
    except Exception as e:
        logger.error(f"❌ Error creating directories: {e}")
        return False

async def main():
    """Main function"""
    logger.info("🚀 Starting Telegram Voice Chat Joiner Bot...")
    
    # Check requirements
    if not check_requirements():
        sys.exit(1)
    
    # Check configuration
    if not check_config():
        logger.error("❌ Configuration check failed")
        sys.exit(1)
    
    # Create directories
    if not create_directories():
        logger.error("❌ Directory creation failed")
        sys.exit(1)
    
    try:
        # Import and start bot
        from bot import TelegramJoinerBot
        
        logger.info("✅ Bot imported successfully")
        logger.info("🔄 Starting bot...")
        
        bot = TelegramJoinerBot()
        await bot.start_bot()
        
    except Exception as e:
        logger.error(f"❌ Error starting bot: {e}")
        logger.error(f"Error details: {str(e)}")
        # Don't exit, just log the error and continue
        logger.info("🔄 Retrying in 5 seconds...")
        await asyncio.sleep(5)
        await main()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        logger.error(f"Error details: {str(e)}")
        # Don't exit, just log the error and retry
        logger.info("🔄 Retrying in 10 seconds...")
        time.sleep(10)
        asyncio.run(main())

