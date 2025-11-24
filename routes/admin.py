"""
관리자 전용 라우트
검색 테스트, 스크립트 입력 등 디버그 기능
"""
from flask import Blueprint, render_template, request, jsonify, session, Response, stream_with_context
import json
from datetime import datetime

from config import config
from utils.db_manager import DatabaseManager
from utils.vector_db_manager import vdb_manager
from utils.stt import STTManager
from utils.decorators import login_required, admin_required

# Blueprint 생성
admin_bp = Blueprint('admin', __name__)

# 매니저 초기화
db = DatabaseManager(str(config.DATABASE_PATH))
stt_manager = STTManager()


@admin_bp.route("/retriever")
@login_required
@admin_required
def retriever_page():
    """
    검색 테스트 페이지 (관리자 전용)

    Returns:
        HTML: 검색 테스트 페이지
    """
    return render_template("retriever.html")


@admin_bp.route("/api/search", methods=["POST"])
@login_required
@admin_required
def search():
    """
    Vector DB 검색 테스트 (관리자 전용)

    Request JSON:
        {
            "query": "검색어",
            "retriever_type": "similarity|mmr|self_query|contextual_compression"
        }

    Returns:
        JSON: 검색 결과
    """
    try:
        data = request.get_json()
        query = data.get('query')
        retriever_type = data.get('retriever_type', 'similarity')

        if not query:
            return jsonify({
                "success": False,
                "error": "검색어를 입력해주세요."
            }), 400

        # Vector DB 검색
        results = vdb_manager.search(
            query=query,
            retriever_type=retriever_type
        )

        return jsonify({
            "success": True,
            "results": results,
            "retriever_type": retriever_type
        })

    except Exception as e:
        print(f"❌ 검색 실패: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": f"검색 중 오류가 발생했습니다: {str(e)}"
        }), 500


@admin_bp.route("/upload_script", methods=["POST"])
@login_required
@admin_required
def upload_script():
    """
    스크립트 직접 입력 처리 (관리자 전용)

    Returns:
        POST: 스크립트 처리 결과 (SSE 스트리밍)
    """
    # POST 요청: 스크립트 처리
    def generate():
        try:
            # 입력 데이터 추출
            title = request.form.get("title", "스크립트 입력")
            script_text = request.form.get("script", "")
            meeting_date_str = request.form.get("meeting_date", "")

            user_id = session['user_id']

            if not script_text:
                yield f"data: {json.dumps({'event': 'error', 'message': '스크립트를 입력해주세요.'})}\n\n"
                return

            # 날짜 파싱
            if meeting_date_str:
                meeting_date = datetime.strptime(meeting_date_str, "%Y-%m-%dT%H:%M")
            else:
                meeting_date = datetime.now()

            meeting_date_formatted = meeting_date.strftime("%Y-%m-%d %H:%M:%S")

            # Step 1: 스크립트 파싱
            yield f"data: {json.dumps({'event': 'script', 'message': '스크립트 분석 중...'})}\n\n"

            # 간단한 파싱 (라인별로 분리)
            lines = script_text.strip().split('\n')
            segments = []

            for idx, line in enumerate(lines):
                if line.strip():
                    segments.append({
                        'speaker_label': f'SPEAKER_{idx % 3:02d}',  # 3명 순환
                        'start_time': idx * 5.0,  # 5초 간격
                        'segment': line.strip(),
                        'confidence': 1.0
                    })

            # Step 2: DB 저장
            yield f"data: {json.dumps({'event': 'db', 'message': 'DB 저장 중...'})}\n\n"

            meeting_id = db.save_stt_to_db(
                segments=segments,
                audio_filename="script_input.txt",
                title=title,
                meeting_date=meeting_date_formatted,
                owner_id=user_id
            )

            # Step 3: Vector DB 저장
            yield f"data: {json.dumps({'event': 'vector', 'message': 'Vector DB 저장 중...'})}\n\n"

            # DB에서 저장된 세그먼트 다시 조회
            all_segments = db.get_segments_by_meeting_id(meeting_id)

            if all_segments:
                first_segment = all_segments[0]
                vdb_manager.add_meeting_as_chunk(
                    meeting_id=meeting_id,
                    title=first_segment['title'],
                    meeting_date=first_segment['meeting_date'],
                    audio_file=first_segment['audio_file'],
                    segments=all_segments
                )
                print(f"✅ meeting_chunks에 저장 완료 (meeting_id: {meeting_id})")

            # 완료
            redirect_url = f"/view/{meeting_id}"
            yield f"data: {json.dumps({'event': 'complete', 'message': '완료!', 'redirect_url': redirect_url})}\n\n"

        except Exception as e:
            print(f"❌ 스크립트 처리 실패: {e}")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'event': 'error', 'message': f'처리 중 오류: {str(e)}'})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


# ==================== 디버그 페이지들 ====================

@admin_bp.route("/summary_template")
@login_required
@admin_required
def summary_template_page():
    """요약 템플릿 페이지 (관리자 전용)"""
    return render_template("summary_template.html")


@admin_bp.route("/test-summary")
@login_required
@admin_required
def test_summary_page():
    """요약 테스트 페이지 (관리자 전용)"""
    return render_template("test_summary.html")


@admin_bp.route("/test-stt")
@login_required
@admin_required
def test_stt_page():
    """STT 테스트 페이지 (관리자 전용)"""
    return render_template("test_stt.html")


@admin_bp.route("/test-minutes")
@login_required
@admin_required
def test_minutes_page():
    """회의록 테스트 페이지 (관리자 전용)"""
    return render_template("test_minutes.html")


