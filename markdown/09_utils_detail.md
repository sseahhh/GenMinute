# 09. 유틸리티 모듈 상세 분석 (1시간 읽기)

> **레벨 4**: utils/ 디렉토리의 모든 헬퍼 함수 및 매니저 클래스 심층 분석

---

## 🎯 이 문서에서 다루는 내용

1. **싱글톤 매니저들**: DatabaseManager, VectorDBManager, STTManager, ChatManager
2. **인증 및 권한**: firebase_auth, user_manager, decorators
3. **데이터 처리**: validation, analysis, document_converter
4. **주요 알고리즘**: 스마트 청킹, 화자 비중 계산

---

## 📊 utils/ 디렉토리 구조

```
utils/
├── db_manager.py              # SQLite 관리 (648 lines)
├── vector_db_manager.py       # ChromaDB 관리 (1081 lines)
├── stt.py                     # Gemini STT/요약/회의록 (548 lines)
├── chat_manager.py            # RAG 챗봇 (405 lines)
├── firebase_auth.py           # Firebase Admin SDK (111 lines)
├── user_manager.py            # 사용자/공유 관리 (485 lines)
├── decorators.py              # 데코레이터 (93 lines)
├── validation.py              # 입력 검증 (56 lines)
├── analysis.py                # 화자 분석 (49 lines)
└── document_converter.py      # 문서 변환 (미사용)
```

---

## 1️⃣ db_manager.py (SQLite 관리)

### 1.1 DatabaseManager 클래스 (싱글톤)

**핵심 특징**:
- 싱글톤 패턴으로 단일 DB 연결 유지
- row_factory로 딕셔너리 형태 반환
- 스레드 안전성 (threading.Lock 사용)

**초기화** (lines 20-70):
```python
class DatabaseManager:
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, db_path="database/minute_ai.db"):
        if self._initialized:
            return

        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # 딕셔너리 형태 반환
        self.cursor = self.conn.cursor()
        self.lock = threading.Lock()  # 스레드 안전성

        self._initialized = True
```

---

### 1.2 주요 CRUD 메서드

#### save_meeting_data() (lines 165-201)

**목적**: STT 결과를 meeting_dialogues 테이블에 일괄 저장

**처리 흐름**:
```python
def save_meeting_data(self, meeting_id, segments, title, meeting_date, audio_file, owner_id):
    with self.lock:
        # 1. 기존 데이터 삭제 (중복 방지)
        self.execute_query(
            "DELETE FROM meeting_dialogues WHERE meeting_id = ?",
            (meeting_id,),
            commit=False
        )

        # 2. 새 세그먼트 일괄 삽입
        for segment in segments:
            self.execute_query("""
                INSERT INTO meeting_dialogues
                (meeting_id, speaker_label, start_time, segment, confidence, ...)
                VALUES (?, ?, ?, ?, ?, ...)
            """, (meeting_id, segment['speaker'], ...), commit=False)

        # 3. 모든 작업 후 한 번에 커밋
        self.conn.commit()
```

---

#### delete_meeting() (lines 227-284)

**특징**: 삭제 전 검증 로깅

```python
def delete_meeting(self, meeting_id):
    # 1. 삭제 전 데이터 조회 (로깅용)
    dialogues = self.execute_query(
        "SELECT COUNT(*) as count FROM meeting_dialogues WHERE meeting_id = ?",
        (meeting_id,)
    ).fetchone()

    # 2. 삭제 실행
    self.execute_query("DELETE FROM meeting_dialogues WHERE meeting_id = ?", (meeting_id,))
    self.execute_query("DELETE FROM meeting_minutes WHERE meeting_id = ?", (meeting_id,))
    self.execute_query("DELETE FROM meeting_mindmap WHERE meeting_id = ?", (meeting_id,))

    # 3. 삭제 결과 로깅
    logger.info(f"✅ meeting_dialogues: {dialogues['count']}개 삭제")

    # 4. ChromaDB도 삭제
    from utils.vector_db_manager import vdb_manager
    vdb_manager.delete_meeting(meeting_id)
```

