# 03. 인증 시스템 상세 (30분 읽기)

> **레벨 3**: Firebase Authentication과 권한 관리 시스템

---

## 🔐 인증 시스템 개요

Minute AI는 **Firebase Authentication**을 사용하여 Google OAuth 로그인을 구현했습니다.

**선택 이유**:
- Google 계정 기반 간편 로그인
- Firebase Admin SDK로 서버 측 토큰 검증
- 별도의 비밀번호 관리 불필요
- 확장 가능 (나중에 다른 OAuth 제공자 추가 가능)

---

## 📊 인증 플로우

```
┌─────────────┐
│   클라이언트  │
│ (Browser)   │
└─────────────┘
       │
       │ 1. Google 로그인 버튼 클릭
       ↓
┌─────────────────────────────────┐
│  Firebase SDK (Client-Side)     │
│  templates/login.html           │
└─────────────────────────────────┘
       │
       │ 2. Google OAuth 팝업
       │    사용자 인증
       ↓
  [Firebase Auth]
       │
       │ 3. ID Token 반환
       ↓
┌─────────────────────────────────┐
│  POST /api/login                │
│  routes/auth.py                 │
└─────────────────────────────────┘
       │
       │ 4. ID Token 검증
       ↓
┌─────────────────────────────────┐
│  firebase_auth.verify_id_token()│
│  utils/firebase_auth.py         │
└─────────────────────────────────┘
       │
       │ 5. Firebase Admin SDK로 토큰 검증
       ↓
  [Firebase Admin API]
       │
       │ 6. {uid, email, name, picture} 반환
       ↓
┌─────────────────────────────────┐
│  user_manager.get_or_create_user│
│  utils/user_manager.py          │
└─────────────────────────────────┘
       │
       │ 7. users 테이블 조회/생성
       ↓
  [SQLite DB]
       │
       │ 8. user_id 반환
       ↓
┌─────────────────────────────────┐
│  session['user_id'] = user['id']│
│  routes/auth.py                 │
└─────────────────────────────────┘
       │
       │ 9. 세션 쿠키 생성
       ↓
  [클라이언트]
       │
       │ 10. 메인 페이지로 리다이렉트
       ↓
    완료
```

---

## 🔧 구현 상세

### 1. Firebase Admin SDK 초기화

**파일**: `utils/firebase_auth.py`

```python
# 전역 변수로 초기화 상태 관리
_firebase_initialized = False

def initialize_firebase():
    """Firebase Admin SDK 초기화 (앱 시작 시 1회만 실행)"""
    global _firebase_initialized

    if _firebase_initialized:
        return

    # firebase-adminsdk.json 파일 경로
    cred_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'firebase-adminsdk.json'
    )

    if not os.path.exists(cred_path):
        raise FileNotFoundError(f"Firebase 인증 파일 없음: {cred_path}")

    # Firebase Admin SDK 초기화
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
    _firebase_initialized = True
```

**호출 위치**: `app.py:40`

```python
# app.py
from utils.firebase_auth import initialize_firebase

try:
    initialize_firebase()
    logger.info("✅ Firebase 초기화 성공")
except Exception as e:
    logger.error(f"⚠️  Firebase 초기화 실패: {e}")
```

---

### 2. ID 토큰 검증

**파일**: `utils/firebase_auth.py:46`

```python
def verify_id_token(id_token: str) -> Optional[Dict[str, str]]:
    """
    Firebase ID 토큰 검증

    Args:
        id_token: 프론트엔드에서 받은 Firebase ID Token

    Returns:
        성공 시: {'uid': '...', 'email': '...', 'name': '...', 'picture': '...'}
        실패 시: None
    """
    try:
        # Firebase에서 토큰 검증
        decoded_token = auth.verify_id_token(id_token)

        # 사용자 정보 추출
        return {
            'uid': decoded_token['uid'],
            'email': decoded_token.get('email'),
            'name': decoded_token.get('name'),
            'picture': decoded_token.get('picture')
        }
    except auth.InvalidIdTokenError:
        logger.error("❌ 유효하지 않은 ID 토큰")
        return None
    except auth.ExpiredIdTokenError:
        logger.error("❌ 만료된 ID 토큰")
        return None
    except Exception as e:
        logger.error(f"❌ 토큰 검증 실패: {e}")
        return None
```

