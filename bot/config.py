"""Configuration loader for the bot."""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """Bot configuration from environment variables."""
    
    # Telegram Bot
    bot_token: str
    
    # Mercle SDK
    mercle_api_url: str
    mercle_api_key: str
    mercle_api_secret: str
    mercle_app_id: str
    
    # Bot Settings
    verification_timeout: int = 30
    action_on_timeout: str = "mute"
    
    # Webhook (for production)
    webhook_path: str = "/webhook"
    webhook_url: str = ""
    
    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        bot_token = os.getenv("BOT_TOKEN")
        if not bot_token:
            raise RuntimeError("BOT_TOKEN environment variable is required")
        
        mercle_api_url = os.getenv("MERCLE_API_URL")
        if not mercle_api_url:
            raise RuntimeError("MERCLE_API_URL environment variable is required")
        
        mercle_api_key = os.getenv("MERCLE_API_KEY")
        if not mercle_api_key:
            raise RuntimeError("MERCLE_API_KEY environment variable is required")
        
        return cls(
            bot_token=bot_token,
            mercle_api_url=mercle_api_url,
            mercle_api_key=os.getenv("MERCLE_API_KEY", ""),
            mercle_api_secret=os.getenv("MERCLE_API_SECRET", ""),
            mercle_app_id=os.getenv("MERCLE_APP_ID", ""),
            verification_timeout=int(os.getenv("VERIFICATION_TIMEOUT", "30")),
            action_on_timeout=os.getenv("ACTION_ON_TIMEOUT", "mute"),
            webhook_path=os.getenv("WEBHOOK_PATH", "/webhook"),
            webhook_url=os.getenv("WEBHOOK_URL", ""),
        )

