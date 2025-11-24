# 12. 코드 리뷰 체크리스트 (실용 참고 자료)

> **레벨 5**: 팀 코드 리뷰 시 확인해야 할 핵심 사항 및 개선 제안

---

## 🎯 이 문서의 목적

1. **코드 품질 검증**: 일관성, 가독성, 유지보수성 체크
2. **보안 취약점 점검**: SQL Injection, XSS 등 OWASP Top 10 확인
3. **성능 최적화**: 병목 지점 및 개선 가능 영역 파악
4. **개선 제안**: 실질적인 리팩토링 아이디어 제공

---

## 📊 코드 리뷰 카테고리

```
1. 아키텍처 & 설계 패턴
2. 보안 (OWASP Top 10)
3. 에러 처리 & 로깅
4. 성능 최적화
5. 코드 일관성 & 가독성
6. 테스트 커버리지
7. 문서화
8. 개선 제안
```

---

## 1️⃣ 아키텍처 & 설계 패턴

### ✅ 현재 잘 구현된 부분

#### 1.1 싱글톤 패턴 일관성

**평가**: ⭐⭐⭐⭐⭐ (5/5)

**근거**:
- DatabaseManager, VectorDBManager, STTManager, ChatManager 모두 싱글톤
- 리소스 효율화 및 상태 일관성 보장

**코드 예시** (`utils/db_manager.py:20-38`):
```python
class DatabaseManager:
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
```

---

#### 1.2 Blueprint 모듈화

**평가**: ⭐⭐⭐⭐⭐ (5/5)

**근거**:
- 5개 Blueprint로 기능별 분리 (auth, meetings, summary, chat, admin)
- 각 Blueprint가 독립적인 책임 수행

**코드 위치**: `routes/__init__.py:7-30`

---

#### 1.3 레이어 분리

**평가**: ⭐⭐⭐⭐☆ (4/5)

**근거**:
- Routes (HTTP) → Services (비즈니스) → Utils (인프라) 분리
- **개선 필요**: 일부 라우트에 비즈니스 로직 혼재

**예시**:
```python
# ❌ routes/meetings.py:432-476 (비즈니스 로직이 라우트에 있음)
@meetings_bp.route("/api/meetings/<meeting_id>", methods=["PATCH"])
def update_meeting(meeting_id):
    # ... 권한 체크 로직 ...
    db.execute_query("UPDATE ...", ...)  # DB 직접 호출
```

**개선안**:
```python
# ✅ services/meeting_service.py (신규 생성)
class MeetingService:
    def update_meeting(self, meeting_id, user_id, new_title):
        if not can_edit_meeting(user_id, meeting_id):
            raise PermissionError("권한이 없습니다.")
        db.update_meeting_title(meeting_id, new_title)
        vdb_manager.update_meeting_metadata(meeting_id, title=new_title)

# routes/meetings.py
@meetings_bp.route("/api/meetings/<meeting_id>", methods=["PATCH"])
def update_meeting(meeting_id):
    try:
        meeting_service.update_meeting(meeting_id, user_id, new_title)
        return jsonify({"success": True})
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
```

---

### ⚠️ 개선이 필요한 부분

#### 1.4 순환 참조 방지

**문제**: `utils/db_manager.py:280`에서 vdb_manager import

```python
# ❌ 순환 참조 가능성
def delete_meeting(self, meeting_id):
    # ...
    from utils.vector_db_manager import vdb_manager
    vdb_manager.delete_meeting(meeting_id)
```

**개선안**: 의존성 주입 (Dependency Injection)

```python
# ✅ 개선된 코드
class DatabaseManager:
    def __init__(self, db_path, vector_db_manager=None):
        self.db_path = db_path
        self.vector_db_manager = vector_db_manager

    def delete_meeting(self, meeting_id):
        # ...
        if self.vector_db_manager:
            self.vector_db_manager.delete_meeting(meeting_id)

# app.py
db = DatabaseManager(config.DATABASE_PATH, vector_db_manager=vdb_manager)
```

---

## 2️⃣ 보안 (OWASP Top 10)

### ✅ 잘 방어된 부분

#### 2.1 SQL Injection 방지

**평가**: ⭐⭐⭐⭐⭐ (5/5)

