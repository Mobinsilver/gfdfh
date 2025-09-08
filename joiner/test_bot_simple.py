#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Simple test to check if bot can start
"""

import asyncio
import sys
from loguru import logger

async def test_bot():
    """Test bot startup"""
    try:
        logger.info("Testing bot startup...")
        
        # Import config
        from config import BOT_TOKEN, API_ID, API_HASH, OWNER_ID
        
        logger.info(f"BOT_TOKEN: {BOT_TOKEN[:10]}...")
        logger.info(f"API_ID: {API_ID}")
        logger.info(f"API_HASH: {API_HASH[:10] if API_HASH else 'None'}...")
        logger.info(f"OWNER_ID: {OWNER_ID}")
        
        # Test bot import
        from bot import TelegramJoinerBot
        
        logger.info("Bot class imported successfully")
        
        # Test bot creation
        bot = TelegramJoinerBot()
        logger.info("Bot instance created successfully")
        
        # Test if bot can start (without actually starting)
        logger.info("Bot is ready to start!")
        
        return True
        
    except Exception as e:
        logger.error(f"Error: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_bot())
    if success:
        logger.info("✅ Bot test passed!")
        sys.exit(0)
    else:
        logger.error("❌ Bot test failed!")
        sys.exit(1)
