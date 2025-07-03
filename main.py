import asyncio
import aiohttp
import logging
import html
import json
from collections import defaultdict
from aiogram import Bot, Dispatcher, Router, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from aiogram.filters import Command
from aiogram.types.callback_query import CallbackQuery
from datetime import datetime, timedelta
from aiogram.exceptions import TelegramBadRequest
from db import (
    set_token, get_tokens, set_current_account, get_current_account, delete_token, 
    set_user_filters, get_user_filters, set_spam_filter, get_spam_filter, 
    is_already_sent, add_sent_id, toggle_token_status, get_active_tokens, 
    get_token_status, set_account_active, get_info_card,
    # Username-based authentication
    set_user_session, get_user_session, clear_user_session, 
    create_username_collection, username_exists, list_usernames
)
from lounge import send_lounge
from chatroom import send_message_to_everyone
from unsubscribe import unsubscribe_everyone
from filters import filter_command, set_filter, get_filter_keyboard
from allcountry import run_all_countries
from chatroom import send_message_to_everyone_all_tokens
from lounge import send_lounge_all_tokens
from signup import signup_command, signup_callback_handler, signup_message_handler
from friend_requests import (
    run_requests, 
    process_all_tokens, 
    user_states,
    stop_markup
)

# Tokens
API_TOKEN = "7616181573:AAGpdqTwQcepXKXq72x58RABIZbvbE-NXKg"

# Admin user IDs
ADMIN_USER_IDS = [7405203657, 8060390897, 7575419069]

# Password access dictionary
password_access = {}

# Password for temporary access
TEMP_PASSWORD = "11223344"

TARGET_CHANNEL_ID = -1002610862940

# Username authentication states
username_auth_states = {}

# Initialize logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Initialize bot, router and dispatcher
bot = Bot(token=API_TOKEN)
router = Router()
dp = Dispatcher()

def is_admin(user_id):
    return user_id in ADMIN_USER_IDS

def has_valid_access(user_id):
    if is_admin(user_id):
        return True
    if user_id in password_access and password_access[user_id] > datetime.now():
        return True
    # Check if user has active username session
    if get_user_session(user_id):
        return True
    return False

