"""Version 1 API router composition."""

from fastapi import APIRouter

from app.api.v1.admin.admin_auth_router import router as admin_auth_router
from app.api.v1.admin.admin_outbox_router import router as admin_outbox_router
from app.api.v1.admin.admin_router import router as admin_router
from app.api.v1.chat.chat_router import router as chat_router
from app.api.v1.dispute.dispute_evidence_router import router as dispute_evidence_router
from app.api.v1.dispute.dispute_survey_router import router as dispute_survey_router
from app.api.v1.notification.notification_router import router as notification_router
from app.api.v1.offer.offer_router import router as offer_router
from app.api.v1.proposal.proposal_report_router import router as proposal_report_router
from app.api.v1.proposal.proposal_router import router as proposal_router
from app.api.v1.settlement.settlement_router import router as settlement_router
from app.api.v1.terms_agreement.terms_router import router as terms_router
from app.api.v1.user_auth.auth_router import router as auth_router
from app.api.v1.user_auth.user_router import router as user_router
from app.realtime.ws_router import router as chat_ws_router


api_router = APIRouter(prefix="/v1")
api_router.include_router(auth_router)
api_router.include_router(user_router)
api_router.include_router(terms_router)
api_router.include_router(dispute_evidence_router)
api_router.include_router(dispute_survey_router)
api_router.include_router(proposal_report_router)
api_router.include_router(proposal_router)
api_router.include_router(offer_router)
api_router.include_router(chat_router)
api_router.include_router(chat_ws_router)
api_router.include_router(settlement_router)
api_router.include_router(notification_router)
api_router.include_router(admin_auth_router)
api_router.include_router(admin_router)
api_router.include_router(admin_outbox_router)
