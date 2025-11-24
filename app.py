"""
Minute AI - 회의록 자동 생성 플랫폼
Flask 애플리케이션 메인 파일

리팩토링 구조:
- config.py : 환경 변수 및 설정 중앙화
- routes/ : HTTP 라우트 (Blueprint)
- services/ : 비즈니스 로직
- utils/ : 데이터베이스 및 인프라
"""
from flask import Flask, send_from_directory, session
import logging

from config import config
from routes import register_blueprints
from utils.firebase_auth import initialize_firebase
from utils.user_manager import is_admin
from utils.db_manager import DatabaseManager
from utils.vector_db_manager import vdb_manager

# ==================== 로깅 설정 ====================
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format=config.LOG_FORMAT
)
logger = logging.getLogger(__name__)


# ==================== Flask 앱 초기화 ====================
app = Flask(__name__)
app.config['SECRET_KEY'] = config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = str(config.UPLOAD_FOLDER)

# 설정 상태 출력
config.print_config_status(show_secrets=config.DEBUG)


# ==================== Firebase 초기화 ====================
try:
    initialize_firebase()
    logger.info("✅ Firebase 초기화 성공")
except Exception as e:
    logger.error(f"⚠️  Firebase 초기화 실패: {e}")
    logger.warning("로그인 기능이 작동하지 않을 수 있습니다.")


# ==================== 데이터베이스 초기화 ====================
# DatabaseManager 인스턴스 생성
db = DatabaseManager(str(config.DATABASE_PATH))

# VectorDBManager에 DatabaseManager 주입
vdb_manager.db_manager = db

logger.info("✅ 데이터베이스 매니저 초기화 완료")


# ==================== Context Processor ====================
@app.context_processor
def inject_user_info():
    """
    모든 템플릿에 사용자 정보 주입

    Returns:
        dict: 템플릿에서 사용 가능한 변수들
    """
    if 'user_id' in session:
        user_id = session['user_id']
        is_user_admin = is_admin(user_id)
        return {
            'current_user_id': user_id,
            'is_admin': is_user_admin,
            'user_name': session.get('name', '사용자'),
            'user_email': session.get('email', ''),
            'user_picture': session.get('profile_picture', '')
        }
    return {
        'current_user_id': None,
        'is_admin': False,
        'user_name': None,
        'user_email': None,
        'user_picture': None
    }


# ==================== Blueprint 등록 ====================
register_blueprints(app)


# ==================== 정적 파일 라우트 ====================
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    """
    업로드된 파일 제공 (오디오 파일 스트리밍)

    Args:
        filename: 파일명

    Returns:
        파일 데이터
    """
    return send_from_directory(str(config.UPLOAD_FOLDER), filename)


# ==================== 에러 핸들러 ====================
@app.errorhandler(404)
def not_found(error):
    """404 에러 핸들러"""
    return "⛔ 페이지를 찾을 수 없습니다.", 404


@app.errorhandler(500)
def internal_error(error):
    """500 에러 핸들러"""
    logger.error(f"❌ 서버 오류: {error}", exc_info=True)
    return "⛔ 서버 오류가 발생했습니다.", 500


# ==================== 애플리케이션 실행 ====================
if __name__ == "__main__":
    logger.info("=" * 70)
    logger.info("🚀 Minute AI 서버 시작")
    logger.info(f"포트: {config.PORT}")
    logger.info(f"디버그 모드: {config.DEBUG}")
    logger.info("=" * 70)

    app.run(
        host="0.0.0.0",
        port=config.PORT,
        debug=config.DEBUG,
        threaded=True
    )