---

### 3. 로그인 API

**파일**: `routes/auth.py:37`

```python
@auth_bp.route("/api/login", methods=["POST"])
def login():
    """
    Firebase ID 토큰을 받아 세션 생성

    Request JSON:
        {
            "idToken": "eyJhbGc..."
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
```

---

### 4. 사용자 조회/생성

**파일**: `utils/user_manager.py:27`

```python
def get_or_create_user(google_id: str, email: str, name: str = None, profile_picture: str = None) -> Dict:
    """
    사용자 조회 또는 생성

    로직:
    1. google_id로 조회 → 있으면 정보 업데이트 후 반환
    2. email로 조회 (더미 계정 migrate) → 있으면 google_id 업데이트
    3. 신규 사용자 생성 → config.ADMIN_EMAILS 기반으로 role 설정

    Args:
        google_id: Firebase UID
        email: 이메일
        name: 이름
        profile_picture: 프로필 사진 URL

    Returns:
        사용자 정보 딕셔너리 {id, google_id, email, name, role, ...}
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. google_id로 기존 사용자 조회
        cursor.execute("SELECT * FROM users WHERE google_id = ?", (google_id,))
        user = cursor.fetchone()

        if user:
            # 기존 사용자 정보 업데이트
            cursor.execute("""
                UPDATE users
                SET name = ?, profile_picture = ?
                WHERE google_id = ?
            """, (name, profile_picture, google_id))
            conn.commit()
            return dict(user)

        # 2. email로 기존 사용자 조회 (migrate)
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()

        if user:
            # 더미 계정의 google_id를 실제 Firebase UID로 업데이트
            cursor.execute("""
                UPDATE users
                SET google_id = ?, name = ?, profile_picture = ?
                WHERE email = ?
            """, (google_id, name, profile_picture, email))
            conn.commit()

            logger.info(f"✅ 기존 사용자 업데이트: {email} (google_id 갱신)")

            # 업데이트된 사용자 반환
            cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
            updated_user = cursor.fetchone()
            return dict(updated_user)

        # 3. 신규 사용자 생성
        admin_emails = [e.strip() for e in config.ADMIN_EMAILS if e.strip()]
        role = 'admin' if email in admin_emails else 'user'

        cursor.execute("""
            INSERT INTO users (google_id, email, name, profile_picture, role)
            VALUES (?, ?, ?, ?, ?)
        """, (google_id, email, name, profile_picture, role))
        conn.commit()

        user_id = cursor.lastrowid

        logger.info(f"✅ 신규 사용자 생성: {email} (role: {role})")

        return {
            'id': user_id,
            'google_id': google_id,
            'email': email,
            'name': name,
            'profile_picture': profile_picture,
            'role': role
        }

    finally:
        conn.close()
```

---

## 🛡️ 권한 관리 시스템

### 권한 레벨

1. **Owner (소유자)**
   - 본인이 생성한 노트
   - 읽기, 수정, 삭제, 공유 가능

2. **Shared User (공유받은 사용자)**
   - 다른 사람이 공유해준 노트
   - 읽기만 가능 (수정 불가)

3. **Admin (관리자)**
   - 모든 노트 접근 가능
   - 수정, 삭제 가능
   - config.ADMIN_EMAILS에 등록된 이메일

---

### 권한 체크 함수

#### `can_access_meeting()` - 읽기 권한

**파일**: `utils/user_manager.py:139`

```python
def can_access_meeting(user_id: int, meeting_id: str) -> bool:
    """
    사용자가 해당 회의에 접근 권한이 있는지 확인

    조건:
    1. 본인이 생성한 노트 (owner_id == user_id)
    2. admin 권한
    3. 공유받은 노트 (meeting_shares 테이블)

    Returns:
        True: 접근 가능
        False: 접근 불가
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. Admin 체크
        if is_admin(user_id):
            return True

        # 2. 본인이 생성한 노트 체크
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM meeting_dialogues
            WHERE meeting_id = ? AND owner_id = ?
        """, (meeting_id, user_id))
        result = cursor.fetchone()
        if result and result['count'] > 0:
            return True

        # 3. 공유받은 노트 체크
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM meeting_shares
            WHERE meeting_id = ? AND shared_with_user_id = ?
        """, (meeting_id, user_id))
        result = cursor.fetchone()
        if result and result['count'] > 0:
            return True

        return False

    finally:
        conn.close()
```

