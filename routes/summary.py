"""
요약 및 회의록 관련 라우트
문단 요약, 회의록 생성
"""
from flask import Blueprint, request, jsonify, session
import logging

from config import config
from utils.db_manager import DatabaseManager
from utils.vector_db_manager import vdb_manager
from utils.stt import STTManager
from utils.decorators import login_required
from utils.user_manager import can_access_meeting

logger = logging.getLogger(__name__)

# Blueprint 생성
summary_bp = Blueprint('summary', __name__)

# 매니저 초기화
db = DatabaseManager(str(config.DATABASE_PATH))
stt_manager = STTManager()


@summary_bp.route("/api/summarize/<string:meeting_id>", methods=["POST"])
@login_required
def summarize(meeting_id):
    """
    문단 요약 생성

    Args:
        meeting_id: 회의 ID

    Returns:
        JSON: 요약 내용
    """
    user_id = session['user_id']

    # 권한 체크
    if not can_access_meeting(user_id, meeting_id):
        return jsonify({
            "success": False,
            "error": "접근 권한이 없습니다."
        }), 403

    try:
        # 1. meeting_id로 회의록 내용 조회
        rows = db.get_meeting_by_id(meeting_id)
        if not rows:
            return jsonify({
                "success": False,
                "error": "해당 회의를 찾을 수 없습니다."
            }), 404

        # 2. title, transcript_text, meeting_date, audio_file 추출
        title = rows[0]['title']
        meeting_date = rows[0]['meeting_date']
        audio_file = rows[0]['audio_file']
        transcript_text = " ".join([row['segment'] for row in rows])

        # 3. stt_manager의 subtopic_generate를 이용해 요약 생성
        summary_content = stt_manager.subtopic_generate(title, transcript_text)

        if not summary_content:
            return jsonify({
                "success": False,
                "error": "요약 생성에 실패했습니다."
            }), 500

        # 4. 생성한 내용을 'meeting_subtopic' DB에 저장
        vdb_manager.add_meeting_as_subtopic(
            meeting_id=meeting_id,
            title=title,
            meeting_date=meeting_date,
            audio_file=audio_file,
            summary_content=summary_content
        )

        return jsonify({
            "success": True,
            "message": "요약이 성공적으로 생성 및 저장되었습니다.",
            "summary": summary_content
        })

    except Exception as e:
        logger.error(f"❌ 요약 생성 실패: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"요약 처리 중 오류 발생: {str(e)}"
        }), 500


@summary_bp.route("/api/check_summary/<string:meeting_id>")
@login_required
def check_summary(meeting_id):
    """
    요약 존재 여부 확인

    Args:
        meeting_id: 회의 ID

    Returns:
        JSON: 요약 존재 여부
    """
    user_id = session['user_id']

    # 권한 체크
    if not can_access_meeting(user_id, meeting_id):
        return jsonify({
            "success": False,
            "error": "접근 권한이 없습니다."
        }), 403

    try:
        # Vector DB에서 문단 요약 조회
        summary_content = vdb_manager.get_summary_by_meeting_id(meeting_id)

        if summary_content:
            return jsonify({
                "success": True,
                "has_summary": True,
                "summary": summary_content
            })
        else:
            return jsonify({
                "success": True,
                "has_summary": False,
                "message": "문단 요약이 아직 생성되지 않았습니다."
            })

    except Exception as e:
        logger.error(f"❌ 요약 확인 실패: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"요약 조회 중 오류 발생: {str(e)}"
        }), 500


@summary_bp.route("/api/generate_minutes/<string:meeting_id>", methods=["POST"])
@login_required
def generate_minutes(meeting_id):
    """
    회의록 생성 (RAG 기반)

    Args:
        meeting_id: 회의 ID

    Returns:
        JSON: 회의록 내용
    """
    user_id = session['user_id']

    # 권한 체크
    if not can_access_meeting(user_id, meeting_id):
        return jsonify({
            "success": False,
            "error": "접근 권한이 없습니다."
        }), 403

    try:
        # 1. meeting_id로 회의록 내용 조회
        rows = db.get_meeting_by_id(meeting_id)
        if not rows:
            return jsonify({
                "success": False,
                "error": "해당 회의를 찾을 수 없습니다."
            }), 404

        # 2. title, meeting_date, transcript_text 추출
        title = rows[0]['title']
        meeting_date = rows[0]['meeting_date']
        transcript_text = " ".join([row['segment'] for row in rows])

        # 3. vector DB에서 청킹된 문서 가져오기 (chunk_index 순서대로)
        chunks_content = vdb_manager.get_chunks_by_meeting_id(meeting_id)

        if not chunks_content:
            return jsonify({
                "success": False,
                "error": "청킹된 회의 내용을 찾을 수 없습니다. 오디오 파일을 먼저 업로드해주세요."
            }), 400

        # 4. stt_manager의 generate_minutes를 이용해 회의록 생성 (meeting_date 전달)
        minutes_content = stt_manager.generate_minutes(
            title,
            transcript_text,
            chunks_content,
            meeting_date
        )

        if not minutes_content:
            return jsonify({
                "success": False,
                "error": "회의록 생성에 실패했습니다."
            }), 500

        # 5. 생성된 회의록을 SQLite DB에 저장
        db.save_minutes(meeting_id, title, meeting_date, minutes_content)

        return jsonify({
            "success": True,
            "message": "회의록이 성공적으로 생성 및 저장되었습니다.",
            "minutes": minutes_content
        })

    except Exception as e:
        logger.error(f"❌ 회의록 생성 실패: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"회의록 생성 중 오류 발생: {str(e)}"
        }), 500


@summary_bp.route("/api/get_minutes/<string:meeting_id>")
@login_required
def get_minutes(meeting_id):
    """
    회의록 조회

    Args:
        meeting_id: 회의 ID

    Returns:
        JSON: 회의록 내용
    """
    user_id = session['user_id']

    # 권한 체크
    if not can_access_meeting(user_id, meeting_id):
        return jsonify({
            "success": False,
            "error": "접근 권한이 없습니다."
        }), 403

    try:
        # DB에서 회의록 조회
        minutes_data = db.get_minutes_by_meeting_id(meeting_id)

        if minutes_data:
            return jsonify({
                "success": True,
                "has_minutes": True,
                "minutes": minutes_data['minutes_content'],
                "created_at": minutes_data['created_at'],
                "updated_at": minutes_data['updated_at']
            })
        else:
            return jsonify({
                "success": True,
                "has_minutes": False,
                "message": "회의록이 아직 생성되지 않았습니다."
            })

    except Exception as e:
        logger.error(f"❌ 회의록 조회 실패: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"회의록 조회 중 오류 발생: {str(e)}"
        }), 500
