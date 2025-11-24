"""
회의 관련 라우트
회의 목록 조회, 상세 보기, 삭제, 공유 등
"""
from flask import Blueprint, render_template, request, jsonify, session, Response, stream_with_context
from werkzeug.utils import secure_filename
import os
import uuid
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

from config import config
from utils.db_manager import DatabaseManager
from utils.vector_db_manager import vdb_manager
from utils.stt import STTManager
from utils.decorators import login_required
from utils.user_manager import (
    can_access_meeting,
    can_edit_meeting,
    get_user_meetings,
    get_shared_meetings,
    share_meeting,
    get_shared_users,
    remove_share
)
from utils.analysis import calculate_speaker_share
from utils.validation import validate_title, parse_meeting_date
from services.upload_service import upload_service

# Blueprint 생성
meetings_bp = Blueprint('meetings', __name__)

# 데이터베이스 매니저 초기화
db = DatabaseManager(str(config.DATABASE_PATH))
stt_manager = STTManager()


@meetings_bp.route("/")
@login_required
def index():
    """
    메인 페이지 (파일 업로드 페이지)

    Returns:
        HTML: 업로드 페이지
    """
    return render_template("index.html")


@meetings_bp.route("/notes")
@login_required
def notes():
    """
    내 노트 목록 조회

    Returns:
        HTML: 노트 목록 페이지
    """
    user_id = session['user_id']
    meetings = get_user_meetings(user_id)
    return render_template("notes.html", meetings=meetings)


@meetings_bp.route("/shared-notes")
@login_required
def shared_notes():
    """
    공유받은 노트 목록 조회

    Returns:
        HTML: 공유 노트 목록 페이지
    """
    user_id = session['user_id']
    shared_meetings = get_shared_meetings(user_id)
    return render_template("shared-notes.html", meetings=shared_meetings)


@meetings_bp.route("/view/<string:meeting_id>")
@login_required
def view_meeting(meeting_id):
    """
    회의록 뷰어 페이지

    Args:
        meeting_id: 회의 ID

    Returns:
        HTML: 회의록 뷰어 페이지 또는 접근 거부 메시지
    """
    user_id = session['user_id']

    # 권한 체크
    if not can_access_meeting(user_id, meeting_id):
        return "⛔ 접근 권한이 없습니다.", 403

    return render_template("viewer.html", meeting_id=meeting_id)


@meetings_bp.route("/api/meeting/<string:meeting_id>")
@login_required
def get_meeting_data(meeting_id):
    """
    회의 데이터 조회 (전사, 요약, 화자 정보 등)

    Args:
        meeting_id: 회의 ID

    Returns:
        JSON: 회의 전체 데이터
    """
    user_id = session['user_id']

    # 권한 체크
    if not can_access_meeting(user_id, meeting_id):
        return jsonify({
            "success": False,
            "error": "접근 권한이 없습니다."
        }), 403

    # 회의 데이터 조회
    rows = db.get_meeting_by_id(meeting_id)

    if not rows:
        return jsonify({
            "success": False,
            "error": "회의를 찾을 수 없습니다."
        }), 404

    # 전사 데이터 변환 (dict로 변환)
    transcript = [dict(row) for row in rows]

    # 회의 정보 추출
    audio_file = rows[0]['audio_file']
    title = rows[0]['title']
    meeting_date = rows[0]['meeting_date']

    # 참석자 목록 추출 (중복 제거)
    participants = list(set([t['speaker_label'] for t in transcript if t.get('speaker_label')]))
    participants.sort()

    # 화자별 점유율 계산
    speaker_share_data = calculate_speaker_share(meeting_id)

    # 수정 권한 확인 (owner 또는 admin만 수정 가능)
    can_edit = can_edit_meeting(user_id, meeting_id)

    return jsonify({
        "success": True,
        "meeting_id": meeting_id,
        "title": title,
        "meeting_date": meeting_date,
        "participants": participants,
        "audio_url": f"/uploads/{audio_file}",
        "transcript": transcript,
        "speaker_share": speaker_share_data,
        "can_edit": can_edit
    })


