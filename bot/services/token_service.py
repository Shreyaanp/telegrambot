"""Token service - creates and validates short-lived deep link tokens."""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select

from database.db import db
from database.models import ConfigLinkToken, VerificationLinkToken, PendingJoinVerification


@dataclass(frozen=True)
class ConfigTokenPayload:
    token: str
    group_id: int
    admin_id: int


@dataclass(frozen=True)
class VerificationTokenPayload:
    token: str
    pending_id: int
    group_id: int
    telegram_id: int


class TokenService:
    """DB-backed tokens for config and verification deep links."""

    def __init__(self, cfg_ttl_minutes: int = 10, ver_ttl_minutes: int = 10):
        self.cfg_ttl_minutes = cfg_ttl_minutes
        self.ver_ttl_minutes = ver_ttl_minutes

    def _new_token(self) -> str:
        # Short, URL-safe token; callback_data limits don't apply to deep links.
        return secrets.token_urlsafe(18)

    async def create_config_token(self, group_id: int, admin_id: int) -> str:
        expires_at = datetime.utcnow() + timedelta(minutes=self.cfg_ttl_minutes)
        token = self._new_token()
        async with db.session() as session:
            session.add(
                ConfigLinkToken(
                    token=token,
                    group_id=group_id,
                    admin_id=admin_id,
                    expires_at=expires_at,
                )
            )
        return token

    async def consume_config_token(self, token: str, admin_id: int) -> Optional[ConfigTokenPayload]:
        now = datetime.utcnow()
        async with db.session() as session:
            result = await session.execute(select(ConfigLinkToken).where(ConfigLinkToken.token == token))
            row = result.scalar_one_or_none()
            if not row:
                return None
            if row.used_at is not None or row.expires_at < now:
                return None
            if row.admin_id != admin_id:
                return None
            row.used_at = now
            return ConfigTokenPayload(token=row.token, group_id=int(row.group_id), admin_id=int(row.admin_id))

    async def create_verification_token(self, pending_id: int, group_id: int, telegram_id: int, expires_at: datetime) -> str:
        token = self._new_token()
        async with db.session() as session:
            session.add(
                VerificationLinkToken(
                    token=token,
                    pending_id=pending_id,
                    group_id=group_id,
                    telegram_id=telegram_id,
                    expires_at=expires_at,
                )
            )
        return token

    async def get_verification_token(self, token: str) -> Optional[VerificationTokenPayload]:
        now = datetime.utcnow()
        async with db.session() as session:
            result = await session.execute(select(VerificationLinkToken).where(VerificationLinkToken.token == token))
            row = result.scalar_one_or_none()
            if not row:
                return None
            if row.expires_at < now:
                return None
            return VerificationTokenPayload(
                token=row.token,
                pending_id=int(row.pending_id),
                group_id=int(row.group_id),
                telegram_id=int(row.telegram_id),
            )

    async def mark_verification_token_used(self, token: str) -> None:
        now = datetime.utcnow()
        async with db.session() as session:
            result = await session.execute(select(VerificationLinkToken).where(VerificationLinkToken.token == token))
            row = result.scalar_one_or_none()
            if row and row.used_at is None:
                row.used_at = now

    async def mark_verification_tokens_used_for_pending(self, pending_id: int, telegram_id: int) -> None:
        """
        Mark any outstanding verification tokens for this pending/user as used.

        This supports the UX where users can open `/start ver_<token>` multiple times
        while still pending, but we only "consume" when they actually confirm.
        """
        now = datetime.utcnow()
        async with db.session() as session:
            result = await session.execute(
                select(VerificationLinkToken).where(
                    VerificationLinkToken.pending_id == pending_id,
                    VerificationLinkToken.telegram_id == telegram_id,
                    VerificationLinkToken.used_at.is_(None),
                )
            )
            for row in result.scalars().all():
                row.used_at = now

    async def get_pending(self, pending_id: int) -> Optional[PendingJoinVerification]:
        async with db.session() as session:
            result = await session.execute(select(PendingJoinVerification).where(PendingJoinVerification.id == pending_id))
            return result.scalar_one_or_none()
