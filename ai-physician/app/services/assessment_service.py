"""Assessment storage and retrieval service."""

from app.models.assessment import TriageAssessment, DifferentialDiagnosis
from app.config.database import get_assessments_collection
from typing import Optional, List
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)


class AssessmentService:
    """Service for managing triage assessments."""

    async def create_assessment(self, assessment: TriageAssessment) -> str:
        """
        Create a new triage assessment.

        Args:
            assessment: TriageAssessment to store

        Returns:
            Assessment ID
        """
        assessment.created_at = datetime.utcnow()

        collection = await get_assessments_collection()
        await collection.insert_one(assessment.model_dump(by_alias=True))

        logger.info(
            f"Created assessment {assessment.assessment_id} for session {assessment.session_id}"
        )
        return assessment.assessment_id

    async def get_assessment(self, assessment_id: str) -> Optional[TriageAssessment]:
        """
        Get an assessment by ID.

        Args:
            assessment_id: Assessment identifier

        Returns:
            TriageAssessment or None if not found
        """
        collection = await get_assessments_collection()
        doc = await collection.find_one({"assessment_id": assessment_id})

        if doc:
            return TriageAssessment(**doc)
        return None

    async def get_user_assessments(
        self, user_id: str, limit: int = 10, offset: int = 0
    ) -> tuple[List[TriageAssessment], int]:
        """
        Get all assessments for a user.

        Args:
            user_id: User identifier
            limit: Maximum number of assessments to return
            offset: Number of assessments to skip

        Returns:
            Tuple of (assessments list, total count)
        """
        collection = await get_assessments_collection()

        # Get total count
        total = await collection.count_documents({"user_id": user_id})

        # Get paginated results
        cursor = (
            collection.find({"user_id": user_id})
            .sort("created_at", -1)
            .skip(offset)
            .limit(limit)
        )

        assessments = []
        async for doc in cursor:
            assessments.append(TriageAssessment(**doc))

        logger.info(
            f"Retrieved {len(assessments)} assessments for user {user_id} (total: {total})"
        )
        return assessments, total

    async def get_session_assessment(
        self, session_id: str
    ) -> Optional[TriageAssessment]:
        """
        Get assessment for a specific session.

        Args:
            session_id: Session identifier

        Returns:
            TriageAssessment or None if not found
        """
        collection = await get_assessments_collection()
        doc = await collection.find_one({"session_id": session_id})

        if doc:
            return TriageAssessment(**doc)
        return None


# Global service instance
_assessment_service: Optional[AssessmentService] = None


def get_assessment_service() -> AssessmentService:
    """Get or create AssessmentService instance."""
    global _assessment_service
    if _assessment_service is None:
        _assessment_service = AssessmentService()
    return _assessment_service
