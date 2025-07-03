from pymongo import MongoClient
import datetime

# MongoDB connection
client = MongoClient("mongodb+srv://irexanon:xUf7PCf9cvMHy8g6@rexdb.d9rwo.mongodb.net/?retryWrites=true&w=majority&appName=RexDB")
db = client.meeff_bot

# Username-based authentication system
USER_SESSIONS = {}  # {telegram_user_id: username}

def set_user_session(telegram_user_id, username):
    """Set the current username session for a telegram user"""
    USER_SESSIONS[telegram_user_id] = username

def get_user_session(telegram_user_id):
    """Get the current username session for a telegram user"""
    return USER_SESSIONS.get(telegram_user_id)

def clear_user_session(telegram_user_id):
    """Clear the current username session"""
    if telegram_user_id in USER_SESSIONS:
        del USER_SESSIONS[telegram_user_id]

def create_username_collection(username):
    """Create a new collection for a username"""
    collection_name = f"user_{username}"
    user_db = db[collection_name]
    
    # Initialize with basic structure
    if user_db.count_documents({}) == 0:
        user_db.insert_one({"type": "metadata", "created_at": datetime.datetime.utcnow(), "username": username})
        user_db.insert_one({"type": "tokens", "items": []})
        user_db.insert_one({"type": "settings", "current_token": None, "spam_filter": False})
        user_db.insert_one({"type": "sent_records", "data": {}})
        user_db.insert_one({"type": "filters", "data": {}})
        user_db.insert_one({"type": "info_cards", "data": {}})
    return True

def username_exists(username):
    """Check if a username collection already exists"""
    collection_name = f"user_{username}"
    return collection_name in db.list_collection_names()

def list_usernames():
    """List all available usernames"""
    collection_names = db.list_collection_names()
    usernames = []
    for name in collection_names:
        if name.startswith("user_") and name != "user_":
            username = name[5:]  # Remove "user_" prefix
            usernames.append(username)
    return usernames

# Helper function to get a user's collection based on session
def _get_user_collection(telegram_user_id):
    """Get the collection for the current user session"""
    username = get_user_session(telegram_user_id)
    if not username:
        return None
    
    collection_name = f"user_{username}"
    if collection_name not in db.list_collection_names():
        return None
    
    return db[collection_name]

# Helper function to ensure collection exists with basic structure
def _ensure_user_collection_exists(telegram_user_id):
    """Make sure user collection exists with default documents"""
    user_db = _get_user_collection(telegram_user_id)
    if not user_db:
        return False

    # Check if the collection is empty
    if user_db.count_documents({}) == 0:
        username = get_user_session(telegram_user_id)
        # Initialize with basic structure
        user_db.insert_one({"type": "metadata", "created_at": datetime.datetime.utcnow(), "username": username})
        user_db.insert_one({"type": "tokens", "items": []})
        user_db.insert_one({"type": "settings", "current_token": None, "spam_filter": False})
        user_db.insert_one({"type": "sent_records", "data": {}})
        user_db.insert_one({"type": "filters", "data": {}})
        user_db.insert_one({"type": "info_cards", "data": {}})
    return True

# Info card functions
def set_info_card(telegram_user_id, token, info_text, email=None):
    """Store info card for a token"""
    if not _ensure_user_collection_exists(telegram_user_id):
        return False
    
    user_db = _get_user_collection(telegram_user_id)
    user_db.update_one(
        {"type": "info_cards"},
        {"$set": {f"data.{token}": {"info": info_text, "email": email, "updated_at": datetime.datetime.utcnow()}}},
        upsert=True
    )
    return True

def get_info_card(telegram_user_id, token):
    """Get info card for a token"""
    if not _ensure_user_collection_exists(telegram_user_id):
        return None
    
    user_db = _get_user_collection(telegram_user_id)
    cards_doc = user_db.find_one({"type": "info_cards"})
    if cards_doc and "data" in cards_doc and token in cards_doc["data"]:
        return cards_doc["data"][token].get("info")
    return None

