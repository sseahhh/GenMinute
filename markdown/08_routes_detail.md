# 08. 라우트 상세 분석 (1시간 읽기)

> **레벨 4**: 모든 HTTP 엔드포인트의 상세 구현 및 비즈니스 로직 분석

---

## 🎯 이 문서에서 다루는 내용

1. **Blueprint 구조**: 5개 라우트 모듈의 역할 분담
2. **auth 라우트**: 로그인/로그아웃 흐름
3. **meetings 라우트**: 회의 CRUD 및 파일 업로드
4. **summary 라우트**: 요약 및 회의록 생성
5. **chat 라우트**: RAG 챗봇 질의응답
6. **admin 라우트**: 관리자 전용 디버그 도구

---

## 📊 Blueprint 아키텍처

### 구조 다이어그램

```
app.py
    ↓
register_blueprints()
    ↓
┌─────────────────────────────────────────┐
│  1. auth_bp (prefix: /auth)             │
│     - /auth/login_page                  │
│     - /api/login                        │
│     - /api/logout                       │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│  2. meetings_bp (prefix: /)             │
│     - /api/meetings (CRUD)              │
│     - /api/upload (SSE streaming)       │
│     - /notes/<meeting_id> (viewer)      │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│  3. summary_bp (prefix: /)              │
│     - /api/summarize/<meeting_id>       │
│     - /api/generate_minutes/<...>       │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│  4. chat_bp (prefix: /)                 │
│     - /api/chat                         │
└─────────────────────────────────────────┘
┌─────────────────────────────────────────┐
│  5. admin_bp (prefix: /admin)           │
│     - /admin/dashboard                  │
│     - /admin/api/search_vector          │
└─────────────────────────────────────────┘
```

**등록 코드** (`routes/__init__.py:7-30`):
```python
def register_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(meetings_bp)
    app.register_blueprint(summary_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(admin_bp)
```

---

## 1️⃣ Auth 라우트 (routes/auth.py)

### 1.1 로그인 페이지 렌더링

**엔드포인트**: `GET /auth/login_page`

**코드 위치**: `routes/auth.py:21-27`

```python
@auth_bp.route("/login_page")
def login_page():
    """Google OAuth 로그인 페이지 렌더링"""
    return render_template("login.html")
```

**응답**: `templates/login.html` (Firebase Auth UI 포함)

---

### 1.2 로그인 처리 (Firebase ID Token 검증)

**엔드포인트**: `POST /api/login`

**코드 위치**: `routes/auth.py:30-98`

**요청 예시**:
```bash
curl -X POST http://localhost:5050/api/login \
  -H "Content-Type: application/json" \
  -d '{"idToken": "eyJhbGciOiJSUzI1NiIsImtpZCI6..."}'
```

**처리 흐름**:
```python
def login():
    # 1. 요청 본문에서 idToken 추출
    id_token = request.json.get('idToken')

    # 2. Firebase Admin SDK로 토큰 검증
    user_info = verify_id_token(id_token)
    # → {
    #     'uid': 'abc123',
    #     'email': 'user@example.com',
    #     'name': 'John Doe',
    #     'picture': 'https://...'
    #   }

    # 3. SQLite에서 사용자 조회 또는 생성
    user = get_or_create_user(
        google_id=user_info['uid'],
        email=user_info['email'],
        name=user_info.get('name'),
        profile_picture=user_info.get('picture')
    )

    # 4. Flask 세션에 사용자 ID 저장
    session['user_id'] = user['id']
    session['email'] = user['email']
    session['name'] = user['name']

    # 5. 성공 응답
    return jsonify({
        "success": True,
        "user": {
            "name": user['name'],
            "email": user['email'],
            "role": user['role']
        }
    })
```

**에러 처리**:
- 토큰 없음 → `400 Bad Request`
- 토큰 검증 실패 → `401 Unauthorized`
- DB 에러 → `500 Internal Server Error`

---

### 1.3 로그아웃

**엔드포인트**: `POST /api/logout`

**코드 위치**: `routes/auth.py:101-138`

```python
@auth_bp.route("/api/logout", methods=["POST"])
@login_required
def logout():
    # 세션 초기화
    session.clear()

    return jsonify({
        "success": True,
        "message": "로그아웃되었습니다."
    })
```

---

## 2️⃣ Meetings 라우트 (routes/meetings.py)

### 2.1 회의 목록 조회

**엔드포인트**: `GET /api/meetings`

**코드 위치**: `routes/meetings.py:37-119`

**응답 예시**:
```json
{
  "owned_meetings": [
    {
      "meeting_id": "abc123",
      "title": "팀 회의",
      "meeting_date": "2025-11-08 14:00:00",
      "audio_file": "abc123_audio.wav",
      "has_summary": true,
      "has_minutes": true
    }
  ],
  "shared_meetings": [
    {
      "meeting_id": "def456",
      "title": "임원 회의",
      "owner_name": "김철수",
      "permission": "read"
    }
  ]
}
```

