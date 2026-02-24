"""
SQLAlchemy ORM Models for OmniAI
Maps Python classes to PostgreSQL tables
"""

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, ARRAY, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()


# ============================================================================
# User Model
# ============================================================================

class User(Base):
    """User account model"""
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    discoveries = relationship("UserCapabilityDiscovery", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, email={self.email})>"


# ============================================================================
# Capability Model
# ============================================================================

class Capability(Base):
    """Capability registry model"""
    __tablename__ = "capabilities"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False, index=True)
    subcategory = Column(String(100))
    description = Column(Text)
    
    # Metadata
    difficulty_level = Column(Integer, default=1)
    popularity_score = Column(Float, default=0.5)
    
    # Configuration
    example_prompts = Column(JSON, default=list)  # List of {"prompt": "...", "outcome": "..."}
    required_integrations = Column(ARRAY(String), default=list)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    discoveries = relationship("UserCapabilityDiscovery", back_populates="capability", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Capability(id={self.id}, name={self.name}, category={self.category})>"
    
    def to_dict(self):
        """Convert to dictionary for API response"""
        return {
            "id": str(self.id),
            "name": self.name,
            "category": self.category,
            "subcategory": self.subcategory,
            "description": self.description,
            "difficulty_level": self.difficulty_level,
            "popularity_score": float(self.popularity_score),
            "example_prompts": self.example_prompts or [],
            "required_integrations": self.required_integrations or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


# ============================================================================
# Conversation Model
# ============================================================================

class Conversation(Base):
    """Conversation model for chat sessions"""
    __tablename__ = "conversations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255))
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
    
    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at")
    
    def __repr__(self):
        return f"<Conversation(id={self.id}, user_id={self.user_id})>"
    
    def to_dict(self, include_messages=True):
        """Convert to dictionary for API response"""
        result = {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "title": self.title,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "message_count": len(self.messages) if self.messages else 0
        }
        
        if include_messages:
            result["messages"] = [msg.to_dict() for msg in self.messages]
        
        return result


# ============================================================================
# Message Model
# ============================================================================

class Message(Base):
    """Individual message in a conversation"""
    __tablename__ = "messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    
    role = Column(String(50), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    
    # Metadata
    model = Column(String(100))  # Which AI model was used
    latency_ms = Column(Integer)  # Response time in milliseconds
    
    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    
    def __repr__(self):
        return f"<Message(id={self.id}, role={self.role})>"
    
    def to_dict(self):
        """Convert to dictionary for API response"""
        return {
            "id": str(self.id),
            "conversation_id": str(self.conversation_id),
            "role": self.role,
            "content": self.content,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


# ============================================================================
# User Capability Discovery Model
# ============================================================================

class UserCapabilityDiscovery(Base):
    """Track user's capability discovery and usage"""
    __tablename__ = "user_capability_discovery"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    capability_id = Column(UUID(as_uuid=True), ForeignKey("capabilities.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Discovery tracking
    discovered_at = Column(DateTime, default=datetime.utcnow)
    discovery_method = Column(String(50))  # "browse", "search", "suggestion", "chat"
    
    # Usage tracking
    first_used_at = Column(DateTime)
    last_used_at = Column(DateTime)
    usage_count = Column(Integer, default=0)
    
    # User preferences
    bookmarked = Column(Boolean, default=False)
    
    # Relationships
    user = relationship("User", back_populates="discoveries")
    capability = relationship("Capability", back_populates="discoveries")
    
    def __repr__(self):
        return f"<UserCapabilityDiscovery(user_id={self.user_id}, capability_id={self.capability_id})>"
    
    def to_dict(self):
        """Convert to dictionary for API response"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "capability_id": str(self.capability_id),
            "discovered_at": self.discovered_at.isoformat() if self.discovered_at else None,
            "discovery_method": self.discovery_method,
            "first_used_at": self.first_used_at.isoformat() if self.first_used_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "usage_count": self.usage_count,
            "bookmarked": self.bookmarked
        }


# ============================================================================
# Action Log Model (for Data Moat)
# ============================================================================

class ActionLog(Base):
    """Log all user actions for pattern detection and ML"""
    __tablename__ = "action_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    
    action_type = Column(String(100), nullable=False, index=True)
    context = Column(JSON)  # Flexible JSON field for action context
    tool_used = Column(String(100))
    
    success = Column(Boolean)
    latency_ms = Column(Integer)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    def __repr__(self):
        return f"<ActionLog(id={self.id}, action_type={self.action_type})>"
    
    def to_dict(self):
        """Convert to dictionary for API response"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id) if self.user_id else None,
            "action_type": self.action_type,
            "context": self.context,
            "tool_used": self.tool_used,
            "success": self.success,
            "latency_ms": self.latency_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }