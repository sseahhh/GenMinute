# 02. 시스템 아키텍처 (15분 읽기)

> **레벨 2**: 전체 시스템 구조와 계층별 역할 이해

---

## 🏗️ 아키텍처 개요

Minute AI는 **계층형 아키텍처(Layered Architecture)**를 채택하여 관심사를 분리했습니다.

```
┌─────────────────────────────────────────────────────┐
│                  Presentation Layer                  │
│              (templates/ + static/)                  │
│           Jinja2 템플릿, JavaScript, CSS              │
└─────────────────────────────────────────────────────┘
                        ↓ HTTP Request
┌─────────────────────────────────────────────────────┐
│                   Application Layer                  │
│                      (app.py)                        │
│        Flask 앱 초기화, Blueprint 등록, 설정          │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│                    Route Layer                       │
│                    (routes/)                         │
│    auth, meetings, summary, chat, admin Blueprint    │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│                   Service Layer                      │
│                   (services/)                        │
│              upload_service (비즈니스 로직)            │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│                Infrastructure Layer                  │
│                     (utils/)                         │
│  STT, DB, VectorDB, Chat, Auth, User, Validation    │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│                   Data Layer                         │
│              (database/, uploads/)                   │
│           SQLite, ChromaDB, 오디오 파일               │
└─────────────────────────────────────────────────────┘
```

---

## 📂 디렉토리 구조 상세

### 1. **app.py** (Application Entry Point)

**역할**:
- Flask 앱 인스턴스 생성
- 환경 변수 로드 (config.py 사용)
- Firebase 초기화
- 데이터베이스 매니저 초기화
- Blueprint 등록
- Context Processor 설정 (모든 템플릿에 user 정보 주입)
- 에러 핸들러 등록

**핵심 코드 흐름**:
```python
app.py:30     → Flask 앱 생성
app.py:40     → Firebase 초기화
app.py:49     → DatabaseManager 초기화
app.py:52     → VectorDBManager에 db_manager 주입
app.py:58-82  → Context Processor (is_admin, user_info 주입)
app.py:86     → register_blueprints(app)
app.py:126    → app.run()
```

---

### 2. **config.py** (Configuration Management)

**역할**:
- 환경 변수 중앙 관리
- .env 파일 로드
- 필수 변수 검증
- 디렉토리 자동 생성

**주요 설정**:
```python
- BASE_DIR, UPLOAD_FOLDER, DATABASE_PATH
- FLASK_SECRET_KEY, DEBUG, PORT
- FIREBASE_API_KEY (7개 항목)
- GOOGLE_API_KEY, OPENAI_API_KEY
- ALLOWED_EXTENSIONS, MAX_FILE_SIZE_MB
- CHUNK_SIZE, TIME_GAP_THRESHOLD_SECONDS
- ADMIN_EMAILS (관리자 이메일 리스트)
```

**싱글톤 인스턴스**:
```python
config = Config()  # 전역에서 import하여 사용
```

---

### 3. **routes/** (Blueprint Layer)

Flask Blueprint 패턴으로 라우트를 모듈화했습니다.

#### 3.1 `auth.py` (인증 관련)
```python
/login                  → 로그인 페이지
/api/login              → Firebase ID 토큰 검증 + 세션 생성
/api/logout             → 세션 삭제
/api/me                 → 현재 사용자 정보
```

#### 3.2 `meetings.py` (회의 관리)
```python
/                       → 메인 페이지 (업로드)
/notes                  → 내 노트 목록
/shared-notes           → 공유받은 노트 목록
/view/<meeting_id>      → 회의록 뷰어

/upload                 → 파일 업로드 (SSE 스트리밍)
/api/meeting/<id>       → 회의 데이터 조회
/api/delete_meeting/<id>→ 회의 삭제
/api/update_title/<id>  → 제목 수정
/api/update_date/<id>   → 날짜 수정

/api/share/<id>         → 노트 공유
/api/shared_users/<id>  → 공유 사용자 목록
/api/unshare/<id>/<uid> → 공유 해제

/api/mindmap/<id>       → 마인드맵 조회
```

#### 3.3 `summary.py` (요약 & 회의록)
```python
/api/summarize/<id>         → 문단 요약 생성
/api/check_summary/<id>     → 요약 존재 여부
/api/generate_minutes/<id>  → 회의록 생성
/api/get_minutes/<id>       → 회의록 조회
```

#### 3.4 `chat.py` (챗봇)
```python
/api/chat  → RAG 기반 챗봇 Q&A
```