**처리 흐름**:
```python
def get_meetings():
    user_id = session['user_id']

    # 1. 본인이 소유한 회의
    owned = db.get_user_meetings(user_id)

    # 2. 공유받은 회의
    shared = get_shared_meetings_for_user(user_id)

    # 3. 각 회의의 요약/회의록 존재 여부 확인
    for meeting in owned:
        meeting['has_summary'] = vdb_manager.has_subtopic(meeting['meeting_id'])
        meeting['has_minutes'] = db.has_minutes(meeting['meeting_id'])

    return jsonify({
        "owned_meetings": owned,
        "shared_meetings": shared
    })
```

---

### 2.2 회의 상세 조회

**엔드포인트**: `GET /api/meetings/<meeting_id>`

**코드 위치**: `routes/meetings.py:122-182`

**응답 예시**:
```json
{
  "meeting_id": "abc123",
  "title": "팀 회의",
  "meeting_date": "2025-11-08 14:00:00",
  "segments": [
    {
      "speaker_label": "1",
      "start_time": 0.0,
      "segment": "안녕하세요. 회의 시작하겠습니다.",
      "confidence": 0.95
    }
  ],
  "speaker_stats": {
    "labels": ["화자 1", "화자 2"],
    "data": [60, 40]
  }
}
```

**권한 체크**:
```python
if not can_access_meeting(user_id, meeting_id):
    return jsonify({"error": "접근 권한이 없습니다."}), 403
```

---

### 2.3 회의 생성 (메타데이터만)

**엔드포인트**: `POST /api/meetings`

**코드 위치**: `routes/meetings.py:185-246`

**요청 예시**:
```json
{
  "title": "팀 회의",
  "meeting_date": "2025-11-08T14:00"
}
```

**처리 흐름**:
```python
def create_meeting():
    # 1. 제목 검증
    is_valid, error = validate_title(title)
    if not is_valid:
        return jsonify({"error": error}), 400

    # 2. UUID 생성
    meeting_id = str(uuid.uuid4())

    # 3. 날짜 파싱
    meeting_date_str = parse_meeting_date(meeting_date)

    # 4. DB에 더미 레코드 생성 (업로드 전)
    db.execute_query("""
        INSERT INTO meeting_dialogues
        (meeting_id, title, meeting_date, owner_id, segment)
        VALUES (?, ?, ?, ?, ?)
    """, (meeting_id, title, meeting_date_str, user_id, ""))

    return jsonify({"meeting_id": meeting_id})
```

---

### 2.4 파일 업로드 (SSE Streaming)

**엔드포인트**: `POST /api/upload`

**코드 위치**: `routes/meetings.py:249-429`

**요청 예시** (multipart/form-data):
```bash
curl -X POST http://localhost:5050/api/upload \
  -F "audio=@meeting.mp3" \
  -F "title=팀 회의" \
  -F "meeting_date=2025-11-08T14:00"
```

**SSE 스트리밍 응답**:
```
data: {"step":"upload","message":"파일 업로드 중...","icon":"📤","progress":0}

data: {"step":"validation","message":"파일 검증 중...","icon":"🔍","progress":10}

data: {"step":"conversion","message":"비디오 변환 중...","icon":"🎬","progress":20}

data: {"step":"stt","message":"음성 인식 중...","icon":"🎤","progress":40}

data: {"step":"chunking","message":"스마트 청킹 중...","icon":"📝","progress":70}

data: {"step":"mindmap","message":"마인드맵 생성 중...","icon":"🗺️","progress":90}

data: {"step":"complete","message":"완료!","meeting_id":"abc123","progress":100}
```

**전체 처리 흐름**:
```python
def upload():
    def generate():
        # 1. 파일 업로드 및 검증
        yield sse_event("upload", "파일 업로드 중...", progress=0)
        audio_path = upload_service.save_file(audio_file, meeting_id)

        # 2. 비디오 변환 (MP4인 경우)
        yield sse_event("conversion", "비디오 변환 중...", progress=20)
        if is_video:
            audio_path = upload_service.convert_video_to_audio(audio_path)

        # 3. STT 처리
        yield sse_event("stt", "음성 인식 중...", progress=40)
        segments = stt_manager.transcribe_audio(audio_path)

        # 4. DB 저장
        yield sse_event("db", "데이터베이스 저장 중...", progress=60)
        db.save_meeting_data(meeting_id, segments, ...)

        # 5. 스마트 청킹 + ChromaDB 저장
        yield sse_event("chunking", "스마트 청킹 중...", progress=70)
        vdb_manager.add_meeting(meeting_id, ...)

        # 6. 마인드맵 생성
        yield sse_event("mindmap", "마인드맵 생성 중...", progress=90)
        mindmap_content = stt_manager.extract_mindmap_keywords(...)
        db.save_mindmap(meeting_id, mindmap_content)

        # 7. 완료
        yield sse_event("complete", "완료!", meeting_id=meeting_id, progress=100)

    return Response(generate(), mimetype='text/event-stream')
```