---

#### get_meeting_by_id() (lines 326-342)

**특징**: start_time 기준 정렬

```python
def get_meeting_by_id(self, meeting_id):
    """시간 순서대로 정렬된 전사 세그먼트 반환"""
    query = """
        SELECT *
        FROM meeting_dialogues
        WHERE meeting_id = ?
        ORDER BY start_time ASC
    """
    return self.execute_query(query, (meeting_id,)).fetchall()
```

---

### 1.3 회의록 관련 메서드

#### save_minutes() (lines 467-503)

**특징**: UPSERT 패턴 (존재하면 UPDATE, 없으면 INSERT)

```python
def save_minutes(self, meeting_id, title, meeting_date, minutes_content):
    existing = self.get_minutes_by_meeting_id(meeting_id)

    if existing:
        # UPDATE
        self.execute_query("""
            UPDATE meeting_minutes
            SET minutes_content = ?, updated_at = CURRENT_TIMESTAMP
            WHERE meeting_id = ?
        """, (minutes_content, meeting_id))
    else:
        # INSERT
        self.execute_query("""
            INSERT INTO meeting_minutes
            (meeting_id, title, meeting_date, minutes_content)
            VALUES (?, ?, ?, ?)
        """, (meeting_id, title, meeting_date, minutes_content))
```

---

## 2️⃣ vector_db_manager.py (ChromaDB 관리)

### 2.1 VectorDBManager 클래스 (싱글톤)

**초기화** (lines 35-85):
```python
class VectorDBManager:
    def __init__(self):
        # Chroma 클라이언트 초기화
        self.client = chromadb.PersistentClient(path="database/chroma_data")

        # OpenAI 임베딩 함수
        self.embedding_function = embedding_functions.OpenAIEmbeddingFunction(
            api_key=config.OPENAI_API_KEY,
            model_name="text-embedding-ada-002"
        )

        # 컬렉션 생성/로드
        self.meeting_chunks_collection = self.client.get_or_create_collection(
            name="meeting_chunks",
            embedding_function=self.embedding_function
        )

        self.meeting_subtopic_collection = self.client.get_or_create_collection(
            name="meeting_subtopic",
            embedding_function=self.embedding_function
        )
```

---

### 2.2 스마트 청킹 알고리즘

**핵심 메서드**: `_smart_chunk()` (lines 241-319)

**청킹 기준 3가지**:

1. **텍스트 길이**: 1000자 이상
2. **시간 간격**: 60초 이상 공백
3. **화자 변경**: 500자 이상이면서 화자 변경

**코드**:
```python
def _smart_chunk(self, formatted_segments, max_chunk_size=1000, time_gap_threshold=60.0):
    chunks = []
    current_chunk = []
    current_length = 0
    current_start_time = None
    current_end_time = None
    current_speakers = set()

    for segment in formatted_segments:
        text = segment['formatted_text']
        speaker = segment.get('speaker_label')
        start_time = segment.get('start_time', 0)

        # 1. 첫 세그먼트면 청크 시작
        if current_start_time is None:
            current_start_time = start_time

        # 2. 시간 간격 체크 (60초 이상 공백 = 새 청크)
        if current_end_time is not None:
            time_gap = start_time - current_end_time
            if time_gap > time_gap_threshold:
                # 현재 청크 저장 후 새 청크 시작
                chunks.append({
                    "text": "\n\n".join(current_chunk),
                    "start_time": current_start_time,
                    "end_time": current_end_time,
                    "speakers": list(current_speakers)
                })
                current_chunk = []
                current_length = 0
                current_speakers = set()
                current_start_time = start_time

        # 3. 화자 변경 + 충분한 길이 (500자) = 새 청크 고려
        if (speaker and speaker not in current_speakers and
            current_length >= 500):
            # 화자 변경 시점에서 청크 분리
            chunks.append({...})
            current_chunk = []
            current_length = 0
            current_speakers = set()
            current_start_time = start_time

        # 4. 텍스트 길이 체크 (1000자 이상 = 새 청크)
        if current_length + len(text) > max_chunk_size and current_chunk:
            chunks.append({...})
            current_chunk = []
            current_length = 0
            current_speakers = set()
            current_start_time = start_time

        # 5. 현재 청크에 추가
        current_chunk.append(text)
        current_length += len(text)
        current_end_time = start_time
        if speaker:
            current_speakers.add(speaker)

    # 6. 마지막 청크 저장
    if current_chunk:
        chunks.append({...})

    return chunks
```

