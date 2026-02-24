"""
OmniAI - Authentication API
Steps 56-62: Registration, Login, JWT, Password Reset, Profiles, Google OAuth, Preferences
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime, timedelta
import bcrypt
import uuid
import secrets
import json
from jose import jwt, JWTError

from database import get_db
from utils.config import settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# ============================================================================
# JWT CONFIG
# ============================================================================

SECRET_KEY = getattr(settings, 'JWT_SECRET', 'change-this-to-a-long-random-string')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE = 24   # hours
REFRESH_TOKEN_EXPIRE = 30  # days

# Google OAuth Config
GOOGLE_CLIENT_ID = getattr(settings, 'GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = getattr(settings, 'GOOGLE_CLIENT_SECRET', '')
GOOGLE_REDIRECT_URI = getattr(settings, 'GOOGLE_REDIRECT_URI', 'http://localhost:8000/api/v1/auth/google/callback')


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        if '@' not in v or '.' not in v:
            raise ValueError('Invalid email address')
        return v.lower().strip()
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one number')
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UpdateProfileRequest(BaseModel):
    name: str = None
    avatar_url: str = None


class DeleteAccountRequest(BaseModel):
    password: str


# ============================================================================
# PASSWORD HASHING
# ============================================================================

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


# ============================================================================
# JWT TOKEN GENERATION
# ============================================================================

def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE)
    payload = {"sub": user_id, "exp": expire, "type": "access"}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE)
    payload = {"sub": user_id, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ============================================================================
# AUTH MIDDLEWARE HELPER
# ============================================================================

async def get_current_user(request: Request, db: AsyncSession) -> str:
    """Extract and verify user from Authorization header"""
    
    auth_header = request.headers.get("Authorization")
    
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = auth_header.split(" ")[1]
    payload = decode_token(token)
    
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    
    return payload["sub"]


# ============================================================================
# STEP 56: REGISTER
# ============================================================================

@router.post("/register")
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user"""
    
    # Check if email already exists
    result = await db.execute(
        text("SELECT id FROM users WHERE email = :email"),
        {"email": request.email}
    )
    if result.fetchone():
        raise HTTPException(status_code=409, detail="Email already registered")
    
    # Create user
    user_id = str(uuid.uuid4())
    hashed = hash_password(request.password)
    
    await db.execute(
        text("""
            INSERT INTO users (id, email, password_hash, name, created_at) 
            VALUES (:id, :email, :hash, :name, NOW())
        """),
        {
            "id": user_id,
            "email": request.email,
            "hash": hashed,
            "name": request.name or request.email.split('@')[0]
        }
    )
    await db.commit()
    
    # Generate tokens
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE * 3600
    )


# ============================================================================
# STEP 57: LOGIN
# ============================================================================

@router.post("/login")
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login and get JWT tokens"""
    
    result = await db.execute(
        text("SELECT id, password_hash FROM users WHERE email = :email"),
        {"email": request.email.lower().strip()}
    )
    user = result.fetchone()
    
    if not user or not verify_password(request.password, user[1]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    user_id = str(user[0])
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE * 3600
    )


# ============================================================================
# STEP 57: TOKEN REFRESH
# ============================================================================

@router.post("/refresh")
async def refresh_token(request: RefreshRequest):
    """Get new access token using refresh token"""
    
    payload = decode_token(request.refresh_token)
    
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")
    
    user_id = payload["sub"]
    new_access = create_access_token(user_id)
    
    return {
        "access_token": new_access,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE * 3600
    }


# ============================================================================
# STEP 58: FORGOT PASSWORD
# ============================================================================

@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Generate password reset token"""
    
    result = await db.execute(
        text("SELECT id FROM users WHERE email = :email"),
        {"email": request.email.lower().strip()}
    )
    user = result.fetchone()
    
    # Always return success to not reveal if email exists
    if not user:
        return {"message": "If that email is registered, a reset link has been sent."}
    
    reset_token = secrets.token_urlsafe(32)
    expires = datetime.utcnow() + timedelta(hours=1)
    
    await db.execute(
        text("""
            UPDATE users 
            SET reset_token = :token, reset_token_expires = :expires 
            WHERE id = :id
        """),
        {"token": reset_token, "expires": expires, "id": str(user[0])}
    )
    await db.commit()
    
    # TODO: Send email with reset link when Gmail is integrated
    # For now, return token directly (REMOVE IN PRODUCTION)
    return {
        "message": "If that email is registered, a reset link has been sent.",
    }


