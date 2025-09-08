import asyncio
from datetime import datetime
from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest, GetFullChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import FloodWaitError, ChatAdminRequiredError, UserBannedInChannelError
from loguru import logger
from config import JOIN_DELAY

class VoiceChatJoiner:
    def __init__(self, account_manager, auto_leave_time=30):
        self.account_manager = account_manager
        self.joined_groups = set()
        self.auto_leave_time = auto_leave_time  # minutes
        self.auto_leave_tasks = {}  # Store auto leave tasks
        self.account_voice_chats = {}  # Track which voice chats each account is in
        # Format: {phone: [{'group_link': '...', 'voice_chat_id': '...', 'joined_at': datetime}]}
    
    async def join_group(self, client, group_link_or_id, join_voice_chat=True):
        """Join a group using client and optionally join voice chat"""
        try:
            logger.info(f"Attempting to join group: {group_link_or_id}")
            
            group_entity = None
            
            if group_link_or_id.startswith('https://t.me/joinchat/') or group_link_or_id.startswith('https://t.me/+'):
                # Handle invite links
                invite_hash = group_link_or_id.split('/')[-1]
                if invite_hash.startswith('+'):
                    invite_hash = invite_hash[1:]
                
                result = await client(ImportChatInviteRequest(invite_hash))
                logger.info(f"Successfully joined group via invite link: {group_link_or_id}")
                group_entity = result.chats[0] if result.chats else None
            else:
                # Handle group username or ID
                result = await client(JoinChannelRequest(group_link_or_id))
                logger.info(f"Successfully joined group: {group_link_or_id}")
                group_entity = result.chats[0] if result.chats else None
            
            # If we want to join voice chat and group was joined successfully
            if join_voice_chat and group_entity:
                try:
                    # Try to find active voice chat in the group
                    voice_chat = await self.find_active_voice_chat(client, group_entity)
                    if voice_chat:
                        voice_result = await self.join_voice_chat(client, group_entity, voice_chat.id)
                        if voice_result:
                            logger.info(f"Successfully joined voice chat in group: {group_entity.title}")
                            return {'group': result, 'voice_chat': voice_result, 'group_entity': group_entity}
                        else:
                            logger.warning(f"Failed to join voice chat in group: {group_entity.title}")
                            return {'group': result, 'voice_chat': None, 'group_entity': group_entity}
                    else:
                        logger.info(f"No active voice chat found in group: {group_entity.title}")
                        return {'group': result, 'voice_chat': None, 'group_entity': group_entity}
                except Exception as e:
                    logger.error(f"Error joining voice chat: {e}")
                    return {'group': result, 'voice_chat': None, 'group_entity': group_entity}
            
            return {'group': result, 'voice_chat': None, 'group_entity': group_entity}
                
        except FloodWaitError as e:
            logger.warning(f"Flood wait error: {e.seconds} seconds. Waiting...")
            await asyncio.sleep(e.seconds)
            return await self.join_group(client, group_link_or_id, join_voice_chat)
        except ChatAdminRequiredError:
            logger.error(f"Admin required to join group: {group_link_or_id}")
            return None
        except UserBannedInChannelError:
            logger.error(f"User banned from group: {group_link_or_id}")
            return None
        except Exception as e:
            logger.error(f"Error joining group {group_link_or_id}: {e}")
            return None
    
    async def find_active_voice_chat(self, client, group_entity):
        """Find active voice chat in a group"""
        try:
            # Get full channel info
            full_channel = await client(GetFullChannelRequest(group_entity))
            
            # Check if there's an active voice chat
            if hasattr(full_channel, 'call') and full_channel.call:
                logger.info(f"Found active voice chat in group: {group_entity.title}")
                return full_channel.call
            else:
                logger.info(f"No active voice chat found in group: {group_entity.title}")
                return None
                
        except Exception as e:
            logger.error(f"Error finding voice chat in group {group_entity.title}: {e}")
            return None
    
    async def join_voice_chat(self, client, group_entity, voice_chat_id):
        """Join a voice chat in a group"""
        try:
            logger.info(f"Attempting to join voice chat {voice_chat_id} in group {group_entity.title}")
            
            # Get the voice chat
            voice_chat = await client.get_entity(voice_chat_id)
            
            # Join the voice chat
            result = await client(JoinChannelRequest(voice_chat))
            logger.info(f"Successfully joined voice chat: {voice_chat_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error joining voice chat {voice_chat_id}: {e}")
            return None
    
    async def join_group_with_all_accounts(self, group_link_or_id, voice_chat_id=None):
        """Join a group with all active accounts"""
        logger.info(f"Starting to join group {group_link_or_id} with all accounts")
        
        active_clients = await self.account_manager.get_active_clients()
        if not active_clients:
            logger.error("No active clients available")
            return False
        
        successful_joins = 0
        failed_joins = 0
        
        for i, client in enumerate(active_clients):
            try:
                logger.info(f"Processing account {i+1}/{len(active_clients)}")
                
                # Join the group
                group_result = await self.join_group(client, group_link_or_id)
                if group_result:
                    successful_joins += 1
                    self.joined_groups.add(group_link_or_id)
                    
                    # If voice chat ID is provided, join the voice chat
                    if voice_chat_id:
                        await asyncio.sleep(2)  # Wait before joining voice chat
                        voice_result = await self.join_voice_chat(client, group_result, voice_chat_id)
                        
                        if voice_result:
                            # Add to tracking
                            phone = None
                            for account in self.account_manager.accounts:
                                if account['phone'] in self.account_manager.clients and self.account_manager.clients[account['phone']] == client:
                                    phone = account['phone']
                                    break
                            
                            if phone:
                                self.add_account_to_voice_chat(phone, group_link_or_id, voice_chat_id)
                    
                    # Schedule auto leave
                    await self.schedule_auto_leave(client, group_link_or_id, voice_chat_id)
                
                else:
                    failed_joins += 1
                
                # Delay between joins
                if i < len(active_clients) - 1:
                    await asyncio.sleep(JOIN_DELAY)
                    
            except Exception as e:
                logger.error(f"Error processing account {i+1}: {e}")
                failed_joins += 1
        
        logger.info(f"Group join completed. Successful: {successful_joins}, Failed: {failed_joins}")
        return successful_joins > 0
    
    async def leave_group(self, client, group_link_or_id):
        """Leave a group using client"""
        try:
            logger.info(f"Attempting to leave group: {group_link_or_id}")
            
            # Get the group entity
            group_entity = await client.get_entity(group_link_or_id)
            
            # Leave the group
            await client.delete_dialog(group_entity)
            logger.info(f"Successfully left group: {group_link_or_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error leaving group {group_link_or_id}: {e}")
            return False
    
    async def leave_group_with_all_accounts(self, group_link_or_id):
        """Leave a group with all active accounts"""
        logger.info(f"Starting to leave group {group_link_or_id} with all accounts")
        
        active_clients = await self.account_manager.get_active_clients()
        if not active_clients:
            logger.error("No active clients available")
            return False
        
        successful_leaves = 0
        failed_leaves = 0
        
        for i, client in enumerate(active_clients):
            try:
                logger.info(f"Processing account {i+1}/{len(active_clients)}")
                
                result = await self.leave_group(client, group_link_or_id)
                if result:
                    successful_leaves += 1
                else:
                    failed_leaves += 1
                
                # Delay between leaves
                if i < len(active_clients) - 1:
                    await asyncio.sleep(JOIN_DELAY)
                    
            except Exception as e:
                logger.error(f"Error processing account {i+1}: {e}")
                failed_leaves += 1
        
        if group_link_or_id in self.joined_groups:
            self.joined_groups.remove(group_link_or_id)
        
        logger.info(f"Group leave completed. Successful: {successful_leaves}, Failed: {failed_leaves}")
        return successful_leaves > 0
    
    def get_joined_groups(self):
        """Get list of joined groups"""
        return list(self.joined_groups)
    
    def set_auto_leave_time(self, minutes):
        """Set auto leave time in minutes"""
        self.auto_leave_time = minutes
        logger.info(f"Auto leave time set to {minutes} minutes")
    
    async def schedule_auto_leave(self, client, group_link, voice_chat_id=None):
        """Schedule auto leave for a client after specified time"""
        try:
            phone = None
            for account in self.account_manager.accounts:
                if account['phone'] in self.account_manager.clients and self.account_manager.clients[account['phone']] == client:
                    phone = account['phone']
                    break
            
            if not phone:
                logger.error("Could not find phone number for client")
                return
            
            if self.auto_leave_time > 0:
                # Schedule auto leave
                task = asyncio.create_task(self._auto_leave_after_delay(client, group_link, voice_chat_id, phone))
                self.auto_leave_tasks[phone] = task
                logger.info(f"Scheduled auto leave for {phone} after {self.auto_leave_time} minutes")
            else:
                logger.info(f"Auto leave disabled for {phone}")
                
        except Exception as e:
            logger.error(f"Error scheduling auto leave: {e}")
    
    async def _auto_leave_after_delay(self, client, group_link, voice_chat_id, phone):
        """Auto leave after specified delay"""
        try:
            await asyncio.sleep(self.auto_leave_time * 60)  # Convert minutes to seconds
            
            logger.info(f"Auto leaving {phone} from group {group_link}")
            
            # Leave the group
            await self.leave_group(client, group_link)
            
            # Remove from voice chat tracking
            if phone in self.account_voice_chats:
                self.account_voice_chats[phone] = [
                    vc for vc in self.account_voice_chats[phone] 
                    if vc['group_link'] != group_link
                ]
            
            # Remove from auto leave tasks
            if phone in self.auto_leave_tasks:
                del self.auto_leave_tasks[phone]
                
        except Exception as e:
            logger.error(f"Error in auto leave for {phone}: {e}")
    
    def add_account_to_voice_chat(self, phone, group_link, voice_chat_id):
        """Add account to voice chat tracking"""
        if phone not in self.account_voice_chats:
            self.account_voice_chats[phone] = []
        
        # Check if already tracking this voice chat
        for vc in self.account_voice_chats[phone]:
            if vc['group_link'] == group_link and vc['voice_chat_id'] == voice_chat_id:
                return
        
        # Add new voice chat
        self.account_voice_chats[phone].append({
            'group_link': group_link,
            'voice_chat_id': voice_chat_id,
            'joined_at': datetime.now()
        })
        
        logger.info(f"Added {phone} to voice chat tracking: {group_link}")
    
    def remove_account_from_voice_chat(self, phone, group_link, voice_chat_id):
        """Remove account from voice chat tracking"""
        if phone not in self.account_voice_chats:
            return
        
        # Remove the voice chat
        self.account_voice_chats[phone] = [
            vc for vc in self.account_voice_chats[phone] 
            if not (vc['group_link'] == group_link and vc['voice_chat_id'] == voice_chat_id)
        ]
        
        logger.info(f"Removed {phone} from voice chat tracking: {group_link}")
    
    def get_account_voice_chats(self, phone):
        """Get voice chats for a specific account"""
        return self.account_voice_chats.get(phone, [])
    
    def get_all_voice_chats(self):
        """Get all voice chats being tracked"""
        return self.account_voice_chats
    
    async def join_multiple_voice_chats(self, voice_chat_configs, account_count_per_chat=10):
        """Join multiple voice chats with specified number of accounts each"""
        logger.info(f"Starting to join {len(voice_chat_configs)} voice chats")
        
        active_clients = await self.account_manager.get_active_clients()
        if not active_clients:
            logger.error("No active clients available")
            return False
        
        total_accounts = len(active_clients)
        total_needed = len(voice_chat_configs) * account_count_per_chat
        
        if total_needed > total_accounts:
            logger.warning(f"Not enough accounts. Available: {total_accounts}, Needed: {total_needed}")
            account_count_per_chat = total_accounts // len(voice_chat_configs)
            if account_count_per_chat == 0:
                logger.error("Not enough accounts for any voice chat")
                return False
        
        results = []
        account_index = 0
        
        for i, config in enumerate(voice_chat_configs):
            group_link = config['group_link']
            voice_chat_id = config['voice_chat_id']
            
            logger.info(f"Processing voice chat {i+1}/{len(voice_chat_configs)}: {group_link}")
            
            # Distribute accounts for this voice chat
            accounts_for_this_chat = active_clients[account_index:account_index + account_count_per_chat]
            account_index += account_count_per_chat
            
            successful_joins = 0
            failed_joins = 0
            
            for j, client in enumerate(accounts_for_this_chat):
                try:
                    logger.info(f"Processing account {j+1}/{len(accounts_for_this_chat)} for voice chat {i+1}")
                    
                    # Join the group first
                    group_result = await self.join_group(client, group_link)
                    if group_result:
                        # Join the voice chat
                        await asyncio.sleep(2)
                        voice_result = await self.join_voice_chat(client, group_result, voice_chat_id)
                        if voice_result:
                            successful_joins += 1
                            
                            # Add to tracking
                            phone = None
                            for account in self.account_manager.accounts:
                                if account['phone'] in self.account_manager.clients and self.account_manager.clients[account['phone']] == client:
                                    phone = account['phone']
                                    break
                            
                            if phone:
                                self.add_account_to_voice_chat(phone, group_link, voice_chat_id)
                        else:
                            failed_joins += 1
                    else:
                        failed_joins += 1
                    
                    # Delay between joins
                    if j < len(accounts_for_this_chat) - 1:
                        await asyncio.sleep(JOIN_DELAY)
                        
                except Exception as e:
                    logger.error(f"Error processing account {j+1} for voice chat {i+1}: {e}")
                    failed_joins += 1
            
            results.append({
                'group_link': group_link,
                'voice_chat_id': voice_chat_id,
                'successful': successful_joins,
                'failed': failed_joins
            })
            
            logger.info(f"Voice chat {i+1} completed. Successful: {successful_joins}, Failed: {failed_joins}")
            
            # Delay between voice chats
            if i < len(voice_chat_configs) - 1:
                await asyncio.sleep(JOIN_DELAY * 2)
        
        logger.info(f"All voice chats completed. Total successful: {sum(r['successful'] for r in results)}, Total failed: {sum(r['failed'] for r in results)}")
        return results