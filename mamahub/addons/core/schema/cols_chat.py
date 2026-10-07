"""Chat module column identifiers aligned with DDL in ``db.ensure_chat_tables``."""
from __future__ import annotations
from addons.core.schema.tenant_tables import TenantTables

class ChatConversationsCols:
    TABLE = TenantTables.chat_conversations
    CONVERSATION_ID = 'CONVERSATION_ID'
    CONVERSATION_TYPE = 'CONVERSATION_TYPE'
    TITLE = 'TITLE'
    CREATED_BY = 'CREATED_BY'
    CREATED_DATE = 'CREATED_DATE'
    UPDATED_DATE = 'UPDATED_DATE'

class ChatMessagesCols:
    TABLE = TenantTables.chat_messages
    MESSAGE_ID = 'MESSAGE_ID'
    CONVERSATION_ID = 'CONVERSATION_ID'
    SENDER_USERNAME = 'SENDER_USERNAME'
    MESSAGE_TEXT = 'MESSAGE_TEXT'
    IMAGE_URL = 'IMAGE_URL'
    FILE_URL = 'FILE_URL'
    FILE_NAME = 'FILE_NAME'
    FILE_MIME = 'FILE_MIME'
    REPLIED_MESSAGE_ID = 'REPLIED_MESSAGE_ID'
    EDITED_FLAG = 'EDITED_FLAG'
    EDITED_DATE = 'EDITED_DATE'
    CREATED_DATE = 'CREATED_DATE'
    ACTIVE_FLAG = 'ACTIVE_FLAG'

class ChatParticipantsCols:
    TABLE = TenantTables.chat_participants
    CONVERSATION_ID = 'CONVERSATION_ID'
    USERNAME = 'USERNAME'
    JOINED_DATE = 'JOINED_DATE'
    LAST_READ_MSG_ID = 'LAST_READ_MSG_ID'
    LAST_SEEN_DATE = 'LAST_SEEN_DATE'
    ACTIVE_FLAG = 'ACTIVE_FLAG'
__all__ = ['ChatConversationsCols', 'ChatMessagesCols', 'ChatParticipantsCols']
