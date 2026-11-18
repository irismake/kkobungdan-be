"""관리자 채팅 조회 API (CHAT-REQ-002, docs/design-docs/chat-architecture.md "API"). 조회 전용이다."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError
from app.core.openapi import ADMIN_CHAT_MESSAGE_LIST_EXAMPLE, ADMIN_CHAT_ROOM_LIST_EXAMPLE, error_responses, success_response
from app.core.security import require_admin
from app.schemas.chat import AdminChatMessageListResponse, AdminChatRoomResponse
from app.schemas.common import ApiResponse
from app.services.chat.chat_admin_service import ChatAdminService

router = APIRouter(
    prefix="/admin/chat-room",
    tags=["관리자"],
    dependencies=[Depends(require_admin)],
    responses=error_responses(AppError.INVALID_TOKEN, AppError.FORBIDDEN),
)


@router.get(
    "",
    response_model=ApiResponse[list[AdminChatRoomResponse]],
    status_code=status.HTTP_200_OK,
    summary="요청의 채팅방 조회 (관리자 전용)",
    description="요청 하나에 지원한 꼬붕마다 있는 채팅방을 조회합니다. 참여자 양쪽의 읽음 위치를 함께 보여주며, 조회는 읽음 상태를 바꾸지 않습니다.",
    responses={200: success_response(ADMIN_CHAT_ROOM_LIST_EXAMPLE), **error_responses(AppError.VALIDATION_ERROR)},
)
def list_admin_chat_rooms(
    proposal_id: int = Query(..., gt=0, alias="proposalId", description="요청 ID"),
    db: Session = Depends(get_db),
) -> ApiResponse[list[AdminChatRoomResponse]]:
    return ApiResponse(success=True, data=ChatAdminService.list_rooms(db, proposal_id), message="Success")


@router.get(
    "/{room_id}/messages",
    response_model=ApiResponse[AdminChatMessageListResponse],
    status_code=status.HTTP_200_OK,
    summary="채팅 조회 (관리자 전용)",
    description=(
        "채팅방의 채팅을 저장 순서로 조회합니다. 페이지 규칙은 참여자 조회와 같습니다(기본 최근 30개, beforeSeq, afterSeq). "
        "시스템 채팅은 행님에게 보이는 문구(content)와 꼬붕에게 보이는 문구(runnerContent)를 함께 보여줍니다. "
        "관리자는 채팅을 보낼 수 없고, 조회는 참여자의 읽음 상태를 바꾸지 않습니다."
    ),
    responses={
        200: success_response(ADMIN_CHAT_MESSAGE_LIST_EXAMPLE),
        **error_responses(AppError.VALIDATION_ERROR, AppError.CHAT_ROOM_NOT_FOUND),
    },
)
def list_admin_chat_messages(
    room_id: int = Path(..., gt=0, description="채팅방 ID"),
    before_seq: int | None = Query(None, ge=1, alias="beforeSeq", description="이 순번보다 앞선 채팅"),
    after_seq: int | None = Query(None, ge=0, alias="afterSeq", description="이 순번 뒤의 채팅"),
    db: Session = Depends(get_db),
) -> ApiResponse[AdminChatMessageListResponse]:
    data = ChatAdminService.list_messages(db, room_id, before_seq=before_seq, after_seq=after_seq)
    return ApiResponse(success=True, data=data, message="Success")