def get_auth_menu():
    """Get the authentication menu for username login"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🆕 Start New", callback_data="auth_start_new"),
            InlineKeyboardButton(text="🔐 Login", callback_data="auth_login")
        ]
    ])

def get_settings_menu(user_id):
    """Generate the enhanced settings menu markup with mobile-friendly design"""
    if user_id not in user_states:
        user_states[user_id] = {}
    
    spam_on = get_spam_filter(user_id)
    current_username = get_user_session(user_id)
    
    buttons = [
        [
            InlineKeyboardButton(text="👤 Manage Accounts", callback_data="manage_accounts"),
            InlineKeyboardButton(text="🎯 Filters", callback_data="show_filters")
        ],
        [
            InlineKeyboardButton(
                text=f"🛡️ Spam Filter: {'ON ✅' if spam_on else 'OFF ❌'}",
                callback_data="toggle_spam_filter"
            )
        ],
        [
            InlineKeyboardButton(text="🆕 Sign Up", callback_data="signup_go"),
            InlineKeyboardButton(text="🔐 Sign In", callback_data="signin_go")
        ]
    ]
    
    if current_username:
        buttons.append([
            InlineKeyboardButton(text="🚪 Logout", callback_data="auth_logout")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="🔙 Back", callback_data="back_to_menu")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# Enhanced mobile-friendly keyboards
start_markup = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="🚀 Send Request", callback_data="send_request_menu"),
        InlineKeyboardButton(text="🌍 All Countries", callback_data="all_countries")
    ],
    [
        InlineKeyboardButton(text="⚙️ Settings", callback_data="settings_menu")
    ]
])

send_request_markup = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="▶️ Start Request", callback_data="start"),
        InlineKeyboardButton(text="🔄 Request All", callback_data="start_all")
    ],
    [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_menu")]
])

back_markup = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_menu")]
])

stop_markup = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="⏹️ Stop", callback_data="stop")]
])

@router.message(Command("password"))
async def password_command(message: types.Message):
    user_id = message.chat.id
    command_text = message.text.strip()

    if len(command_text.split()) < 2:
        await message.reply("Please provide the password. Usage: /password <password>")
        return

    provided_password = command_text.split()[1]
    if provided_password == TEMP_PASSWORD:
        password_access[user_id] = datetime.now() + timedelta(hours=1)
        await message.reply("✅ Temporary access granted for 1 hour.")
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    else:
        await message.reply("❌ Incorrect password.")

@router.message(Command("start"))
async def start_command(message: types.Message):
    user_id = message.chat.id
    
    # Check if user has username session
    current_username = get_user_session(user_id)
    
    if not has_valid_access(user_id):
        await message.reply(
            "🔐 <b>Authentication Required</b>\n\n"
            "Please choose an option to continue:",
            reply_markup=get_auth_menu(),
            parse_mode="HTML"
        )
        return
    
    state = user_states[user_id]
    welcome_text = "🎯 <b>Meeff Bot Dashboard</b>\n\n"
    if current_username:
        welcome_text += f"👤 Logged in as: <code>{current_username}</code>\n\n"
    welcome_text += "Choose an option below to get started:"
    
    status = await message.answer(
        welcome_text,
        reply_markup=start_markup,
        parse_mode="HTML"
    )
    state["status_message_id"] = status.message_id
    state["pinned_message_id"] = None

@router.message(Command("signup"))
async def signup_cmd(message: types.Message):
    if not has_valid_access(message.chat.id):
        await message.reply("🚫 You are not authorized to use this bot.")
        return
    await signup_command(message)

@router.message(Command("send_lounge_all"))
async def send_lounge_all(message: types.Message):
    user_id = message.chat.id

    if not has_valid_access(user_id):
        return await message.reply("🚫 You are not authorized to use this bot.")

    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        return await message.reply(
            "ℹ️ <b>Usage</b>\n\n"
            "<code>/send_lounge_all &lt;message&gt;</code>",
            parse_mode="HTML"
        )

    custom_message = parts[1]
    active_tokens_data = get_active_tokens(user_id)

    if not active_tokens_data:
        return await message.reply("🔍 No active tokens found.")
        
    spam_enabled = get_spam_filter(user_id)
    status = await message.reply(
        f"⏳ <b>Starting Lounge Messages</b>\n\n"
        f"📊 Active tokens: {len(active_tokens_data)}\n"
        f"📝 Message: <code>{custom_message[:50]}...</code>\n"
        f"🛡️ Spam filter: {'ON' if spam_enabled else 'OFF'}",
        parse_mode="HTML"
    )

    try:
        await send_lounge_all_tokens(
            active_tokens_data, 
            custom_message, 
            status, 
            bot, 
            message.chat.id, 
            spam_enabled
        )
    except Exception as e:
        await status.edit_text(f"❌ Error sending lounge messages: {str(e)}")
        logging.error(f"Error in /send_lounge_all command: {str(e)}")

@router.message(Command("lounge"))
async def lounge_command(message: types.Message):
    user_id = message.chat.id

    if not has_valid_access(user_id):
        await message.reply("🚫 You are not authorized to use this bot.")
        return

    token = get_current_account(user_id)
    if not token:
        await message.reply("🔍 No active account found. Please set an account before sending messages.")
        return

    command_text = message.text.strip()
    if len(command_text.split()) < 2:
        await message.reply(
            "ℹ️ <b>Usage</b>\n\n"
            "<code>/lounge &lt;message&gt;</code>",
            parse_mode="HTML"
        )
        return

    custom_message = " ".join(command_text.split()[1:])
    spam_enabled = get_spam_filter(user_id)
    
    status_message = await message.reply(
        f"⏳ <b>Starting Lounge Messaging</b>\n\n"
        f"📝 Message: <code>{custom_message[:50]}...</code>\n"
        f"🛡️ Spam filter: {'ON' if spam_enabled else 'OFF'}",
        parse_mode="HTML"
    )

    try:
        await send_lounge(
            token, 
            custom_message, 
            status_message, 
            bot, 
            user_id, 
            spam_enabled
        )
    except Exception as e:
        await status_message.edit_text(f"❌ Error sending lounge messages: {str(e)}")
        logging.error(f"Error in /lounge command: {str(e)}")

@router.message(Command("chatroom"))
async def send_to_all_command(message: types.Message):
    """Enhanced chatroom command with better mobile UI"""
    user_id = message.chat.id

    if not has_valid_access(user_id):
        await message.reply("🚫 You are not authorized to use this bot.")
        return

    token = get_current_account(user_id)
    if not token:
        await message.reply("🔍 No active account found. Please set an account before sending messages.")
        return

    command_text = message.text.strip()
    if len(command_text.split()) < 2:
        await message.reply(
            "ℹ️ <b>Usage</b>\n\n"
            "<code>/chatroom &lt;message&gt;</code>",
            parse_mode="HTML"
        )
        return

    custom_message = " ".join(command_text.split()[1:])
    spam_enabled = get_spam_filter(user_id)
    
    status_message = await message.reply(
        f"⏳ <b>Starting Chatroom Messages</b>\n\n"
        f"📝 Message: <code>{custom_message[:50]}...</code>\n"
        f"🛡️ Spam filter: {'ON' if spam_enabled else 'OFF'}\n\n"
        f"🔄 Initializing...",
        parse_mode="HTML"
    )

    try:
        total_chatrooms, sent_count, filtered_count = await send_message_to_everyone(
            token, 
            custom_message, 
            status_message=status_message, 
            bot=bot, 
            chat_id=user_id, 
            spam_enabled=spam_enabled
        )

        await status_message.edit_text(
            f"✅ <b>Chatroom Messages Complete</b>\n\n"
            f"📊 <b>Results:</b>\n"
            f"• Total chatrooms: <code>{total_chatrooms}</code>\n"
            f"• Messages sent: <code>{sent_count}</code>\n"
            f"• Filtered (duplicates): <code>{filtered_count}</code>\n\n"
            f"🛡️ Spam filter: {'ON' if spam_enabled else 'OFF'}",
            parse_mode="HTML"
        )
    except Exception as e:
        await status_message.edit_text(
            f"❌ <b>Error</b>\n\n"
            f"Failed to send messages: {str(e)[:200]}",
            parse_mode="HTML"
        )
        logging.error(f"Error in /chatroom command: {str(e)}")

@router.message(Command("send_chat_all"))
async def send_chat_all(message: types.Message):
    """Enhanced send_chat_all command with better mobile UI"""
    user_id = message.chat.id

    if not has_valid_access(user_id):
        await message.reply("🚫 You are not authorized to use this bot.")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await message.reply(
            "ℹ️ <b>Usage</b>\n\n"
            "<code>/send_chat_all &lt;message&gt;</code>",
            parse_mode="HTML"
        )
        return

    custom_message = parts[1]
    active_tokens = get_active_tokens(user_id)
    tokens = [t["token"] for t in active_tokens]
    
    if not tokens:
        await message.reply("🔍 No active tokens found.")
        return
        
    spam_enabled = get_spam_filter(user_id)

    status = await message.reply(
        f"⏳ <b>Starting Multi-Account Chatroom</b>\n\n"
        f"📊 Active tokens: <code>{len(tokens)}</code>\n"
        f"📝 Message: <code>{custom_message[:50]}...</code>\n"
        f"🛡️ Spam filter: {'ON' if spam_enabled else 'OFF'}\n\n"
        f"🔄 Initializing...",
        parse_mode="HTML"
    )

    try:
        await send_message_to_everyone_all_tokens(
            tokens, 
            custom_message, 
            status, 
            bot, 
            message.chat.id, 
            spam_enabled=spam_enabled
        )
    except Exception as e:
        await status.edit_text(
            f"❌ <b>Error</b>\n\n"
            f"Failed to send messages: {str(e)[:200]}",
            parse_mode="HTML"
        )
        logging.error(f"Error in /send_chat_all command: {str(e)}")

@router.message(Command("skip"))
async def unsubscribe_all_command(message: types.Message):
    user_id = message.chat.id
    if not has_valid_access(user_id):
        await message.reply("🚫 You are not authorized to use this bot.")
        return
    token = get_current_account(user_id)
    if not token:
        await message.reply("🔍 No active account found. Please set an account before unsubscribing.")
        return

    status_message = await message.reply(
        "⏳ <b>Unsubscribing from Chatrooms</b>\n\n"
        "🔄 Fetching chatrooms and unsubscribing...",
        parse_mode="HTML"
    )
    await unsubscribe_everyone(token, status_message=status_message, bot=bot, chat_id=user_id)

@router.message(Command("invoke"))
async def invoke_command(message: types.Message):
    user_id = message.chat.id
    if not has_valid_access(user_id):
        await message.reply("🚫 You are not authorized to use this bot.")
        return

    tokens = get_tokens(user_id)
    if not tokens:
        await message.reply("🔍 No tokens found.")
        return

    status_msg = await message.reply(
        "🔄 <b>Checking Account Status</b>\n\n"
        "Verifying all accounts...",
        parse_mode="HTML"
    )

    disabled_accounts = []
    working_accounts = []
    url = "https://api.meeff.com/facetalk/vibemeet/history/count/v1"
    params = {'locale': "en"}

    async with aiohttp.ClientSession() as session:
        for token_obj in tokens:
            token = token_obj["token"]
            headers = {
                'User-Agent': "okhttp/5.0.0-alpha.14",
                'Accept-Encoding': "gzip",
                'meeff-access-token': token
            }
            try:
                async with session.get(url, params=params, headers=headers) as resp:
                    result = await resp.json(content_type=None)
                    if "errorCode" in result and result["errorCode"] == "AuthRequired":
                        disabled_accounts.append(token_obj)
                    else:
                        working_accounts.append(token_obj)
            except Exception as e:
                logging.error(f"Error checking token {token_obj.get('name')}: {e}")
                disabled_accounts.append(token_obj)

    if disabled_accounts:
        for token_obj in disabled_accounts:
            delete_token(user_id, token_obj["token"])
        
        await status_msg.edit_text(
            f"🔧 <b>Account Cleanup Complete</b>\n\n"
            f"✅ Working accounts: <code>{len(working_accounts)}</code>\n"
            f"❌ Disabled accounts removed: <code>{len(disabled_accounts)}</code>\n\n"
            f"<b>Removed accounts:</b>\n" + 
            "\n".join([f"• {acc['name']}" for acc in disabled_accounts]),
            parse_mode="HTML"
        )
    else:
        await status_msg.edit_text(
            f"✅ <b>All Accounts Working</b>\n\n"
            f"All {len(working_accounts)} accounts are functioning properly.",
            parse_mode="HTML"
        )

@router.message(Command("settings"))
async def settings_command(message: types.Message):
    user_id = message.chat.id
    if not has_valid_access(user_id):
        await message.reply("🚫 You are not authorized to use this bot.")
        return
    
    current_username = get_user_session(user_id)
    settings_text = "⚙️ <b>Settings Menu</b>\n\n"
    if current_username:
        settings_text += f"👤 Current profile: <code>{current_username}</code>\n\n"
    settings_text += "Choose an option below:"
    
    await message.reply(
        settings_text,
        reply_markup=get_settings_menu(user_id),
        parse_mode="HTML"
    )

@router.message()
async def handle_new_token(message: types.Message):
    if message.text and message.text.startswith("/"):
        return
    user_id = message.from_user.id

    if message.from_user.is_bot:
        return

    # Handle signup/signin messages first
    if await signup_message_handler(message):
        return

    # Handle username authentication
    if user_id in username_auth_states:
        state = username_auth_states[user_id]
        
        if state.get("stage") == "ask_username_new":
            username = message.text.strip()
            if not username or len(username) < 3:
                await message.reply("❌ Username must be at least 3 characters long.")
                return
            
            if username_exists(username):
                await message.reply(f"❌ Username '{username}' already exists. Please choose another.")
                return
            
            # Create new username collection
            create_username_collection(username)
            set_user_session(user_id, username)
            del username_auth_states[user_id]
            
            await message.reply(
                f"✅ <b>Profile Created</b>\n\n"
                f"Welcome! Your profile '<code>{username}</code>' has been created.\n\n"
                f"You can now use the bot. Use /start to begin.",
                parse_mode="HTML"
            )
            return
            
        elif state.get("stage") == "ask_username_login":
            username = message.text.strip()
            if not username_exists(username):
                await message.reply(f"❌ Username '{username}' not found. Please try again or create a new profile.")
                return
            
            set_user_session(user_id, username)
            del username_auth_states[user_id]
            
            await message.reply(
                f"✅ <b>Logged In</b>\n\n"
                f"Welcome back to profile '<code>{username}</code>'!\n\n"
                f"Use /start to continue.",
                parse_mode="HTML"
            )
            return

    if not has_valid_access(user_id):
        await message.reply("🚫 You are not authorized to use this bot.")
        return

    if message.text:
        token_data = message.text.strip().split(" ")
        token = token_data[0]
        if len(token) < 10:
            await message.reply("❌ Invalid token. Please try again.")
            return

        # Verify token
        url = "https://api.meeff.com/facetalk/vibemeet/history/count/v1"
        params = {'locale': "en"}
        headers = {
            'User-Agent': "okhttp/5.0.0-alpha.14",
            'Accept-Encoding': "gzip",
            'meeff-access-token': token
        }
        
        verification_msg = await message.reply(
            "🔄 <b>Verifying Token</b>\n\n"
            "Please wait...",
            parse_mode="HTML"
        )
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, params=params, headers=headers) as resp:
                    result = await resp.json(content_type=None)
                    if "errorCode" in result and result["errorCode"] == "AuthRequired":
                        await verification_msg.edit_text(
                            "❌ <b>Invalid Token</b>\n\n"
                            "The token you provided is invalid or disabled. Please try a different token.",
                            parse_mode="HTML"
                        )
                        return
            except Exception as e:
                logging.error(f"Error verifying token: {e}")
                await verification_msg.edit_text(
                    "❌ <b>Verification Error</b>\n\n"
                    "Error verifying the token. Please try again.",
                    parse_mode="HTML"
                )
                return

        tokens = get_tokens(user_id)
        account_name = " ".join(token_data[1:]) if len(token_data) > 1 else f"Account {len(tokens) + 1}"
        set_token(user_id, token, account_name)
        
        await verification_msg.edit_text(
            f"✅ <b>Token Verified</b>\n\n"
            f"Your access token has been verified and saved as '<code>{account_name}</code>'.\n\n"
            f"Use the settings menu to manage accounts.",
            parse_mode="HTML"
        )
    else:
        await message.reply("❌ Message text is empty. Please provide a valid token.")

@router.callback_query()
async def callback_handler(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data

    # Handle signup/signin callbacks first
    if await signup_callback_handler(callback_query):
        return

    # Handle username authentication
    if data == "auth_start_new":
        username_auth_states[user_id] = {"stage": "ask_username_new"}
        await callback_query.message.edit_text(
            "🆕 <b>Create New Profile</b>\n\n"
            "Please enter a username for your new profile (minimum 3 characters):",
            parse_mode="HTML"
        )
        return
        
    elif data == "auth_login":
        usernames = list_usernames()
        if not usernames:
            await callback_query.message.edit_text(
                "❌ <b>No Profiles Found</b>\n\n"
                "No profiles exist yet. Please create a new profile first.",
                reply_markup=get_auth_menu(),
                parse_mode="HTML"
            )
            return
            
        username_auth_states[user_id] = {"stage": "ask_username_login"}
        username_list = "\n".join([f"• <code>{u}</code>" for u in usernames[:10]])
        await callback_query.message.edit_text(
            f"🔐 <b>Login to Profile</b>\n\n"
            f"Available profiles:\n{username_list}\n\n"
            f"Please enter the username you want to login to:",
            parse_mode="HTML"
        )
        return
        
    elif data == "auth_logout":
        current_username = get_user_session(user_id)
        clear_user_session(user_id)
        await callback_query.message.edit_text(
            f"🚪 <b>Logged Out</b>\n\n"
            f"You have been logged out from profile '<code>{current_username}</code>'.\n\n"
            f"Use /start to login again.",
            parse_mode="HTML"
        )
        return

    if not has_valid_access(user_id):
        await callback_query.answer("🚫 You are not authorized to use this bot.")
        return

    if user_id not in user_states:
        user_states[user_id] = {}
    state = user_states[user_id]

    if data == "send_request_menu":
        await callback_query.message.edit_text(
            "🚀 <b>Send Request Options</b>\n\n"
            "Choose your request type:",
            reply_markup=send_request_markup,
            parse_mode="HTML"
        )
        return
    
    elif data == "settings_menu":
        current_username = get_user_session(user_id)
        settings_text = "⚙️ <b>Settings Menu</b>\n\n"
        if current_username:
            settings_text += f"👤 Current profile: <code>{current_username}</code>\n\n"
        settings_text += "Choose an option below:"
        
        await callback_query.message.edit_text(
            settings_text,
            reply_markup=get_settings_menu(user_id),
            parse_mode="HTML"
        )
        return

    elif data == "show_filters":
        await callback_query.message.edit_text(
            "🎯 <b>Filter Settings</b>\n\n"
            "Configure your search preferences:",
            reply_markup=get_filter_keyboard(),
            parse_mode="HTML"
        )
        return

    elif data in ["filter_gender", "filter_age", "filter_nationality", "filter_back"] or \
         data.startswith("filter_gender_") or data.startswith("filter_age_") or \
         data.startswith("filter_nationality_"):
        await set_filter(callback_query)
        return

    elif data == "manage_accounts":
        tokens = get_tokens(user_id)
        current_token = get_current_account(user_id)

        if not tokens:
            await callback_query.message.edit_text(
                "👤 <b>No Accounts Found</b>\n\n"
                "No accounts saved. Send a new token to add an account.",
                reply_markup=back_markup,
                parse_mode="HTML"
            )
            return

        buttons = []
        for i, tok in enumerate(tokens):
            is_active = tok.get("active", True)
            status_emoji = "✅" if is_active else "❌"
            is_current = tok['token'] == current_token
            
            # Account name row
            buttons.append([
                InlineKeyboardButton(
                    text=f"{'🔹' if is_current else '▫️'} {tok['name'][:20]}",
                    callback_data=f"set_account_{i}"
                )
            ])
            
            # Action buttons row
            buttons.append([
                InlineKeyboardButton(
                    text=f"{status_emoji} {'Active' if is_active else 'Inactive'}",
                    callback_data=f"toggle_status_{i}"
                ),
                InlineKeyboardButton(
                    text="👁️ View",
                    callback_data=f"view_account_{i}"
                ),
                InlineKeyboardButton(
                    text="🗑️ Delete",
                    callback_data=f"confirm_delete_{i}"
                )
            ])

        buttons.append([
            InlineKeyboardButton(text="🔙 Back", callback_data="settings_menu")
        ])

        current_text = f"Current: {current_token[:10]}..." if current_token else "None"
        await callback_query.message.edit_text(
            f"👤 <b>Manage Accounts</b>\n\n"
            f"🔹 = Current account\n"
            f"Active accounts are used for multi-token functions.\n\n"
            f"<b>Current:</b> <code>{current_text}</code>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML"
        )
        return
    
    elif data.startswith("view_account_"):
        idx = int(data.split("_")[-1])
        tokens = get_tokens(user_id)
        if 0 <= idx < len(tokens):
            token = tokens[idx]["token"]
            info_card = get_info_card(user_id, token)
            if info_card:
                await callback_query.message.answer(
                    info_card,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
                await callback_query.answer("📱 Account info displayed below")
            else:
                await callback_query.answer("❌ No information card found for this account.", show_alert=True)
        else:
            await callback_query.answer("❌ Invalid account selected.")
        return
    
    elif data.startswith("confirm_delete_"):
        idx = int(data.split("_")[-1])
        tokens = get_tokens(user_id)
        if 0 <= idx < len(tokens):
            account_name = tokens[idx]["name"]
            buttons = [
                [
                    InlineKeyboardButton(text="🗑️ Yes, Delete", callback_data=f"delete_account_{idx}"),
                    InlineKeyboardButton(text="❌ Cancel", callback_data="manage_accounts")
                ]
            ]
            await callback_query.message.edit_text(
                f"⚠️ <b>Confirm Deletion</b>\n\n"
                f"Are you sure you want to delete account:\n"
                f"<code>{account_name}</code>?\n\n"
                f"This action cannot be undone.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                parse_mode="HTML"
            )
        else:
            await callback_query.answer("❌ Invalid account selected.")
        return
        
    elif data.startswith("toggle_status_"):
        idx = int(data.split("_")[-1])
        tokens = get_tokens(user_id)
        if 0 <= idx < len(tokens):
            token = tokens[idx]["token"]
            old_status = tokens[idx].get("active", True)
            toggle_token_status(user_id, token)
            new_status = not old_status
            
            await callback_query.answer(
                f"{'✅ Activated' if new_status else '❌ Deactivated'} {tokens[idx]['name']}"
            )
            
            # Refresh the manage accounts view
            await callback_query.message.edit_text("🔄 Updating...", parse_mode="HTML")
            
            # Trigger manage_accounts view refresh
            callback_query.data = "manage_accounts"
            await callback_handler(callback_query)
        else:
            await callback_query.answer("❌ Invalid account selected.")
        return

    elif data == "toggle_spam_filter":
        new_state = not get_spam_filter(user_id)
        set_spam_filter(user_id, new_state)
        await callback_query.answer(
            f"🛡️ Spam Filter {'Enabled ✅' if new_state else 'Disabled ❌'}"
        )
        
        # Refresh settings menu
        current_username = get_user_session(user_id)
        settings_text = "⚙️ <b>Settings Menu</b>\n\n"
        if current_username:
            settings_text += f"👤 Current profile: <code>{current_username}</code>\n\n"
        settings_text += "Choose an option below:"
        
        await callback_query.message.edit_text(
            settings_text,
            reply_markup=get_settings_menu(user_id),
            parse_mode="HTML"
        )
        return

    elif data.startswith("set_account_"):
        idx = int(data.split("_")[-1])
        tokens = get_tokens(user_id)
        if 0 <= idx < len(tokens):
            if not tokens[idx].get("active", True):
                await callback_query.answer("❌ This account is inactive. Activate it first.", show_alert=True)
                return
            set_current_account(user_id, tokens[idx]["token"])
            await callback_query.answer(f"✅ Set {tokens[idx]['name']} as current account")
            
            # Refresh the manage accounts view
            callback_query.data = "manage_accounts"
            await callback_handler(callback_query)
        else:
            await callback_query.answer("❌ Invalid account selected.")
        return

    elif data.startswith("delete_account_"):
        idx = int(data.split("_")[-1])
        tokens = get_tokens(user_id)
        if 0 <= idx < len(tokens):
            account_name = tokens[idx]["name"]
            delete_token(user_id, tokens[idx]["token"])
            await callback_query.message.edit_text(
                f"🗑️ <b>Account Deleted</b>\n\n"
                f"Account '<code>{account_name}</code>' has been deleted.",
                reply_markup=back_markup,
                parse_mode="HTML"
            )
        else:
            await callback_query.answer("❌ Invalid account selected.")
        return

    elif data == "back_to_menu":
        current_username = get_user_session(user_id)
        welcome_text = "🎯 <b>Meeff Bot Dashboard</b>\n\n"
        if current_username:
            welcome_text += f"👤 Logged in as: <code>{current_username}</code>\n\n"
        welcome_text += "Choose an option below to get started:"
        
        await callback_query.message.edit_text(
            welcome_text,
            reply_markup=start_markup,
            parse_mode="HTML"
        )
        return

    elif data == "start":
        if state.get("running", False):
            await callback_query.answer("⚠️ Requests are already running!")
        else:
            state["running"] = True
            state["total_added_friends"] = 0
            try:
                status_message = await callback_query.message.edit_text(
                    "🔄 <b>Initializing Requests</b>\n\n"
                    "Setting up friend requests...",
                    reply_markup=stop_markup,
                    parse_mode="HTML"
                )
                state["status_message_id"] = status_message.message_id
                state["pinned_message_id"] = status_message.message_id
                
                await bot.pin_chat_message(chat_id=user_id, message_id=state["status_message_id"])
                
                asyncio.create_task(run_requests(user_id, bot, TARGET_CHANNEL_ID))
                await callback_query.answer("🚀 Requests started!")
            except Exception as e:
                logging.error(f"Error while starting requests: {e}")
                await callback_query.message.edit_text(
                    "❌ <b>Failed to Start</b>\n\n"
                    "Failed to start requests. Please try again later.",
                    reply_markup=start_markup,
                    parse_mode="HTML"
                )
                state["running"] = False

    elif data == "start_all":
        if state.get("running", False):
            await callback_query.answer("⚠️ Another request is already running!")
        else:
            tokens = get_active_tokens(user_id)
            if not tokens:
                await callback_query.answer("❌ No active tokens found.", show_alert=True)
                return
        
            state["running"] = True
            state["total_added_friends"] = 0
        
            try:
                msg = await callback_query.message.edit_text(
                    f"🔄 <b>Starting Multi-Account Requests</b>\n\n"
                    f"📊 Active accounts: <code>{len(tokens)}</code>\n"
                    f"🚀 Initializing...",
                    reply_markup=stop_markup,
                    parse_mode="HTML"
                )
                state["status_message_id"] = msg.message_id
                state["pinned_message_id"] = msg.message_id
                
                await bot.pin_chat_message(chat_id=user_id, message_id=msg.message_id)
                
                asyncio.create_task(process_all_tokens(user_id, tokens, bot, TARGET_CHANNEL_ID))
                await callback_query.answer("🚀 Multi-account processing started!")
            except Exception as e:
                logging.error(f"Error starting all tokens: {e}")
                await callback_query.message.edit_text(
                    "❌ <b>Failed to Start</b>\n\n"
                    "Failed to start processing all tokens. Please try again later.",
                    reply_markup=start_markup,
                    parse_mode="HTML"
                )
                state["running"] = False

    elif data == "stop":
        if not state.get("running", False):
            await callback_query.answer("⚠️ Requests are not running!")
        else:
            state["running"] = False
            state["stopped"] = True  # Mark as user-stopped
            message_text = (
                f"⏹️ <b>Requests Stopped</b>\n\n"
                f"Total Added Friends: <code>{state.get('total_added_friends', 0)}</code>\n\n"
                f"Use the button below to start again."
            )
            await callback_query.message.edit_text(
                message_text,
                reply_markup=start_markup,
                parse_mode="HTML"
            )
            await callback_query.answer("⏹️ Requests stopped.")
            if state.get("pinned_message_id"):
                await bot.unpin_chat_message(chat_id=user_id, message_id=state["pinned_message_id"])
                state["pinned_message_id"] = None

    elif data == "all_countries":
        if state.get("running", False):
            await callback_query.answer("⚠️ Another process is already running!")
        else:
            state["running"] = True
            try:
                status_message = await callback_query.message.edit_text(
                    "🌍 <b>Starting All Countries Feature</b>\n\n"
                    "🔄 Initializing global search...",
                    reply_markup=stop_markup,
                    parse_mode="HTML"
                )
                state["status_message_id"] = status_message.message_id
                state["pinned_message_id"] = status_message.message_id
                state["stop_markup"] = stop_markup
                await bot.pin_chat_message(chat_id=user_id, message_id=status_message.message_id)
                asyncio.create_task(run_all_countries(user_id, state, bot, get_current_account))
                await callback_query.answer("🌍 All Countries feature started!")
            except Exception as e:
                logging.error(f"Error while starting All Countries feature: {e}")
                await callback_query.message.edit_text(
                    "❌ <b>Failed to Start</b>\n\n"
                    "Failed to start All Countries feature.",
                    reply_markup=start_markup,
                    parse_mode="HTML"
                )
                state["running"] = False

async def set_bot_commands():
    commands = [
        BotCommand(command="start", description="🎯 Start the bot"),
        BotCommand(command="settings", description="⚙️ Access bot settings"),
        BotCommand(command="lounge", description="💬 Send message in the lounge"),
        BotCommand(command="chatroom", description="📨 Send message in chatrooms"),
        BotCommand(command="send_lounge_all", description="🔄 Send lounge message to ALL accounts"),
        BotCommand(command="send_chat_all", description="🔄 Send chatroom message to ALL accounts"),
        BotCommand(command="invoke", description="🔧 Verify and remove disabled accounts"),
        BotCommand(command="skip", description="⏭️ Unsubscribe from all chatrooms"),
        BotCommand(command="signup", description="🆕 Create new Meeff account"),
        BotCommand(command="password", description="🔐 Enter password for temporary access")
    ]
    await bot.set_my_commands(commands)

async def main():
    await set_bot_commands()
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