---

### 2.3 텍스트 정제 (Cleaning)

**메서드**: `_clean_text()` (lines 106-125)

**정제 단계**:

1. **화자 정보 제거**: `[Speaker 1, 00:05]` → 제거
2. **타임스탬프 제거**: `(120초)` → 제거
3. **연속 공백 정리**: 여러 공백 → 하나로

```python
def _clean_text(self, formatted_text):
    # 1. 화자 정보 제거
    pattern = r'\[Speaker [^,]+, \d{2}:\d{2}\]\s*'
    cleaned_text = re.sub(pattern, '', formatted_text)

    # 2. 타임스탬프 제거
    cleaned_text = re.sub(r'\(\d+초\)', '', cleaned_text)

    # 3. 연속 공백 제거
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text)

    return cleaned_text.strip()
```

---

### 2.4 add_meeting() (lines 321-589)

**목적**: STT 결과를 스마트 청킹 후 ChromaDB에 저장

**전체 흐름**:
```python
def add_meeting(self, meeting_id, title, meeting_date, audio_file, formatted_segments):
    # 1. 기존 데이터 삭제
    self.delete_meeting(meeting_id)

    # 2. 세그먼트 포맷팅
    formatted_for_chunking = []
    for seg in formatted_segments:
        formatted_for_chunking.append({
            "formatted_text": f"[Speaker {seg['speaker']}, {format_time(seg['start_time'])}] {seg['text']}",
            "speaker_label": str(seg['speaker']),
            "start_time": seg['start_time']
        })

    # 3. 스마트 청킹
    chunks = self._smart_chunk(formatted_for_chunking)

    # 4. 각 청크 정제 + 임베딩 + 저장
    for idx, chunk in enumerate(chunks):
        cleaned_text = self._clean_text(chunk['text'])

        self.meeting_chunks_collection.add(
            ids=[f"{meeting_id}_chunk_{idx}"],
            documents=[cleaned_text],
            metadatas=[{
                "meeting_id": meeting_id,
                "title": title,
                "meeting_date": meeting_date,
                "audio_file": audio_file,
                "chunk_index": idx,
                "start_time": chunk['start_time'],
                "end_time": chunk['end_time'],
                "speakers": ", ".join(chunk['speakers'])
            }]
        )
```

---

### 2.5 similarity_search() (lines 851-930)

**목적**: 질문과 유사한 문서 검색

```python
def similarity_search(self, collection_name, query_text, meeting_id=None, n_results=3):
    # 1. 컬렉션 선택
    collection = (self.meeting_chunks_collection if collection_name == "meeting_chunks"
                  else self.meeting_subtopic_collection)

    # 2. 검색 쿼리 (임베딩 자동 생성)
    results = collection.query(
        query_texts=[query_text],
        n_results=n_results,
        where={"meeting_id": meeting_id} if meeting_id else None
    )

    # 3. Document 객체로 변환
    documents = []
    for i in range(len(results['ids'][0])):
        documents.append(Document(
            page_content=results['documents'][0][i],
            metadata=results['metadatas'][0][i]
        ))

    return documents
```

---

## 3️⃣ stt.py (Gemini AI 처리)

### 3.1 STTManager 클래스 (싱글톤)

