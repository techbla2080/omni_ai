"""
Configuration Management
Loads settings from .env file
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Application settings from environment variables"""
    
    # API Settings
    API_HOST: str = Field(default="0.0.0.0")
    API_PORT: int = Field(default=8000)
    DEBUG: bool = Field(default=True)
    
    # LLM Model
    MODEL_NAME: str = Field(default="llama3.2:1b")
    
    # JWT
    JWT_SECRET: str = Field(default="change-me")
    JWT_ALGORITHM: str = Field(default="HS256")
    
    # Database
    DATABASE_URL: str = Field(default="postgresql://localhost/omniai")
    REDIS_URL: str = Field(default="redis://localhost:6379")
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434")
    
    # API Keys (NEW!)
    SERPER_API_KEY: Optional[str] = Field(default=None)  # ← ADDED
    OPENAI_API_KEY: Optional[str] = Field(default=None)  # ← ADDED (for Step 35)
    BRAVE_API_KEY: Optional[str] = Field(default=None)   # ← ADDED (optional)
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # ← ADDED: Allows extra fields without errors


# Create global settings instance
settings = Settings()


# Test function to display settings
def print_settings():
    """Print current configuration"""
    print("=" * 50)
    print("🔧 OmniAI Configuration")
    print("=" * 50)
    print(f"API Host: {settings.API_HOST}")
    print(f"API Port: {settings.API_PORT}")
    print(f"Debug Mode: {settings.DEBUG}")
    print(f"LLM Model: {settings.MODEL_NAME}")
    print(f"JWT Algorithm: {settings.JWT_ALGORITHM}")
    print(f"Serper API Key: {'✅ Set' if settings.SERPER_API_KEY else '❌ Not Set'}")  # ← ADDED
    print(f"OpenAI API Key: {'✅ Set' if settings.OPENAI_API_KEY else '❌ Not Set'}")  # ← ADDED
    print("=" * 50)


if __name__ == "__main__":
    # Test the configuration
    print_settings()