@meetings_bp.route("/api/delete_meeting/<string:meeting_id>", methods=["POST"])
@login_required
def delete_meeting(meeting_id):
    """
    회의 삭제 (SQLite, Vector DB, 오디오 파일 모두 삭제)

    Args:
        meeting_id: 회의 ID

    Returns:
        JSON: 삭제 성공 여부
    """
    user_id = session['user_id']

    # 권한 체크 (소유자만 삭제 가능)
    if not can_edit_meeting(user_id, meeting_id):
        return jsonify({
            "success": False,
            "error": "삭제 권한이 없습니다. (소유자만 삭제 가능)"
        }), 403

    try:
        # Vector DB, SQLite DB, 오디오 파일 모두 삭제
        # db_type="all"로 모든 데이터 삭제
        result = vdb_manager.delete_from_collection(db_type="all", meeting_id=meeting_id)
        return jsonify(result)

    except ValueError as e:
        # meeting_id를 찾을 수 없는 경우
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404
    except Exception as e:
        logger.error(f"❌ 회의 삭제 실패: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"삭제 중 오류가 발생했습니다: {str(e)}"
        }), 500


@meetings_bp.route("/api/update_title/<string:meeting_id>", methods=["POST"])
@login_required
def update_meeting_title(meeting_id):
    """
    회의 제목 수정

    Args:
        meeting_id: 회의 ID

    Request JSON:
        {
            "new_title": "새로운 제목"
        }

    Returns:
        JSON: 수정 성공 여부
    """
    user_id = session['user_id']

    # 권한 체크
    if not can_edit_meeting(user_id, meeting_id):
        return jsonify({
            "success": False,
            "error": "수정 권한이 없습니다."
        }), 403

    try:
        data = request.get_json()
        new_title = data.get('title', '').strip()

        # 제목 검증
        is_valid, error_message = validate_title(new_title)
        if not is_valid:
            return jsonify({
                "success": False,
                "error": error_message
            }), 400

        # DB 업데이트
        result = db.update_meeting_title(meeting_id, new_title)

        return jsonify(result)

    except Exception as e:
        logger.error(f"❌ 제목 수정 실패: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"제목 수정 중 오류가 발생했습니다: {str(e)}"
        }), 500


@meetings_bp.route("/api/update_date/<string:meeting_id>", methods=["POST"])
@login_required
def update_meeting_date(meeting_id):
    """
    회의 날짜 수정

    Args:
        meeting_id: 회의 ID

    Request JSON:
        {
            "new_date": "2025-11-13T14:30"
        }

    Returns:
        JSON: 수정 성공 여부
    """
    user_id = session['user_id']

    # 권한 체크
    if not can_edit_meeting(user_id, meeting_id):
        return jsonify({
            "success": False,
            "error": "수정 권한이 없습니다."
        }), 403

    try:
        data = request.get_json()
        new_date = data.get('date', '').strip()

        if not new_date:
            return jsonify({
                "success": False,
                "error": "날짜를 입력해주세요."
            }), 400

        # 날짜 파싱 및 포맷팅
        formatted_date = parse_meeting_date(new_date)

        # DB 업데이트
        result = db.update_meeting_date(meeting_id, formatted_date)

        return jsonify(result)

    except Exception as e:
        logger.error(f"❌ 날짜 수정 실패: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"날짜 수정 중 오류가 발생했습니다: {str(e)}"
        }), 500


# ==================== 공유 기능 ====================

@meetings_bp.route("/api/share/<string:meeting_id>", methods=["POST"])
@login_required
def share_meeting_route(meeting_id):
    """
    노트 공유 (이메일 기반)

    Args:
        meeting_id: 회의 ID

    Request JSON:
        {
            "email": "user@example.com"
        }

    Returns:
        JSON: 공유 성공 여부
    """
    user_id = session['user_id']

    # 권한 체크 (소유자만 공유 가능)
    if not can_edit_meeting(user_id, meeting_id):
        return jsonify({
            "success": False,
            "error": "공유 권한이 없습니다. (소유자만 공유 가능)"
        }), 403

    try:
        data = request.get_json()
        target_email = data.get('email')

        if not target_email:
            return jsonify({
                "success": False,
                "error": "이메일을 입력해주세요."
            }), 400

        # 공유 처리
        result = share_meeting(meeting_id, user_id, target_email)

        return jsonify(result)

    except Exception as e:
        logger.error(f"❌ 공유 실패: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"공유 중 오류가 발생했습니다: {str(e)}"
        }), 500