#### 3.5 `admin.py` (관리자 전용)
```python
/retriever              → 검색 테스트 페이지
/api/search             → Vector DB 검색 테스트
/upload_script          → 스크립트 직접 입력 (테스트용)
/summary_template       → 요약 템플릿 테스트
/test-*                 → 각종 테스트 페이지
```

---

### 4. **services/** (Business Logic Layer)

#### `upload_service.py`

**역할**: 파일 업로드 전체 프로세스 관리

**클래스**: `UploadService` (싱글톤)

**주요 메서드**:
```python
validate_file()              → 파일 검증
save_uploaded_file()         → 파일 저장 (UUID 추가)
convert_video_to_audio()     → ffmpeg 비디오 변환
process_audio_file()         → STT → DB 저장
generate_summary()           → 요약 + 마인드맵 생성
cleanup_temp_files()         → 임시 파일 삭제
```

**의존성**:
- `STTManager`: Gemini STT
- `DatabaseManager`: SQLite 저장
- `VectorDBManager`: ChromaDB 저장

---

### 5. **utils/** (Infrastructure Layer)

#### 5.1 `stt.py` - **STTManager**

**역할**: Gemini API를 이용한 STT 및 AI 처리

**싱글톤 클래스**: `STTManager`

**주요 메서드**:
```python
transcribe_audio(audio_path)
    → Gemini 2.5 Pro로 음성 인식
    → 화자 분리 + 타임스탬프 + 신뢰도 반환

subtopic_generate(title, transcript_text)
    → Gemini 2.5 Pro로 주제별 요약 생성
    → [cite: N] 형식 인용 포함

generate_minutes(title, transcript, summary, date)
    → Gemini 2.5 Pro로 정식 회의록 생성
    → 마크다운 템플릿 기반

extract_mindmap_keywords(summary_content, title)
    → Gemini 2.5 Flash로 마인드맵 키워드 추출
    → Markmap 호환 마크다운 반환

parse_script(script_text)
    → 스크립트 텍스트 → segments 형식 변환 (테스트용)
```

---

#### 5.2 `db_manager.py` - **DatabaseManager**

**역할**: SQLite 데이터베이스 CRUD 작업

**싱글톤 클래스**: `DatabaseManager`

**주요 메서드**:
```python
save_stt_to_db(segments, audio_filename, title, meeting_date, owner_id)
    → meeting_dialogues 테이블에 세그먼트 저장
    → meeting_id (UUID) 반환

get_meeting_by_id(meeting_id)
    → 회의 전사 내용 조회 (start_time 순)

save_minutes(meeting_id, title, meeting_date, minutes_content, owner_id)
    → meeting_minutes 테이블에 회의록 저장/업데이트

get_minutes_by_meeting_id(meeting_id)
    → 회의록 조회

save_mindmap(meeting_id, mindmap_content)
    → meeting_mindmap 테이블에 저장

delete_meeting_by_id(meeting_id)
    → 회의 삭제 (dialogues, minutes, shares, mindmap 모두)
    → 삭제 전후 검증 로그 포함

update_meeting_title(meeting_id, new_title)
    → ChromaDB + SQLite 동시 업데이트
    → 트랜잭션 관리

update_meeting_date(meeting_id, new_date)
    → ChromaDB + SQLite 동시 업데이트
```

---

#### 5.3 `vector_db_manager.py` - **VectorDBManager**

**역할**: ChromaDB 벡터 데이터베이스 관리

**싱글톤 클래스**: `VectorDBManager`

**컬렉션**:
```python
meeting_chunks    → 스마트 청킹된 회의 전사본
meeting_subtopic  → 주제별 요약
```

**주요 메서드**:
```python
add_meeting_as_chunk(meeting_id, title, meeting_date, audio_file, segments)
    → 스마트 청킹 → 정규표현식으로 화자/타임스탬프 제거
    → OpenAI Embeddings → ChromaDB 저장

add_meeting_as_subtopic(meeting_id, title, meeting_date, audio_file, summary_content)
    → 요약을 ### 제목별로 분리 → Embeddings → ChromaDB 저장

search(db_type, query, k, retriever_type, filter_criteria, ...)
    → retriever_type: similarity | mmr | self_query | similarity_score_threshold
    → LangChain retriever 사용

get_chunks_by_meeting_id(meeting_id)
    → chunk_index 순서대로 청크 조회 → 하나의 문자열로 결합

get_summary_by_meeting_id(meeting_id)
    → summary_index 순서대로 요약 조회

delete_from_collection(db_type, meeting_id, audio_file, title)
    → db_type="all"이면 SQLite + Vector DB + 오디오 파일 모두 삭제
    → 삭제 전후 검증 로그 포함

update_metadata_title(meeting_id, new_title)
    → ChromaDB 메타데이터 일괄 업데이트

update_metadata_date(meeting_id, new_date)
    → ChromaDB 메타데이터 일괄 업데이트
```