---

### 2.5 회의 수정

**엔드포인트**: `PATCH /api/meetings/<meeting_id>`

**코드 위치**: `routes/meetings.py:432-476`

**요청 예시**:
```json
{
  "title": "수정된 팀 회의 제목"
}
```

**처리**:
```python
def update_meeting(meeting_id):
    # 1. 소유자 확인
    if not can_edit_meeting(user_id, meeting_id):
        return 403

    # 2. 제목 업데이트
    db.execute_query("""
        UPDATE meeting_dialogues
        SET title = ?
        WHERE meeting_id = ?
    """, (new_title, meeting_id))

    # 3. ChromaDB 메타데이터도 업데이트
    vdb_manager.update_meeting_metadata(meeting_id, title=new_title)
```

---

### 2.6 회의 삭제

**엔드포인트**: `DELETE /api/meetings/<meeting_id>`

**코드 위치**: `routes/meetings.py:479-517`

**처리 흐름**:
```python
def delete_meeting(meeting_id):
    # 1. 소유자 확인
    if not can_edit_meeting(user_id, meeting_id):
        return 403

    # 2. DB 삭제 (SQLite + ChromaDB 모두)
    db.delete_meeting(meeting_id)

    # 3. 파일 삭제
    audio_file_path = get_audio_file_path(meeting_id)
    if os.path.exists(audio_file_path):
        os.remove(audio_file_path)
```

---

### 2.7 회의 공유

**엔드포인트**: `POST /api/meetings/<meeting_id>/share`

**코드 위치**: `routes/meetings.py:520-562`

**요청 예시**:
```json
{
  "email": "colleague@example.com",
  "permission": "read"
}
```

**처리**:
```python
def share_meeting(meeting_id):
    # 1. 소유자 확인
    if not can_edit_meeting(user_id, meeting_id):
        return 403

    # 2. 대상 사용자 조회
    target_user = get_user_by_email(email)
    if not target_user:
        return 404

    # 3. 공유 테이블에 INSERT
    share_meeting(
        meeting_id=meeting_id,
        owner_id=user_id,
        shared_user_id=target_user['id'],
        permission=permission
    )
```

---

### 2.8 회의 공유 해제

**엔드포인트**: `DELETE /api/meetings/<meeting_id>/share/<user_id>`

**코드 위치**: `routes/meetings.py:565-603`

---

## 3️⃣ Summary 라우트 (routes/summary.py)

### 3.1 문단 요약 생성

**엔드포인트**: `POST /api/summarize/<meeting_id>`

**코드 위치**: `routes/summary.py:25-90`

**처리 흐름**:
```python
def summarize(meeting_id):
    # 1. 전사 내용 조회
    rows = db.get_meeting_by_id(meeting_id)
    transcript_text = " ".join([row['segment'] for row in rows])

    # 2. Gemini로 요약 생성
    summary_content = stt_manager.subtopic_generate(title, transcript_text)

    # 3. ChromaDB에 저장
    vdb_manager.add_meeting_as_subtopic(
        meeting_id, title, meeting_date, audio_file, summary_content
    )

    return jsonify({
        "success": True,
        "summary": summary_content
    })
```

---

### 3.2 요약 존재 여부 확인

**엔드포인트**: `GET /api/check_summary/<meeting_id>`

**코드 위치**: `routes/summary.py:93-136`

**응답 예시**:
```json
{
  "success": true,
  "has_summary": true,
  "summary": "### 주제 1\n* 내용..."
}
```

---

### 3.3 회의록 생성

**엔드포인트**: `POST /api/generate_minutes/<meeting_id>`

**코드 위치**: `routes/summary.py:139-211`

**처리 흐름**:
```python
def generate_minutes(meeting_id):
    # 1. 전사 내용 + 청크 조회
    transcript_text = ...
    chunks_content = vdb_manager.get_chunks_by_meeting_id(meeting_id)

    # 2. Gemini로 회의록 생성
    minutes_content = stt_manager.generate_minutes(
        title, transcript_text, chunks_content, meeting_date
    )

    # 3. SQLite에 저장
    db.save_minutes(meeting_id, title, meeting_date, minutes_content)
```

---

### 3.4 회의록 조회

**엔드포인트**: `GET /api/get_minutes/<meeting_id>`

