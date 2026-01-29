"""Repository for managing model aliases."""

import logging
from typing import Any

from sqlalchemy.orm import Session

from orchestrator.db.models import Model, ModelAlias

logger = logging.getLogger(__name__)


class AliasRepository:
    """
    Repository for managing model alias mappings.

    Handles CRUD operations for the ModelAlias table and
    provides utilities for alias resolution.
    """

    def __init__(self, session: Session) -> None:
        """
        Initialize the repository.

        Args:
            session: SQLAlchemy session
        """
        self._session = session

    def get_canonical_id(self, alias: str) -> int | None:
        """
        Get the canonical model ID for an alias.

        Args:
            alias: Model alias to look up

        Returns:
            Canonical model ID or None if not found
        """
        result = (
            self._session.query(ModelAlias)
            .filter(ModelAlias.alias == alias)
            .first()
        )
        return result.canonical_id if result else None

    def get_canonical_model(self, alias: str) -> Model | None:
        """
        Get the canonical model for an alias.

        Args:
            alias: Model alias to look up

        Returns:
            Model instance or None
        """
        result = (
            self._session.query(ModelAlias)
            .filter(ModelAlias.alias == alias)
            .first()
        )
        return result.canonical_model if result else None

    def add_alias(
        self,
        alias: str,
        canonical_id: int,
        confidence: float = 1.0,
        reviewed: bool = False,
        source: str | None = None,
    ) -> ModelAlias:
        """
        Add a new alias mapping.

        Args:
            alias: The alias name
            canonical_id: ID of the canonical model
            confidence: Match confidence (0.0-1.0)
            reviewed: Whether the alias has been reviewed
            source: Source of the alias (e.g., 'lmsys', 'huggingface')

        Returns:
            Created ModelAlias instance
        """
        model_alias = ModelAlias(
            alias=alias,
            canonical_id=canonical_id,
            confidence=confidence,
            reviewed=reviewed,
            source=source,
        )
        self._session.add(model_alias)
        return model_alias

    def update_alias(
        self,
        alias: str,
        canonical_id: int | None = None,
        confidence: float | None = None,
        reviewed: bool | None = None,
    ) -> ModelAlias | None:
        """
        Update an existing alias.

        Args:
            alias: The alias to update
            canonical_id: New canonical ID (optional)
            confidence: New confidence (optional)
            reviewed: New reviewed status (optional)

        Returns:
            Updated alias or None if not found
        """
        model_alias = (
            self._session.query(ModelAlias)
            .filter(ModelAlias.alias == alias)
            .first()
        )
        
        if not model_alias:
            return None

        if canonical_id is not None:
            model_alias.canonical_id = canonical_id
        if confidence is not None:
            model_alias.confidence = confidence
        if reviewed is not None:
            model_alias.reviewed = reviewed

        return model_alias

    def remove_alias(self, alias: str) -> bool:
        """
        Remove an alias mapping.

        Args:
            alias: The alias to remove

        Returns:
            True if removed, False if not found
        """
        result = (
            self._session.query(ModelAlias)
            .filter(ModelAlias.alias == alias)
            .first()
        )
        
        if result:
            self._session.delete(result)
            return True
        return False

    def get_pending_reviews(self, limit: int = 100) -> list[ModelAlias]:
        """
        Get aliases pending human review.

        Args:
            limit: Maximum number to return

        Returns:
            List of unreviewed aliases
        """
        return (
            self._session.query(ModelAlias)
            .filter(ModelAlias.reviewed == False)  # noqa: E712
            .order_by(ModelAlias.confidence.desc())
            .limit(limit)
            .all()
        )

    def get_aliases_for_model(self, canonical_id: int) -> list[ModelAlias]:
        """
        Get all aliases for a canonical model.

        Args:
            canonical_id: ID of the canonical model

        Returns:
            List of aliases
        """
        return (
            self._session.query(ModelAlias)
            .filter(ModelAlias.canonical_id == canonical_id)
            .all()
        )

    def bulk_add_aliases(
        self,
        aliases: list[dict[str, Any]],
    ) -> int:
        """
        Add multiple aliases in bulk.

        Args:
            aliases: List of alias dicts with keys:
                - alias: str
                - canonical_id: int
                - confidence: float (optional)
                - reviewed: bool (optional)
                - source: str (optional)

        Returns:
            Number of aliases added
        """
        count = 0
        for alias_data in aliases:
            # Skip if alias already exists
            existing = self.get_canonical_id(alias_data["alias"])
            if existing:
                continue

            self.add_alias(
                alias=alias_data["alias"],
                canonical_id=alias_data["canonical_id"],
                confidence=alias_data.get("confidence", 1.0),
                reviewed=alias_data.get("reviewed", False),
                source=alias_data.get("source"),
            )
            count += 1

        return count

    def mark_reviewed(self, alias: str, approved: bool = True) -> bool:
        """
        Mark an alias as reviewed.

        Args:
            alias: The alias to mark
            approved: Whether the match was approved

        Returns:
            True if updated, False if not found
        """
        result = self.update_alias(
            alias=alias,
            reviewed=True,
            confidence=1.0 if approved else 0.0,
        )
        return result is not None

    def get_all_aliases_map(self) -> dict[str, int]:
        """
        Get a mapping of all aliases to canonical IDs.

        Returns:
            Dict of {alias: canonical_id}
        """
        aliases = self._session.query(ModelAlias).all()
        return {a.alias: a.canonical_id for a in aliases}
