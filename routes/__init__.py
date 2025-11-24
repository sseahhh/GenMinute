"""
라우트 패키지
Flask Blueprint를 사용하여 라우트를 모듈화합니다.
"""
from flask import Flask
import logging

logger = logging.getLogger(__name__)


def register_blueprints(app: Flask):
    """
    모든 Blueprint를 Flask 앱에 등록합니다.

    Args:
        app: Flask 애플리케이션 인스턴스
    """
    from .auth import auth_bp
    from .meetings import meetings_bp
    from .summary import summary_bp
    from .chat import chat_bp
    from .admin import admin_bp

    # Blueprint 등록
    app.register_blueprint(auth_bp)
    app.register_blueprint(meetings_bp)
    app.register_blueprint(summary_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(admin_bp)

    logger.info("✅ 모든 Blueprint 등록 완료")
