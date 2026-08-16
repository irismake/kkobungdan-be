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
from app.core.firebase import get_notification_worker
from app.services.notification_outbox import pop_pending_notification_ids
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

        # No HTTP request context here, so flush the outbox directly instead of
        # handing the ids to BackgroundTasks like the routers do.
        notification_ids = pop_pending_notification_ids(db)
        if notification_ids:
            get_notification_worker().flush_pending(db_factory, notification_ids)

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


def send_pending_payment_reminders(db_factory: Callable[[], Session] = SessionLocal) -> int:
    """
    Remind orderers whose proposals are still awaiting payment 30 minutes after creation.

    This function should be called periodically (e.g., every 10 minutes) by a scheduler.
    """
    db = db_factory()
    try:
        reminded_count = ProposalService.send_payment_reminders(db)

        notification_ids = pop_pending_notification_ids(db)
        if notification_ids:
            get_notification_worker().flush_pending(db_factory, notification_ids)

        if reminded_count > 0:
            logger.info(
                f"Sent {reminded_count} payment reminder(s) at {datetime.now(timezone.utc)}"
            )

        return reminded_count

    except Exception as e:
        logger.error(f"Error sending payment reminders: {str(e)}", exc_info=True)
        raise
    finally:
        db.close()