**근거**: 모든 SQL 쿼리가 파라미터화되어 있음

**코드 예시** (`utils/db_manager.py:326-342`):
```python
# ✅ Parameterized Query
def get_meeting_by_id(self, meeting_id):
    query = "SELECT * FROM meeting_dialogues WHERE meeting_id = ?"
    return self.execute_query(query, (meeting_id,)).fetchall()
```

---

#### 2.2 인증 토큰 검증

**평가**: ⭐⭐⭐⭐⭐ (5/5)

**근거**: Firebase Admin SDK로 서버 측 토큰 검증

**코드 위치**: `utils/firebase_auth.py:47-91`

```python
def verify_id_token(id_token):
    decoded_token = auth.verify_id_token(id_token)
    return {
        'uid': decoded_token['uid'],
        'email': decoded_token.get('email'),
        ...
    }
```

---

### ⚠️ 개선이 필요한 부분

#### 2.3 CSRF 보호

**문제**: Flask-WTF CSRF 토큰 미사용

**현재 상태**: 세션 쿠키만 사용

**개선안**:
```python
# config.py
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect()

# app.py
csrf.init_app(app)

# HTML 템플릿
<form method="POST">
    {{ csrf_token() }}
    ...
</form>
```

---

#### 2.4 Rate Limiting

**문제**: API 호출 제한 없음 → DoS 공격 가능

**개선안**: Flask-Limiter 사용
```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

@app.route("/api/login")
@limiter.limit("5 per minute")  # 1분에 5번만 허용
def login():
    ...
```

---

#### 2.5 파일 업로드 보안

**평가**: ⭐⭐⭐☆☆ (3/5)

**현재 방어**:
- ✅ 확장자 체크 (`allowed_file()`)
- ✅ 파일 크기 제한 (500MB)
- ✅ `secure_filename()` 사용

**개선 필요**:
- ❌ MIME 타입 검증 미흡

**개선안**:
```python
import magic

def validate_mime_type(file_path, expected_extension):
    """실제 파일 내용 기반 MIME 타입 검증"""
    mime = magic.Magic(mime=True)
    detected_mime = mime.from_file(file_path)

    allowed_mimes = {
        'mp3': 'audio/mpeg',
        'wav': 'audio/wav',
        'mp4': 'video/mp4',
        ...
    }

    if detected_mime != allowed_mimes.get(expected_extension):
        raise ValueError(f"파일 형식 불일치: {detected_mime}")
```

---

#### 2.6 로그에 민감 정보 노출

**문제**: API 키, 토큰이 로그에 노출될 가능성

**예시**:
```python
# ❌ 위험한 로깅
logger.info(f"사용자 로그인: {user_info}")  # user_info에 토큰 포함 가능
```

**개선안**:
```python
# ✅ 안전한 로깅
def sanitize_log(data):
    """민감 정보 마스킹"""
    sanitized = data.copy()
    if 'idToken' in sanitized:
        sanitized['idToken'] = '***REDACTED***'
    if 'api_key' in sanitized:
        sanitized['api_key'] = '***REDACTED***'
    return sanitized

logger.info(f"사용자 로그인: {sanitize_log(user_info)}")
```

---

## 3️⃣ 에러 처리 & 로깅

### ✅ 잘 구현된 부분

#### 3.1 JSON 파싱 에러 처리

**평가**: ⭐⭐⭐⭐⭐ (5/5)

**코드 위치**: `utils/stt.py:130-150`

```python
try:
    result_list = json.loads(cleaned_response)
except json.JSONDecodeError as e:
    logger.error(f"❌ JSON 파싱 실패: {e}")
    # 오류 위치 상세 로깅
    logger.info(f"📝 오류 위치: line {e.lineno}, column {e.colno}")
    # 전체 응답 파일로 저장 (디버깅용)
    with open('gemini_error_response.txt', 'w') as f:
        f.write(cleaned_response)
```

---

#### 3.2 권한 체크 레이어

**평가**: ⭐⭐⭐⭐☆ (4/5)

**코드 위치**: `utils/decorators.py:16-58`

```python
@login_required
@admin_required
def admin_dashboard():
    ...
```

**개선 필요**: 에러 메시지 일관성

---

