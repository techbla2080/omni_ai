"""
Database Connection and Session Management
Handles PostgreSQL connections via SQLAlchemy
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from contextlib import asynccontextmanager
import os

# Database URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://omniai:omniai@localhost:5432/omniai"
)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=True,  # Set to False in production
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True  # Verify connections before using
)

# Create async session factory
async_session_factory = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


# ============================================================================
# Dependency for FastAPI
# ============================================================================

async def get_db() -> AsyncSession:
    """
    FastAPI dependency for database sessions
    
    Usage in FastAPI endpoint:
        @app.get("/users")
        async def get_users(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(User))
            return result.scalars().all()
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ============================================================================
# Context Manager (Alternative Usage)
# ============================================================================

@asynccontextmanager
async def get_db_session():
    """
    Context manager for database sessions
    
    Usage:
        async with get_db_session() as db:
            result = await db.execute(select(User))
            users = result.scalars().all()
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ============================================================================
# Database Initialization
# ============================================================================

async def init_db():
    """
    Initialize database tables
    
    Creates all tables defined in models.py if they don't exist
    """
    from models import Base
    
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
    
    print("✅ Database tables initialized")


async def drop_db():
    """
    Drop all database tables
    
    WARNING: This deletes all data!
    Only use in development
    """
    from backend.models import Base
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    print("⚠️  Database tables dropped")


# ============================================================================
# Health Check
# ============================================================================

async def check_db_connection() -> bool:
    """
    Check if database connection is healthy
    
    Returns:
        bool: True if connection works, False otherwise
    """
    try:
        async with async_session_factory() as session:
            await session.execute("SELECT 1")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False