**핵심 메서드**:
1. `transcribe_audio()` - Gemini 2.5 Pro STT (lines 45-169)
2. `subtopic_generate()` - 문단 요약 생성 (lines 171-239)
3. `generate_minutes()` - 회의록 생성 (lines 241-361)
4. `extract_mindmap_keywords()` - 마인드맵 키워드 (lines 449-543)
5. `parse_script()` - 스크립트 파싱 (lines 364-447)

---

### 3.2 transcribe_audio() 상세

**프롬프트 엔지니어링 핵심** (lines 69-107):

```python
prompt = """
당신은 최고 수준의 정확도를 가진 전문적인 회의록 STT 시스템입니다.

I. 핵심 지침 (오류 방지)
1. 충실도 우선: 제공된 오디오에서 실제 발화된 내용만을 인식
2. 금지 사항: 문장 보정 오류, 동사 생성/보정, 불필요한 단어 추가 금지
3. 단어 정확성: 들리는 음운에 충실, 문맥상 명백히 오류면 보정
4. 불확실성 처리: 들리지 않거나 불분명한 부분은 공란

II. 화자 분리 (Diarization) 지침
5. 화자 분리 원칙: 동일 화자가 톤이 달라져도 같은 번호 유지
6. 화자 구분: 발화자의 등장 순서대로 새로운 번호 할당
7. 끼어들기 감지: 짧은 맞장구는 독립 화자로 분리하지 않음
8. 겹침 처리: 화자 겹칠 시 각각의 start_time 기록
9. 동일 화자 재개: 다른 화자 끼어들기 후 주 화자가 다시 말하면 같은 번호

III. 출력 형식
10. 신뢰도: 0.0~1.0 값
11. start_time_mmss: "분:초:밀리초" 형태
12. JSON 형식:
[
    {"speaker": 1, "start_time_mmss": "0:00:000", "confidence": 0.95, "text": "..."}
]
"""
```

**JSON 파싱 및 에러 처리** (lines 127-150):
```python
try:
    result_list = json.loads(cleaned_response)
except json.JSONDecodeError as e:
    logger.error(f"❌ JSON 파싱 실패: {e}")
    logger.info(f"📝 오류 위치: line {e.lineno}, column {e.colno}")

    # 오류 줄 출력
    lines = cleaned_response.split('\n')
    error_line = lines[e.lineno - 1]
    logger.info(f"📄 오류 발생 줄: {error_line}")

    # 전체 응답 저장 (디버깅용)
    error_log_path = 'gemini_error_response.txt'
    with open(error_log_path, 'w', encoding='utf-8') as f:
        f.write(cleaned_response)

    raise ValueError(f"Gemini 응답이 올바른 JSON 형식이 아닙니다")
```

---

### 3.3 parse_script() (스크립트 파싱)

**목적**: 텍스트 스크립트를 STT 결과와 동일한 형식으로 변환

**지원 형식**:
- `화자1: 텍스트` 또는 `1: 텍스트`
- `A: 텍스트` 또는 `화자A: 텍스트`
- `[화자1] 텍스트` 또는 `[1] 텍스트`

**코드** (lines 364-447):
```python
def parse_script(script_text):
    segments = []
    speaker_map = {}  # 화자 레이블 → 숫자 매핑
    next_speaker_id = 1

    for line in script_text.strip().split('\n'):
        # 패턴 1: "화자1: 텍스트"
        match = re.match(r'^(?:화자\s*)?(\d+)\s*:\s*(.+)$', line)
        if match:
            speaker_num = int(match.group(1))
            text = match.group(2).strip()
        else:
            # 패턴 2: "A: 텍스트" (알파벳 화자)
            match = re.match(r'^(?:화자\s*)?([A-Za-z가-힣]+)\s*:\s*(.+)$', line)
            if match:
                speaker_label = match.group(1)
                text = match.group(2).strip()

                # 화자 레이블을 숫자로 매핑
                if speaker_label not in speaker_map:
                    speaker_map[speaker_label] = next_speaker_id
                    next_speaker_id += 1
                speaker_num = speaker_map[speaker_label]

        segments.append({
            "speaker": speaker_num,
            "start_time": current_time,
            "confidence": 1.0,
            "text": text
        })
        current_time += 5.0  # 5초 간격으로 가정

    return segments
```

