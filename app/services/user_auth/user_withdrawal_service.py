"""Transactional user withdrawal orchestration."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import AppError, api_error
from app.core.time import utcnow_naive
from app.models.notification import Notification
from app.models.mission import TERMINAL_STATUSES as MISSION_TERMINAL_STATUSES, Mission
from app.models.offer import Offer, OfferStatus
from app.models.proposal import Proposal, ProposalStatus
from app.models.refund import Refund, RefundStatus
from app.models.settlement import SettlementAccount
from app.models.user import (
    AuthPhoneVerification,
    User,
    UserFCMToken,
    UserWithdrawal,
    UserWithdrawalReasonQuestion,
)
from app.schemas.user import (
    UserWithdrawalReasonQuestionResponse,
    UserWithdrawalRequest,
    UserWithdrawalResponse,
)
from app.services.chat.chat_lifecycle import ChatLifecycle


# 탈퇴는 환불·지급 계좌와 전화번호를 하드 삭제한다. 그래서 차단 기준은 "거래가 진행 중이냐"가
# 아니라 "그 개인정보가 아직 필요하냐"이고, 그건 곧 애그리거트가 종결되지 않았다는 뜻이다.
# 차단 상태가 아니라 종결 상태를 열거한다. 상태가 새로 생겨도 기본값이 차단으로 잡히게 하기 위해서다.
WITHDRAWAL_TERMINAL_PROPOSAL_STATUSES = {
    ProposalStatus.ALL_COMPLETED,
    ProposalStatus.REFUNDED,
    ProposalStatus.CANCELLED,
    ProposalStatus.REPORTED,
}
WITHDRAWAL_TERMINAL_OFFER_STATUSES = {
    OfferStatus.ALL_COMPLETED,
    OfferStatus.REJECTED,
    OfferStatus.CANCELLED,
}
WITHDRAWAL_TERMINAL_REFUND_STATUSES = {
    RefundStatus.COMPLETED,
    RefundStatus.VOIDED,
}
# 돈이 개입된 적 없는 활동만 탈퇴 트랜잭션 안에서 종결시킨다. 꼬붕의 지원은 입금과 무관하다.
# HOLDING Proposal은 입금 여부를 알 수 없어 여기 들어가지 않는다. 자동 취소하면 REVIEW 환불을
# 남긴 채 계좌를 지우게 되고, 뒤늦게 입금이 확인돼도 보낼 곳이 없다.
WITHDRAWAL_AUTO_CANCEL_OFFER_STATUSES = {OfferStatus.WAITING}
WITHDRAWAL_PROPOSAL_BLOCK_ERRORS = {
    ProposalStatus.HOLDING: AppError.USER_WITHDRAWAL_BLOCKED_PROPOSAL_DEPOSIT,
    ProposalStatus.REFUND_PENDING: AppError.USER_WITHDRAWAL_BLOCKED_REFUND,
}



class UserWithdrawalService:
    @staticmethod
    def list_reason_questions(db: Session) -> list[UserWithdrawalReasonQuestionResponse]:
        questions = (
            db.query(UserWithdrawalReasonQuestion)
            .filter(UserWithdrawalReasonQuestion.is_active.is_(True))
            .order_by(UserWithdrawalReasonQuestion.display_order.asc(), UserWithdrawalReasonQuestion.id.asc())
            .all()
        )
        return [UserWithdrawalReasonQuestionResponse.model_validate(question) for question in questions]

    @staticmethod
    def withdraw_user(db: Session, user: User, request: UserWithdrawalRequest | None = None) -> UserWithdrawalResponse:
        fresh_user = db.query(User).filter(User.id == str(user.id), User.deleted.is_(False)).first()
        if fresh_user is None:
            raise api_error(AppError.USER_NOT_FOUND)

        user_id = str(fresh_user.id)
        block_error = UserWithdrawalService._find_blocking_error(db, user_id)
        if block_error is not None:
            raise api_error(block_error)

        reason_question = UserWithdrawalService._validate_request(db, request)
        # 커밋 뒤에는 인스턴스가 만료되므로 응답에 쓸 값을 미리 읽어 둔다.
        reason_question_id = reason_question.id
        reason_question_text = reason_question.question_text
        detail_reason = request.detail_reason if request is not None else None
        original_phone = fresh_user.phone
        withdrawn_at = utcnow_naive()
        try:
            UserWithdrawalService._auto_cancel_waiting_offers(db, user_id)
            withdrawal = UserWithdrawal(
                user_id=user_id,
                reason_question_id=reason_question_id,
                detail_reason=detail_reason,
                withdrawn_at=withdrawn_at,
            )
            db.add(withdrawal)
            if original_phone is not None:
                db.query(AuthPhoneVerification).filter(AuthPhoneVerification.phone == original_phone).delete(
                    synchronize_session=False
                )
            db.query(UserFCMToken).filter(UserFCMToken.user_id == user_id).delete(synchronize_session=False)
            db.query(SettlementAccount).filter(SettlementAccount.user_id == user_id).delete(
                synchronize_session=False
            )
            db.query(Notification).filter(Notification.user_id == user_id).delete(synchronize_session=False)
            fresh_user.withdraw(withdrawn_at)
            db.commit()
        except Exception:
            db.rollback()
            raise

        return UserWithdrawalResponse(
            id=withdrawal.id,
            user_id=user_id,
            reason_question_id=reason_question_id,
            reason_question_text=reason_question_text,
            detail_reason=detail_reason,
            withdrawn_at=withdrawn_at,
        )

    @staticmethod
    def _validate_request(
        db: Session, request: UserWithdrawalRequest | None
    ) -> UserWithdrawalReasonQuestion:
        """탈퇴 사유를 검증한다. 신고·분쟁과 같이 사유는 필수이고 기타 사유만 상세 사유를 요구한다."""
        if request is None:
            raise api_error(AppError.VALIDATION_ERROR, "reasonQuestionId")

        question = (
            db.query(UserWithdrawalReasonQuestion)
            .filter(
                UserWithdrawalReasonQuestion.id == request.reason_question_id,
                UserWithdrawalReasonQuestion.is_active.is_(True),
            )
            .one_or_none()
        )
        if question is None:
            raise api_error(AppError.VALIDATION_ERROR, "reasonQuestionId")
        if question.requires_detail and request.detail_reason is None:
            raise api_error(AppError.VALIDATION_ERROR, "detailReason")
        return question

    @staticmethod
    def _find_blocking_error(db: Session, user_id: str) -> AppError | None:
        """종결되지 않은 애그리거트를 찾아 첫 사유의 에러를 돌려준다. 없으면 탈퇴할 수 있다."""
        open_proposal_status = (
            db.query(Proposal.status)
            .filter(
                Proposal.orderer_id == user_id,
                Proposal.status.notin_(WITHDRAWAL_TERMINAL_PROPOSAL_STATUSES),
            )
            .first()
        )
        if open_proposal_status is not None:
            # 같은 "미결 요청"이라도 사용자가 기다리는 대상이 달라 문구를 나눈다.
            # REFUND_PENDING은 아래 Refund 검사와 같은 상황이므로 환불 문구로 보낸다.
            return WITHDRAWAL_PROPOSAL_BLOCK_ERRORS.get(
                open_proposal_status[0], AppError.USER_WITHDRAWAL_BLOCKED_PROPOSAL
            )

        has_open_offer = (
            db.query(Offer.id)
            .filter(
                Offer.runner_id == user_id,
                Offer.status.notin_(WITHDRAWAL_TERMINAL_OFFER_STATUSES),
                # 대기 지원은 탈퇴 트랜잭션 안에서 취소하므로 차단하지 않는다.
                Offer.status.notin_(WITHDRAWAL_AUTO_CANCEL_OFFER_STATUSES),
            )
            .first()
            is not None
        )
        if has_open_offer:
            return AppError.USER_WITHDRAWAL_BLOCKED_OFFER

        # 요청이 종결됐어도 환불이 남아 있으면 계좌를 지울 수 없다. REVIEW는 입금 여부를 모르는
        # 단계라 확정된 PENDING과 같이 차단한다. 대조 결과 입금이 없으면 VOIDED로 풀린다.
        has_open_refund = (
            db.query(Refund.id)
            .filter(
                Refund.orderer_id == user_id,
                Refund.status.notin_(WITHDRAWAL_TERMINAL_REFUND_STATUSES),
            )
            .first()
            is not None
        )
        if has_open_refund:
            return AppError.USER_WITHDRAWAL_BLOCKED_REFUND

        # 꼬붕 수행비 지급 축. 지급 완료는 PAID로 전이하므로 COMPLETED로 남아 종결인 경우는
        # 반려뿐이다. 행님 쪽 미결은 Proposal과 Refund가 이미 잡는다.
        has_open_payout = (
            db.query(Mission.id)
            .filter(
                Mission.runner_id == user_id,
                Mission.status.notin_(MISSION_TERMINAL_STATUSES),
                Mission.settlement_paid_at.is_(None),
                Mission.settlement_rejected_at.is_(None),
            )
            .first()
            is not None
        )
        if has_open_payout:
            return AppError.USER_WITHDRAWAL_BLOCKED_PAYOUT

        return None

    @staticmethod
    def _auto_cancel_waiting_offers(db: Session, user_id: str) -> None:
        """돈이 오간 적 없는 대기 지원만 탈퇴와 함께 취소한다."""
        waiting_offers = (
            db.query(Offer)
            .filter(
                Offer.runner_id == user_id,
                Offer.status.in_(WITHDRAWAL_AUTO_CANCEL_OFFER_STATUSES),
            )
            .all()
        )
        for offer in waiting_offers:
            offer.cancel()
            ChatLifecycle.on_offer_cancelled(db, offer)
