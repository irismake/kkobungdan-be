"""Proposal report commands, moderation, and reason queries."""

from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, api_error
from app.core.time import utcnow_naive
from app.models.offer import Offer, OfferStatus
from app.models.proposal import Proposal, ProposalStatus
from app.models.proposal_report import ProposalReport, ProposalReportReasonQuestion, ProposalReportStatus
from app.schemas.admin import AdminProposalReportResponse
from app.schemas.common import PageResponse
from app.schemas.proposal_report import ProposalReportCreateRequest, ProposalReportReasonQuestionResponse, ProposalReportResponse
from app.services.admin.admin_user_display import WITHDRAWN_USER_NAME, admin_user_names
from app.services.chat.chat_lifecycle import ChatLifecycle


REPORTABLE_PROPOSAL_STATUSES = (ProposalStatus.POSTED, ProposalStatus.OFFERED)


class ProposalReportService:
    @staticmethod
    def list_reason_questions(db: Session) -> list[ProposalReportReasonQuestionResponse]:
        questions = (
            db.query(ProposalReportReasonQuestion)
            .filter(ProposalReportReasonQuestion.is_active.is_(True))
            .order_by(ProposalReportReasonQuestion.display_order.asc(), ProposalReportReasonQuestion.id.asc())
            .all()
        )
        return [ProposalReportReasonQuestionResponse.model_validate(question) for question in questions]

    @staticmethod
    def _get_proposal(db: Session, proposal_id: int) -> Proposal:
        proposal = db.query(Proposal).filter(Proposal.id == proposal_id).first()
        if proposal is None:
            raise api_error(AppError.PROPOSAL_NOT_FOUND, f"id: {proposal_id}")
        return proposal

    @staticmethod
    def _resolve_reason_question(
        db: Session,
        question_id: int,
        detail_reason: str | None,
    ) -> ProposalReportReasonQuestion:
        """신고 사유를 검증한다. 사유는 필수이고 기타 사유만 상세 사유를 요구한다. 분쟁·탈퇴와 같은 정책이다."""
        question = (
            db.query(ProposalReportReasonQuestion)
            .filter(
                ProposalReportReasonQuestion.id == question_id,
                ProposalReportReasonQuestion.is_active.is_(True),
            )
            .one_or_none()
        )
        if question is None:
            raise api_error(AppError.VALIDATION_ERROR, "reasonQuestionId")
        if question.requires_detail and detail_reason is None:
            raise api_error(AppError.VALIDATION_ERROR, "detailReason")
        return question

    @staticmethod
    def _question_text(db: Session, question_id: int) -> str:
        question = (
            db.query(ProposalReportReasonQuestion)
            .filter(ProposalReportReasonQuestion.id == question_id)
            .one()
        )
        return question.question_text

    @staticmethod
    def _reporter_names(db: Session, reporter_ids: list[str]) -> dict[str, str]:
        """신고자 이름을 한 번에 읽어 온다. 목록마다 N+1 조회를 하지 않기 위해서다."""
        return admin_user_names(db, reporter_ids)

    @staticmethod
    def _to_response(
        report: ProposalReport,
        question_text: str,
        proposal_status: ProposalStatus | None = None,
        reporter_name: str | None = None,
    ) -> ProposalReportResponse:
        return ProposalReportResponse(
            id=report.id,
            proposal_id=report.proposal_id,
            reporter_id=report.reporter_id,
            reporter_name=reporter_name,
            reason_question_id=report.reason_question_id,
            reason_question_text=question_text,
            detail_reason=report.detail_reason,
            status=report.status,
            created_at=report.created_at,
            reviewed_at=report.reviewed_at,
            proposal_status=proposal_status,
        )

    @staticmethod
    def _to_admin_response(
        report: ProposalReport,
        question_text: str,
        reporter_name: str,
        proposal_status: ProposalStatus | None = None,
    ) -> AdminProposalReportResponse:
        return AdminProposalReportResponse(
            **ProposalReportService._to_response(
                report,
                question_text,
                proposal_status=proposal_status,
                reporter_name=reporter_name,
            ).model_dump()
        )

    @staticmethod
    def create(db: Session, proposal_id: int, reporter_id: str, request: ProposalReportCreateRequest) -> ProposalReportResponse:
        proposal = ProposalReportService._get_proposal(db, proposal_id)
        if proposal.orderer_id == reporter_id:
            raise api_error(AppError.PROPOSAL_SELF_REPORT_NOT_ALLOWED)
        if proposal.status not in REPORTABLE_PROPOSAL_STATUSES:
            raise api_error(AppError.PROPOSAL_NOT_REPORTABLE, f"status: {proposal.status.value}")
        question = ProposalReportService._resolve_reason_question(db, request.reason_question_id, request.detail_reason)
        report = ProposalReport(
            proposal_id=proposal.id,
            reporter_id=reporter_id,
            reason_question_id=question.id,
            detail_reason=request.detail_reason,
            status=ProposalReportStatus.PENDING,
        )
        db.add(report)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise api_error(AppError.DUPLICATE_PROPOSAL_REPORT) from None
        db.refresh(report)
        return ProposalReportService._to_response(report, question.question_text)

    @staticmethod
    def list_reports(
        db: Session,
        report_status: ProposalReportStatus | None,
        page: int,
        size: int,
        proposal_id: int | None = None,
        keyword: str | None = None,
    ) -> PageResponse[AdminProposalReportResponse]:
        query = db.query(ProposalReport, ProposalReportReasonQuestion.question_text).join(
            ProposalReportReasonQuestion,
            ProposalReport.reason_question_id == ProposalReportReasonQuestion.id,
        )
        if report_status is not None:
            query = query.filter(ProposalReport.status == report_status)
        if proposal_id is not None:
            query = query.filter(ProposalReport.proposal_id == proposal_id)
        if keyword:
            conditions = [
                ProposalReport.reporter_id.like(f"%{keyword}%"),
                ProposalReport.detail_reason.like(f"%{keyword}%"),
                ProposalReportReasonQuestion.question_text.like(f"%{keyword}%"),
            ]
            numeric = None
            try:
                numeric = int(keyword)
            except ValueError:
                numeric = None
            if numeric is not None:
                conditions.append(ProposalReport.id == numeric)
                conditions.append(ProposalReport.proposal_id == numeric)
            query = query.filter(or_(*conditions))
        total = query.count()
        rows = (
            query.order_by(ProposalReport.created_at.asc(), ProposalReport.id.asc())
            .offset(page * size)
            .limit(size)
            .all()
        )
        proposal_statuses = ProposalReportService._proposal_statuses(db, [report.proposal_id for report, _ in rows])
        reporter_names = ProposalReportService._reporter_names(db, [report.reporter_id for report, _ in rows])
        return PageResponse.of(
            content=[
                ProposalReportService._to_admin_response(
                    report,
                    question_text,
                    reporter_name=reporter_names.get(report.reporter_id) or WITHDRAWN_USER_NAME,
                    proposal_status=proposal_statuses.get(report.proposal_id),
                )
                for report, question_text in rows
            ],
            page_number=page,
            page_size=size,
            total_elements=total,
        )

    @staticmethod
    def _proposal_statuses(db: Session, proposal_ids: list[int]) -> dict[int, ProposalStatus]:
        unique_ids = set(proposal_ids)
        if not unique_ids:
            return {}
        rows = db.query(Proposal.id, Proposal.status).filter(Proposal.id.in_(unique_ids)).all()
        return {row[0]: row[1] for row in rows}

    @staticmethod
    def _get_report(db: Session, report_id: int) -> ProposalReport:
        report = db.query(ProposalReport).filter(ProposalReport.id == report_id).first()
        if report is None:
            raise api_error(AppError.PROPOSAL_REPORT_NOT_FOUND, f"id: {report_id}")
        return report

    @staticmethod
    def _ensure_pending(report: ProposalReport) -> None:
        if report.status != ProposalReportStatus.PENDING:
            raise api_error(AppError.PROPOSAL_REPORT_NOT_REVIEWABLE, f"status: {report.status.value}")

    @staticmethod
    def accept(db: Session, report_id: int) -> AdminProposalReportResponse:
        report = ProposalReportService._get_report(db, report_id)
        ProposalReportService._ensure_pending(report)
        proposal = ProposalReportService._get_proposal(db, report.proposal_id)
        if proposal.status not in (*REPORTABLE_PROPOSAL_STATUSES, ProposalStatus.REPORTED):
            raise api_error(AppError.PROPOSAL_NOT_REPORTABLE, f"status: {proposal.status.value}")
        if proposal.status in REPORTABLE_PROPOSAL_STATUSES:
            proposal.status = ProposalStatus.REPORTED
            (
                db.query(Offer)
                .filter(Offer.proposal_id == proposal.id, Offer.status == OfferStatus.WAITING)
                .update({Offer.status: OfferStatus.REJECTED}, synchronize_session=False)
            )
            ChatLifecycle.on_report_accepted(db, proposal.id)
        report.status = ProposalReportStatus.ACCEPTED
        report.reviewed_at = utcnow_naive()
        db.commit()
        db.refresh(report)
        question_text = ProposalReportService._question_text(db, report.reason_question_id)
        reporter_names = ProposalReportService._reporter_names(db, [report.reporter_id])
        return ProposalReportService._to_admin_response(
            report,
            question_text,
            reporter_name=reporter_names.get(report.reporter_id) or WITHDRAWN_USER_NAME,
        )

    @staticmethod
    def reject(db: Session, report_id: int) -> AdminProposalReportResponse:
        report = ProposalReportService._get_report(db, report_id)
        ProposalReportService._ensure_pending(report)
        report.status = ProposalReportStatus.REJECTED
        report.reviewed_at = utcnow_naive()
        db.commit()
        db.refresh(report)
        question_text = ProposalReportService._question_text(db, report.reason_question_id)
        reporter_names = ProposalReportService._reporter_names(db, [report.reporter_id])
        return ProposalReportService._to_admin_response(
            report,
            question_text,
            reporter_name=reporter_names.get(report.reporter_id) or WITHDRAWN_USER_NAME,
        )