@meetings_bp.route("/api/shared_users/<string:meeting_id>")
@login_required
def get_shared_users_route(meeting_id):
    """
    공유받은 사용자 목록 조회

    Args:
        meeting_id: 회의 ID

    Returns:
        JSON: 공유 사용자 목록
    """
    user_id = session['user_id']

    # 권한 체크
    if not can_access_meeting(user_id, meeting_id):
        return jsonify({
            "success": False,
            "error": "접근 권한이 없습니다."
        }), 403

    try:
        shared_users = get_shared_users(meeting_id)

        return jsonify({
            "success": True,
            "shared_users": shared_users
        })

    except Exception as e:
        logger.error(f"❌ 공유 사용자 조회 실패: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"조회 중 오류가 발생했습니다: {str(e)}"
        }), 500


@meetings_bp.route("/api/unshare/<string:meeting_id>/<int:target_user_id>", methods=["POST"])
@login_required
def unshare_meeting_route(meeting_id, target_user_id):
    """
    공유 해제

    Args:
        meeting_id: 회의 ID
        target_user_id: 공유 해제할 사용자 ID

    Returns:
        JSON: 해제 성공 여부
    """
    user_id = session['user_id']

    # 권한 체크 (소유자만 공유 해제 가능)
    if not can_edit_meeting(user_id, meeting_id):
        return jsonify({
            "success": False,
            "error": "공유 해제 권한이 없습니다. (소유자만 가능)"
        }), 403

    try:
        result = remove_share(meeting_id, target_user_id)

        return jsonify(result)

    except Exception as e:
        logger.error(f"❌ 공유 해제 실패: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"공유 해제 중 오류가 발생했습니다: {str(e)}"
        }), 500


# ==================== 파일 업로드 ====================

