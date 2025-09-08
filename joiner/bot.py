import asyncio
import os
import json
from telethon import TelegramClient, events
from telethon.tl.types import User, KeyboardButtonUrl, ReplyInlineMarkup, KeyboardButtonCallback
from telethon.tl.functions import help
from loguru import logger
from config import BOT_TOKEN, API_ID, API_HASH, LOG_LEVEL, LOG_FILE, OWNER_ID
import requests
from bs4 import BeautifulSoup
from account_manager import AccountManager
from voice_chat_joiner import VoiceChatJoiner

class TelegramJoinerBot:
    def __init__(self):
        self.bot = None
        self.auto_leave_time = 30  # زمان خروج خودکار (دقیقه)
        self.account_manager = AccountManager()
        self.voice_chat_joiner = VoiceChatJoiner(self.account_manager, self.auto_leave_time)
        self.admin_users = set()
        self.owner_id = OWNER_ID  # آیدی مالک ربات
        self.owner_phone = None  # شماره تلفن مالک ربات
        self.pending_verification = {}  # کدهای در انتظار تایید
        self.user_permissions = {}  # سطح دسترسی کاربران
        
        # Add owner to admin users
        if self.owner_id:
            self.admin_users.add(self.owner_id)
            self.user_permissions[self.owner_id] = {
                'add_accounts': True,
                'remove_accounts': True,
                'join_groups': True,
                'join_voice_chats': True,
                'manage_admins': True,
                'view_status': True
            }
        
        self.setup_logging()
    
    async def get_api_credentials(self, phone_number):
        """Get API credentials from Telegram website using account"""
        try:
            logger.info(f"Attempting to get API credentials for {phone_number}")
            
            # Create a temporary client for API credentials
            temp_client = TelegramClient(f'temp_{phone_number}', API_ID or 0, API_HASH or '')
            
            try:
                await temp_client.start(phone=phone_number)
                
                # Get API credentials from Telegram
                from telethon.tl.functions import help
                api_credentials = await temp_client(help.GetAppConfigRequest())
                
                # Extract API ID and Hash from the response
                api_id = None
                api_hash = None
                
                # Try to get from app config
                if hasattr(api_credentials, 'config') and api_credentials.config:
                    for item in api_credentials.config:
                        if hasattr(item, 'key') and hasattr(item, 'value'):
                            if item.key == 'api_id':
                                api_id = item.value
                            elif item.key == 'api_hash':
                                api_hash = item.value
                
                # If not found in app config, try alternative method
                if not api_id or not api_hash:
                    # Use the current client's credentials
                    api_id = temp_client.api_id
                    api_hash = temp_client.api_hash
                
                await temp_client.disconnect()
                
                if api_id and api_hash:
                    logger.info(f"Successfully retrieved API credentials for {phone_number}")
                    return {
                        'api_id': str(api_id),
                        'api_hash': str(api_hash),
                        'success': True
                    }
                else:
                    logger.error(f"Could not retrieve API credentials for {phone_number}")
                    return {
                        'success': False,
                        'error': 'Could not retrieve API credentials'
                    }
                    
            except Exception as e:
                logger.error(f"Error getting API credentials: {e}")
                await temp_client.disconnect()
                return {
                    'success': False,
                    'error': str(e)
                }
                
        except Exception as e:
            logger.error(f"Error in get_api_credentials: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_api_credentials_alternative(self, phone_number):
        """Alternative method to get API credentials"""
        try:
            logger.info(f"Using alternative method to get API credentials for {phone_number}")
            
            # Create a simple client to get credentials
            temp_client = TelegramClient(f'temp_api_{phone_number}', 0, '')
            
            try:
                await temp_client.start(phone=phone_number)
                
                # Get the client's API credentials
                api_id = temp_client.api_id
                api_hash = temp_client.api_hash
                
                await temp_client.disconnect()
                
                if api_id and api_hash:
                    logger.info(f"Successfully retrieved API credentials via alternative method")
                    return {
                        'api_id': str(api_id),
                        'api_hash': str(api_hash),
                        'success': True
                    }
                else:
                    return {
                        'success': False,
                        'error': 'No API credentials found'
                    }
                    
            except Exception as e:
                logger.error(f"Error in alternative method: {e}")
                await temp_client.disconnect()
                return {
                    'success': False,
                    'error': str(e)
                }
                
        except Exception as e:
            logger.error(f"Error in get_api_credentials_alternative: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def setup_logging(self):
        """Setup logging configuration"""
        logger.remove()
        logger.add(LOG_FILE, level=LOG_LEVEL, rotation="10 MB", retention="7 days")
        logger.add(lambda msg: print(msg, end=""), level=LOG_LEVEL)
        logger.info("Logging system initialized")
    
    async def start_bot(self):
        """Start the Telegram bot"""
        try:
            logger.info("Starting Telegram bot...")
            
            # Check if API credentials are available
            if not API_ID or not API_HASH or API_ID == 0:
                logger.warning("⚠️ API_ID or API_HASH not configured")
                logger.info("Bot will start but will request API credentials when needed")
                logger.info("Use /getapi +989123456789 to get API credentials")
                # Use default values for bot startup (bot only needs BOT_TOKEN)
                temp_api_id = 12345
                temp_api_hash = "temp_hash_for_startup"
            else:
                temp_api_id = API_ID
                temp_api_hash = API_HASH
            
            self.bot = TelegramClient('bot_session', temp_api_id, temp_api_hash)
            await self.bot.start(bot_token=BOT_TOKEN)
            
            # Register event handlers
            self.bot.add_event_handler(self.handle_message, events.NewMessage)
            self.bot.add_event_handler(self.handle_callback_query, events.CallbackQuery)
            
            logger.info("Bot started successfully")
            logger.info(f"Bot username: @{self.bot.me.username}")
            logger.info(f"Bot ID: {self.bot.me.id}")
            logger.info("Waiting for messages...")
            
            await self.bot.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            logger.error("Please check your BOT_TOKEN and API credentials")
            logger.error(f"Error details: {str(e)}")
            # Don't raise the exception, just log it and continue
    
    async def handle_message(self, event):
        """Handle incoming messages"""
        try:
            message = event.message
            sender = await event.get_sender()
            
            if not isinstance(sender, User):
                return
            
            user_id = sender.id
            text = message.text
            
            logger.info(f"Received message from {user_id}: {text}")
            
            # Check if user is admin
            if not self.is_authorized_user(user_id):
                # If no owner is set, allow first user to become owner
                if not self.owner_id or self.owner_id == 0:
                    await message.reply("""
🔐 **ربات برای اولین بار راه‌اندازی می‌شود**

برای شروع، ابتدا مالک ربات را تنظیم کنید:
/setowner YOUR_USER_ID

**نحوه دریافت آیدی خود:**
1. به @userinfobot پیام دهید
2. آیدی عددی خود را کپی کنید
3. دستور /setowner را با آیدی خود ارسال کنید
                    """)
                    return
                else:
                    await message.reply("❌ شما دسترسی لازم را ندارید.")
                    return
            
            # Handle commands
            if text.startswith('/start'):
                await self.handle_start_command(message)
            elif text.startswith('/add_account'):
                await self.handle_add_account_command(message)
            elif text.startswith('/remove_account'):
                await self.handle_remove_account_command(message)
            elif text.startswith('/list_accounts'):
                await self.handle_list_accounts_command(message)
            elif text.startswith('/join_group'):
                await self.handle_join_group_command(message)
            elif text.startswith('/leave_group'):
                await self.handle_leave_group_command(message)
            elif text.startswith('/join_voice'):
                await self.handle_join_voice_command(message)
            elif text.startswith('/status'):
                await self.handle_status_command(message)
            elif text.startswith('/add_admin'):
                await self.handle_add_admin_command(message)
            elif text.startswith('/join_multiple_voice'):
                await self.handle_join_multiple_voice_command(message)
            elif text.startswith('/joinall'):
                await self.handle_joinall_command(message)
            elif text.startswith('/code'):
                await self.handle_code_command(message)
            elif text.startswith('/promote'):
                await self.handle_promote_command(message)
            elif text.startswith('/demote'):
                await self.handle_demote_command(message)
            elif text.startswith('/list_admins'):
                await self.handle_list_admins_command(message)
            elif text.startswith('/clear_accounts'):
                await self.handle_clear_accounts_command(message)
            elif text.startswith('/confirm_clear_accounts'):
                await self.handle_confirm_clear_accounts_command(message)
            elif text.startswith('/ping'):
                await self.handle_ping_command(message)
            elif text.startswith('/acc'):
                await self.handle_acc_command(message)
            elif text.startswith('/del'):
                await self.handle_del_command(message)
            elif text.startswith('/logout'):
                await self.handle_logout_command(message)
            elif text.startswith('/time'):
                await self.handle_time_command(message)
            elif text.startswith('/setowner'):
                await self.handle_setowner_command(message)
            elif text.startswith('/addvoice'):
                await self.handle_addvoice_command(message)
            elif text.startswith('/removevoice'):
                await self.handle_removevoice_command(message)
            elif text.startswith('/listvoice'):
                await self.handle_listvoice_command(message)
            elif text.startswith('/accountvoice'):
                await self.handle_accountvoice_command(message)
            elif text.startswith('/join'):
                await self.handle_join_command(message)
            elif text.startswith('/getapi'):
                await self.handle_getapi_command(message)
            elif text.startswith('/password'):
                await self.handle_password_command(message)
            elif text.startswith('/help'):
                await self.handle_help_command(message)
            else:
                # Check if it's a phone number (starts with +)
                if text.startswith('+') and len(text) > 10:
                    await self.handle_phone_number(message)
                else:
                    await message.reply("❌ دستور نامعتبر. از /help برای دیدن دستورات استفاده کنید.")
                
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            try:
                await message.reply("❌ خطا در پردازش پیام.")
            except:
                pass
    
    async def handle_callback_query(self, event):
        """Handle callback queries from inline keyboards"""
        try:
            query = event.query
            user_id = query.user_id
            data = query.data
            
            logger.info(f"Received callback query from {user_id}: {data}")
            
            # Check if user is authorized
            if not self.is_authorized_user(user_id):
                await query.answer("❌ شما دسترسی لازم را ندارید.")
                return
            
            if data == "help_command":
                # Create a fake message object for help command
                class FakeMessage:
                    def __init__(self, user_id):
                        self.sender_id = user_id
                    
                    async def reply(self, text):
                        await query.edit_message(text)
                
                fake_message = FakeMessage(user_id)
                await self.handle_help_command(fake_message)
                await query.answer("📖 راهنمای کامل نمایش داده شد")
            
        except Exception as e:
            logger.error(f"Error handling callback query: {e}")
            await query.answer("❌ خطا در پردازش درخواست")
    
    async def handle_start_command(self, message):
        """Handle /start command"""
        try:
            sender_id = message.sender_id
            
            # Check if sender is authorized
            if not self.is_authorized_user(sender_id):
                await message.reply("❌ شما دسترسی لازم را ندارید.")
                return
            
            welcome_text = """
🤖 **ربات جوینر ویس چت تلگرام**

**کاربرد ربات:**
• مدیریت تا 50 اکانت تلگرام
• جوین شدن همزمان همه اکانت‌ها به گروه
• جوین شدن به ویس چت‌ها
• کنترل کامل از طریق دستورات

**نحوه استفاده:**
1️⃣ شماره تلفن را ارسال کنید (مثل: +989123456789)
2️⃣ کد تایید را با /code ارسال کنید
3️⃣ از دستورات برای کنترل استفاده کنید

**دستورات اصلی:**
/setowner آیدی - تنظیم مالک ربات (فقط یک بار)
شماره_تلفن - تایید اکانت جدید
/code کد - ارسال کد تایید
/password رمز - ارسال رمز عبور 2FA
/acc - مشاهده لیست اکانت‌ها
/del شماره - حذف اکانت خاص
/logout شماره - خروج از اکانت خاص
/time دقیقه - تنظیم زمان خروج خودکار
/join تعداد - جوین شدن تعداد مشخص اکانت به گروه فعلی
/joinall لینک - جوین شدن همه اکانت‌ها
/addvoice تعداد - اضافه کردن تعداد مشخص اکانت به ویس چت گروه فعلی
/removevoice شماره لینک ویس_چت - حذف اکانت از ویس چت
/listvoice - لیست ویس چت‌های فعال
/accountvoice شماره - ویس چت‌های اکانت
/promote آیدی - ترفیع کاربر به ادمین
/demote آیدی - حذف ادمین
/ping - بررسی وضعیت ربات
/status - وضعیت ربات
/getapi شماره - دریافت API credentials
/help - راهنمای کامل
        """
        
            # Create inline keyboard with buttons
            keyboard = ReplyInlineMarkup(rows=[
                [KeyboardButtonUrl("📞 تماس با ادمین", "https://t.me/silverrmb")],
                [KeyboardButtonCallback("📖 راهنمای کامل", "help_command")]
            ])
            
            await message.reply(welcome_text, buttons=keyboard)
            
        except Exception as e:
            logger.error(f"Error in start command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_add_account_command(self, message):
        """Handle /add_account command"""
        try:
            text = message.text
            if len(text.split()) < 2:
                await message.reply("❌ فرمت صحیح: /add_account شماره_تلفن")
                return
            
            phone = text.split()[1]
            success = self.account_manager.add_account(phone)
            
            if success:
                await message.reply(f"✅ اکانت {phone} اضافه شد.")
            else:
                await message.reply(f"❌ خطا در اضافه کردن اکانت {phone}")
                
        except Exception as e:
            logger.error(f"Error in add_account command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_remove_account_command(self, message):
        """Handle /remove_account command"""
        try:
            text = message.text
            if len(text.split()) < 2:
                await message.reply("❌ فرمت صحیح: /remove_account شماره_تلفن")
                return
            
            phone = text.split()[1]
            success = self.account_manager.remove_account(phone)
            
            if success:
                await message.reply(f"✅ اکانت {phone} حذف شد.")
            else:
                await message.reply(f"❌ خطا در حذف اکانت {phone}")
                
        except Exception as e:
            logger.error(f"Error in remove_account command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_list_accounts_command(self, message):
        """Handle /list_accounts command"""
        try:
            info = self.account_manager.get_accounts_info()
            
            response = f"""
📊 **وضعیت اکانت‌ها:**
🔢 کل اکانت‌ها: {info['total']}
✅ فعال: {info['active']}
❌ غیرفعال: {info['inactive']}

**لیست اکانت‌ها:**
"""
            
            for i, account in enumerate(info['accounts'], 1):
                status = "✅" if account['active'] else "❌"
                response += f"{i}. {status} {account['phone']}\n"
            
            await message.reply(response)
            
        except Exception as e:
            logger.error(f"Error in list_accounts command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_join_group_command(self, message):
        """Handle /join_group command"""
        try:
            text = message.text
            if len(text.split()) < 2:
                await message.reply("❌ فرمت صحیح: /join_group لینک_گروه")
                return
            
            group_link = text.split()[1]
            await message.reply("🔄 در حال جوین شدن به گروه...")
            
            # Initialize clients if not already done
            await self.account_manager.initialize_all_clients()
            
            success = await self.voice_chat_joiner.join_group_with_all_accounts(group_link)
            
            if success:
                await message.reply("✅ همه اکانت‌ها با موفقیت به گروه جوین شدند.")
            else:
                await message.reply("❌ خطا در جوین شدن به گروه")
                
        except Exception as e:
            logger.error(f"Error in join_group command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_leave_group_command(self, message):
        """Handle /leave_group command"""
        try:
            text = message.text
            if len(text.split()) < 2:
                await message.reply("❌ فرمت صحیح: /leave_group لینک_گروه")
                return
            
            group_link = text.split()[1]
            await message.reply("🔄 در حال ترک کردن گروه...")
            
            success = await self.voice_chat_joiner.leave_group_with_all_accounts(group_link)
            
            if success:
                await message.reply("✅ همه اکانت‌ها با موفقیت از گروه خارج شدند.")
            else:
                await message.reply("❌ خطا در ترک کردن گروه")
                
        except Exception as e:
            logger.error(f"Error in leave_group command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_join_voice_command(self, message):
        """Handle /join_voice command"""
        try:
            text = message.text
            if len(text.split()) < 3:
                await message.reply("❌ فرمت صحیح: /join_voice لینک_گروه آیدی_ویس_چت")
                return
            
            parts = text.split()
            group_link = parts[1]
            voice_chat_id = parts[2]
            
            await message.reply("🔄 در حال جوین شدن به ویس چت...")
            
            # Initialize clients if not already done
            await self.account_manager.initialize_all_clients()
            
            success = await self.voice_chat_joiner.join_group_with_all_accounts(group_link, voice_chat_id)
            
            if success:
                await message.reply("✅ همه اکانت‌ها با موفقیت به ویس چت جوین شدند.")
            else:
                await message.reply("❌ خطا در جوین شدن به ویس چت")
                
        except Exception as e:
            logger.error(f"Error in join_voice command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_status_command(self, message):
        """Handle /status command"""
        try:
            info = self.account_manager.get_accounts_info()
            joined_groups = self.voice_chat_joiner.get_joined_groups()
            
            response = f"""
📊 **وضعیت ربات:**
🔢 کل اکانت‌ها: {info['total']}
✅ اکانت‌های فعال: {info['active']}
❌ اکانت‌های غیرفعال: {info['inactive']}
🏠 گروه‌های جوین شده: {len(joined_groups)}

**گروه‌های جوین شده:**
"""
            
            for group in joined_groups:
                response += f"• {group}\n"
            
            await message.reply(response)
            
        except Exception as e:
            logger.error(f"Error in status command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_add_admin_command(self, message):
        """Handle /add_admin command"""
        try:
            text = message.text
            if len(text.split()) < 2:
                await message.reply("❌ فرمت صحیح: /add_admin آیدی_کاربر")
                return
            
            user_id = int(text.split()[1])
            self.admin_users.add(user_id)
            await message.reply(f"✅ کاربر {user_id} به عنوان ادمین اضافه شد.")
            
        except Exception as e:
            logger.error(f"Error in add_admin command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_join_multiple_voice_command(self, message):
        """Handle /join_multiple_voice command"""
        try:
            text = message.text
            if len(text.split()) < 2:
                await message.reply("""
❌ فرمت صحیح:
/join_multiple_voice JSON_CONFIG

مثال:
/join_multiple_voice [{"group_link":"@group1","voice_chat_id":"123456789","account_count":10},{"group_link":"@group2","voice_chat_id":"987654321","account_count":15}]
                """)
                return
            
            # Parse JSON config
            try:
                config_text = ' '.join(text.split()[1:])
                voice_chat_configs = json.loads(config_text)
            except json.JSONDecodeError:
                await message.reply("❌ فرمت JSON نامعتبر است.")
                return
            
            await message.reply("🔄 در حال جوین شدن به چندین ویس چت...")
            
            # Initialize clients if not already done
            await self.account_manager.initialize_all_clients()
            
            results = await self.voice_chat_joiner.join_multiple_voice_chats(voice_chat_configs)
            
            if results:
                response = "✅ نتایج جوین شدن به ویس چت‌ها:\n\n"
                for i, result in enumerate(results, 1):
                    response += f"**ویس چت {i}:**\n"
                    response += f"گروه: {result['group_link']}\n"
                    response += f"موفق: {result['successful']}\n"
                    response += f"ناموفق: {result['failed']}\n\n"
                
                await message.reply(response)
            else:
                await message.reply("❌ خطا در جوین شدن به ویس چت‌ها")
                
        except Exception as e:
            logger.error(f"Error in join_multiple_voice command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_joinall_command(self, message):
        """Handle /joinall command - Join all accounts to a group/channel"""
        try:
            text = message.text
            if len(text.split()) < 2:
                await message.reply("""
❌ فرمت صحیح: /joinall لینک_گروه_یا_کانال

**مثال‌ها:**
/joinall @group_username
/joinall https://t.me/group_username
/joinall https://t.me/joinchat/ABC123DEF456
/joinall @channel_username

**نکته:** این دستور همه اکانت‌های فعال را به گروه/کانال مورد نظر جوین می‌کند.
                """)
                return
            
            group_link = text.split()[1]
            await message.reply(f"🔄 در حال جوین شدن همه اکانت‌ها به {group_link}...")
            
            # Initialize clients if not already done
            await self.account_manager.initialize_all_clients()
            
            # Get active clients count
            active_clients = await self.account_manager.get_active_clients()
            if not active_clients:
                await message.reply("❌ هیچ اکانت فعالی وجود ندارد. ابتدا اکانت‌ها را اضافه کنید.")
                return
            
            await message.reply(f"📊 {len(active_clients)} اکانت فعال پیدا شد. شروع جوین شدن...")
            
            # Join group with all accounts
            success = await self.voice_chat_joiner.join_group_with_all_accounts(group_link)
            
            if success:
                await message.reply(f"✅ همه اکانت‌ها با موفقیت به {group_link} جوین شدند!")
            else:
                await message.reply(f"❌ خطا در جوین شدن به {group_link}")
                
        except Exception as e:
            logger.error(f"Error in joinall command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_phone_number(self, message):
        """Handle phone number input for account verification"""
        try:
            phone = message.text.strip()
            sender_id = message.sender_id
            
            logger.info(f"Phone number received from {sender_id}: {phone}")
            
            # Check if user is authorized
            if not self.is_authorized_user(sender_id):
                await message.reply("❌ شما دسترسی لازم را ندارید.")
                return
            
            # Check if we need to get API credentials first
            global API_ID, API_HASH
            if not API_ID or not API_HASH or API_ID == 0 or API_HASH == 'YOUR_API_HASH_HERE':
                await message.reply("🔄 در حال دریافت API credentials...")
                
                # Try to get API credentials using the phone number
                credentials = await self.get_api_credentials_alternative(phone)
                
                if credentials['success']:
                    # Update config with new credentials
                    API_ID = int(credentials['api_id'])
                    API_HASH = credentials['api_hash']
                    
                    await message.reply(f"""
✅ **API credentials دریافت شد!**

🔑 **API ID:** `{credentials['api_id']}`
🔑 **API Hash:** `{credentials['api_hash'][:10]}...`

🔄 حالا در حال تایید اکانت...
                    """)
                else:
                    await message.reply(f"""
❌ **خطا در دریافت API credentials**

🔍 **خطا:** {credentials.get('error', 'نامشخص')}

**راه حل:**
1. مطمئن شوید که شماره تلفن صحیح است
2. اکانت باید معتبر باشد
3. دوباره تلاش کنید

**یا به صورت دستی:**
1. به https://my.telegram.org/apps بروید
2. API_ID و API_HASH دریافت کنید
3. در Railway متغیرها را تنظیم کنید
                    """)
                    return
            
            # Validate phone number format
            if not phone.startswith('+') or len(phone) < 10:
                await message.reply("❌ فرمت شماره تلفن نامعتبر است. مثال: +989123456789")
                return
            
            # Store phone number for verification
            self.pending_verification[sender_id] = {
                'phone': phone,
                'timestamp': asyncio.get_event_loop().time()
            }
            
            await message.reply(f"""
📱 **تایید شماره تلفن**

شماره تلفن: `{phone}`

✅ شماره تلفن دریافت شد.
🔐 کد ورود به اکانت را بفرستید.

**فرمت:** `/code کد_ورود`

**مثال:** `/code 12345`

⏰ زمان باقی‌مانده: 5 دقیقه

**نکات مهم:**
• کد را سریع‌تر ارسال کنید
• اگر 2FA دارید، ابتدا آن را غیرفعال کنید
• کد فقط یک بار قابل استفاده است
            """)
            
        except Exception as e:
            logger.error(f"Error handling phone number: {e}")
            await message.reply("❌ خطا در پردازش شماره تلفن")
    
    async def handle_code_command(self, message):
        """Handle /code command for account verification"""
        try:
            text = message.text
            sender_id = message.sender_id
            
            if len(text.split()) < 2:
                await message.reply("❌ فرمت صحیح: /code کد_ورود")
                return
            
            code = text.split()[1]
            
            # Check if user has pending verification
            if sender_id not in self.pending_verification:
                await message.reply("❌ ابتدا شماره تلفن را ارسال کنید.")
                return
            
            # Check if verification is not expired (5 minutes)
            verification_data = self.pending_verification[sender_id]
            current_time = asyncio.get_event_loop().time()
            if current_time - verification_data['timestamp'] > 300:  # 5 minutes
                del self.pending_verification[sender_id]
                await message.reply("❌ زمان تایید منقضی شده است. دوباره شماره تلفن را ارسال کنید.")
                return
            
            phone = verification_data['phone']
            
            await message.reply(f"🔄 در حال تایید کد برای {phone}...")
            
            # Try to verify the account
            success = await self.verify_account(phone, code)
            
            if success:
                # Clean up verification data
                del self.pending_verification[sender_id]
                
                await message.reply(f"""
✅ **اکانت با موفقیت تایید و اضافه شد!**

📱 شماره تلفن: `{phone}`
🔐 کد تایید: `{code}`
📊 وضعیت: فعال
🔗 Session: ذخیره شده

🎉 اکانت آماده استفاده است!

**دستورات بعدی:**
/acc - نمایش لیست اکانت‌ها
/join 25 - جوین شدن 25 اکانت به گروه فعلی
/joinall @group - جوین شدن همه اکانت‌ها
/ping - بررسی وضعیت ربات
                """)
                
                logger.info(f"Account {phone} verified and added successfully")
                
            else:
                await message.reply(f"""
❌ **تایید ناموفق**

🔍 **مشکلات احتمالی:**
• کد ورود اشتباه است
• کد منقضی شده است
• اکانت 2FA دارد (نیاز به رمز عبور)
• خطا در اتصال

**راه حل‌ها:**
1. کد جدید را از تلگرام دریافت کنید
2. کد را سریع‌تر ارسال کنید
3. اگر 2FA دارید، ابتدا آن را غیرفعال کنید
4. دوباره تلاش کنید

**دستور جدید:**
/code کد_جدید
                """)
                
        except Exception as e:
            logger.error(f"Error handling code command: {e}")
            await message.reply("❌ خطا در پردازش کد تایید")
    
    async def verify_account(self, phone, code):
        """Verify account with phone and code"""
        try:
            from telethon import TelegramClient
            from telethon.sessions import StringSession
            from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError
            
            logger.info(f"Starting verification for {phone} with code {code}")
            
            # Create temporary client for verification
            session = StringSession()
            client = TelegramClient(session, API_ID, API_HASH)
            
            try:
                # Start client with phone and code
                await client.start(phone=phone, code=code)
                
                # Get account info
                me = await client.get_me()
                logger.info(f"Account verified successfully: {me.first_name} ({phone})")
                
                # Save session for future use
                session_string = client.session.save()
                
                # Add to account manager with session
                self.account_manager.add_account_with_session(phone, session_string)
                
                # Disconnect client
                await client.disconnect()
                
                return True
                
            except SessionPasswordNeededError:
                logger.warning(f"2FA enabled for {phone}, need password")
                await client.disconnect()
                return False
                
            except PhoneCodeInvalidError:
                logger.error(f"Invalid code for {phone}")
                await client.disconnect()
                return False
                
            except PhoneCodeExpiredError:
                logger.error(f"Expired code for {phone}")
                await client.disconnect()
                return False
                
            except Exception as e:
                logger.error(f"Error during verification for {phone}: {e}")
                await client.disconnect()
                return False
            
        except Exception as e:
            logger.error(f"Error in verify_account for {phone}: {e}")
            return False
    
    async def handle_promote_command(self, message):
        """Handle /promote command - Promote user to admin with specific permissions"""
        try:
            text = message.text
            sender_id = message.sender_id
            
            if len(text.split()) < 2:
                await message.reply("""
❌ فرمت صحیح: /promote آیدی_کاربر

**مثال:**
/promote 123456789

**نکته:** این دستور کاربر را به ادمین تبدیل می‌کند و دسترسی کامل به همه قابلیت‌ها می‌دهد.
                """)
                return
            
            # Check if sender is authorized
            if not self.is_authorized_user(sender_id):
                await message.reply("❌ شما دسترسی لازم را ندارید.")
                return
            
            try:
                user_id = int(text.split()[1])
            except ValueError:
                await message.reply("❌ آیدی کاربر نامعتبر است. باید عدد باشد.")
                return
            
            # Add user to admin list
            self.admin_users.add(user_id)
            
            # Set permissions for the user
            self.user_permissions[user_id] = {
                'level': 'admin',
                'can_add_accounts': True,
                'can_join_groups': True,
                'can_join_voice': True,
                'can_manage_accounts': True,
                'can_promote': True
            }
            
            await message.reply(f"""
✅ **کاربر با موفقیت به ادمین تبدیل شد!**

👤 آیدی کاربر: `{user_id}`
🔑 سطح دسترسی: ادمین کامل
📋 دسترسی‌ها:
• اضافه کردن اکانت
• جوین شدن به گروه‌ها
• جوین شدن به ویس چت‌ها
• مدیریت اکانت‌ها
• ترفیع کاربران

🎉 کاربر حالا می‌تواند از همه دستورات استفاده کند.
            """)
            
            logger.info(f"User {user_id} promoted to admin by {sender_id}")
            
        except Exception as e:
            logger.error(f"Error in promote command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_demote_command(self, message):
        """Handle /demote command - Remove admin privileges from user"""
        try:
            text = message.text
            sender_id = message.sender_id
            
            if len(text.split()) < 2:
                await message.reply("""
❌ فرمت صحیح: /demote آیدی_ادمین

**مثال:**
/demote 123456789

**نکته:** این دستور کاربر را از ادمینی خارج می‌کند و همه دسترسی‌ها را حذف می‌کند.
                """)
                return
            
            # Check if sender is authorized
            if not self.is_authorized_user(sender_id):
                await message.reply("❌ شما دسترسی لازم را ندارید.")
                return
            
            try:
                user_id = int(text.split()[1])
            except ValueError:
                await message.reply("❌ آیدی کاربر نامعتبر است. باید عدد باشد.")
                return
            
            # Check if user is admin
            if user_id not in self.admin_users:
                await message.reply("❌ این کاربر ادمین نیست.")
                return
            
            # Check if user is trying to demote themselves
            if user_id == sender_id:
                await message.reply("❌ نمی‌توانید خودتان را از ادمینی خارج کنید.")
                return
            
            # Remove user from admin list
            self.admin_users.remove(user_id)
            
            # Remove user permissions
            if user_id in self.user_permissions:
                del self.user_permissions[user_id]
            
            await message.reply(f"""
✅ **کاربر با موفقیت از ادمینی خارج شد!**

👤 آیدی کاربر: `{user_id}`
🔑 سطح دسترسی: کاربر عادی
📋 دسترسی‌ها: هیچ

❌ کاربر دیگر نمی‌تواند از دستورات ادمین استفاده کند.
            """)
            
            logger.info(f"User {user_id} demoted from admin by {sender_id}")
            
        except Exception as e:
            logger.error(f"Error in demote command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_list_admins_command(self, message):
        """Handle /list_admins command - List all admin users"""
        try:
            sender_id = message.sender_id
            
            # Check if sender is authorized
            if not self.is_authorized_user(sender_id):
                await message.reply("❌ شما دسترسی لازم را ندارید.")
                return
            
            if not self.admin_users:
                await message.reply("❌ هیچ ادمینی وجود ندارد.")
                return
            
            response = "👥 **لیست ادمین‌ها:**\n\n"
            
            for i, admin_id in enumerate(self.admin_users, 1):
                user_perms = self.user_permissions.get(admin_id, {})
                level = user_perms.get('level', 'admin')
                
                response += f"**{i}.** آیدی: `{admin_id}`\n"
                response += f"   سطح: {level}\n"
                response += f"   دسترسی: کامل\n\n"
            
            response += f"📊 **مجموع:** {len(self.admin_users)} ادمین"
            
            await message.reply(response)
            
        except Exception as e:
            logger.error(f"Error in list_admins command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_clear_accounts_command(self, message):
        """Handle /clear_accounts command - Clear all accounts"""
        try:
            sender_id = message.sender_id
            
            # Check if sender is authorized
            if not self.is_authorized_user(sender_id):
                await message.reply("❌ شما دسترسی لازم را ندارید.")
                return
            
            # Get current account count
            info = self.account_manager.get_accounts_info()
            account_count = info['total']
            
            if account_count == 0:
                await message.reply("❌ هیچ اکانتی وجود ندارد.")
                return
            
            await message.reply(f"""
⚠️ **هشدار: حذف همه اکانت‌ها**

📊 تعداد اکانت‌ها: {account_count}
❌ این عمل قابل بازگشت نیست!

برای تایید، دستور زیر را ارسال کنید:
/confirm_clear_accounts
            """)
            
        except Exception as e:
            logger.error(f"Error in clear_accounts command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_confirm_clear_accounts_command(self, message):
        """Handle /confirm_clear_accounts command - Confirm clearing all accounts"""
        try:
            sender_id = message.sender_id
            
            # Check if sender is authorized
            if not self.is_authorized_user(sender_id):
                await message.reply("❌ شما دسترسی لازم را ندارید.")
                return
            
            # Clear all accounts
            self.account_manager.accounts = []
            self.account_manager.save_accounts()
            
            # Close all clients
            await self.account_manager.close_all_clients()
            
            await message.reply("""
✅ **همه اکانت‌ها با موفقیت حذف شدند!**

🗑️ اکانت‌ها: حذف شدند
🔌 اتصالات: قطع شدند
💾 فایل‌ها: پاک شدند

🎉 ربات آماده اضافه کردن اکانت‌های جدید است.
            """)
            
            logger.info(f"All accounts cleared by {sender_id}")
            
        except Exception as e:
            logger.error(f"Error in confirm_clear_accounts command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_ping_command(self, message):
        """Handle /ping command - Check bot and accounts status"""
        try:
            sender_id = message.sender_id
            start_time = asyncio.get_event_loop().time()
            
            # Check if sender is authorized
            if not self.is_authorized_user(sender_id):
                await message.reply("❌ شما دسترسی لازم را ندارید.")
                return
            
            await message.reply("🔄 در حال بررسی وضعیت ربات و اکانت‌ها...")
            
            # Get bot status
            bot_status = "✅ آنلاین" if self.bot else "❌ آفلاین"
            
            # Get accounts info
            info = self.account_manager.get_accounts_info()
            total_accounts = info['total']
            active_accounts = info['active']
            inactive_accounts = info['inactive']
            
            # Test account connections
            connection_tests = []
            if active_accounts > 0:
                try:
                    active_clients = await self.account_manager.get_active_clients()
                    for i, client in enumerate(active_clients[:5]):  # Test first 5 accounts
                        try:
                            me = await client.get_me()
                            connection_tests.append(f"✅ اکانت {i+1}: {me.first_name or 'نامشخص'}")
                        except Exception as e:
                            connection_tests.append(f"❌ اکانت {i+1}: خطا در اتصال")
                except Exception as e:
                    connection_tests.append("❌ خطا در تست اتصالات")
            
            # Calculate response time
            end_time = asyncio.get_event_loop().time()
            response_time = round((end_time - start_time) * 1000, 2)  # Convert to milliseconds
            
            # Get system info
            import psutil
            import platform
            
            try:
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                memory_percent = memory.percent
                memory_used = round(memory.used / (1024**3), 2)  # GB
                memory_total = round(memory.total / (1024**3), 2)  # GB
            except:
                cpu_percent = "نامشخص"
                memory_percent = "نامشخص"
                memory_used = "نامشخص"
                memory_total = "نامشخص"
            
            # Build response
            response = f"""
🏓 **Ping ربات و اکانت‌ها**

🤖 **وضعیت ربات:**
• وضعیت: {bot_status}
• زمان پاسخ: {response_time}ms
• سیستم: {platform.system()}
• CPU: {cpu_percent}%
• RAM: {memory_used}GB / {memory_total}GB ({memory_percent}%)

📱 **وضعیت اکانت‌ها:**
• کل اکانت‌ها: {total_accounts}
• فعال: {active_accounts}
• غیرفعال: {inactive_accounts}

🔌 **تست اتصالات:**
"""
            
            if connection_tests:
                for test in connection_tests:
                    response += f"• {test}\n"
            else:
                response += "• هیچ اکانت فعالی وجود ندارد\n"
            
            # Add admin info
            admin_count = len(self.admin_users)
            response += f"""
👥 **مدیریت:**
• تعداد ادمین‌ها: {admin_count}
• ادمین فعلی: {sender_id}

⏰ **زمان:**
• زمان بررسی: {response_time}ms
• وضعیت: {'🟢 عالی' if response_time < 1000 else '🟡 متوسط' if response_time < 3000 else '🔴 کند'}
            """
            
            await message.reply(response)
            
            logger.info(f"Ping command executed by {sender_id} - Response time: {response_time}ms")
            
        except Exception as e:
            logger.error(f"Error in ping command: {e}")
            await message.reply("❌ خطا در بررسی وضعیت ربات")
    
    async def handle_acc_command(self, message):
        """Handle /acc command - Show detailed list of registered accounts"""
        try:
            sender_id = message.sender_id
            
            # Check if sender is authorized
            if not self.is_authorized_user(sender_id):
                await message.reply("❌ شما دسترسی لازم را ندارید.")
                return
            
            # Get accounts info
            info = self.account_manager.get_accounts_info()
            total_accounts = info['total']
            active_accounts = info['active']
            inactive_accounts = info['inactive']
            
            if total_accounts == 0:
                await message.reply("""
📱 **لیست اکانت‌های ثبت شده**

❌ هیچ اکانتی ثبت نشده است.

**برای اضافه کردن اکانت:**
1. شماره تلفن را ارسال کنید
2. کد تایید را با /code ارسال کنید
                """)
                return
            
            # Build detailed response
            response = f"""
📱 **لیست اکانت‌های ثبت شده**

📊 **آمار کلی:**
• کل اکانت‌ها: {total_accounts}
• فعال: {active_accounts}
• غیرفعال: {inactive_accounts}

📋 **جزئیات اکانت‌ها:**
"""
            
            # Add each account with details
            for i, account in enumerate(info['accounts'], 1):
                phone = account['phone']
                active = account['active']
                joined_groups = account.get('joined_groups', [])
                
                status_icon = "✅" if active else "❌"
                status_text = "فعال" if active else "غیرفعال"
                
                response += f"""
**{i}.** {status_icon} `{phone}`
   وضعیت: {status_text}
   گروه‌های جوین شده: {len(joined_groups)}
"""
                
                # Add joined groups if any
                if joined_groups:
                    for group in joined_groups[:3]:  # Show first 3 groups
                        response += f"   • {group}\n"
                    if len(joined_groups) > 3:
                        response += f"   • و {len(joined_groups) - 3} گروه دیگر...\n"
                
                # Add separator between accounts
                if i < len(info['accounts']):
                    response += "\n"
            
            # Add summary
            response += f"""
📈 **خلاصه:**
• اکانت‌های فعال: {active_accounts}/{total_accounts}
• درصد موفقیت: {(active_accounts/total_accounts*100):.1f}%
• آماده برای استفاده: {'✅ بله' if active_accounts > 0 else '❌ خیر'}
            """
            
            # Split message if too long
            if len(response) > 4000:
                # Send first part
                first_part = response[:4000] + "\n\n... (ادامه در پیام بعدی)"
                await message.reply(first_part)
                
                # Send remaining accounts
                remaining_accounts = info['accounts'][10:]  # Skip first 10
                if remaining_accounts:
                    remaining_response = "📱 **ادامه لیست اکانت‌ها:**\n\n"
                    for i, account in enumerate(remaining_accounts, 11):
                        phone = account['phone']
                        active = account['active']
                        status_icon = "✅" if active else "❌"
                        status_text = "فعال" if active else "غیرفعال"
                        
                        remaining_response += f"**{i}.** {status_icon} `{phone}` - {status_text}\n"
                    
                    await message.reply(remaining_response)
            else:
                await message.reply(response)
            
            logger.info(f"Account list requested by {sender_id} - Total: {total_accounts}, Active: {active_accounts}")
            
        except Exception as e:
            logger.error(f"Error in acc command: {e}")
            await message.reply("❌ خطا در نمایش لیست اکانت‌ها")
    
    async def handle_del_command(self, message):
        """Handle /del command - Delete specific account"""
        try:
            text = message.text
            sender_id = message.sender_id
            
            if len(text.split()) < 2:
                await message.reply("""
❌ فرمت صحیح: /del شماره_تلفن

**مثال:**
/del +989123456789

**نکته:** این دستور اکانت مشخص شده را از ربات حذف می‌کند.
                """)
                return
            
            # Check if sender is authorized
            if not self.is_authorized_user(sender_id):
                await message.reply("❌ شما دسترسی لازم را ندارید.")
                return
            
            phone = text.split()[1]
            
            # Validate phone number format
            if not phone.startswith('+') or len(phone) < 10:
                await message.reply("❌ فرمت شماره تلفن نامعتبر است. مثال: +989123456789")
                return
            
            # Check if account exists
            account_exists = False
            for account in self.account_manager.accounts:
                if account['phone'] == phone:
                    account_exists = True
                    break
            
            if not account_exists:
                await message.reply(f"❌ اکانت `{phone}` در ربات وجود ندارد.")
                return
            
            await message.reply(f"🔄 در حال حذف اکانت `{phone}`...")
            
            # Remove account from manager
            success = self.account_manager.remove_account(phone)
            
            if success:
                # Close client if exists
                if phone in self.account_manager.clients:
                    try:
                        await self.account_manager.clients[phone].disconnect()
                        del self.account_manager.clients[phone]
                    except:
                        pass
                
                await message.reply(f"""
✅ **اکانت با موفقیت حذف شد!**

📱 شماره تلفن: `{phone}`
🗑️ وضعیت: حذف شده
🔌 اتصال: قطع شده

**دستورات بعدی:**
/acc - مشاهده لیست اکانت‌ها
/status - وضعیت ربات
                """)
                
                logger.info(f"Account {phone} deleted by {sender_id}")
                
            else:
                await message.reply(f"❌ خطا در حذف اکانت `{phone}`")
                
        except Exception as e:
            logger.error(f"Error in del command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_logout_command(self, message):
        """Handle /logout command - Logout from specific account"""
        try:
            text = message.text
            sender_id = message.sender_id
            
            if len(text.split()) < 2:
                await message.reply("""
❌ فرمت صحیح: /logout شماره_تلفن

**مثال:**
/logout +989123456789

**نکته:** این دستور ربات را از اکانت مشخص شده خارج می‌کند (اکانت حذف نمی‌شود).
                """)
                return
            
            # Check if sender is authorized
            if not self.is_authorized_user(sender_id):
                await message.reply("❌ شما دسترسی لازم را ندارید.")
                return
            
            phone = text.split()[1]
            
            # Validate phone number format
            if not phone.startswith('+') or len(phone) < 10:
                await message.reply("❌ فرمت شماره تلفن نامعتبر است. مثال: +989123456789")
                return
            
            # Check if account exists
            account_exists = False
            account_active = False
            for account in self.account_manager.accounts:
                if account['phone'] == phone:
                    account_exists = True
                    account_active = account['active']
                    break
            
            if not account_exists:
                await message.reply(f"❌ اکانت `{phone}` در ربات وجود ندارد.")
                return
            
            if not account_active:
                await message.reply(f"❌ اکانت `{phone}` قبلاً غیرفعال است.")
                return
            
            await message.reply(f"🔄 در حال خروج از اکانت `{phone}`...")
            
            # Disconnect client if exists
            if phone in self.account_manager.clients:
                try:
                    await self.account_manager.clients[phone].disconnect()
                    del self.account_manager.clients[phone]
                    logger.info(f"Client disconnected for {phone}")
                except Exception as e:
                    logger.error(f"Error disconnecting client for {phone}: {e}")
            
            # Mark account as inactive
            for account in self.account_manager.accounts:
                if account['phone'] == phone:
                    account['active'] = False
                    break
            
            # Save changes
            self.account_manager.save_accounts()
            
            await message.reply(f"""
✅ **ربات با موفقیت از اکانت خارج شد!**

📱 شماره تلفن: `{phone}`
🔌 وضعیت: غیرفعال
📝 اکانت: حفظ شده

**نکات مهم:**
• اکانت حذف نشده است
• می‌توانید دوباره فعال کنید
• اطلاعات اکانت حفظ شده است

**دستورات بعدی:**
/acc - مشاهده لیست اکانت‌ها
/status - وضعیت ربات
            """)
            
            logger.info(f"Account {phone} logged out by {sender_id}")
            
        except Exception as e:
            logger.error(f"Error in logout command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_time_command(self, message):
        """Handle /time command - Set auto leave time for voice chats"""
        try:
            text = message.text
            sender_id = message.sender_id
            
            if len(text.split()) < 2:
                await message.reply(f"""
❌ فرمت صحیح: /time تعداد_دقیقه

**مثال:**
/time 30
/time 60
/time 120

**وضعیت فعلی:** {self.auto_leave_time} دقیقه

**نکته:** این دستور زمان خروج خودکار اکانت‌ها از ویس چت را تنظیم می‌کند.
                """)
                return
            
            # Check if sender is authorized
            if not self.is_authorized_user(sender_id):
                await message.reply("❌ شما دسترسی لازم را ندارید.")
                return
            
            try:
                minutes = int(text.split()[1])
            except ValueError:
                await message.reply("❌ تعداد دقیقه نامعتبر است. باید عدد باشد.")
                return
            
            # Validate time range
            if minutes < 1:
                await message.reply("❌ زمان باید حداقل 1 دقیقه باشد.")
                return
            
            if minutes > 1440:  # 24 hours
                await message.reply("❌ زمان نمی‌تواند بیش از 1440 دقیقه (24 ساعت) باشد.")
                return
            
            # Set new time
            old_time = self.auto_leave_time
            self.auto_leave_time = minutes
            self.voice_chat_joiner.set_auto_leave_time(minutes)
            
            await message.reply(f"""
✅ **زمان خروج خودکار تنظیم شد!**

⏰ زمان قبلی: {old_time} دقیقه
⏰ زمان جدید: {minutes} دقیقه

**نحوه کار:**
• اکانت‌ها بعد از {minutes} دقیقه از ویس چت خارج می‌شوند
• این تنظیم برای همه اکانت‌ها اعمال می‌شود
• می‌توانید هر زمان تغییر دهید

**دستورات بعدی:**
/joinall لینک - جوین شدن با تنظیم جدید
/status - وضعیت ربات
            """)
            
            logger.info(f"Auto leave time changed from {old_time} to {minutes} minutes by {sender_id}")
            
        except Exception as e:
            logger.error(f"Error in time command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_setowner_command(self, message):
        """Handle /setowner command - Set bot owner"""
        try:
            text = message.text
            sender_id = message.sender_id
            
            if len(text.split()) < 2:
                await message.reply("""
❌ فرمت صحیح: /setowner آیدی_کاربر

**مثال:**
/setowner 123456789

**نکته:** این دستور مالک ربات را تنظیم می‌کند.
                """)
                return
            
            # Only allow if no owner is set yet or owner_id is 0
            if self.owner_id is not None and self.owner_id != 0:
                # Check if sender is the current owner
                if sender_id != self.owner_id:
                    await message.reply("❌ فقط مالک فعلی می‌تواند مالک جدید تنظیم کند.")
                    return
            
            try:
                owner_id = int(text.split()[1])
            except ValueError:
                await message.reply("❌ آیدی کاربر نامعتبر است. باید عدد باشد.")
                return
            
            # Set owner
            self.owner_id = owner_id
            self.admin_users.add(owner_id)
            self.user_permissions[owner_id] = {
                'add_accounts': True,
                'remove_accounts': True,
                'join_groups': True,
                'join_voice_chats': True,
                'manage_admins': True,
                'view_status': True
            }
            
            await message.reply(f"""
✅ **مالک ربات تنظیم شد!**

👤 آیدی مالک: `{owner_id}`
🔐 دسترسی: کامل
📝 وضعیت: فعال

**نکات مهم:**
• مالک ربات دسترسی کامل دارد
• می‌تواند ادمین‌ها را مدیریت کند
• این تنظیم فقط یک بار انجام می‌شود

**دستورات بعدی:**
/start - شروع کار با ربات
/help - راهنمای کامل
            """)
            
            logger.info(f"Bot owner set to {owner_id}")
            
        except Exception as e:
            logger.error(f"Error in setowner command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_addvoice_command(self, message):
        """Handle /addvoice command - Add specified number of accounts to current group's voice chat"""
        try:
            text = message.text
            sender_id = message.sender_id
            
            if len(text.split()) < 2:
                await message.reply("""
❌ فرمت صحیح: /addvoice تعداد_اکانت

**مثال:**
/addvoice 25
/addvoice 50
/addvoice 10

**نکته:** این دستور تعداد مشخص شده از اکانت‌ها را به ویس چت گروه فعلی اضافه می‌کند.
                """)
                return
            
            # Check if sender is authorized
            if not self.is_authorized_user(sender_id):
                await message.reply("❌ شما دسترسی لازم را ندارید.")
                return
            
            try:
                account_count = int(text.split()[1])
            except ValueError:
                await message.reply("❌ تعداد اکانت نامعتبر است. باید عدد باشد.")
                return
            
            # Validate account count
            if account_count < 1:
                await message.reply("❌ تعداد اکانت باید حداقل 1 باشد.")
                return
            
            if account_count > 50:
                await message.reply("❌ تعداد اکانت نمی‌تواند بیش از 50 باشد.")
                return
            
            # Get current chat info
            chat = await message.get_chat()
            chat_id = chat.id
            chat_title = getattr(chat, 'title', 'Unknown')
            
            # Check if bot is admin in this group
            try:
                bot_member = await self.bot.get_participants(chat_id, filter='bots')
                bot_is_admin = False
                for member in bot_member:
                    if member.id == self.bot.me.id:
                        if hasattr(member, 'admin_rights') and member.admin_rights:
                            bot_is_admin = True
                        break
                
                if not bot_is_admin:
                    await message.reply("❌ ربات در این گروه ادمین نیست.")
                    return
                    
            except Exception as e:
                logger.error(f"Error checking bot admin status: {e}")
                await message.reply("❌ خطا در بررسی وضعیت ادمین ربات.")
                return
            
            # Get active accounts
            active_clients = await self.account_manager.get_active_clients()
            if not active_clients:
                await message.reply("❌ هیچ اکانت فعالی در ربات وجود ندارد.")
                return
            
            # Limit account count to available accounts
            if account_count > len(active_clients):
                account_count = len(active_clients)
                await message.reply(f"⚠️ فقط {len(active_clients)} اکانت فعال موجود است. از همه استفاده می‌شود.")
            
            await message.reply(f"🔄 در حال اضافه کردن {account_count} اکانت به ویس چت گروه...")
            
            # Select accounts to join
            selected_clients = active_clients[:account_count]
            
            successful_joins = 0
            failed_joins = 0
            
            for i, client in enumerate(selected_clients):
                try:
                    logger.info(f"Processing account {i+1}/{len(selected_clients)} for voice chat")
                    
                    # Join the group and voice chat
                    join_result = await self.voice_chat_joiner.join_group(client, chat_id, join_voice_chat=True)
                    if join_result and join_result.get('group'):
                        successful_joins += 1
                        
                        # Add to tracking
                        phone = None
                        for account in self.account_manager.accounts:
                            if account['phone'] in self.account_manager.clients and self.account_manager.clients[account['phone']] == client:
                                phone = account['phone']
                                break
                        
                        if phone:
                            # Add to joined groups tracking
                            self.voice_chat_joiner.joined_groups.add(chat_id)
                            
                            # Track voice chat if joined successfully
                            if join_result.get('voice_chat'):
                                group_entity = join_result.get('group_entity')
                                if group_entity:
                                    self.voice_chat_joiner.add_account_to_voice_chat(
                                        phone, 
                                        f"https://t.me/{group_entity.username}" if group_entity.username else str(chat_id),
                                        join_result['voice_chat'].id
                                    )
                            
                            # Schedule auto leave if time is set
                            if self.auto_leave_time > 0:
                                await self.voice_chat_joiner.schedule_auto_leave(client, chat_id)
                    else:
                        failed_joins += 1
                    
                    # Delay between joins
                    if i < len(selected_clients) - 1:
                        await asyncio.sleep(2)  # 2 second delay between joins
                        
                except Exception as e:
                    logger.error(f"Error processing account {i+1}: {e}")
                    failed_joins += 1
            
            # Send result
            result_message = f"""
✅ **عملیات اضافه کردن اکانت‌ها به ویس چت کامل شد!**

📊 **نتایج:**
• موفق: {successful_joins} اکانت
• ناموفق: {failed_joins} اکانت
• کل: {account_count} اکانت

🏠 **گروه:** {chat_title}
🎤 **ویس چت:** خودکار جوین شد
⏰ **خروج خودکار:** {self.auto_leave_time} دقیقه

**دستورات بعدی:**
/acc - مشاهده لیست اکانت‌ها
/listvoice - لیست ویس چت‌های فعال
/accountvoice شماره - ویس چت‌های اکانت خاص
/status - وضعیت ربات
            """
            
            await message.reply(result_message)
            
            logger.info(f"Addvoice command executed: {successful_joins} successful, {failed_joins} failed by {sender_id}")
            
        except Exception as e:
            logger.error(f"Error in addvoice command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_removevoice_command(self, message):
        """Handle /removevoice command - Remove account from specific voice chat"""
        try:
            text = message.text
            sender_id = message.sender_id
            
            if len(text.split()) < 3:
                await message.reply("""
❌ فرمت صحیح: /removevoice شماره_تلفن لینک_گروه ویس_چت_آیدی

**مثال:**
/removevoice +989123456789 @group1 voice_chat_123

**نکته:** این دستور اکانت مشخص شده را از ویس چت حذف می‌کند.
                """)
                return
            
            # Check if sender is authorized
            if not self.is_authorized_user(sender_id):
                await message.reply("❌ شما دسترسی لازم را ندارید.")
                return
            
            parts = text.split()
            phone = parts[1]
            group_link = parts[2]
            voice_chat_id = parts[3]
            
            # Validate phone number format
            if not phone.startswith('+') or len(phone) < 10:
                await message.reply("❌ فرمت شماره تلفن نامعتبر است. مثال: +989123456789")
                return
            
            # Check if account exists
            account_exists = False
            for account in self.account_manager.accounts:
                if account['phone'] == phone:
                    account_exists = True
                    break
            
            if not account_exists:
                await message.reply(f"❌ اکانت `{phone}` در ربات وجود ندارد.")
                return
            
            # Check if account is in this voice chat
            existing_voice_chats = self.voice_chat_joiner.get_account_voice_chats(phone)
            in_voice_chat = False
            for vc in existing_voice_chats:
                if vc['group_link'] == group_link and vc['voice_chat_id'] == voice_chat_id:
                    in_voice_chat = True
                    break
            
            if not in_voice_chat:
                await message.reply(f"❌ اکانت `{phone}` در این ویس چت حضور ندارد.")
                return
            
            await message.reply(f"🔄 در حال حذف اکانت `{phone}` از ویس چت...")
            
            # Get client for the account
            if phone in self.account_manager.clients:
                client = self.account_manager.clients[phone]
                
                # Leave the group
                await self.voice_chat_joiner.leave_group(client, group_link)
                
                # Cancel auto leave task
                self.voice_chat_joiner.cancel_auto_leave(phone, group_link)
            
            # Remove from tracking
            self.voice_chat_joiner.remove_account_from_voice_chat(phone, group_link, voice_chat_id)
            
            await message.reply(f"""
✅ **اکانت با موفقیت از ویس چت حذف شد!**

📱 شماره تلفن: `{phone}`
🏠 گروه: `{group_link}`
🎵 ویس چت: `{voice_chat_id}`

**دستورات بعدی:**
/accountvoice {phone} - مشاهده ویس چت‌های اکانت
/listvoice - لیست همه ویس چت‌ها
            """)
            
            logger.info(f"Account {phone} removed from voice chat {group_link} by {sender_id}")
            
        except Exception as e:
            logger.error(f"Error in removevoice command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_listvoice_command(self, message):
        """Handle /listvoice command - List all voice chats"""
        try:
            sender_id = message.sender_id
            
            # Check if sender is authorized
            if not self.is_authorized_user(sender_id):
                await message.reply("❌ شما دسترسی لازم را ندارید.")
                return
            
            all_voice_chats = self.voice_chat_joiner.get_all_account_voice_chats()
            
            if not all_voice_chats:
                await message.reply("📭 هیچ ویس چتی در حال حاضر فعال نیست.")
                return
            
            response = "🎵 **لیست ویس چت‌های فعال:**\n\n"
            
            for phone, voice_chats in all_voice_chats.items():
                if voice_chats:  # Only show accounts with active voice chats
                    response += f"📱 **{phone}:**\n"
                    for i, vc in enumerate(voice_chats, 1):
                        joined_time = vc['joined_at'].strftime("%H:%M:%S")
                        response += f"  {i}. 🏠 {vc['group_link']}\n"
                        response += f"     🎵 {vc['voice_chat_id']}\n"
                        response += f"     ⏰ {joined_time}\n"
                    response += "\n"
            
            # Split message if too long
            if len(response) > 4000:
                parts = [response[i:i+4000] for i in range(0, len(response), 4000)]
                for part in parts:
                    await message.reply(part)
            else:
                await message.reply(response)
            
            logger.info(f"Voice chats listed by {sender_id}")
            
        except Exception as e:
            logger.error(f"Error in listvoice command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_accountvoice_command(self, message):
        """Handle /accountvoice command - List voice chats for specific account"""
        try:
            text = message.text
            sender_id = message.sender_id
            
            if len(text.split()) < 2:
                await message.reply("""
❌ فرمت صحیح: /accountvoice شماره_تلفن

**مثال:**
/accountvoice +989123456789

**نکته:** این دستور ویس چت‌های اکانت مشخص شده را نمایش می‌دهد.
                """)
                return
            
            # Check if sender is authorized
            if not self.is_authorized_user(sender_id):
                await message.reply("❌ شما دسترسی لازم را ندارید.")
                return
            
            phone = text.split()[1]
            
            # Validate phone number format
            if not phone.startswith('+') or len(phone) < 10:
                await message.reply("❌ فرمت شماره تلفن نامعتبر است. مثال: +989123456789")
                return
            
            # Check if account exists
            account_exists = False
            for account in self.account_manager.accounts:
                if account['phone'] == phone:
                    account_exists = True
                    break
            
            if not account_exists:
                await message.reply(f"❌ اکانت `{phone}` در ربات وجود ندارد.")
                return
            
            voice_chats = self.voice_chat_joiner.get_account_voice_chats(phone)
            
            if not voice_chats:
                await message.reply(f"📭 اکانت `{phone}` در هیچ ویس چتی حضور ندارد.")
                return
            
            response = f"🎵 **ویس چت‌های اکانت `{phone}`:**\n\n"
            
            for i, vc in enumerate(voice_chats, 1):
                joined_time = vc['joined_at'].strftime("%H:%M:%S")
                response += f"{i}. 🏠 **گروه:** {vc['group_link']}\n"
                response += f"   🎵 **ویس چت:** {vc['voice_chat_id']}\n"
                response += f"   ⏰ **زمان جوین:** {joined_time}\n\n"
            
            await message.reply(response)
            
            logger.info(f"Voice chats for account {phone} listed by {sender_id}")
            
        except Exception as e:
            logger.error(f"Error in accountvoice command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_join_command(self, message):
        """Handle /join command - Join specific number of accounts to current group"""
        try:
            text = message.text
            sender_id = message.sender_id
            
            if len(text.split()) < 2:
                await message.reply("""
❌ فرمت صحیح: /join تعداد_اکانت

**مثال:**
/join 50
/join 25
/join 10

**نکته:** این دستور تعداد مشخص شده از اکانت‌ها را به گروه فعلی اضافه می‌کند.
                """)
                return
            
            # Check if sender is authorized
            if not self.is_authorized_user(sender_id):
                await message.reply("❌ شما دسترسی لازم را ندارید.")
                return
            
            try:
                account_count = int(text.split()[1])
            except ValueError:
                await message.reply("❌ تعداد اکانت نامعتبر است. باید عدد باشد.")
                return
            
            # Validate account count
            if account_count < 1:
                await message.reply("❌ تعداد اکانت باید حداقل 1 باشد.")
                return
            
            if account_count > 50:
                await message.reply("❌ تعداد اکانت نمی‌تواند بیش از 50 باشد.")
                return
            
            # Get current chat info
            chat = await message.get_chat()
            chat_id = chat.id
            chat_title = getattr(chat, 'title', 'Unknown')
            
            # Check if bot is admin in this group
            try:
                bot_member = await self.bot.get_participants(chat_id, filter='bots')
                bot_is_admin = False
                for member in bot_member:
                    if member.id == self.bot.me.id:
                        if hasattr(member, 'admin_rights') and member.admin_rights:
                            bot_is_admin = True
                        break
                
                if not bot_is_admin:
                    await message.reply("❌ ربات در این گروه ادمین نیست.")
                    return
                    
            except Exception as e:
                logger.error(f"Error checking bot admin status: {e}")
                await message.reply("❌ خطا در بررسی وضعیت ادمین ربات.")
                return
            
            # Get active accounts
            active_clients = await self.account_manager.get_active_clients()
            if not active_clients:
                await message.reply("❌ هیچ اکانت فعالی در ربات وجود ندارد.")
                return
            
            # Limit account count to available accounts
            if account_count > len(active_clients):
                account_count = len(active_clients)
                await message.reply(f"⚠️ فقط {len(active_clients)} اکانت فعال موجود است. از همه استفاده می‌شود.")
            
            await message.reply(f"🔄 در حال اضافه کردن {account_count} اکانت به گروه...")
            
            # Select accounts to join
            selected_clients = active_clients[:account_count]
            
            successful_joins = 0
            failed_joins = 0
            
            for i, client in enumerate(selected_clients):
                try:
                    logger.info(f"Processing account {i+1}/{len(selected_clients)}")
                    
                    # Join the group and voice chat
                    join_result = await self.voice_chat_joiner.join_group(client, chat_id, join_voice_chat=True)
                    if join_result and join_result.get('group'):
                        successful_joins += 1
                        
                        # Add to tracking
                        phone = None
                        for account in self.account_manager.accounts:
                            if account['phone'] in self.account_manager.clients and self.account_manager.clients[account['phone']] == client:
                                phone = account['phone']
                                break
                        
                        if phone:
                            # Add to joined groups tracking
                            self.voice_chat_joiner.joined_groups.add(chat_id)
                            
                            # Track voice chat if joined successfully
                            if join_result.get('voice_chat'):
                                group_entity = join_result.get('group_entity')
                                if group_entity:
                                    self.voice_chat_joiner.add_account_to_voice_chat(
                                        phone, 
                                        f"https://t.me/{group_entity.username}" if group_entity.username else str(chat_id),
                                        join_result['voice_chat'].id
                                    )
                            
                            # Schedule auto leave if time is set
                            if self.auto_leave_time > 0:
                                await self.voice_chat_joiner.schedule_auto_leave(client, chat_id)
                    else:
                        failed_joins += 1
                    
                    # Delay between joins
                    if i < len(selected_clients) - 1:
                        await asyncio.sleep(2)  # 2 second delay between joins
                        
                except Exception as e:
                    logger.error(f"Error processing account {i+1}: {e}")
                    failed_joins += 1
            
            # Send result
            result_message = f"""
✅ **عملیات جوین شدن کامل شد!**

📊 **نتایج:**
• موفق: {successful_joins} اکانت
• ناموفق: {failed_joins} اکانت
• کل: {account_count} اکانت

🏠 **گروه:** {chat_title}
🎤 **ویس چت:** خودکار جوین شد
⏰ **خروج خودکار:** {self.auto_leave_time} دقیقه

**دستورات بعدی:**
/acc - مشاهده لیست اکانت‌ها
/listvoice - لیست ویس چت‌های فعال
/accountvoice شماره - ویس چت‌های اکانت خاص
/status - وضعیت ربات
            """
            
            await message.reply(result_message)
            
            logger.info(f"Join command executed: {successful_joins} successful, {failed_joins} failed by {sender_id}")
            
        except Exception as e:
            logger.error(f"Error in join command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_getapi_command(self, message):
        """Handle /getapi command - Get API credentials"""
        try:
            text = message.text
            sender_id = message.sender_id
            
            if len(text.split()) < 2:
                await message.reply("""
❌ فرمت صحیح: /getapi شماره_تلفن

**مثال:**
/getapi +989123456789

**نکته:** این دستور API credentials را از اکانت مشخص شده دریافت می‌کند.
                """)
                return
            
            # Check if sender is authorized
            if not self.is_authorized_user(sender_id):
                await message.reply("❌ شما دسترسی لازم را ندارید.")
                return
            
            phone = text.split()[1]
            
            # Validate phone number format
            if not phone.startswith('+') or len(phone) < 10:
                await message.reply("❌ فرمت شماره تلفن نامعتبر است. مثال: +989123456789")
                return
            
            await message.reply(f"🔄 در حال دریافت API credentials از اکانت `{phone}`...")
            
            # Try to get API credentials
            credentials = await self.get_api_credentials_alternative(phone)
            
            if credentials['success']:
                await message.reply(f"""
✅ **API credentials با موفقیت دریافت شد!**

🔑 **API ID:** `{credentials['api_id']}`
🔑 **API Hash:** `{credentials['api_hash']}`

**نحوه استفاده:**
1. این مقادیر را در Railway متغیرهای محیطی تنظیم کنید
2. یا در فایل .env قرار دهید
3. ربات را restart کنید

**متغیرهای محیطی:**
```
API_ID={credentials['api_id']}
API_HASH={credentials['api_hash']}
```

**نکات مهم:**
• این credentials برای اکانت `{phone}` دریافت شده
• می‌توانید از هر اکانت معتبر استفاده کنید
• credentials را در جای امن نگهداری کنید
                """)
                
                logger.info(f"API credentials retrieved successfully for {phone} by {sender_id}")
                
            else:
                await message.reply(f"""
❌ **خطا در دریافت API credentials**

🔍 **خطا:** {credentials.get('error', 'نامشخص')}

**راه حل‌ها:**
1. مطمئن شوید که شماره تلفن صحیح است
2. اکانت باید معتبر و فعال باشد
3. اکانت نباید محدودیت داشته باشد
4. دوباره تلاش کنید

**راه حل جایگزین:**
1. به https://my.telegram.org/apps بروید
2. با اکانت خود وارد شوید
3. API_ID و API_HASH را دریافت کنید
4. در Railway متغیرها را تنظیم کنید
                """)
                
                logger.error(f"Failed to retrieve API credentials for {phone}: {credentials.get('error')}")
            
        except Exception as e:
            logger.error(f"Error in getapi command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def handle_password_command(self, message):
        """Handle /password command for 2FA"""
        try:
            text = message.text
            sender_id = message.sender_id
            
            if len(text.split()) < 2:
                await message.reply("""
❌ فرمت صحیح: /password رمز_عبور

**مثال:**
/password mypassword123

**نکته:** این دستور برای اکانت‌هایی که 2FA دارند استفاده می‌شود.
                """)
                return
            
            # Check if sender is authorized
            if not self.is_authorized_user(sender_id):
                await message.reply("❌ شما دسترسی لازم را ندارید.")
                return
            
            password = text.split()[1]
            
            # Check if user has pending verification
            if sender_id not in self.pending_verification:
                await message.reply("❌ ابتدا شماره تلفن و کد را ارسال کنید.")
                return
            
            verification_data = self.pending_verification[sender_id]
            phone = verification_data['phone']
            
            await message.reply(f"🔄 در حال تایید رمز عبور برای {phone}...")
            
            # Try to verify with password
            success = await self.verify_account_with_password(phone, password)
            
            if success:
                # Clean up verification data
                del self.pending_verification[sender_id]
                
                await message.reply(f"""
✅ **اکانت با موفقیت تایید شد!**

📱 شماره تلفن: `{phone}`
🔐 رمز عبور: تایید شد
📊 وضعیت: فعال
🔗 Session: ذخیره شده

🎉 اکانت آماده استفاده است!

**دستورات بعدی:**
/acc - نمایش لیست اکانت‌ها
/join 25 - جوین شدن 25 اکانت به گروه فعلی
/ping - بررسی وضعیت ربات
                """)
                
                logger.info(f"Account {phone} verified with password successfully")
                
            else:
                await message.reply(f"""
❌ **تایید ناموفق**

🔍 **مشکلات احتمالی:**
• رمز عبور اشتباه است
• اکانت مشکل دارد
• خطا در اتصال

**راه حل‌ها:**
1. رمز عبور را دوباره بررسی کنید
2. اطمینان حاصل کنید که 2FA فعال است
3. دوباره تلاش کنید

**دستور جدید:**
/password رمز_عبور_جدید
                """)
            
        except Exception as e:
            logger.error(f"Error in password command: {e}")
            await message.reply("❌ خطا در پردازش دستور")
    
    async def verify_account_with_password(self, phone, password):
        """Verify account with 2FA password"""
        try:
            from telethon import TelegramClient
            from telethon.sessions import StringSession
            from telethon.errors import SessionPasswordNeededError, PasswordHashInvalidError
            
            logger.info(f"Starting verification with password for {phone}")
            
            # Create temporary client for verification
            session = StringSession()
            client = TelegramClient(session, API_ID, API_HASH)
            
            try:
                # Start client with phone (will ask for password)
                await client.start(phone=phone, password=password)
                
                # Get account info
                me = await client.get_me()
                logger.info(f"Account verified with password: {me.first_name} ({phone})")
                
                # Save session for future use
                session_string = client.session.save()
                
                # Add to account manager with session
                self.account_manager.add_account_with_session(phone, session_string)
                
                # Disconnect client
                await client.disconnect()
                
                return True
                
            except PasswordHashInvalidError:
                logger.error(f"Invalid password for {phone}")
                await client.disconnect()
                return False
                
            except Exception as e:
                logger.error(f"Error during password verification for {phone}: {e}")
                await client.disconnect()
                return False
            
        except Exception as e:
            logger.error(f"Error in verify_account_with_password for {phone}: {e}")
            return False
    
    def is_authorized_user(self, user_id):
        """Check if user is owner or admin"""
        return user_id == self.owner_id or user_id in self.admin_users
    
    def check_user_permission(self, user_id, permission):
        """Check if user has specific permission"""
        if not self.is_authorized_user(user_id):
            return False
        
        user_perms = self.user_permissions.get(user_id, {})
        return user_perms.get(permission, False)
    
    async def handle_help_command(self, message):
        """Handle /help command - Show complete bot commands"""
        try:
            sender_id = message.sender_id
            
            # Check if sender is authorized
            if not self.is_authorized_user(sender_id):
                await message.reply("❌ شما دسترسی لازم را ندارید.")
                return
            
            # Get account count
            account_count = len(self.account_manager.accounts)
            active_count = len([acc for acc in self.account_manager.accounts if acc.get('active', False)])
            
            help_text = f"""
🤖 **راهنمای کامل ربات جوینر ویس چت تلگرام**

📊 **وضعیت فعلی:**
• کل اکانت‌ها: {account_count}
• اکانت‌های فعال: {active_count}
• حداکثر اکانت: 50
• زمان خروج خودکار: {self.auto_leave_time} دقیقه

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔐 **احراز هویت اکانت:**
`+989123456789` - ارسال شماره تلفن برای تایید
`/code 12345` - ارسال کد تایید
`/password mypass` - ارسال رمز عبور 2FA

📱 **مدیریت اکانت‌ها:**
`/acc` - نمایش لیست اکانت‌ها
`/del +989123456789` - حذف اکانت خاص
`/logout +989123456789` - خروج از اکانت خاص

🏠 **جوین شدن به گروه:**
`/join 25` - جوین شدن 25 اکانت به گروه فعلی و ویس چت
`/joinall @group` - جوین شدن همه اکانت‌ها به گروه

🎤 **مدیریت ویس چت:**
`/addvoice 25` - اضافه کردن 25 اکانت به ویس چت گروه فعلی
`/removevoice +989123456789 @group voice_chat_id` - حذف اکانت از ویس چت
`/listvoice` - لیست همه ویس چت‌های فعال
`/accountvoice +989123456789` - ویس چت‌های اکانت خاص

👥 **مدیریت کاربران:**
`/setowner 123456789` - تنظیم مالک ربات (فقط یک بار)
`/promote 123456789` - ترفیع کاربر به ادمین
`/demote 123456789` - حذف ادمین

⚙️ **تنظیمات:**
`/time 30` - تنظیم زمان خروج خودکار (دقیقه)
`/ping` - بررسی وضعیت ربات
`/getapi +989123456789` - دریافت API credentials

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🚀 **نحوه استفاده:**
1️⃣ `/setowner 5803428693` - تنظیم مالک
2️⃣ `+989123456789` - اضافه کردن اکانت
3️⃣ `/code 12345` - تایید اکانت
4️⃣ `/join 25` - جوین شدن 25 اکانت به گروه

💡 **نکات مهم:**
• دستور `/join` اکانت‌ها را به گروه و ویس چت اضافه می‌کند
• پشتیبانی کامل از 2FA
• خروج خودکار بعد از زمان مشخص
• ردیابی کامل ویس چت‌ها

📞 **پشتیبانی:** [@silverrmb](https://t.me/silverrmb)
            """
            
            await message.reply(help_text)
            
        except Exception as e:
            logger.error(f"Error in help command: {e}")
            await message.reply("❌ خطا در پردازش دستور")

async def main():
    """Main function to run the bot"""
    bot = TelegramJoinerBot()
    await bot.start_bot()

if __name__ == "__main__":
    asyncio.run(main())