**스마트 청킹 알고리즘** (`_create_smart_chunks`):
```python
청크 분리 조건:
1. 청크 크기 > max_chunk_size (1000자)
2. 시간 간격 > time_gap_threshold (60초)
3. 화자 변경 AND 청크 크기 > 500자

→ 의미적 일관성 유지
```

---

#### 5.4 `chat_manager.py` - **ChatManager**

**역할**: RAG 기반 챗봇 로직

**싱글톤 클래스**: `ChatManager`

**주요 메서드**:
```python
search_documents(query, meeting_id, accessible_meeting_ids)
    → meeting_chunks에서 3개 검색
    → meeting_subtopic에서 3개 검색
    → 총 6개 문서 반환

format_context(search_results)
    → 검색된 문서를 Gemini 프롬프트용 텍스트로 포맷팅
    → 메타데이터 (회의명, 일시, 시간대) 포함

generate_answer(query, context)
    → Gemini 2.5 Flash로 답변 생성
    → 프롬프트: "반드시 컨텍스트 안에서만 답변"

process_query(query, meeting_id, accessible_meeting_ids)
    → 전체 프로세스 통합
    → 검색 → 컨텍스트 구성 → 답변 생성 → 출처 정보 반환
```

---

#### 5.5 `firebase_auth.py`

**역할**: Firebase Admin SDK 초기화 및 토큰 검증

**함수**:
```python
initialize_firebase()
    → firebase-adminsdk.json 로드
    → Firebase Admin SDK 초기화 (전역 1회)

verify_id_token(id_token)
    → 프론트엔드에서 받은 ID Token 검증
    → {uid, email, name, picture} 반환

get_user_by_uid(uid)
    → Firebase UID로 사용자 정보 조회
```

---

#### 5.6 `user_manager.py`

**역할**: 사용자 CRUD 및 권한 관리

**주요 함수**:
```python
get_or_create_user(google_id, email, name, profile_picture)
    → 사용자 조회/생성 (더미 계정 migrate 포함)
    → config.ADMIN_EMAILS 기반으로 role 설정

get_user_by_id(user_id)
get_user_by_email(email)

is_admin(user_id)
    → role == 'admin' 체크

can_access_meeting(user_id, meeting_id)
    → Admin | Owner | Shared User 중 하나면 True

can_edit_meeting(user_id, meeting_id)
    → Admin | Owner만 True (공유받은 사람은 읽기만 가능)

get_user_meetings(user_id)
    → Admin: 모든 노트, User: 본인 노트만

get_shared_meetings(user_id)
    → 공유받은 노트 목록

share_meeting(meeting_id, owner_id, shared_with_email)
    → meeting_shares 테이블에 공유 관계 생성

get_shared_users(meeting_id)
    → 공유받은 사용자 목록 조회

remove_share(meeting_id, owner_id, shared_user_id)
    → 공유 관계 삭제

get_user_accessible_meeting_ids(user_id)
    → 사용자가 접근 가능한 모든 meeting_id 목록 (챗봇용)
```

---

#### 5.7 `decorators.py`

**역할**: Flask 라우트 데코레이터

**데코레이터**:
```python
@login_required
    → session에 user_id가 없으면 로그인 페이지로 리다이렉트
    → API 요청이면 401 JSON 응답

@admin_required
    → @login_required + is_admin() 체크
    → Admin이 아니면 403 에러

@optional_login
    → 로그인 선택적 (현재 미사용)
```

---

#### 5.8 `validation.py`

**역할**: 입력 검증 및 날짜 파싱

**함수**:
```python
validate_title(title)
    → 빈 문자열 체크
    → (is_valid, error_message) 반환

parse_meeting_date(meeting_date)
    → "YYYY-MM-DDTHH:MM" → "YYYY-MM-DD HH:MM:SS"
    → 빈 값이면 현재 시간 반환

get_current_datetime_string()
    → 현재 시간을 "YYYY-MM-DD HH:MM:SS" 형식으로
```

---

#### 5.9 `analysis.py`

**역할**: 화자 비중 분석

**함수**:
```python
calculate_speaker_share(meeting_id)
    → 화자별 발언 글자 수 합산
    → 전체 대비 비율 계산
    → Chart.js 형식으로 반환: {labels: [...], data: [...]}
```

---

## 🔄 데이터 흐름

### 예시: 파일 업로드 → 회의록 생성 전체 흐름

