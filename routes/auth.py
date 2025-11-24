"""
인증 관련 라우트
로그인, 로그아웃, 사용자 정보 조회
"""
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session
import logging

from config import config
from utils.firebase_auth import verify_id_token
from utils.user_manager import get_or_create_user
from utils.decorators import login_required

logger = logging.getLogger(__name__)

# Blueprint 생성
auth_bp = Blueprint('auth', __name__)


@auth_bp.route("/login")
def login_page():
    """
    로그인 페이지 표시

    Returns:
        로그인 페이지 HTML 또는 메인 페이지로 리다이렉트
    """
    # 이미 로그인된 경우 메인 페이지로 리다이렉트
    if 'user_id' in session:
        return redirect(url_for('meetings.index'))

    # Firebase Config를 템플릿에 전달
    firebase_config = config.get_firebase_config()

    return render_template("login.html", firebase_config=firebase_config)


@auth_bp.route("/api/login", methods=["POST"])
def login():
    """
    Firebase ID 토큰을 받아 세션 생성

    Request JSON:
        {
            "idToken": "Firebase ID 토큰"
        }

    Returns:
        JSON: 로그인 성공 여부 및 사용자 정보
    """
    try:
        data = request.get_json()
        id_token = data.get('idToken')

        if not id_token:
            return jsonify({
                'success': False,
                'error': 'ID 토큰이 필요합니다.'
            }), 400

        # Firebase ID 토큰 검증
        user_info = verify_id_token(id_token)

        if not user_info:
            return jsonify({
                'success': False,
                'error': '유효하지 않은 토큰입니다.'
            }), 401

        # DB에서 사용자 조회 또는 생성
        user = get_or_create_user(
            google_id=user_info['uid'],
            email=user_info['email'],
            name=user_info.get('name'),
            profile_picture=user_info.get('picture')
        )

        # 세션 생성
        session['user_id'] = user['id']
        session['email'] = user['email']
        session['name'] = user.get('name', '')
        session['role'] = user['role']
        session['profile_picture'] = user.get('profile_picture', '')

        logger.info(f"✅ 로그인 성공: {user['email']} (role: {user['role']})")

        return jsonify({
            'success': True,
            'user': {
                'id': user['id'],
                'email': user['email'],
                'name': user.get('name'),
                'role': user['role']
            }
        })

    except Exception as e:
        logger.error(f"❌ 로그인 실패: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'로그인 처리 중 오류가 발생했습니다: {str(e)}'
        }), 500


@auth_bp.route("/api/logout", methods=["POST"])
def logout():
    """
    세션 삭제 (로그아웃)

    Returns:
        JSON: 로그아웃 성공 메시지
    """
    session.clear()
    return jsonify({
        'success': True,
        'message': '로그아웃되었습니다.'
    })


@auth_bp.route("/api/me", methods=["GET"])
@login_required
def get_current_user():
    """
    현재 로그인한 사용자 정보 반환

    Returns:
        JSON: 사용자 정보
    """
    return jsonify({
        'success': True,
        'user': {
            'id': session['user_id'],
            'email': session['email'],
            'name': session.get('name', ''),
            'role': session['role'],
            'profile_picture': session.get('profile_picture', '')
        }
    })