**사용 예시** (routes/meetings.py:96):
```python
@meetings_bp.route("/view/<string:meeting_id>")
@login_required
def view_meeting(meeting_id):
    user_id = session['user_id']

    # 권한 체크
    if not can_access_meeting(user_id, meeting_id):
        return "⛔ 접근 권한이 없습니다.", 403

    return render_template("viewer.html", meeting_id=meeting_id)
```

---

#### `can_edit_meeting()` - 수정 권한

**파일**: `utils/user_manager.py:445`

```python
def can_edit_meeting(user_id: int, meeting_id: str) -> bool:
    """
    사용자가 회의를 수정할 권한이 있는지 확인

    조건:
    - Admin: 모든 노트 수정 가능
    - Owner: 본인 노트만 수정 가능
    - 공유받은 사람: 수정 불가 (읽기만 가능)

    Returns:
        수정 권한 여부 (True/False)
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. Admin 체크
        if is_admin(user_id):
            return True

        # 2. Owner 체크
        cursor.execute("""
            SELECT owner_id
            FROM meeting_dialogues
            WHERE meeting_id = ?
            LIMIT 1
        """, (meeting_id,))
        result = cursor.fetchone()

        if not result:
            return False

        return result['owner_id'] == user_id

    finally:
        conn.close()
```

**사용 예시** (routes/meetings.py:204):
```python
@meetings_bp.route("/api/update_title/<string:meeting_id>", methods=["POST"])
@login_required
def update_meeting_title(meeting_id):
    user_id = session['user_id']

    # 권한 체크
    if not can_edit_meeting(user_id, meeting_id):
        return jsonify({
            "success": False,
            "error": "수정 권한이 없습니다."
        }), 403

    # ... 제목 수정 로직
```

---

### 노트 공유 기능

#### 공유 생성

**파일**: `utils/user_manager.py:277`

```python
def share_meeting(meeting_id: str, owner_id: int, shared_with_email: str) -> Dict:
    """
    회의 노트 공유

    Args:
        meeting_id: 회의 ID
        owner_id: 소유자 ID
        shared_with_email: 공유받을 사용자 이메일

    Returns:
        {'success': bool, 'message': str}
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. 공유받을 사용자 조회
        shared_user = get_user_by_email(shared_with_email)
        if not shared_user:
            return {'success': False, 'message': '해당 이메일의 사용자를 찾을 수 없습니다.'}

        # 2. 본인에게 공유 방지
        if shared_user['id'] == owner_id:
            return {'success': False, 'message': '본인에게는 공유할 수 없습니다.'}

        # 3. 소유자 확인
        cursor.execute("""
            SELECT owner_id FROM meeting_dialogues WHERE meeting_id = ? LIMIT 1
        """, (meeting_id,))
        result = cursor.fetchone()

        if not result or result['owner_id'] != owner_id:
            return {'success': False, 'message': '회의 소유자만 공유할 수 있습니다.'}

        # 4. 이미 공유되어 있는지 확인
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM meeting_shares
            WHERE meeting_id = ? AND shared_with_user_id = ?
        """, (meeting_id, shared_user['id']))
        result = cursor.fetchone()

        if result['count'] > 0:
            return {'success': False, 'message': '이미 공유된 사용자입니다.'}

        # 5. 공유 생성
        cursor.execute("""
            INSERT INTO meeting_shares (meeting_id, owner_id, shared_with_user_id, permission)
            VALUES (?, ?, ?, 'read')
        """, (meeting_id, owner_id, shared_user['id']))
        conn.commit()

        logger.info(f"✅ 회의 공유 완료: {meeting_id} → {shared_with_email}")

        return {'success': True, 'message': f'{shared_with_email}에게 공유되었습니다.'}

    except Exception as e:
        logger.error(f"❌ 회의 공유 실패: {e}")
        return {'success': False, 'message': f'공유 실패: {str(e)}'}

    finally:
        conn.close()
```

---

## 🎭 데코레이터

### `@login_required`

**파일**: `utils/decorators.py:12`