# ============================================================================
# STEP 58: RESET PASSWORD
# ============================================================================

@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Reset password using reset token"""
    
    if len(request.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    
    result = await db.execute(
        text("""
            SELECT id FROM users 
            WHERE reset_token = :token 
            AND reset_token_expires > NOW()
        """),
        {"token": request.token}
    )
    user = result.fetchone()
    
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    
    hashed = hash_password(request.new_password)
    await db.execute(
        text("""
            UPDATE users 
            SET password_hash = :hash, reset_token = NULL, reset_token_expires = NULL 
            WHERE id = :id
        """),
        {"hash": hashed, "id": str(user[0])}
    )
    await db.commit()
    
    return {"message": "Password reset successful"}


# ============================================================================
# STEP 59: GET PROFILE
# ============================================================================

@router.get("/me")
async def get_profile(request: Request, db: AsyncSession = Depends(get_db)):
    """Get current user profile"""
    
    user_id = await get_current_user(request, db)
    
    result = await db.execute(
        text("""
            SELECT id, email, name, avatar_url, preferences, created_at 
            FROM users WHERE id = :id
        """),
        {"id": user_id}
    )
    user = result.fetchone()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "id": str(user[0]),
        "email": user[1],
        "name": user[2],
        "avatar_url": user[3],
        "preferences": user[4] or {},
        "created_at": user[5].isoformat() if user[5] else None
    }


# ============================================================================
# STEP 59: UPDATE PROFILE
# ============================================================================

@router.put("/me")
async def update_profile(
    request: Request,
    body: UpdateProfileRequest,
    db: AsyncSession = Depends(get_db)
):
    """Update user profile"""
    
    user_id = await get_current_user(request, db)
    
    updates = []
    params = {"id": user_id}
    
    if body.name is not None:
        updates.append("name = :name")
        params["name"] = body.name
    if body.avatar_url is not None:
        updates.append("avatar_url = :avatar_url")
        params["avatar_url"] = body.avatar_url
    
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    await db.execute(
        text(f"UPDATE users SET {', '.join(updates)}, updated_at = NOW() WHERE id = :id"),
        params
    )
    await db.commit()
    
    return {"status": "updated"}


# ============================================================================
# STEP 59: CHANGE PASSWORD
# ============================================================================

@router.put("/me/password")
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """Change password (requires current password)"""
    
    user_id = await get_current_user(request, db)
    
    result = await db.execute(
        text("SELECT password_hash FROM users WHERE id = :id"),
        {"id": user_id}
    )
    user = result.fetchone()
    
    if not verify_password(body.current_password, user[0]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    
    hashed = hash_password(body.new_password)
    await db.execute(
        text("UPDATE users SET password_hash = :hash WHERE id = :id"),
        {"hash": hashed, "id": user_id}
    )
    await db.commit()
    
    return {"message": "Password changed successfully"}


# ============================================================================
# STEP 59: DELETE ACCOUNT
# ============================================================================

@router.delete("/me")
async def delete_account(
    request: Request,
    body: DeleteAccountRequest,
    db: AsyncSession = Depends(get_db)
):
    """Delete account and all user data"""
    
    user_id = await get_current_user(request, db)
    
    # Verify password
    result = await db.execute(
        text("SELECT password_hash FROM users WHERE id = :id"),
        {"id": user_id}
    )
    user = result.fetchone()
    
    if not verify_password(body.password, user[0]):
        raise HTTPException(status_code=400, detail="Incorrect password")
    
    # Delete all user data
    await db.execute(
        text("DELETE FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE user_id = :id)"),
        {"id": user_id}
    )
    await db.execute(text("DELETE FROM conversations WHERE user_id = :id"), {"id": user_id})
    await db.execute(text("DELETE FROM oauth_tokens WHERE user_id = :id"), {"id": user_id})
    await db.execute(text("DELETE FROM sessions WHERE user_id = :id"), {"id": user_id})
    await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    await db.commit()
    
    return {"message": "Account deleted"}


# ============================================================================
# STEP 60: GOOGLE OAUTH - INITIATE
# ============================================================================

@router.get("/google")
async def google_login():
    """Get Google OAuth consent screen URL"""
    
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")
    
    scope = "openid email profile"
    url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={GOOGLE_CLIENT_ID}&"
        f"redirect_uri={GOOGLE_REDIRECT_URI}&"
        f"response_type=code&"
        f"scope={scope}&"
        f"access_type=offline&"
        f"prompt=consent"
    )
    
    return {"auth_url": url}


# ============================================================================
# STEP 60: GOOGLE OAUTH - CALLBACK
# ============================================================================

@router.get("/google/callback")
async def google_callback(code: str, db: AsyncSession = Depends(get_db)):
    """Handle Google OAuth callback"""
    
    import httpx
    
    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code"
            }
        )
    
    if token_response.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to exchange code")
    
    token_data = token_response.json()
    
    # Get user info from Google
    async with httpx.AsyncClient() as client:
        userinfo = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"}
        )
    
    google_user = userinfo.json()
    email = google_user["email"]
    name = google_user.get("name", email.split("@")[0])
    
    # Check if user exists
    result = await db.execute(
        text("SELECT id FROM users WHERE email = :email"),
        {"email": email}
    )
    user = result.fetchone()
    
    if user:
        user_id = str(user[0])
    else:
        # Auto-create user from Google profile
        user_id = str(uuid.uuid4())
        await db.execute(
            text("""
                INSERT INTO users (id, email, name, avatar_url, google_id, created_at) 
                VALUES (:id, :email, :name, :avatar, :google_id, NOW())
            """),
            {
                "id": user_id,
                "email": email,
                "name": name,
                "avatar": google_user.get("picture"),
                "google_id": google_user.get("id")
            }
        )
        await db.commit()
    
    # Store OAuth tokens for future Gmail/Calendar access
    if "refresh_token" in token_data:
        await db.execute(
            text("""
                INSERT INTO oauth_tokens (user_id, provider, access_token, refresh_token, expires_at)
                VALUES (:uid, 'google', :at, :rt, NOW() + INTERVAL '1 hour')
                ON CONFLICT (user_id, provider) 
                DO UPDATE SET access_token = :at, refresh_token = :rt, expires_at = NOW() + INTERVAL '1 hour'
            """),
            {
                "uid": user_id,
                "at": token_data["access_token"],
                "rt": token_data.get("refresh_token", "")
            }
        )
        await db.commit()
    
    # Generate JWT tokens
    access_token = create_access_token(user_id)
    refresh_token_jwt = create_refresh_token(user_id)
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token_jwt,
        "user": {
            "id": user_id,
            "email": email,
            "name": name
        }
    }


# ============================================================================
# STEP 62: GET PREFERENCES
# ============================================================================

@router.get("/me/preferences")
async def get_preferences(request: Request, db: AsyncSession = Depends(get_db)):
    """Get user preferences"""
    
    user_id = await get_current_user(request, db)
    
    result = await db.execute(
        text("SELECT preferences FROM users WHERE id = :id"),
        {"id": user_id}
    )
    row = result.fetchone()
    
    return row[0] if row and row[0] else {
        "theme": "dark",
        "default_model": "auto",
        "language": "en",
        "notifications": True
    }


# ============================================================================
# STEP 62: UPDATE PREFERENCES
# ============================================================================

@router.put("/me/preferences")
async def update_preferences(
    request: Request,
    preferences: dict,
    db: AsyncSession = Depends(get_db)
):
    """Update user preferences (stored as JSONB)"""
    
    user_id = await get_current_user(request, db)
    
    await db.execute(
        text("UPDATE users SET preferences = :prefs::jsonb WHERE id = :id"),
        {"prefs": json.dumps(preferences), "id": user_id}
    )
    await db.commit()
    
    return {"status": "updated", "preferences": preferences}