@admin_bp.route("/test-mindmap")
@login_required
@admin_required
def test_mindmap_page():
    """마인드맵 테스트 페이지 (관리자 전용)"""
    return render_template("test_mindmap.html")


@admin_bp.route("/script-input")
@login_required
@admin_required
def script_input_page():
    """스크립트 입력 페이지 (관리자 전용)"""
    return render_template("script_input.html")


# ==================== 테스트 API들 ====================

@admin_bp.route("/api/test_summary", methods=["POST"])
@login_required
@admin_required
def test_summary_api():
    """요약 생성 테스트 API (관리자 전용)"""
    try:
        data = request.get_json()
        text = data.get("text", "").strip()
        title = data.get("title", "테스트 회의").strip()

        if not text:
            return jsonify({"success": False, "error": "텍스트를 입력해주세요."}), 400

        # subtopic_generate 호출
        summary_content = stt_manager.subtopic_generate(title, text)

        if summary_content:
            return jsonify({
                "success": True,
                "summary": summary_content
            })
        else:
            return jsonify({"success": False, "error": "요약 생성에 실패했습니다."}), 500

    except Exception as e:
        print(f"❌ 요약 테스트 API 오류: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/api/test_mindmap", methods=["POST"])
@login_required
@admin_required
def test_mindmap_api():
    """마인드맵 생성 테스트 API (관리자 전용)"""
    try:
        data = request.get_json()
        summary_text = data.get("summary_text", "").strip()
        title = data.get("title", "테스트 회의").strip()

        if not summary_text:
            return jsonify({"success": False, "error": "요약 텍스트를 입력해주세요."}), 400

        # extract_mindmap_keywords 호출
        mindmap_content = stt_manager.extract_mindmap_keywords(summary_text, title)

        if mindmap_content:
            return jsonify({
                "success": True,
                "mindmap": mindmap_content
            })
        else:
            return jsonify({"success": False, "error": "마인드맵 생성에 실패했습니다."}), 500

    except Exception as e:
        print(f"❌ 마인드맵 테스트 API 오류: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/api/test_stt", methods=["POST"])
@login_required
@admin_required
def test_stt_api():
    """STT 테스트 API (관리자 전용)"""
    try:
        # 파일 확인
        if 'audio_file' not in request.files:
            return jsonify({"success": False, "error": "파일을 선택해주세요."}), 400

        file = request.files['audio_file']
        if file.filename == '':
            return jsonify({"success": False, "error": "파일을 선택해주세요."}), 400

        # 파일 확장자 검증
        allowed_extensions = {"wav", "mp3", "m4a", "flac", "mp4"}
        if not ('.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed_extensions):
            return jsonify({"success": False, "error": "지원하지 않는 파일 형식입니다."}), 400

        # 임시 파일로 저장
        import tempfile
        import os

        temp_dir = tempfile.gettempdir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"test_stt_{timestamp}_{file.filename}"
        temp_path = os.path.join(temp_dir, filename)

        file.save(temp_path)

        # STT 처리
        segments = stt_manager.transcribe_audio(temp_path)

        # 임시 파일 삭제
        if os.path.exists(temp_path):
            os.remove(temp_path)

        if segments:
            # 세그먼트를 텍스트로 변환
            transcript_text = "\n".join([
                f"Speaker {seg['speaker_label']}: {seg['segment']}"
                for seg in segments
            ])

            return jsonify({
                "success": True,
                "segments": segments,
                "transcript_text": transcript_text
            })
        else:
            return jsonify({"success": False, "error": "음성 인식에 실패했습니다."}), 500

    except Exception as e:
        print(f"❌ STT 테스트 API 오류: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/api/test_minutes", methods=["POST"])
@login_required
@admin_required
def test_minutes_api():
    """회의록 생성 테스트 API (관리자 전용)"""
    try:
        data = request.get_json()
        summary_text = data.get("summary_text", "").strip()
        transcript_text = data.get("transcript_text", "").strip()
        title = data.get("title", "테스트 회의").strip()

        if not summary_text:
            return jsonify({"success": False, "error": "요약 텍스트를 입력해주세요."}), 400

        # transcript_text가 없으면 summary_text를 사용
        if not transcript_text:
            transcript_text = summary_text

        # meeting_date는 현재 시간으로 설정
        meeting_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # generate_minutes 호출
        minutes_content = stt_manager.generate_minutes(title, transcript_text, summary_text, meeting_date)

        if minutes_content:
            return jsonify({
                "success": True,
                "minutes": minutes_content
            })
        else:
            return jsonify({"success": False, "error": "회의록 생성에 실패했습니다."}), 500

    except Exception as e:
        print(f"❌ 회의록 테스트 API 오류: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/api/delete_vector_db_entry", methods=["POST"])
@login_required
@admin_required
def delete_vector_db_entry():
    """Vector DB 엔트리 삭제 API (관리자 전용)"""
    try:
        data = request.get_json()
        db_type = data.get("db_type")
        meeting_id = data.get("meeting_id")
        audio_file = data.get("audio_file")
        title = data.get("title")

        if not db_type:
            return jsonify({"success": False, "error": "삭제할 DB 타입을 지정해야 합니다."}), 400

        vdb_manager.delete_from_collection(
            db_type=db_type,
            meeting_id=meeting_id,
            audio_file=audio_file,
            title=title
        )
        return jsonify({"success": True, "message": f"'{db_type}' 컬렉션에서 항목 삭제 요청이 처리되었습니다."})

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        print(f"❌ Vector DB 삭제 오류: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": f"벡터 DB 삭제 중 오류 발생: {str(e)}"}), 500
