"""Configuration loader for the bot with validation."""
import os
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """
    Bot configuration from environment variables.
    
    All settings are validated on load to fail fast if misconfigured.
    """
    
    # Telegram Bot
    bot_token: str
    
    # Mercle SDK
    mercle_api_url: str
    mercle_api_key: str
    mercle_api_secret: str = ""
    mercle_app_id: str = ""
    
    # Verification Settings
    verification_timeout: int = 300  # 5 minutes default (more reasonable)
    action_on_timeout: str = "kick"  # kick or mute
    
    # Webhook (for production)
    webhook_path: str = "/webhook"
    webhook_url: str = ""
    
    # App URLs
    mercle_ios_url: str = "https://apps.apple.com/ng/app/mercle/id6751991316"
    mercle_android_url: str = "https://play.google.com/store/apps/details?id=com.mercle.app"
    
    # Bot behavior
    auto_delete_verification_messages: bool = True
    send_welcome_message: bool = True
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.verification_timeout < 30:
            raise ValueError("Verification timeout must be at least 30 seconds")
        
        if self.action_on_timeout not in ["kick", "mute"]:
            raise ValueError("action_on_timeout must be 'kick' or 'mute'")
    
    @classmethod
    def from_env(cls) -> "Config":
        """
        Load configuration from environment variables.
        
        Raises:
            RuntimeError: If required environment variables are missing
            ValueError: If configuration values are invalid
        """
        # Required fields
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
            mercle_api_key=mercle_api_key,
            mercle_api_secret=os.getenv("MERCLE_API_SECRET", ""),
            mercle_app_id=os.getenv("MERCLE_APP_ID", ""),
            verification_timeout=int(os.getenv("VERIFICATION_TIMEOUT", "300")),
            action_on_timeout=os.getenv("ACTION_ON_TIMEOUT", "kick"),
            webhook_path=os.getenv("WEBHOOK_PATH", "/webhook"),
            webhook_url=os.getenv("WEBHOOK_URL", ""),
            auto_delete_verification_messages=os.getenv("AUTO_DELETE_MESSAGES", "true").lower() == "true",
            send_welcome_message=os.getenv("SEND_WELCOME_MESSAGE", "true").lower() == "true",
        )
    
    @property
    def timeout_minutes(self) -> int:
        """Get timeout in minutes for display."""
        return self.verification_timeout // 60
    
    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return bool(self.webhook_url)
