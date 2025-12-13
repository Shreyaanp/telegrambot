"""Mercle SDK integration client."""
import logging
from typing import Dict, Optional
import httpx

logger = logging.getLogger(__name__)


class MercleSDK:
    """Client for Mercle SDK API."""
    
    def __init__(self, api_url: str, api_key: str):
        """Initialize Mercle SDK client."""
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json",
        }
    
    async def create_session(self, metadata: Optional[Dict] = None) -> Dict:
        """
        Create a new verification session.
        
        Args:
            metadata: Optional metadata to attach to the session
            
        Returns:
            Dict with session_id, qr_data, base64_qr, deep_link (if available)
        """
        url = f"{self.api_url}/session/create"
        payload = {}
        if metadata:
            payload["metadata"] = metadata
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                
                logger.info(f"Created Mercle session: {data.get('session_id')}")
                return data
        except httpx.HTTPError as e:
            logger.error(f"Failed to create Mercle session: {e}")
            raise
    
    async def check_status(self, session_id: str) -> Dict:
        """
        Check verification session status.
        
        Args:
            session_id: The session ID to check
            
        Returns:
            Dict with status and localized_user_id (if approved)
        """
        url = f"{self.api_url}/session/status"
        params = {"session_id": session_id}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                
                logger.debug(f"Session {session_id} status: {data.get('status')}")
                return data
        except httpx.HTTPError as e:
            logger.error(f"Failed to check session status: {e}")
            raise
    
    async def get_user_info(self, localized_user_id: str) -> Dict:
        """
        Get user information from Mercle.
        
        Args:
            localized_user_id: The Mercle user ID
            
        Returns:
            Dict with user information
        """
        url = f"{self.api_url}/user/info"
        params = {"localized_user_id": localized_user_id}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to get user info: {e}")
            raise