# Set or update token for a user
def set_token(telegram_user_id, token, meeff_user_id, email=None, filters=None):
    if not _ensure_user_collection_exists(telegram_user_id):
        return False
    
    user_db = _get_user_collection(telegram_user_id)

    # Get current tokens
    tokens_doc = user_db.find_one({"type": "tokens"})
    tokens = tokens_doc.get("items", []) if tokens_doc else []

    # Check if token exists
    token_exists = False
    for i, t in enumerate(tokens):
        if t.get("token") == token:
            # Update existing token
            tokens[i]["name"] = meeff_user_id
            if email:
                tokens[i]["email"] = email
            if filters:
                tokens[i]["filters"] = filters
            # Keep existing active status or default to True
            if "active" not in tokens[i]:
                tokens[i]["active"] = True
            token_exists = True
            break

    # Add new token if not exists
    if not token_exists:
        token_data = {"token": token, "name": meeff_user_id, "active": True}
        if email:
            token_data["email"] = email
        if filters:
            token_data["filters"] = filters
        tokens.append(token_data)

    # Update tokens in database
    user_db.update_one(
        {"type": "tokens"},
        {"$set": {"items": tokens}},
        upsert=True
    )
    return True

# Add new functions to toggle token active status
def toggle_token_status(telegram_user_id, token):
    if not _ensure_user_collection_exists(telegram_user_id):
        return False
    
    user_db = _get_user_collection(telegram_user_id)

    # Get current tokens
    tokens_doc = user_db.find_one({"type": "tokens"})
    if not tokens_doc:
        return False

    tokens = tokens_doc.get("items", [])
    status_changed = False

    # Find and toggle the token's active status
    for i, t in enumerate(tokens):
        if t.get("token") == token:
            current_status = t.get("active", True)
            tokens[i]["active"] = not current_status
            status_changed = True
            break

    if status_changed:
        # Update tokens in database
        user_db.update_one(
            {"type": "tokens"},
            {"$set": {"items": tokens}}
        )
        return True
    return False

def set_account_active(telegram_user_id, token, active_status):
    """Set account active/inactive status"""
    if not _ensure_user_collection_exists(telegram_user_id):
        return False
    
    user_db = _get_user_collection(telegram_user_id)
    tokens_doc = user_db.find_one({"type": "tokens"})
    if not tokens_doc:
        return False

    tokens = tokens_doc.get("items", [])
    for i, t in enumerate(tokens):
        if t.get("token") == token:
            tokens[i]["active"] = active_status
            break

    user_db.update_one(
        {"type": "tokens"},
        {"$set": {"items": tokens}}
    )
    return True

# Add function to get active tokens only
def get_active_tokens(telegram_user_id):
    if not _ensure_user_collection_exists(telegram_user_id):
        return []
    
    user_db = _get_user_collection(telegram_user_id)

    tokens_doc = user_db.find_one({"type": "tokens"})
    if not tokens_doc:
        return []

    # Filter tokens that are active (or where active field doesn't exist)
    return [t for t in tokens_doc.get("items", []) if t.get("active", True)]

# Add function to get token status
def get_token_status(telegram_user_id, token):
    if not _ensure_user_collection_exists(telegram_user_id):
        return None
    
    user_db = _get_user_collection(telegram_user_id)

    tokens_doc = user_db.find_one({"type": "tokens"})
    if tokens_doc:
        for t in tokens_doc.get("items", []):
            if t.get("token") == token:
                return t.get("active", True)
    return None

# Get all tokens for a user
def get_tokens(telegram_user_id):
    if not _ensure_user_collection_exists(telegram_user_id):
        return []
    
    user_db = _get_user_collection(telegram_user_id)
    tokens_doc = user_db.find_one({"type": "tokens"})
    return tokens_doc.get("items", []) if tokens_doc else []

def get_all_tokens(telegram_user_id):
    """Alias for get_tokens for compatibility"""
    return get_tokens(telegram_user_id)

