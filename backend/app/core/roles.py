"""
Central definitions for the free-text-turned-enum columns used across the
app (user roles, document status, message role).

These enums exist purely to give the DB layer a real type (Postgres native
ENUM via SQLAlchemy's Enum type) instead of an unconstrained String column.
The string VALUES below are unchanged from what the app already used as
plain string literals -- this is a representation change only, not a
behavior change. Do not alter these values without a coordinated DB
migration + frontend update.
"""
import enum


class Role(str, enum.Enum):
    SUPER_ADMIN = "Super Admin"
    KNOWLEDGE_MANAGER = "SAP Knowledge Manager"
    CONSULTANT = "SAP Consultant"
    END_USER = "End User"
    GUEST = "Guest"


class DocumentStatus(str, enum.Enum):
    PROCESSING = "processing"
    ACTIVE = "active"
    FAILED = "failed"


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
