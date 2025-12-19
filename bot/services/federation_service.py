"""Federation service - shared banlists across multiple groups."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from database.db import db
from database.models import Federation, FederationBan, Group


class FederationService:
    async def create_federation(self, *, name: str, owner_id: int) -> int:
        name = (name or "").strip()
        if not name:
            raise ValueError("name is required")
        if len(name) > 64:
            raise ValueError("name is too long (max 64 chars)")

        now = datetime.utcnow()
        fed = Federation(name=name, owner_id=int(owner_id), created_at=now, updated_at=now)
        async with db.session() as session:
            session.add(fed)
            await session.flush()
            return int(fed.id)

    async def get_federation(self, federation_id: int) -> Federation | None:
        async with db.session() as session:
            return await session.get(Federation, int(federation_id))

    async def get_group_federation_id(self, group_id: int) -> int | None:
        async with db.session() as session:
            group = await session.get(Group, int(group_id))
            if not group:
                return None
            fid = getattr(group, "federation_id", None)
            return int(fid) if fid is not None else None

    async def set_group_federation(self, *, group_id: int, federation_id: int | None, actor_id: int) -> None:
        """
        Attach/detach a group from a federation.

        Security: attaching to a federation requires actor_id == federation.owner_id.
        Detaching requires the group to already be in that federation and actor to be the owner.
        """
        async with db.session() as session:
            group = await session.get(Group, int(group_id))
            if not group:
                group = Group(group_id=int(group_id))
                session.add(group)
                await session.flush()

            current = getattr(group, "federation_id", None)
            if federation_id is None:
                if current is None:
                    return
                fed = await session.get(Federation, int(current))
                if not fed or int(getattr(fed, "owner_id", 0) or 0) != int(actor_id):
                    raise PermissionError("only the federation owner can detach a group")
                group.federation_id = None
                return

            fed = await session.get(Federation, int(federation_id))
            if not fed:
                raise ValueError("federation not found")
            if int(getattr(fed, "owner_id", 0) or 0) != int(actor_id):
                raise PermissionError("only the federation owner can attach groups")
            group.federation_id = int(federation_id)

    async def list_federation_groups(self, federation_id: int) -> list[dict[str, Any]]:
        async with db.session() as session:
            result = await session.execute(select(Group).where(Group.federation_id == int(federation_id)))
            rows = list(result.scalars().all())
        out = []
        for g in rows:
            out.append({"group_id": int(g.group_id), "group_name": getattr(g, "group_name", None)})
        return out

    async def is_banned(self, *, federation_id: int, telegram_id: int) -> bool:
        async with db.session() as session:
            result = await session.execute(
                select(FederationBan.id).where(
                    FederationBan.federation_id == int(federation_id),
                    FederationBan.telegram_id == int(telegram_id),
                )
            )
            return result.scalar_one_or_none() is not None

    async def ban_user(
        self,
        *,
        federation_id: int,
        telegram_id: int,
        banned_by: int,
        reason: str | None = None,
    ) -> bool:
        now = datetime.utcnow()
        reason = (reason or "").strip() or None
        async with db.session() as session:
            # idempotent
            existing = await session.execute(
                select(FederationBan).where(
                    FederationBan.federation_id == int(federation_id),
                    FederationBan.telegram_id == int(telegram_id),
                )
            )
            row = existing.scalar_one_or_none()
            if row:
                if reason:
                    row.reason = reason
                row.banned_by = int(banned_by)
                row.banned_at = now
                return False
            session.add(
                FederationBan(
                    federation_id=int(federation_id),
                    telegram_id=int(telegram_id),
                    reason=reason,
                    banned_by=int(banned_by),
                    banned_at=now,
                )
            )
            return True

    async def unban_user(self, *, federation_id: int, telegram_id: int) -> bool:
        async with db.session() as session:
            existing = await session.execute(
                select(FederationBan).where(
                    FederationBan.federation_id == int(federation_id),
                    FederationBan.telegram_id == int(telegram_id),
                )
            )
            row = existing.scalar_one_or_none()
            if not row:
                return False
            await session.delete(row)
            return True

