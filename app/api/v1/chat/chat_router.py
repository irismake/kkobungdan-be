"""Chat room API endpoints (docs/design-docs/chat-architecture.md "API")."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError
from app.core.openapi import (
    CHAT_MESSAGE_LIST_EXAMPLE,
    CHAT_MESSAGE_SEND_EXAMPLE,
    CHAT_ROOM_DETAIL_EXAMPLE,
    CHAT_ROOM_LIST_EXAMPLE,
    error_responses,
    success_response,
)
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.chat import (
    ChatMessageListResponse,
    ChatMessageResponse,
    ChatMessageSendRequest,
    ChatRoomDetailResponse,
    ChatRoomListResponse,
)
from app.schemas.common import ApiResponse
from app.services.chat.chat_message_service import ChatMessageService
from app.services.chat.chat_room_service import ChatRoomService, list_rooms


router = APIRouter(prefix="/chat-room", tags=["채팅"])

ROOM_ERRORS = error_responses(
    AppError.INVALID_TOKEN,
    AppError.VALIDATION_ERROR,
    AppError.FORBIDDEN,
    AppError.CHAT_ROOM_NOT_FOUND,
)


@router.get(
    "",
    response_model=ApiResponse[ChatRoomListResponse],
    status_code=status.HTTP_200_OK,
    summary="채팅 목록 조회",
    description=(
        "행님·꼬붕 역할과 관계없이 내가 참여한 모든 채팅방을 마지막 채팅이 최신인 순서로 조회합니다. "
        "채팅이 없는 채팅방은 생성 시각으로 정렬합니다. 목록 조회는 읽음 처리하지 않습니다. "
        "다음 페이지는 응답의 nextCursor를 cursor로 넘겨 조회합니다."
    ),
    responses={200: success_response(CHAT_ROOM_LIST_EXAMPLE), **error_responses(AppError.INVALID_TOKEN, AppError.VALIDATION_ERROR)},
)
def list_chat_rooms(
    cursor: str | None = Query(None, max_length=200, description="이전 응답의 nextCursor"),
    size: int = Query(20, ge=1, le=50, description="페이지 크기"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[ChatRoomListResponse]:
    return ApiResponse(success=True, data=list_rooms(db, current_user.id, cursor, size), message="Success")


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
    description=(
        "채팅을 저장 순서(seq 오름차순)로 조회합니다. 기본은 최근 30개, beforeSeq를 주면 그보다 앞선 30개, "
        "afterSeq를 주면 그 뒤의 채팅(최대 100개, 재연결 후 놓친 채팅 복구)입니다. 둘은 함께 쓸 수 없습니다. "
        "시스템 채팅의 내용은 보는 사람에 맞는 문구입니다."
    ),
    responses={200: success_response(CHAT_MESSAGE_LIST_EXAMPLE), **ROOM_ERRORS},
)
def list_chat_messages(
    room_id: int = Path(..., gt=0, description="채팅방 ID"),
    before_seq: int | None = Query(None, ge=1, alias="beforeSeq", description="이 순번보다 앞선 채팅"),
    after_seq: int | None = Query(None, ge=0, alias="afterSeq", description="이 순번 뒤의 채팅"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[ChatMessageListResponse]:
    data = ChatMessageService.list_messages(db, room_id, current_user.id, before_seq=before_seq, after_seq=after_seq)
    return ApiResponse(success=True, data=data, message="Success")


@router.post(
    "/{room_id}/messages",
    response_model=ApiResponse[ChatMessageResponse],
    status_code=status.HTTP_201_CREATED,
    summary="채팅 전송",
    description=(
        "ACTIVE 채팅방에 텍스트 채팅을 보냅니다. 같은 clientMessageId로 다시 보내면 처음 저장된 채팅으로 응답하고 "
        "한 번만 저장합니다. 같은 clientMessageId로 내용이나 채팅방이 다르면 409입니다. "
        "INACTIVE·CLOSED 채팅방이나 차단 중이면 409 CHAT_ROOM_NOT_SENDABLE입니다."
    ),
    responses={
        201: success_response(CHAT_MESSAGE_SEND_EXAMPLE),
        **error_responses(
            AppError.INVALID_TOKEN,
            AppError.VALIDATION_ERROR,
            AppError.FORBIDDEN,
            AppError.CHAT_ROOM_NOT_FOUND,
            AppError.CHAT_MESSAGE_ID_CONFLICT,
            AppError.CHAT_ROOM_NOT_SENDABLE,
        ),
    },
)
def send_chat_message(
    request: ChatMessageSendRequest,
    room_id: int = Path(..., gt=0, description="채팅방 ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[ChatMessageResponse]:
    return ApiResponse(success=True, data=ChatMessageService.send(db, room_id, current_user.id, request), message="Success")
