"""
Admin System
- Superadmin = creator, highest authority (one person only)
- Supports cross-platform identity linking (Telegram ↔ Discord ↔ etc.)
- All significant actions require superadmin approval
"""

import json
import os
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

ADMIN_DB_PATH = "data/admin_db.json"


def _load_db() -> dict:
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(ADMIN_DB_PATH):
        return {"superadmin": None, "identities": {}, "pending_approvals": []}
    with open(ADMIN_DB_PATH, "r") as f:
        return json.load(f)


def _save_db(db: dict):
    os.makedirs("data", exist_ok=True)
    with open(ADMIN_DB_PATH, "w") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


class AdminSystem:
    """
    Manages superadmin authority and cross-platform identity.
    Superadmin is the singular creator — treated as the supreme authority.
    Agent will ALWAYS ask superadmin before taking major autonomous actions.
    """

    def __init__(self):
        self.db = _load_db()
        self._setup_superadmin()

    def _setup_superadmin(self):
        """Initialize superadmin from env if not set yet."""
        env_id = os.getenv("SUPERADMIN_TELEGRAM_ID")
        if env_id and not self.db["superadmin"]:
            self.db["superadmin"] = {
                "telegram_id": str(env_id),
                "discord_id": os.getenv("SUPERADMIN_DISCORD_ID", None),
                "name": os.getenv("SUPERADMIN_NAME", "Creator"),
                "registered_at": datetime.utcnow().isoformat(),
                "platforms": {}
            }
            # Build identity map
            sa = self.db["superadmin"]
            if sa["telegram_id"]:
                self.db["identities"][f"telegram:{sa['telegram_id']}"] = "superadmin"
            if sa["discord_id"]:
                self.db["identities"][f"discord:{sa['discord_id']}"] = "superadmin"
            _save_db(self.db)
            logger.info(f"Superadmin registered: {sa['name']} (Telegram: {sa['telegram_id']})")

    # ─────────────────────────────────────────
    # Identity Resolution
    # ─────────────────────────────────────────

    def resolve_identity(self, platform: str, user_id: str) -> Optional[str]:
        """
        Given platform + user_id, return who this person is.
        Returns: 'superadmin' | 'user:<linked_id>' | None
        """
        key = f"{platform}:{user_id}"
        return self.db["identities"].get(key)

    def is_superadmin(self, platform: str, user_id: str) -> bool:
        """Check if this platform+user_id is the superadmin."""
        return self.resolve_identity(platform, user_id) == "superadmin"

    def get_superadmin_info(self) -> Optional[dict]:
        return self.db.get("superadmin")

    def get_superadmin_telegram_id(self) -> Optional[str]:
        sa = self.db.get("superadmin")
        return sa["telegram_id"] if sa else None

    # ─────────────────────────────────────────
    # Cross-Platform Identity Linking
    # ─────────────────────────────────────────

    def link_identity(self, platform: str, user_id: str, linked_to: str, linked_by_platform: str, linked_by_id: str) -> dict:
        """
        Link a user across platforms. Only superadmin can link.
        Example: link discord:12345 → same person as telegram:67890
        """
        if not self.is_superadmin(linked_by_platform, linked_by_id):
            return {"ok": False, "reason": "Only superadmin can link identities."}

        key = f"{platform}:{user_id}"
        self.db["identities"][key] = linked_to
        _save_db(self.db)
        logger.info(f"Identity linked: {key} → {linked_to}")
        return {"ok": True, "linked": key, "to": linked_to}

    def link_own_identity(self, new_platform: str, new_user_id: str, from_platform: str, from_user_id: str) -> dict:
        """Superadmin links their own new platform account."""
        if not self.is_superadmin(from_platform, from_user_id):
            return {"ok": False, "reason": "Only superadmin can do this."}

        key = f"{new_platform}:{new_user_id}"
        self.db["identities"][key] = "superadmin"
        sa = self.db["superadmin"]
        sa["platforms"][new_platform] = new_user_id
        _save_db(self.db)
        logger.info(f"Superadmin added platform: {key}")
        return {"ok": True, "message": f"Linked {key} as superadmin."}

    # ─────────────────────────────────────────
    # Approval System
    # ─────────────────────────────────────────

    def create_approval_request(self, action_id: str, description: str, payload: dict) -> dict:
        """Agent creates an approval request before doing something significant."""
        req = {
            "id": action_id,
            "description": description,
            "payload": payload,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "resolved_at": None
        }
        self.db["pending_approvals"].append(req)
        _save_db(self.db)
        return req

    def approve(self, action_id: str, platform: str, user_id: str) -> dict:
        if not self.is_superadmin(platform, user_id):
            return {"ok": False, "reason": "Only superadmin can approve."}
        return self._resolve(action_id, "approved")

    def deny(self, action_id: str, platform: str, user_id: str) -> dict:
        if not self.is_superadmin(platform, user_id):
            return {"ok": False, "reason": "Only superadmin can deny."}
        return self._resolve(action_id, "denied")

    def _resolve(self, action_id: str, status: str) -> dict:
        for req in self.db["pending_approvals"]:
            if req["id"] == action_id and req["status"] == "pending":
                req["status"] = status
                req["resolved_at"] = datetime.utcnow().isoformat()
                _save_db(self.db)
                return {"ok": True, "action_id": action_id, "status": status}
        return {"ok": False, "reason": "Request not found or already resolved."}

    def get_pending_approvals(self) -> list:
        return [r for r in self.db["pending_approvals"] if r["status"] == "pending"]

    def get_approval(self, action_id: str) -> Optional[dict]:
        for req in self.db["pending_approvals"]:
            if req["id"] == action_id:
                return req
        return None

    # ─────────────────────────────────────────
    # Status
    # ─────────────────────────────────────────

    def status(self) -> dict:
        sa = self.db.get("superadmin")
        return {
            "superadmin_set": sa is not None,
            "superadmin_name": sa["name"] if sa else None,
            "superadmin_telegram": sa["telegram_id"] if sa else None,
            "total_identities": len(self.db["identities"]),
            "pending_approvals": len(self.get_pending_approvals())
        }
