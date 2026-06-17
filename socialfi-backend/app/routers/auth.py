from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
from google.oauth2 import id_token
from google.auth.transport import requests

from app.db.session import get_db
from app.db.models import Creator
from app.config import settings
from app.core.security import create_access_token, decode_access_token

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()

# Schemas
class GoogleAuthRequest(BaseModel):
    id_token: str

class LinkWalletRequest(BaseModel):
    wallet_address: str

# Dependencies
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: AsyncSession = Depends(get_db)):
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    user_id = payload.get("user_id")
    result = await db.execute(select(Creator).where(Creator.id == user_id))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user

@router.post("/google")
async def auth_google(req: GoogleAuthRequest, db: AsyncSession = Depends(get_db)):
    try:
        # 1. Check for the development bypass token
        if req.id_token == "dev-test-token":
            id_info = {
                "sub": "mock_google_id_12345",
                "email": "devuser@test.com",
                "name": "Dev Tester"
            }
        else:
            # 2. Fall back to real Google token verification if it's not the bypass token
            id_info = id_token.verify_oauth2_token(
                req.id_token, requests.Request(), settings.google_client_id
            )
        
        google_id = id_info.get("sub")
        email = id_info.get("email")
        display_name = id_info.get("name")
        
        if not google_id:
            raise HTTPException(status_code=400, detail="Invalid Google token")

        # Upsert user
        result = await db.execute(select(Creator).where(Creator.google_id == google_id))
        user = result.scalars().first()
        
        if not user:
            user = Creator(
                google_id=google_id,
                display_name=display_name,
                youtube_channel_id=f"temp_{google_id}", 
                wallet_address=f"temp_wallet_{google_id}",
                tier=0,
                base_price_usdc=0,
                k_value=0
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

        is_creator = user.token_contract is not None
        token = create_access_token({"user_id": user.id, "is_creator": is_creator})
        
        return {
            "access_token": token,
            "user_id": user.id,
            "is_creator": is_creator
        }

    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token")

@router.post("/link-wallet")
async def link_wallet(req: LinkWalletRequest, current_user: Creator = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    current_user.wallet_address = req.wallet_address.lower()
    await db.commit()
    return {"status": "success", "wallet_address": current_user.wallet_address}

@router.get("/me")
async def get_me(current_user: Creator = Depends(get_current_user)):
    is_creator = current_user.token_contract is not None
    
    profile = {
        "user_id": current_user.id,
        "display_name": current_user.display_name,
        "email": "user@example.com", # Mocked as it's not saved in DB per spec
        "wallet_address": current_user.wallet_address if not current_user.wallet_address.startswith("temp_wallet_") else None,
        "is_creator": is_creator,
        "creator_profile": None
    }
    
    if is_creator:
        tier_names = {0: "Micro", 1: "Mid", 2: "Star"}
        profile["creator_profile"] = {
            "token_contract": current_user.token_contract,
            "tier": current_user.tier,
            "tier_name": tier_names.get(current_user.tier, "Unknown"),
            "base_price_usdc": float(current_user.base_price_usdc),
            "youtube_channel_id": current_user.youtube_channel_id,
            "subscriber_count": current_user.subscriber_count
        }
        
    return profile
