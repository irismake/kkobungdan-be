"""
Payment deadline checker task.

This module provides a background task to automatically cancel proposals
with expired payment deadlines (24 hours after creation).
"""
import logging
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.services.proposal.proposal_service import ProposalService


logger = logging.getLogger(__name__)


def check_and_cancel_expired_payment_proposals(db_factory: Callable[[], Session] = SessionLocal) -> int:
    """
    Check for HOLDING proposals with expired payment deadlines and cancel them.

    This function should be called periodically (e.g., every hour) by a scheduler.
    """
    db = db_factory()
    try:
        cancelled_count = ProposalService.cancel_expired_payment_proposals(db)

        if cancelled_count > 0:
            logger.info(
                f"Cancelled {cancelled_count} proposal(s) with expired payment deadlines "
                f"at {datetime.now(timezone.utc)}"
            )
        else:
            logger.debug(f"No expired proposals found at {datetime.now(timezone.utc)}")

        return cancelled_count

    except Exception as e:
        logger.error(f"Error checking expired proposals: {str(e)}", exc_info=True)
        raise
    finally:
        db.close()
