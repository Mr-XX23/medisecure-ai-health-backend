"""Session management service."""

from app.models.session import SymptomSession, Message, SymptomsData, TriageData
from app.models.triage import SessionStatus
from app.config.database import get_sessions_collection
from typing import Optional, List
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)


class SessionService:
    """Service for managing symptom check sessions."""

    async def create_session(self, user_id: str, user_email: str) -> SymptomSession:
        """
        Create a new symptom check session.

        Args:
            user_id: User identifier from JWT
            user_email: User email from JWT

        Returns:
            Created SymptomSession
        """
        session = SymptomSession(
            session_id=str(uuid.uuid4()),
            user_id=user_id,
            user_email=user_email,
            status=SessionStatus.ACTIVE,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            message_count=0,
            messages=[],
            symptoms_collected=SymptomsData(),
            triage_result=None,
        )

        collection = await get_sessions_collection()
        await collection.insert_one(session.model_dump(by_alias=True))

        logger.info(f"Created session {session.session_id} for user {user_id}")
        return session

    async def get_session(self, session_id: str) -> Optional[SymptomSession]:
        """
        Get a session by ID.

        Args:
            session_id: Session identifier

        Returns:
            SymptomSession or None if not found
        """
        collection = await get_sessions_collection()
        doc = await collection.find_one({"session_id": session_id})

        if doc:
            return SymptomSession(**doc)
        return None

    async def update_session(self, session: SymptomSession) -> bool:
        """
        Update an existing session.

        Args:
            session: SymptomSession to update

        Returns:
            True if successful
        """
        session.updated_at = datetime.utcnow()

        collection = await get_sessions_collection()
        result = await collection.update_one(
            {"session_id": session.session_id},
            {"$set": session.model_dump(by_alias=True)},
        )

        if result.modified_count > 0:
            logger.info(f"Updated session {session.session_id}")
            return True
        return False

    async def add_message(self, session_id: str, role: str, content: str) -> bool:
        """
        Add a message to a session.

        Args:
            session_id: Session identifier
            role: Message role ("user" or "assistant")
            content: Message content

        Returns:
            True if successful
        """
        message = Message(role=role, content=content, timestamp=datetime.utcnow())

        collection = await get_sessions_collection()
        result = await collection.update_one(
            {"session_id": session_id},
            {
                "$push": {"messages": message.model_dump()},
                "$inc": {"message_count": 1},
                "$set": {"updated_at": datetime.utcnow()},
            },
        )

        return result.modified_count > 0

    async def get_user_sessions(
        self, user_id: str, limit: int = 10, offset: int = 0
    ) -> List[SymptomSession]:
        """
        Get all sessions for a user.

        Args:
            user_id: User identifier
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip

        Returns:
            List of SymptomSession
        """
        collection = await get_sessions_collection()
        cursor = (
            collection.find({"user_id": user_id})
            .sort("created_at", -1)
            .skip(offset)
            .limit(limit)
        )

        sessions = []
        async for doc in cursor:
            sessions.append(SymptomSession(**doc))

        return sessions

    async def complete_session(self, session_id: str) -> bool:
        """
        Mark a session as completed.

        Args:
            session_id: Session identifier

        Returns:
            True if successful
        """
        collection = await get_sessions_collection()
        result = await collection.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "status": SessionStatus.COMPLETED,
                    "completed_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                }
            },
        )

        if result.modified_count > 0:
            logger.info(f"Completed session {session_id}")
            return True
        return False


# Global service instance
_session_service: SessionService = None


def get_session_service() -> SessionService:
    """Get or create SessionService instance."""
    global _session_service
    if _session_service is None:
        _session_service = SessionService()
    return _session_service
