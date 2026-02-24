"""
Context Manager with Redis Caching
Provides conversation memory and context for AI responses
"""

import redis
import json
from typing import List, Dict, Optional
from datetime import datetime


class ContextManager:
    """Manages conversation context using Redis cache"""
    
    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                decode_responses=True
            )
            # Test connection
            self.redis_client.ping()
            self.connected = True
            print("✅ Redis connected!")
        except Exception as e:
            print(f"⚠️ Redis connection failed: {e}")
            self.redis_client = None
            self.connected = False
        
        self.cache_ttl = 3600  # 1 hour
        self.max_context_messages = 10  # Last 10 messages for context
    
    def _get_conversation_key(self, conversation_id: str) -> str:
        """Generate Redis key for conversation"""
        return f"conv:{conversation_id}:messages"
    
    def _get_user_key(self, user_id: str) -> str:
        """Generate Redis key for user context"""
        return f"user:{user_id}:context"
    
    def add_message(self, conversation_id: str, role: str, content: str) -> bool:
        """Add a message to conversation cache"""
        if not self.connected:
            return False
        
        try:
            key = self._get_conversation_key(conversation_id)
            message = json.dumps({
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Add to list
            self.redis_client.rpush(key, message)
            
            # Keep only last N messages
            self.redis_client.ltrim(key, -self.max_context_messages, -1)
            
            # Set expiry
            self.redis_client.expire(key, self.cache_ttl)
            
            return True
        except Exception as e:
            print(f"❌ Error adding message to cache: {e}")
            return False
    
    def get_conversation_context(self, conversation_id: str) -> List[Dict]:
        """Get recent messages for context"""
        if not self.connected:
            return []
        
        try:
            key = self._get_conversation_key(conversation_id)
            messages_json = self.redis_client.lrange(key, 0, -1)
            
            messages = []
            for msg_json in messages_json:
                messages.append(json.loads(msg_json))
            
            return messages
        except Exception as e:
            print(f"❌ Error getting context: {e}")
            return []
    
    def format_context_for_llm(self, conversation_id: str) -> str:
        """Format conversation context for LLM prompt"""
        messages = self.get_conversation_context(conversation_id)
        
        if not messages:
            return ""
        
        context_parts = ["Previous conversation:"]
        for msg in messages[-self.max_context_messages:]:
            role = "User" if msg["role"] == "user" else "Assistant"
            context_parts.append(f"{role}: {msg['content']}")
        
        return "\n".join(context_parts)
    
    def save_user_info(self, user_id: str, key: str, value: str) -> bool:
        """Save user-specific information"""
        if not self.connected:
            return False
        
        try:
            redis_key = self._get_user_key(user_id)
            self.redis_client.hset(redis_key, key, value)
            self.redis_client.expire(redis_key, self.cache_ttl * 24)  # 24 hours
            return True
        except Exception as e:
            print(f"❌ Error saving user info: {e}")
            return False
    
    def get_user_info(self, user_id: str, key: str) -> Optional[str]:
        """Get user-specific information"""
        if not self.connected:
            return None
        
        try:
            redis_key = self._get_user_key(user_id)
            return self.redis_client.hget(redis_key, key)
        except Exception as e:
            print(f"❌ Error getting user info: {e}")
            return None
    
    def clear_conversation(self, conversation_id: str) -> bool:
        """Clear conversation cache"""
        if not self.connected:
            return False
        
        try:
            key = self._get_conversation_key(conversation_id)
            self.redis_client.delete(key)
            return True
        except Exception as e:
            print(f"❌ Error clearing conversation: {e}")
            return False
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        if not self.connected:
            return {"connected": False}
        
        try:
            info = self.redis_client.info()
            return {
                "connected": True,
                "used_memory": info.get("used_memory_human", "unknown"),
                "total_keys": self.redis_client.dbsize(),
                "uptime_seconds": info.get("uptime_in_seconds", 0)
            }
        except Exception as e:
            return {"connected": False, "error": str(e)}


# Global instance
context_manager = ContextManager()