### ⚠️ 개선이 필요한 부분

#### 3.3 전역 에러 핸들러

**문제**: 예외 발생 시 500 에러가 클라이언트에 노출

**개선안**:
```python
# app.py
@app.errorhandler(500)
def handle_500(error):
    logger.error(f"❌ Internal Server Error: {error}", exc_info=True)
    return jsonify({
        "error": "서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
    }), 500

@app.errorhandler(404)
def handle_404(error):
    return jsonify({"error": "요청한 리소스를 찾을 수 없습니다."}), 404

@app.errorhandler(Exception)
def handle_exception(error):
    logger.error(f"❌ Unhandled Exception: {error}", exc_info=True)
    return jsonify({
        "error": "예상치 못한 오류가 발생했습니다."
    }), 500
```

---

#### 3.4 로깅 레벨 통일

**문제**: 로깅 레벨이 일관되지 않음

**현재**:
```python
logger.info("✅ 파일 저장 완료")
logger.warning("⚠️  파일이 존재하지 않습니다")
logger.error("❌ 파일 삭제 실패")
```

**개선안**: 로깅 정책 문서화
```markdown
# 로깅 정책
- DEBUG: 개발 중 디버깅 정보
- INFO: 정상 동작 (✅ 아이콘)
- WARNING: 경고 (⚠️  아이콘)
- ERROR: 오류 (❌ 아이콘)
- CRITICAL: 치명적 오류 (🚨 아이콘)
```

---

## 4️⃣ 성능 최적화

### ✅ 잘 구현된 부분

#### 4.1 인덱스 생성

**평가**: ⭐⭐⭐⭐☆ (4/5)

**코드 위치**: `init_db.py:139-145`

```sql
CREATE INDEX idx_meeting_id ON meeting_dialogues(meeting_id);
CREATE INDEX idx_owner_id ON meeting_dialogues(owner_id);
CREATE INDEX idx_shares_meeting ON meeting_shares(meeting_id);
```

---

#### 4.2 스마트 청킹 알고리즘

**평가**: ⭐⭐⭐⭐⭐ (5/5)

**근거**: 의미 단위로 청킹하여 RAG 검색 정확도 향상

**코드 위치**: `utils/vector_db_manager.py:241-319`

---

### ⚠️ 개선이 필요한 부분

#### 4.3 N+1 쿼리 문제

**문제**: `routes/meetings.py:37-119`

```python
# ❌ N+1 쿼리
for meeting in owned:
    meeting['has_summary'] = vdb_manager.has_subtopic(meeting['meeting_id'])
    meeting['has_minutes'] = db.has_minutes(meeting['meeting_id'])
    # → 회의 개수만큼 쿼리 반복
```

**개선안**: 일괄 조회
```python
# ✅ 개선된 코드
meeting_ids = [m['meeting_id'] for m in owned]
summaries = vdb_manager.batch_has_subtopic(meeting_ids)  # 1번의 쿼리
minutes = db.batch_has_minutes(meeting_ids)  # 1번의 쿼리

for meeting in owned:
    meeting['has_summary'] = summaries.get(meeting['meeting_id'], False)
    meeting['has_minutes'] = minutes.get(meeting['meeting_id'], False)
```

---

#### 4.4 캐싱 전략

**문제**: 동일한 요약/회의록을 매번 재생성

**개선안**: Redis 캐시 도입
```python
import redis

cache = redis.Redis(host='localhost', port=6379, db=0)

def get_summary(meeting_id):
    # 1. 캐시 체크
    cached = cache.get(f"summary:{meeting_id}")
    if cached:
        return cached.decode('utf-8')

    # 2. 생성
    summary = stt_manager.subtopic_generate(...)

    # 3. 캐시 저장 (1시간 TTL)
    cache.setex(f"summary:{meeting_id}", 3600, summary)

    return summary
```

---

#### 4.5 Gemini API 비용 최적화

**현재**:
- STT: Gemini 2.5 Pro (비싸고 느림)
- 요약: Gemini 2.5 Pro
- 회의록: Gemini 2.5 Pro
- 마인드맵: Gemini 2.5 Flash (저렴하고 빠름)