---

## 4️⃣ chat_manager.py (RAG 챗봇)

### 4.1 search_documents() (lines 56-221)

**특징**: 2개 컬렉션 동시 검색

```python
def search_documents(self, query, meeting_id=None, accessible_meeting_ids=None):
    # 1. Chunks 검색 (상위 20개 후보)
    chunks_results = self.vdb_manager.search(
        db_type="chunks",
        query=query,
        k=20
    )

    # 2. Subtopic 검색 (상위 20개 후보)
    subtopic_results = self.vdb_manager.search(
        db_type="subtopic",
        query=query,
        k=20
    )

    # 3. 권한 필터링
    if accessible_meeting_ids:
        chunks_results = [doc for doc in chunks_results
                         if doc.metadata.get('meeting_id') in accessible_meeting_ids]
        subtopic_results = [doc for doc in subtopic_results
                           if doc.metadata.get('meeting_id') in accessible_meeting_ids]

    # 4. 상위 3개씩만 선택
    return {
        "chunks": chunks_results[:3],
        "subtopics": subtopic_results[:3],
        "total_count": len(chunks_results[:3]) + len(subtopic_results[:3])
    }
```

---

## 5️⃣ firebase_auth.py (Firebase Admin SDK)

### 5.1 initialize_firebase() (lines 17-44)

**Firebase Admin SDK 초기화**:
```python
def initialize_firebase():
    cred = credentials.Certificate({
        "type": "service_account",
        "project_id": config.FIREBASE_PROJECT_ID,
        "private_key_id": config.FIREBASE_PRIVATE_KEY_ID,
        "private_key": config.FIREBASE_PRIVATE_KEY.replace('\\n', '\n'),
        "client_email": config.FIREBASE_CLIENT_EMAIL,
        "client_id": config.FIREBASE_CLIENT_ID,
        ...
    })

    firebase_admin.initialize_app(cred)
    logger.info("✅ Firebase Admin SDK 초기화 완료")
```

---

### 5.2 verify_id_token() (lines 47-91)

**ID Token 검증**:
```python
def verify_id_token(id_token):
    try:
        # Firebase Admin SDK로 토큰 검증
        decoded_token = auth.verify_id_token(id_token)

        return {
            'uid': decoded_token['uid'],
            'email': decoded_token.get('email'),
            'name': decoded_token.get('name'),
            'picture': decoded_token.get('picture')
        }
    except Exception as e:
        logger.error(f"❌ 토큰 검증 실패: {e}")
        raise ValueError("유효하지 않은 인증 토큰입니다.")
```

---

## 6️⃣ user_manager.py (사용자 및 권한)

### 6.1 get_or_create_user() (lines 29-93)

**UPSERT 패턴**:
```python
def get_or_create_user(google_id, email, name, profile_picture):
    # 1. 기존 사용자 조회
    existing_user = db.execute_query(
        "SELECT * FROM users WHERE google_id = ?",
        (google_id,)
    ).fetchone()

    if existing_user:
        # UPDATE (이름/프로필 변경 가능)
        db.execute_query("""
            UPDATE users
            SET name = ?, profile_picture = ?
            WHERE google_id = ?
        """, (name, profile_picture, google_id))
        return dict(existing_user)
    else:
        # INSERT
        db.execute_query("""
            INSERT INTO users (google_id, email, name, profile_picture, role)
            VALUES (?, ?, ?, ?, 'user')
        """, (google_id, email, name, profile_picture))

        return get_user_by_google_id(google_id)
```

---

### 6.2 can_access_meeting() (lines 335-385)