```
[사용자] POST /upload
    ↓
meetings.py:upload_and_process()
    ↓
upload_service.validate_file()           # 파일 검증
    ↓
upload_service.save_uploaded_file()      # UUID 추가하여 저장
    ↓
upload_service.convert_video_to_audio()  # MP4면 WAV로 변환
    ↓
upload_service.process_audio_file()
    ├─ stt_manager.transcribe_audio()    # Gemini STT
    ├─ db_manager.save_stt_to_db()       # SQLite 저장
    └─ vdb_manager.add_meeting_as_chunk()# ChromaDB 저장
    ↓
upload_service.generate_summary()
    ├─ stt_manager.subtopic_generate()   # Gemini 요약
    ├─ vdb_manager.add_meeting_as_subtopic()
    └─ stt_manager.extract_mindmap_keywords()
        └─ db_manager.save_mindmap()
    ↓
[SSE 스트리밍으로 각 단계 진행상황 전송]
    ↓
[완료] redirect to /view/{meeting_id}
```

---

## 🔐 인증 & 권한 흐름

```
[사용자] Google 로그인 클릭
    ↓
Firebase SDK (클라이언트)
    ↓
POST /api/login {idToken}
    ↓
firebase_auth.verify_id_token(idToken)   # Firebase Admin SDK
    ↓
user_manager.get_or_create_user()        # users 테이블 조회/생성
    ↓
session['user_id'] = user['id']          # Flask 세션 생성
session['email'], session['role'], ...
    ↓
[이후 모든 요청]
    ↓
@login_required 데코레이터
    ├─ session['user_id'] 체크
    └─ 없으면 401 또는 /login 리다이렉트
    ↓
라우트 핸들러
    ├─ can_access_meeting(user_id, meeting_id)
    └─ can_edit_meeting(user_id, meeting_id)
```

---

## 🧩 싱글톤 패턴 의존성 그래프

```
app.py
  ├─ config (싱글톤)
  ├─ DatabaseManager (싱글톤)
  │   └─ SQLite Connection Pool
  ├─ VectorDBManager (싱글톤)
  │   ├─ ChromaDB PersistentClient
  │   ├─ OpenAI Embeddings
  │   └─ db_manager (주입)
  ├─ STTManager (싱글톤)
  │   └─ Gemini Client
  ├─ ChatManager (싱글톤)
  │   ├─ vdb_manager (주입)
  │   └─ Gemini Client
  └─ UploadService (싱글톤)
      ├─ stt_manager
      ├─ db_manager
      └─ vdb_manager
```

**장점**:
- 리소스 효율화 (API 클라이언트, DB 커넥션 재사용)
- 전역 상태 관리 용이
- 의존성 주입으로 테스트 가능

---

## 📊 성능 최적화 전략

### 1. **데이터베이스 최적화**
- SQLite Row factory 사용 (딕셔너리 접근)
- meeting_id, owner_id에 인덱스 자동 생성 (UNIQUE, FOREIGN KEY)
- 트랜잭션 사용 (commit 일괄 처리)

### 2. **벡터 DB 최적화**
- 스마트 청킹으로 문서 수 감소 (검색 속도 향상)
- ChromaDB PersistentClient로 메모리 효율화
- 필터링된 검색으로 연산량 감소

### 3. **캐싱**
- Firebase SDK 초기화 전역 캐싱 (1회만 실행)
- 싱글톤 매니저로 인스턴스 재사용

### 4. **비동기 처리**
- SSE (Server-Sent Events) 스트리밍으로 긴 작업 처리
- 사용자는 실시간 진행상황 확인 가능

---

## 🚨 에러 핸들링 전략

### 1. **계층별 에러 처리**
```python
Route Layer
    ├─ try-except로 500 에러 방지
    └─ JSON 에러 응답: {"success": False, "error": "..."}

Service Layer
    ├─ 비즈니스 로직 검증
    └─ ValueError, FileNotFoundError 등 명시적 예외

Utils Layer
    ├─ API 호출 실패 처리
    └─ 폴백 로직 (예: self_query 실패 → similarity search)
```

### 2. **로깅**
```python
logger = logging.getLogger(__name__)
logger.info("✅ 정상 동작")
logger.warning("⚠️ 경고")
logger.error("❌ 에러", exc_info=True)  # 트레이스백 포함
```

### 3. **삭제 검증 로그**
- 삭제 전후 데이터 개수 확인
- 로그로 검증 결과 출력 (고아 데이터 방지)

---

## 🎓 다음 단계

- **인증 시스템 이해**: `03_authentication.md`
- **파일 업로드 & STT**: `04_file_upload_stt.md`
- **요약 & 회의록**: `05_summarization_minutes.md`
- **RAG 챗봇**: `06_chatbot_rag.md`
- **데이터베이스**: `07_database.md`