**개선안**: 작업별 모델 선택
```python
# STT: Pro 필요 (화자 분리 정확도)
# 요약: Flash로도 충분 (간단한 요약)
# 회의록: Pro 유지 (템플릿 준수 필요)
# 마인드맵: Flash 유지
```

---

## 5️⃣ 코드 일관성 & 가독성

### ✅ 잘 구현된 부분

#### 5.1 명명 규칙 일관성

**평가**: ⭐⭐⭐⭐⭐ (5/5)

**근거**:
- 클래스: PascalCase (`DatabaseManager`)
- 함수: snake_case (`get_meeting_by_id`)
- 상수: UPPER_SNAKE_CASE (`MAX_FILE_SIZE_MB`)

---

#### 5.2 Docstring 작성

**평가**: ⭐⭐⭐☆☆ (3/5)

**근거**:
- ✅ 일부 함수에 docstring 존재
- ❌ 일관되지 않음 (일부 함수만 작성)

**개선안**: Google Style Docstring 통일
```python
def get_meeting_by_id(self, meeting_id):
    """
    회의 ID로 전사 세그먼트 조회

    Args:
        meeting_id (str): 회의 고유 ID (UUID)

    Returns:
        list: 세그먼트 딕셔너리 리스트 (start_time 순 정렬)

    Raises:
        ValueError: meeting_id가 빈 문자열인 경우
    """
    ...
```

---

### ⚠️ 개선이 필요한 부분

#### 5.3 매직 넘버 제거

**문제**: 하드코딩된 숫자

```python
# ❌ 매직 넘버
if current_length >= 500:  # 500이 무엇을 의미하는지 불명확
    ...

if time_gap > 60.0:  # 60초가 왜 기준인지 불명확
    ...
```

**개선안**: 상수로 정의
```python
# ✅ 상수 정의
SPEAKER_CHANGE_MIN_LENGTH = 500  # 화자 변경 감지 최소 길이
TIME_GAP_THRESHOLD_SECONDS = 60.0  # 주제 전환 감지 시간 간격

if current_length >= SPEAKER_CHANGE_MIN_LENGTH:
    ...

if time_gap > TIME_GAP_THRESHOLD_SECONDS:
    ...
```

---

#### 5.4 긴 함수 분리

**문제**: `routes/meetings.py:249-429` (180 lines)

**개선안**: 함수 분리
```python
# ❌ 하나의 긴 함수
def upload():
    def generate():
        # ... 180줄 ...

# ✅ 여러 작은 함수로 분리
def validate_upload_request(audio_file, title, meeting_date):
    ...

def process_audio_file(audio_path, meeting_id):
    ...

def save_to_databases(meeting_id, segments, ...):
    ...

def upload():
    def generate():
        validate_upload_request(...)
        audio_path = process_audio_file(...)
        save_to_databases(...)
```

---

## 6️⃣ 테스트 커버리지

### ⚠️ 개선이 필요한 부분

#### 6.1 단위 테스트 미흡

**문제**: `tests/` 디렉토리 없음

**개선안**: pytest로 단위 테스트 작성
```python
# tests/test_validation.py
import pytest
from utils.validation import validate_title, parse_meeting_date

def test_validate_title_empty():
    is_valid, error = validate_title("")
    assert is_valid == False
    assert "제목을 입력해 주세요" in error

def test_validate_title_valid():
    is_valid, error = validate_title("팀 회의")
    assert is_valid == True
    assert error is None

def test_parse_meeting_date_iso_format():
    result = parse_meeting_date("2025-11-08T14:00")
    assert result == "2025-11-08 14:00:00"
```

---

#### 6.2 통합 테스트

**개선안**:
```python
# tests/test_api.py
import pytest
from app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_login_without_token(client):
    response = client.post('/api/login', json={})
    assert response.status_code == 400

def test_meetings_list_unauthorized(client):
    response = client.get('/api/meetings')
    assert response.status_code == 401
```

---

## 7️⃣ 문서화

### ✅ 잘 작성된 부분

#### 7.1 README.md

**평가**: ⭐⭐⭐⭐⭐ (5/5)

**근거**: 기능, 설치 방법, 기술 스택 상세히 작성됨

---

### ⚠️ 개선이 필요한 부분

#### 7.2 API 문서 자동화

