"""Chat room API endpoints (docs/design-docs/chat-architecture.md "API")."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError
from app.core.openapi import CHAT_MESSAGE_LIST_EXAMPLE, CHAT_ROOM_DETAIL_EXAMPLE, error_responses, success_response
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.chat import ChatMessageListResponse, ChatRoomDetailResponse
from app.schemas.common import ApiResponse
from app.services.chat.chat_message_service import ChatMessageService
from app.services.chat.chat_room_service import ChatRoomService


router = APIRouter(prefix="/chat-room", tags=["채팅"])

ROOM_ERRORS = error_responses(
    AppError.INVALID_TOKEN,
    AppError.VALIDATION_ERROR,
    AppError.FORBIDDEN,
    AppError.CHAT_ROOM_NOT_FOUND,
)


@router.get(
    "/{room_id}",
    response_model=ApiResponse[ChatRoomDetailResponse],
    status_code=status.HTTP_200_OK,
    summary="채팅방 상세 조회",
    description="채팅방 참여자(행님, 꼬붕)가 채팅방 상태와 요청·지원 상태, 읽음 위치를 조회합니다. 참여자가 아니면 403입니다.",
    responses={200: success_response(CHAT_ROOM_DETAIL_EXAMPLE), **ROOM_ERRORS},
)
def get_chat_room(
    room_id: int = Path(..., gt=0, description="채팅방 ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[ChatRoomDetailResponse]:
    return ApiResponse(success=True, data=ChatRoomService.get_detail(db, room_id, current_user.id), message="Success")


@router.get(
    "/{room_id}/messages",
    response_model=ApiResponse[ChatMessageListResponse],
    status_code=status.HTTP_200_OK,
    summary="채팅 조회",
    description="채팅방의 최근 채팅 30개를 저장 순서(seq 오름차순)로 조회합니다. 시스템 채팅의 내용은 보는 사람에 맞는 문구입니다.",
    responses={200: success_response(CHAT_MESSAGE_LIST_EXAMPLE), **ROOM_ERRORS},
)
def list_chat_messages(
    room_id: int = Path(..., gt=0, description="채팅방 ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[ChatMessageListResponse]:
    return ApiResponse(success=True, data=ChatMessageService.list_latest(db, room_id, current_user.id), message="Success")