**권한 체크 로직**:
```python
def can_access_meeting(user_id, meeting_id):
    # 1. Owner 체크
    owner_check = db.execute_query("""
        SELECT 1 FROM meeting_dialogues
        WHERE meeting_id = ? AND owner_id = ?
    """, (meeting_id, user_id)).fetchone()

    if owner_check:
        return True

    # 2. Shared User 체크
    share_check = db.execute_query("""
        SELECT 1 FROM meeting_shares
        WHERE meeting_id = ? AND shared_with_user_id = ?
    """, (meeting_id, user_id)).fetchone()

    if share_check:
        return True

    # 3. Admin 체크
    if is_admin(user_id):
        return True

    return False
```

---

## 7️⃣ decorators.py (데코레이터)

### 7.1 @login_required (lines 16-58)

**세션 기반 인증 체크**:
```python
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 세션에 user_id 있는지 체크
        if 'user_id' not in session:
            # API 요청인 경우
            if request.path.startswith('/api/'):
                return jsonify({"error": "로그인이 필요합니다."}), 401

            # HTML 요청인 경우
            return redirect(url_for('auth.login_page'))

        return f(*args, **kwargs)

    return decorated_function
```

---

### 7.2 @admin_required (lines 61-93)

**Admin 권한 체크**:
```python
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')

        if not is_admin(user_id):
            if request.path.startswith('/api/'):
                return jsonify({"error": "관리자 권한이 필요합니다."}), 403
            else:
                return "관리자 권한이 필요합니다.", 403

        return f(*args, **kwargs)

    return decorated_function
```

---

## 8️⃣ validation.py (입력 검증)

### validate_title() (lines 7-21)

```python
def validate_title(title):
    if not title or title.strip() == "":
        return False, "제목을 입력해 주세요."
    return True, None
```

### parse_meeting_date() (lines 34-55)

**datetime-local → SQL 형식 변환**:
```python
def parse_meeting_date(meeting_date):
    if not meeting_date or meeting_date.strip() == "":
        return get_current_datetime_string()  # 현재 시간

    try:
        # "YYYY-MM-DDTHH:MM" → "YYYY-MM-DD HH:MM:SS"
        dt = datetime.datetime.fromisoformat(meeting_date)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return get_current_datetime_string()
```

---

## 9️⃣ analysis.py (화자 분석)

### calculate_speaker_share() (lines 12-49)

**화자 비중 계산** (Chart.js용):
```python
def calculate_speaker_share(segments):
    speaker_lengths = {}

    # 1. 화자별 텍스트 길이 합산
    for segment in segments:
        speaker = segment.get('speaker_label', 'Unknown')
        text = segment.get('segment', '')
        speaker_lengths[speaker] = speaker_lengths.get(speaker, 0) + len(text)

    # 2. 총 텍스트 길이
    total_length = sum(speaker_lengths.values())

    # 3. 비율 계산
    speaker_shares = {}
    for speaker, length in speaker_lengths.items():
        percentage = (length / total_length * 100) if total_length > 0 else 0
        speaker_shares[speaker] = round(percentage, 2)

    # 4. Chart.js 형식으로 반환
    return {
        "labels": [f"화자 {speaker}" for speaker in speaker_shares.keys()],
        "data": list(speaker_shares.values())
    }
```

**반환 예시**:
```json
{
  "labels": ["화자 1", "화자 2", "화자 3"],
  "data": [45.32, 38.15, 16.53]
}
```

---

## 🎓 학습 포인트

1. **싱글톤 패턴**: 리소스 효율화 및 일관된 상태 유지
2. **스레드 안전성**: threading.Lock으로 동시 접근 제어
3. **UPSERT 패턴**: 존재 여부 확인 후 INSERT/UPDATE
4. **프롬프트 엔지니어링**: LLM 출력 품질 향상
5. **스마트 청킹**: 의미 단위로 텍스트 분할

---

## 📞 다음 단계

- **서비스 레이어 분석**: `10_services_detail.md`로 이동
- **API 전체 명세**: `11_api_specification.md` 참고
- **코드 리뷰 체크리스트**: `12_code_review_checklist.md` 참고