# List all tokens in the database
def list_tokens():
    result = []
    # Get all collection names
    collection_names = db.list_collection_names()

    # Filter for user collections
    user_collections = [name for name in collection_names if name.startswith("user_")]

    for collection_name in user_collections:
        username = collection_name.split("_", 1)[1]  # Extract username from collection name
        user_db = db[collection_name]

        tokens_doc = user_db.find_one({"type": "tokens"})
        if tokens_doc:
            for token in tokens_doc.get("items", []):
                result.append({
                    "username": username,
                    "token": token.get("token"),
                    "name": token.get("name")
                })

    return result

# Set current account token for a user
def set_current_account(telegram_user_id, token):
    if not _ensure_user_collection_exists(telegram_user_id):
        return False
    
    user_db = _get_user_collection(telegram_user_id)

    user_db.update_one(
        {"type": "settings"},
        {"$set": {"current_token": token}},
        upsert=True
    )
    return True

# Get current account token for a user
def get_current_account(telegram_user_id):
    if not _ensure_user_collection_exists(telegram_user_id):
        return None
    
    user_db = _get_user_collection(telegram_user_id)

    settings = user_db.find_one({"type": "settings"})
    return settings.get("current_token") if settings else None

# Delete a token for a user
def delete_token(telegram_user_id, token):
    if not _ensure_user_collection_exists(telegram_user_id):
        return False
    
    user_db = _get_user_collection(telegram_user_id)

    # Get current tokens and filter out the one to delete
    tokens_doc = user_db.find_one({"type": "tokens"})
    if tokens_doc:
        tokens = tokens_doc.get("items", [])
        updated_tokens = [t for t in tokens if t.get("token") != token]

        # Update tokens in database
        user_db.update_one(
            {"type": "tokens"},
            {"$set": {"items": updated_tokens}}
        )

    # Check if this was the current token
    settings = user_db.find_one({"type": "settings"})
    if settings and settings.get("current_token") == token:
        user_db.update_one(
            {"type": "settings"},
            {"$set": {"current_token": None}}
        )
    
    # Also delete info card
    user_db.update_one(
        {"type": "info_cards"},
        {"$unset": {f"data.{token}": ""}}
    )
    return True

# Set filters for a specific user and token
def set_user_filters(telegram_user_id, token, filters):
    if not _ensure_user_collection_exists(telegram_user_id):
        return False
    
    user_db = _get_user_collection(telegram_user_id)

    # Get current tokens
    tokens_doc = user_db.find_one({"type": "tokens"})
    tokens = tokens_doc.get("items", []) if tokens_doc else []

    # Update the token's filters
    for i, t in enumerate(tokens):
        if t.get("token") == token:
            tokens[i]["filters"] = filters
            break

    # Update tokens in database
    user_db.update_one(
        {"type": "tokens"},
        {"$set": {"items": tokens}}
    )
    return True

# Get filters for a specific user and token
def get_user_filters(telegram_user_id, token):
    if not _ensure_user_collection_exists(telegram_user_id):
        return None
    
    user_db = _get_user_collection(telegram_user_id)

    tokens_doc = user_db.find_one({"type": "tokens"})
    if tokens_doc:
        for t in tokens_doc.get("items", []):
            if t.get("token") == token:
                return t.get("filters")
    return None

# Enable or disable spam filter for a user
def set_spam_filter(telegram_user_id, status: bool):
    if not _ensure_user_collection_exists(telegram_user_id):
        return False
    
    user_db = _get_user_collection(telegram_user_id)

    user_db.update_one(
        {"type": "settings"},
        {"$set": {"spam_filter": status}},
        upsert=True
    )
    return True

# Get spam filter status for a user
def get_spam_filter(telegram_user_id: int) -> bool:
    if not _ensure_user_collection_exists(telegram_user_id):
        return False
    
    user_db = _get_user_collection(telegram_user_id)

    settings = user_db.find_one({"type": "settings"})
    return settings.get("spam_filter", False) if settings else False