**코드 위치**: `routes/summary.py:214-259`

---

## 4️⃣ Chat 라우트 (routes/chat.py)

### 4.1 챗봇 질의응답

**엔드포인트**: `POST /api/chat`

**코드 위치**: `routes/chat.py:23-85`

**요청 예시**:
```json
{
  "query": "이번 회의의 주요 결정 사항은?",
  "meeting_id": "abc123"  // Optional
}
```

**처리 흐름**:
```python
def chat():
    user_id = session['user_id']
    query = data.get('query')
    meeting_id = data.get('meeting_id')  # Optional

    # 1. 권한 기반 접근 가능한 노트 목록
    if meeting_id:
        if not can_access_meeting(user_id, meeting_id):
            return 403
        accessible_meeting_ids = [meeting_id]
    else:
        accessible_meeting_ids = get_user_accessible_meeting_ids(user_id)

    # 2. RAG 처리
    result = chat_manager.process_query(
        query=query,
        accessible_meeting_ids=accessible_meeting_ids
    )

    return jsonify(result)
```

**응답 예시**:
```json
{
  "success": true,
  "answer": "주요 결정 사항은...",
  "sources": [
    {"type": "chunk", "meeting_id": "abc123", "title": "팀 회의", ...}
  ]
}
```

---

## 5️⃣ Admin 라우트 (routes/admin.py)

### 5.1 Admin 대시보드

**엔드포인트**: `GET /admin/dashboard`

**코드 위치**: `routes/admin.py:26-50`

**권한 체크**:
```python
@admin_bp.route("/dashboard")
@login_required
@admin_required
def dashboard():
    return render_template("admin_dashboard.html")
```

---

### 5.2 벡터 검색 테스트

**엔드포인트**: `POST /admin/api/search_vector`

**코드 위치**: `routes/admin.py:53-155`

**요청 예시**:
```json
{
  "query": "예산",
  "db_type": "chunks",
  "k": 5
}
```

**응답 예시**:
```json
{
  "success": true,
  "results": [
    {
      "content": "예산은 500만원으로...",
      "metadata": {"meeting_id": "abc123", "title": "팀 회의", ...},
      "score": 0.87
    }
  ]
}
```

---

### 5.3 스크립트 입력 테스트

**엔드포인트**: `POST /admin/api/script_input`

**코드 위치**: `routes/admin.py:158-293`

**목적**: 음성 파일 없이 텍스트 스크립트로 회의 생성 (테스트용)

**요청 예시**:
```json
{
  "title": "테스트 회의",
  "script_text": "화자1: 안녕하세요\n화자2: 반갑습니다",
  "meeting_date": "2025-11-08T14:00"
}
```

---

## 📈 엔드포인트 요약표

| 경로 | 메서드 | 인증 | Admin | 설명 |
|------|--------|------|-------|------|
| `/auth/login_page` | GET | ❌ | ❌ | 로그인 페이지 |
| `/api/login` | POST | ❌ | ❌ | Firebase 로그인 |
| `/api/logout` | POST | ✅ | ❌ | 로그아웃 |
| `/api/meetings` | GET | ✅ | ❌ | 회의 목록 |
| `/api/meetings/<id>` | GET | ✅ | ❌ | 회의 상세 |
| `/api/meetings` | POST | ✅ | ❌ | 회의 생성 |
| `/api/meetings/<id>` | PATCH | ✅ | ❌ | 회의 수정 |
| `/api/meetings/<id>` | DELETE | ✅ | ❌ | 회의 삭제 |
| `/api/upload` | POST | ✅ | ❌ | 파일 업로드 (SSE) |
| `/api/summarize/<id>` | POST | ✅ | ❌ | 문단 요약 생성 |
| `/api/generate_minutes/<id>` | POST | ✅ | ❌ | 회의록 생성 |
| `/api/chat` | POST | ✅ | ❌ | 챗봇 질의응답 |
| `/admin/dashboard` | GET | ✅ | ✅ | Admin 대시보드 |
| `/admin/api/search_vector` | POST | ✅ | ✅ | 벡터 검색 테스트 |

---

## 🎓 학습 포인트

1. **Blueprint 패턴**: 기능별 라우트 분리로 코드 구조화
2. **SSE Streaming**: 긴 작업의 진행 상황 실시간 전달
3. **권한 데코레이터**: `@login_required`, `@admin_required`로 일관된 보안
4. **RESTful API**: HTTP 메서드와 URL 구조의 일관성
5. **에러 핸들링**: 각 엔드포인트에서 적절한 HTTP 상태 코드 반환

---

## 📞 다음 단계

- **유틸리티 함수 심화**: `09_utils_detail.md`로 이동
- **API 전체 명세**: `11_api_specification.md` 참고