**개선안**: Swagger/OpenAPI 적용
```python
from flasgger import Swagger

swagger = Swagger(app)

@app.route("/api/meetings", methods=["GET"])
def get_meetings():
    """
    회의 목록 조회
    ---
    tags:
      - Meetings
    responses:
      200:
        description: 회의 목록
        schema:
          type: object
          properties:
            owned_meetings:
              type: array
            shared_meetings:
              type: array
    """
    ...
```

---

#### 7.3 환경 변수 문서화

**개선안**: `.env.example` 주석 추가
```bash
# Flask 설정
FLASK_SECRET_KEY=random-secret-key  # openssl rand -hex 32로 생성

# Google API
GOOGLE_API_KEY=your-gemini-api-key  # https://ai.google.dev/에서 발급

# Firebase 설정
FIREBASE_API_KEY=your-api-key  # Firebase Console > 프로젝트 설정
FIREBASE_PROJECT_ID=your-project-id
...

# Admin 설정
ADMIN_EMAILS=admin@example.com,admin2@example.com  # 쉼표로 구분
```

---

## 8️⃣ 종합 개선 제안 우선순위

### 🔴 긴급 (보안 관련)

1. **CSRF 보호 추가** (Flask-WTF)
2. **Rate Limiting 적용** (Flask-Limiter)
3. **MIME 타입 검증 강화** (python-magic)
4. **로그 민감 정보 마스킹**

---

### 🟡 중요 (성능 & 안정성)

1. **N+1 쿼리 개선** (일괄 조회)
2. **전역 에러 핸들러 추가**
3. **캐싱 전략 도입** (Redis)
4. **단위 테스트 작성** (pytest)

---

### 🟢 권장 (코드 품질)

1. **Docstring 일관성 확보**
2. **매직 넘버 상수화**
3. **긴 함수 분리 (SRP 원칙)**
4. **순환 참조 제거 (DI 적용)**

---

## 📈 코드 품질 점수

| 카테고리 | 점수 | 비고 |
|---------|------|------|
| **아키텍처** | 4.5/5 | 싱글톤 패턴, Blueprint 우수 |
| **보안** | 3.5/5 | SQL Injection 방지 우수, CSRF/Rate Limiting 미흡 |
| **에러 처리** | 4.0/5 | JSON 파싱 에러 처리 우수, 전역 핸들러 미흡 |
| **성능** | 3.8/5 | 인덱스 우수, N+1 쿼리 문제 존재 |
| **코드 일관성** | 4.2/5 | 명명 규칙 우수, Docstring 일관성 미흡 |
| **테스트** | 1.0/5 | 단위 테스트 없음 |
| **문서화** | 4.8/5 | README 우수, API 자동화 미흡 |
| **종합** | 3.7/5 | **양호, 일부 개선 필요** |

---

## 🎓 코드 리뷰 체크리스트 (출력용)

```markdown
## 코드 리뷰 체크리스트

### 보안
- [ ] CSRF 보호 추가 (Flask-WTF)
- [ ] Rate Limiting 적용 (Flask-Limiter)
- [ ] MIME 타입 검증 강화
- [ ] 로그에 API 키/토큰 노출 여부 확인

### 성능
- [ ] N+1 쿼리 개선
- [ ] 캐싱 전략 검토
- [ ] 인덱스 최적화 확인

### 에러 처리
- [ ] 전역 에러 핸들러 추가
- [ ] 모든 에러가 적절히 로깅되는지 확인
- [ ] 사용자 친화적인 에러 메시지 제공

### 코드 품질
- [ ] Docstring 작성 (Google Style)
- [ ] 매직 넘버 상수화
- [ ] 긴 함수(100줄 이상) 분리
- [ ] 순환 참조 제거

### 테스트
- [ ] 단위 테스트 작성 (pytest)
- [ ] 통합 테스트 작성
- [ ] 테스트 커버리지 70% 이상 목표

### 문서화
- [ ] API 문서 자동화 (Swagger)
- [ ] .env.example 주석 추가
- [ ] 아키텍처 다이어그램 업데이트
```

---

## 📞 관련 문서

- **아키텍처 문서**: `02_architecture.md`
- **API 명세서**: `11_api_specification.md`
- **유틸리티 상세**: `09_utils_detail.md`