@meetings_bp.route("/upload", methods=["POST"])
@login_required
def upload_and_process():
    """
    파일 업로드 및 STT 처리 (SSE 스트리밍)
    
    Form Data:
        title: 회의 제목
        audio_file: 오디오/비디오 파일
    
    Returns:
        SSE Stream: 실시간 진행 상황
    """
    owner_id = session['user_id']
    
    # 제목 검증
    title = request.form.get('title', '').strip()
    is_valid, error_message = validate_title(title)
    if not is_valid:
        return render_template("index.html", error=error_message)
    
    # 파일 검증
    if 'audio_file' not in request.files:
        return render_template("index.html", error="오디오 파일이 없습니다.")
    
    file = request.files['audio_file']
    is_valid, error_message = upload_service.validate_file(file.filename)
    if not is_valid:
        return render_template("index.html", error=error_message)
    
    # 파일 저장 (generator 시작 전에 완료)
    meeting_id = uuid.uuid4().hex
    file_path, original_filename, is_video = upload_service.save_uploaded_file(file, meeting_id)
    meeting_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # SSE Generator 함수
    def generate():
        temp_audio_path = None
        
        try:
            # Step 1: 파일 업로드 완료
            yield f"data: {json.dumps({'step': 'upload', 'message': '파일 업로드가 완료되었습니다...', 'icon': '📤'})}\n\n"
            
            # Step 2: 비디오 변환 (필요 시)
            audio_path_for_stt = file_path
            if is_video:
                yield f"data: {json.dumps({'step': 'convert', 'message': '비디오를 오디오로 변환 중...', 'icon': '🎬'})}\n\n"
                
                success, temp_audio_path, error_msg = upload_service.convert_video_to_audio(file_path)
                if not success:
                    yield f"data: {json.dumps({'step': 'error', 'message': f'비디오 변환 실패: {error_msg}'})}\n\n"
                    return
                
                audio_path_for_stt = temp_audio_path
            
            # Step 3: STT 처리
            yield f"data: {json.dumps({'step': 'stt', 'message': '회의 음성을 텍스트로 변환하고 있습니다...', 'icon': '🎤'})}\n\n"
            
            result = upload_service.process_audio_file(
                audio_path=audio_path_for_stt,
                meeting_id=meeting_id,
                title=title,
                meeting_date=meeting_date,
                owner_id=owner_id
            )

            if not result['success']:
                yield f"data: {json.dumps({'step': 'error', 'message': 'STT 처리 실패'})}\n\n"
                return

            # 실제로 저장된 meeting_id 가져오기 (중요!)
            actual_meeting_id = result['meeting_id']

            # 임시 WAV 파일 삭제
            if temp_audio_path:
                upload_service.cleanup_temp_files(temp_audio_path)

            # Step 4: 문단 요약 생성
            yield f"data: {json.dumps({'step': 'summary', 'message': '회의 내용을 분석하고 요약하고 있습니다...', 'icon': '📝'})}\n\n"

            try:
                result = upload_service.generate_summary(actual_meeting_id)
                logger.info(f"✅ 문단 요약 생성 완료 (meeting_id: {actual_meeting_id})")

                # Step 5: 마인드맵 생성 (요약 성공 시에만)
                if result.get('success'):
                    yield f"data: {json.dumps({'step': 'mindmap', 'message': '마인드맵을 생성하고 있습니다...', 'icon': '🗺️'})}\n\n"
                    logger.info(f"✅ 마인드맵도 자동 생성되었습니다 (meeting_id: {actual_meeting_id})")

            except Exception as e:
                logger.warning(f"⚠️  문단 요약 생성 실패: {e}", exc_info=True)
                # 요약 실패해도 계속 진행

            # Step 6: 완료
            redirect_url = f"/view/{actual_meeting_id}"
            yield f"data: {json.dumps({'step': 'complete', 'message': '노트 생성이 완료되었습니다!', 'redirect': redirect_url, 'icon': '✅'})}\n\n"
        
        except Exception as e:
            logger.error(f"❌ 업로드 처리 실패: {e}", exc_info=True)

            # 임시 파일 정리
            if temp_audio_path:
                upload_service.cleanup_temp_files(temp_audio_path)
            
            yield f"data: {json.dumps({'step': 'error', 'message': f'서버 처리 중 오류가 발생했습니다: {str(e)}'})}\n\n"
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')


# ==================== 노트 목록 JSON ====================

@meetings_bp.route("/notes_json")
@login_required
def notes_json():
    """
    노트 목록을 JSON으로 반환 (업로드 상태 확인용)
    
    Returns:
        JSON: 노트 목록
    """
    try:
        user_id = session['user_id']
        meetings = get_user_meetings(user_id)
        return jsonify({"success": True, "meetings": meetings})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== 마인드맵 ====================

@meetings_bp.route("/api/mindmap/<string:meeting_id>", methods=["GET"])
@login_required
def get_mindmap(meeting_id):
    """
    마인드맵 조회
    
    Args:
        meeting_id: 회의 ID
    
    Returns:
        JSON: 마인드맵 데이터
    """
    user_id = session['user_id']
    
    # 권한 체크
    if not can_access_meeting(user_id, meeting_id):
        return jsonify({
            "success": False,
            "error": "접근 권한이 없습니다."
        }), 403
    
    try:
        # SQLite DB에서 마인드맵 조회 (string 반환)
        mindmap_content = db.get_mindmap_by_meeting_id(meeting_id)

        if mindmap_content:
            return jsonify({
                "success": True,
                "has_mindmap": True,
                "mindmap_content": mindmap_content
            })
        else:
            return jsonify({
                "success": True,
                "has_mindmap": False,
                "message": "마인드맵이 아직 생성되지 않았습니다."
            })

    except Exception as e:
        logger.error(f"❌ 마인드맵 조회 실패: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"마인드맵 조회 중 오류 발생: {str(e)}"
        }), 500
