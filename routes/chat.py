"""
챗봇 관련 라우트
AI 질의응답
"""
from flask import Blueprint, request, jsonify, session
import logging

from config import config
from utils.vector_db_manager import vdb_manager
from utils.chat_manager import ChatManager
from utils.decorators import login_required
from utils.user_manager import can_access_meeting, get_user_accessible_meeting_ids

logger = logging.getLogger(__name__)

# Blueprint 생성
chat_bp = Blueprint('chat', __name__)

# ChatManager 초기화 (similarity retriever 사용)
chat_manager = ChatManager(vdb_manager, retriever_type="similarity")


@chat_bp.route("/api/chat", methods=["POST"])
@login_required
def chat():
    """
    챗봇 질의응답

    Request JSON:
        {
            "query": "질문 내용",
            "meeting_id": "특정 회의 ID (optional)"
        }

    Returns:
        JSON: AI 답변 및 출처
    """
    user_id = session['user_id']

    try:
        data = request.get_json()
        query = data.get('query')
        meeting_id = data.get('meeting_id')  # Optional

        if not query:
            return jsonify({
                "success": False,
                "error": "질문을 입력해주세요."
            }), 400

        # 권한 체크
        if meeting_id:
            # 특정 회의에 대한 질문
            if not can_access_meeting(user_id, meeting_id):
                return jsonify({
                    "success": False,
                    "error": "해당 회의에 접근 권한이 없습니다."
                }), 403

            # 해당 회의에 대해서만 검색
            accessible_meeting_ids = [meeting_id]
        else:
            # 전체 노트에서 검색 (사용자가 접근 가능한 노트만)
            accessible_meeting_ids = get_user_accessible_meeting_ids(user_id)

            if not accessible_meeting_ids:
                return jsonify({
                    "success": False,
                    "error": "조회 가능한 노트가 없습니다."
                }), 404

        # 챗봇 쿼리 처리
        result = chat_manager.process_query(
            query=query,
            accessible_meeting_ids=accessible_meeting_ids
        )

        return jsonify(result)

    except Exception as e:
        logger.error(f"❌ 챗봇 처리 실패: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"챗봇 처리 중 오류가 발생했습니다: {str(e)}"
        }), 500