# Get all target IDs for a category for a user
def get_already_sent_ids(telegram_user_id, category):
    """Fetch all target_ids for a given user and category."""
    if not _ensure_user_collection_exists(telegram_user_id):
        return set()
    
    user_db = _get_user_collection(telegram_user_id)
    records_doc = user_db.find_one({"type": "sent_records"}, {"data." + category: 1})
    if records_doc and "data" in records_doc and category in records_doc["data"]:
        return set(records_doc["data"][category])
    return set()

# Record that we've sent a message/request to a target
def add_sent_id(telegram_user_id, category, target_id):
    """Record a target_id as sent for a user and category."""
    if not _ensure_user_collection_exists(telegram_user_id):
        return False
    
    user_db = _get_user_collection(telegram_user_id)
    user_db.update_one(
        {"type": "sent_records"},
        {"$addToSet": {f"data.{category}": target_id}},
        upsert=True
    )
    return True

# Check if we've already sent to this target
async def is_already_sent(telegram_user_id, category, target_id, bulk=False):
    """Check if target_id(s) have already been recorded as sent"""
    if not _ensure_user_collection_exists(telegram_user_id):
        return False if not bulk else set()
    
    user_db = _get_user_collection(telegram_user_id)
    
    if not bulk:
        # Single ID check
        records_doc = user_db.find_one({"type": "sent_records"}, {f"data.{category}": 1})
        if records_doc and "data" in records_doc and category in records_doc["data"]:
            sent_ids = records_doc["data"][category]
            if isinstance(sent_ids, (list, set)):
                return target_id in sent_ids
        return False
    else:
        # Bulk check - returns set of existing IDs
        records_doc = user_db.find_one({"type": "sent_records"}, {f"data.{category}": 1})
        if records_doc and "data" in records_doc and category in records_doc["data"]:
            existing_ids = records_doc["data"][category]
            if isinstance(existing_ids, (list, set)):
                return set(existing_ids)
        return set()

async def bulk_add_sent_ids(telegram_user_id, category, target_ids):
    """Record multiple target_ids as sent for a user and category"""
    if not target_ids:
        return False
    
    if not _ensure_user_collection_exists(telegram_user_id):
        return False
        
    user_db = _get_user_collection(telegram_user_id)
    user_db.update_one(
        {"type": "sent_records"},
        {"$addToSet": {f"data.{category}": {"$each": list(target_ids)}}},
        upsert=True
    )
    return True

async def has_valid_access(telegram_user_id):
    """Check if user has valid access to use the bot"""
    username = get_user_session(telegram_user_id)
    if not username:
        return False
    
    collection_name = f"user_{username}"
    if collection_name not in db.list_collection_names():
        return False
    
    user_db = db[collection_name]
    # Check if collection exists and has basic structure
    if user_db.count_documents({"type": "metadata"}) == 0:
        return False
    return True

def get_message_delay(telegram_user_id):
    # Return the delay in seconds for this user
    # You could store this in your database
    return 2  # Default 2 second delay

def transfer_user_data(from_telegram_id, to_telegram_id):
    """Transfer all user data from one telegram user to another"""
    from_username = get_user_session(from_telegram_id)
    if not from_username:
        return False
    
    # For now, we'll just transfer the session
    # In a real implementation, you might want to copy the entire collection
    set_user_session(to_telegram_id, from_username)
    clear_user_session(from_telegram_id)
    return True

# Legacy functions for backward compatibility
def has_interacted(telegram_user_id, action_type, user_token):
    """Legacy function - checks a separate interactions collection"""
    interaction_record = db.interactions.find_one({
        "user_id": telegram_user_id,
        "action_type": action_type,
        "user_token": user_token
    })
    return interaction_record is not None

def log_interaction(telegram_user_id, action_type, user_token):
    """Legacy function - logs to a separate interactions collection"""
    interaction_data = {
        "user_id": telegram_user_id,
        "action_type": action_type,
        "user_token": user_token,
        "timestamp": datetime.datetime.utcnow()
    }
    db.interactions.insert_one(interaction_data)