```python
def login_required(f):
    """
    로그인이 필요한 라우트에 사용하는 데코레이터

    사용법:
        @app.route('/protected')
        @login_required
        def protected_route():
            user_id = session['user_id']
            return "Protected content"
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            # API 요청인 경우 JSON 응답
            if request.path.startswith('/api/'):
                return jsonify({'error': '로그인이 필요합니다.', 'redirect': '/login'}), 401

            # HTML 페이지 요청인 경우 로그인 페이지로 리다이렉트
            return redirect(url_for('auth.login_page'))

        return f(*args, **kwargs)

    return decorated_function
```

---

### `@admin_required`

**파일**: `utils/decorators.py:38`

```python
def admin_required(f):
    """
    Admin 권한이 필요한 라우트에 사용하는 데코레이터

    사용법:
        @app.route('/admin/debug')
        @admin_required
        def debug_page():
            return "Admin only content"
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 로그인 체크
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'error': '로그인이 필요합니다.', 'redirect': '/login'}), 401
            return redirect(url_for('auth.login_page'))

        # Admin 권한 체크
        user_id = session['user_id']
        if not is_admin(user_id):
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Admin 권한이 필요합니다.'}), 403
            return "⛔ 접근 권한이 없습니다. Admin 권한이 필요합니다.", 403

        return f(*args, **kwargs)

    return decorated_function
```

---

## 🔒 보안 고려사항

### 1. **ID 토큰 검증**
- Firebase Admin SDK가 서버 측에서 토큰 검증
- 토큰 위조 불가능
- 만료 시간 자동 체크

### 2. **세션 관리**
- Flask 기본 세션 (암호화된 쿠키)
- SECRET_KEY 256비트 랜덤 hex 사용
- 세션 하이재킹 방지

### 3. **권한 체크 2중 확인**
```python
@login_required           # 1차: 로그인 여부
def some_route():
    if not can_access_meeting():  # 2차: 리소스 접근 권한
        return 403
```

### 4. **SQL 인젝션 방지**
- 파라미터화된 쿼리 사용
```python
cursor.execute("SELECT * FROM users WHERE email = ?", (email,))  # ✅ 안전
# cursor.execute(f"SELECT * FROM users WHERE email = '{email}'")  # ❌ 위험
```

---

## 📊 데이터베이스 스키마

### `users` 테이블

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    google_id TEXT UNIQUE NOT NULL,     -- Firebase UID
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    profile_picture TEXT,
    role TEXT DEFAULT 'user',           -- 'user' 또는 'admin'
    created_at TEXT NOT NULL
);
```

### `meeting_shares` 테이블

```sql
CREATE TABLE meeting_shares (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id TEXT NOT NULL,
    owner_id INTEGER NOT NULL,
    shared_with_user_id INTEGER NOT NULL,
    permission TEXT DEFAULT 'read',     -- 현재는 'read'만 지원
    created_at TEXT NOT NULL,
    FOREIGN KEY (owner_id) REFERENCES users(id),
    FOREIGN KEY (shared_with_user_id) REFERENCES users(id),
    UNIQUE(meeting_id, shared_with_user_id)  -- 중복 공유 방지
);
```

---

## 🎓 테스트 시나리오

### 1. 신규 사용자 가입
```
1. /login 접속
2. Google 로그인 클릭
3. Firebase 팝업에서 계정 선택
4. POST /api/login {idToken}
5. users 테이블에 신규 사용자 생성
6. role: config.ADMIN_EMAILS에 있으면 'admin', 없으면 'user'
7. 세션 생성
8. / 페이지로 리다이렉트
```

### 2. 노트 공유
```
1. 노트 소유자: POST /api/share/{meeting_id} {email: "friend@example.com"}
2. meeting_shares 테이블에 레코드 생성
3. friend@example.com 사용자: /shared-notes에서 공유받은 노트 확인
4. 노트 클릭 → can_access_meeting() = True (읽기 가능)
5. 제목 수정 시도 → can_edit_meeting() = False (403 에러)
```

---

## 🚀 다음 단계

- **파일 업로드 & STT**: `04_file_upload_stt.md`
- **데이터베이스 구조**: `07_database.md`
- **API 명세서**: `11_api_specification.md`
