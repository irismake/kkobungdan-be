"""Offer request and response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.offer import OfferStatus
from app.models.proposal import ProposalStatus
from app.services.chat.content import validate_message_content


class OfferCreate(BaseModel):
    """Request body for creating an offer."""

    proposal_id: int = Field(..., gt=0, validation_alias="proposalId")
    greeting: str = Field(
        ...,
        description="꼬붕의 첫 인사. 지원과 함께 채팅방에 꼬붕의 일반 채팅으로 저장된다. 공백만 있으면 안 되고 화면 글자 기준 500자 이하",
        examples=["안녕하세요! 근처에 있어서 바로 갈 수 있어요."],
    )

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @field_validator("greeting")
    @classmethod
    def validate_greeting(cls, value: str) -> str:
        return validate_message_content(value)


class OfferResponse(BaseModel):
    """Offer API response."""

    id: int
    proposal_id: int = Field(..., serialization_alias="proposalId")
    orderer_id: str = Field(..., serialization_alias="ordererId")
    orderer_name: str = Field(..., serialization_alias="ordererName")
    orderer_level: int = Field(..., serialization_alias="ordererLevel")
    runner_id: str = Field(..., serialization_alias="runnerId")
    runner_name: str = Field(..., serialization_alias="runnerName")
    runner_level: int = Field(..., serialization_alias="runnerLevel")
    status: OfferStatus
    accepted_at: datetime | None = Field(None, serialization_alias="acceptedAt")
    runner_confirmed_at: datetime | None = Field(None, serialization_alias="runnerConfirmedAt")
    orderer_confirmed_at: datetime | None = Field(None, serialization_alias="ordererConfirmedAt")
    disputed_at: datetime | None = Field(None, serialization_alias="disputedAt")
    resolved_at: datetime | None = Field(None, serialization_alias="resolvedAt")
    created_at: datetime = Field(..., serialization_alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class OfferSummaryResponse(BaseModel):
    """Offer response for proposal-scoped lookup."""

    id: int
    proposal_id: int = Field(..., serialization_alias="proposalId")
    orderer_id: str = Field(..., serialization_alias="ordererId")
    orderer_name: str = Field(..., serialization_alias="ordererName")
    orderer_level: int = Field(..., serialization_alias="ordererLevel")
    runner_id: str = Field(..., serialization_alias="runnerId")
    runner_name: str = Field(..., serialization_alias="runnerName")
    runner_level: int = Field(..., serialization_alias="runnerLevel")
    status: OfferStatus
    accepted_at: datetime | None = Field(None, serialization_alias="acceptedAt")
    runner_confirmed_at: datetime | None = Field(None, serialization_alias="runnerConfirmedAt")
    orderer_confirmed_at: datetime | None = Field(None, serialization_alias="ordererConfirmedAt")
    disputed_at: datetime | None = Field(None, serialization_alias="disputedAt")
    resolved_at: datetime | None = Field(None, serialization_alias="resolvedAt")
    created_at: datetime = Field(..., serialization_alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class OfferDetailResponse(BaseModel):
    """Offer detail response."""

    id: int
    proposal_id: int = Field(..., serialization_alias="proposalId")
    orderer_id: str = Field(..., serialization_alias="ordererId")
    orderer_name: str = Field(..., serialization_alias="ordererName")
    orderer_level: int = Field(..., serialization_alias="ordererLevel")
    runner_id: str = Field(..., serialization_alias="runnerId")
    runner_name: str = Field(..., serialization_alias="runnerName")
    runner_level: int = Field(..., serialization_alias="runnerLevel")
    status: OfferStatus
    accepted_at: datetime | None = Field(None, serialization_alias="acceptedAt")
    runner_confirmed_at: datetime | None = Field(None, serialization_alias="runnerConfirmedAt")
    orderer_confirmed_at: datetime | None = Field(None, serialization_alias="ordererConfirmedAt")
    disputed_at: datetime | None = Field(None, serialization_alias="disputedAt")
    resolved_at: datetime | None = Field(None, serialization_alias="resolvedAt")
    open_chat_url: str | None = Field(None, serialization_alias="openChatUrl")
    created_at: datetime = Field(..., serialization_alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class OfferAcceptResponse(BaseModel):
    """Response body for accepted offer orchestration."""

    proposal_id: int = Field(..., serialization_alias="proposalId")
    offer_id: int = Field(..., serialization_alias="offerId")
    proposal_status: ProposalStatus = Field(..., serialization_alias="proposalStatus")
    accepted_offer_status: OfferStatus = Field(..., serialization_alias="acceptedOfferStatus")
    rejected_offer_count: int = Field(..., serialization_alias="rejectedOfferCount")
    orderer_id: str = Field(..., serialization_alias="ordererId")
    orderer_name: str = Field(..., serialization_alias="ordererName")
    orderer_level: int = Field(..., serialization_alias="ordererLevel")
    runner_id: str = Field(..., serialization_alias="runnerId")
    runner_name: str = Field(..., serialization_alias="runnerName")
    runner_level: int = Field(..., serialization_alias="runnerLevel")
    accepted_at: datetime = Field(..., serialization_alias="acceptedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
