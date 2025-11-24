# 07. 데이터베이스 설계 (30분 읽기)

> **레벨 3**: SQLite 관계형 DB와 ChromaDB 벡터 DB의 이중 저장 전략 및 스키마 설계

---

## 🎯 이 문서에서 다루는 내용

1. **이중 데이터베이스 전략**: SQLite (관계형) + ChromaDB (벡터)
2. **SQLite 스키마**: 5개 테이블 구조 및 관계
3. **ChromaDB 컬렉션**: 2개 컬렉션 설계
4. **ERD 다이어그램**: 테이블 간 관계
5. **인덱스 전략**: 성능 최적화
6. **CRUD 패턴**: DatabaseManager 주요 메서드

---

## 📊 데이터베이스 아키텍처 개요

```
┌─────────────────────────────────────────────┐
│         SQLite (minute_ai.db)               │
│  ┌──────────────────────────────────────┐   │
│  │ 1. meeting_dialogues (전사 세그먼트) │   │
│  │ 2. meeting_minutes (회의록)          │   │
│  │ 3. meeting_mindmap (마인드맵)        │   │
│  │ 4. users (사용자 정보)               │   │
│  │ 5. meeting_shares (공유 설정)        │   │
│  └──────────────────────────────────────┘   │
│         ↑ 관계형 데이터, 정확한 조회         │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│    ChromaDB (database/chroma_data/)         │
│  ┌──────────────────────────────────────┐   │
│  │ 1. meeting_chunks (스마트 청킹)      │   │
│  │ 2. meeting_subtopic (문단 요약)      │   │
│  └──────────────────────────────────────┘   │
│         ↑ 벡터 임베딩, 유사도 검색           │
└─────────────────────────────────────────────┘
```

---

## 1️⃣ 왜 이중 데이터베이스를 사용하는가?

### 1.1 각 DB의 역할 분담

| 항목 | SQLite | ChromaDB |
|------|--------|----------|
| **데이터 타입** | 관계형 (행/열) | 벡터 (임베딩) |
| **저장 내용** | 메타데이터, 회의록, 사용자 | 전사 청크, 요약 (임베딩) |
| **검색 방식** | meeting_id, user_id 등 정확한 매칭 | 의미 기반 유사도 검색 |
| **사용 예시** | "회의록 조회", "사용자 권한 체크" | "예산 관련 내용 검색" |
| **트랜잭션** | 지원 (ACID) | 미지원 |
| **쿼리 언어** | SQL | Python API (Langchain) |

---

### 1.2 데이터 흐름

```
[STT 완료 후 저장]
    ↓
SQLite.meeting_dialogues
    - meeting_id, speaker_label, start_time, segment 등 저장
    ↓
ChromaDB.meeting_chunks
    - 스마트 청킹 → 임베딩 → 벡터 저장
    ↓
Gemini 요약 생성
    ↓
ChromaDB.meeting_subtopic
    - 문단 요약 → 임베딩 → 벡터 저장
    ↓
Gemini 회의록 생성
    ↓
SQLite.meeting_minutes
    - 회의록 전체 텍스트 저장
```

---

## 2️⃣ SQLite 스키마 (5개 테이블)

### 2.1 meeting_dialogues (전사 세그먼트)

**목적**: STT 결과의 각 발화 세그먼트 저장

**위치**: `init_db.py:35-52`

```sql
CREATE TABLE meeting_dialogues (
    segment_id INTEGER PRIMARY KEY AUTOINCREMENT,  -- 세그먼트 고유 ID
    meeting_id TEXT NOT NULL,                      -- 회의 고유 ID (UUID)
    meeting_date TEXT,                             -- 회의 일시 (YYYY-MM-DD HH:MM:SS)
    speaker_label TEXT,                            -- 화자 번호 (1, 2, 3, ...)
    start_time REAL,                               -- 발화 시작 시간 (초)
    segment TEXT,                                  -- 발화 내용
    confidence REAL,                               -- 인식 신뢰도 (0.0~1.0)
    audio_file TEXT,                               -- 오디오 파일명
    title TEXT,                                    -- 회의 제목
    owner_id INTEGER                               -- 회의 생성자 (users.id FK)
);
```

**인덱스**:
```sql
CREATE INDEX idx_meeting_id ON meeting_dialogues(meeting_id);
CREATE INDEX idx_owner_id ON meeting_dialogues(owner_id);
```

**데이터 예시**:
| segment_id | meeting_id | speaker_label | start_time | segment | confidence |
|------------|------------|---------------|------------|---------|------------|
| 1 | abc123 | 1 | 0.0 | 안녕하세요. 회의 시작하겠습니다. | 0.95 |
| 2 | abc123 | 2 | 5.2 | 네, 좋습니다. | 0.92 |
| 3 | abc123 | 1 | 8.5 | 오늘 안건은 예산입니다. | 0.97 |

**CRUD 메서드** (`utils/db_manager.py`):
- `save_meeting_data()` - INSERT (lines 165-201)
- `get_meeting_by_id()` - SELECT (lines 326-342)
- `delete_meeting()` - DELETE (lines 227-284)

---

### 2.2 meeting_minutes (회의록)

**목적**: Gemini로 생성한 정식 회의록 문서 저장

**위치**: `init_db.py:54-69`

```sql
CREATE TABLE meeting_minutes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id TEXT UNIQUE NOT NULL,           -- 회의 ID (UNIQUE 제약)
    title TEXT,                                -- 회의 제목
    meeting_date TEXT,                         -- 회의 일시
    minutes_content TEXT NOT NULL,             -- 회의록 마크다운 전체 텍스트
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    owner_id INTEGER                           -- 회의 생성자
);
```

**특징**:
- `meeting_id`가 UNIQUE → 한 회의당 하나의 회의록만 존재
- `minutes_content`에 마크다운 형식 저장 (Gemini 생성 결과)

**CRUD 메서드**:
- `save_minutes()` - INSERT/UPDATE (lines 467-503)
- `get_minutes_by_meeting_id()` - SELECT (lines 505-521)

---

### 2.3 meeting_mindmap (마인드맵)

**목적**: 마인드맵 키워드 마크다운 저장

**위치**: `init_db.py:71-82`

```sql
CREATE TABLE meeting_mindmap (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id TEXT UNIQUE NOT NULL,           -- 회의 ID
    mindmap_content TEXT NOT NULL,             -- Markmap 호환 마크다운
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**mindmap_content 예시**:
```markdown
# 팀 회의

## 예산 논의
- 초기 제안: 500만원
- 최종 결정: 400만원

## 다음 회의 일정
- 11월 15일 오후 2시
```

**CRUD 메서드**:
- `save_mindmap()` - INSERT/UPDATE (lines 523-559)
- `get_mindmap_by_meeting_id()` - SELECT (lines 561-577)

---

### 2.4 users (사용자 정보)

**목적**: Firebase 인증으로 로그인한 사용자 정보 저장

**위치**: `init_db.py:84-98`

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,      -- 내부 사용자 ID
    google_id TEXT UNIQUE NOT NULL,            -- Firebase UID (unique)
    email TEXT UNIQUE NOT NULL,                -- 이메일 (unique)
    name TEXT,                                 -- 사용자 이름
    profile_picture TEXT,                      -- 프로필 이미지 URL
    role TEXT DEFAULT 'user',                  -- 역할 (user/admin)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**역할 (role)**:
- `user`: 일반 사용자 (자신의 노트만 접근)
- `admin`: 관리자 (모든 노트 접근 + 디버그 기능)

**CRUD 메서드** (`utils/user_manager.py`):
- `get_or_create_user()` - INSERT if not exists (lines 29-93)
- `get_user_by_id()` - SELECT (lines 95-114)
- `is_admin()` - 역할 체크 (lines 231-254)

**Admin 사용자 생성** (`init_db.py:118-136`):
```python
# .env 파일에서 ADMIN_EMAILS 읽기
admin_emails = os.getenv('ADMIN_EMAILS', '').split(',')

for email in admin_emails:
    cursor.execute("""
        INSERT INTO users (google_id, email, name, role)
        VALUES (?, ?, ?, 'admin')
    """, (f"admin_{email}", email, "Admin User"))
```

---

### 2.5 meeting_shares (공유 설정)

**목적**: 회의록을 다른 사용자와 공유하는 권한 관리

**위치**: `init_db.py:100-116`

```sql
CREATE TABLE meeting_shares (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id TEXT NOT NULL,                  -- 공유할 회의 ID
    owner_id INTEGER NOT NULL,                 -- 회의 소유자 (users.id)
    shared_with_user_id INTEGER NOT NULL,      -- 공유받는 사용자 (users.id)
    permission TEXT DEFAULT 'read',            -- 권한 (read/write)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (owner_id) REFERENCES users(id),
    FOREIGN KEY (shared_with_user_id) REFERENCES users(id),
    UNIQUE(meeting_id, shared_with_user_id)    -- 중복 공유 방지
);
```

**인덱스**:
```sql
CREATE INDEX idx_shares_meeting ON meeting_shares(meeting_id);
```

**데이터 예시**:
| id | meeting_id | owner_id | shared_with_user_id | permission |
|----|------------|----------|---------------------|------------|
| 1 | abc123 | 1 | 2 | read |
| 2 | abc123 | 1 | 3 | read |

→ `abc123` 회의를 사용자 1이 사용자 2, 3에게 읽기 권한으로 공유

**CRUD 메서드** (`utils/user_manager.py`):
- `share_meeting()` - INSERT (lines 116-154)
- `unshare_meeting()` - DELETE (lines 156-183)
- `get_shared_users()` - SELECT (lines 185-209)

---

## 3️⃣ ERD (Entity Relationship Diagram)

```
┌──────────────────────┐
│      users           │
│──────────────────────│
│ id (PK)              │
│ google_id (UNIQUE)   │
│ email (UNIQUE)       │
│ name                 │
│ role                 │
└──────────────────────┘
        │ 1
        │
        │ owner_id (FK)
        ↓ N
┌──────────────────────────────┐
│   meeting_dialogues          │
│──────────────────────────────│
│ segment_id (PK)              │
│ meeting_id                   │◄─────┐
│ speaker_label                │      │
│ start_time                   │      │ meeting_id로 연결
│ segment                      │      │
│ owner_id (FK) → users.id     │      │
└──────────────────────────────┘      │
                                       │
┌──────────────────────────────┐      │
│   meeting_minutes            │      │
│──────────────────────────────│      │
│ id (PK)                      │      │
│ meeting_id (UNIQUE) ─────────┼──────┤
│ minutes_content              │      │
│ owner_id (FK) → users.id     │      │
└──────────────────────────────┘      │
                                       │
┌──────────────────────────────┐      │
│   meeting_mindmap            │      │
│──────────────────────────────│      │
│ id (PK)                      │      │
│ meeting_id (UNIQUE) ─────────┼──────┘
│ mindmap_content              │
└──────────────────────────────┘

┌──────────────────────────────┐
│   meeting_shares             │
│──────────────────────────────│
│ id (PK)                      │
│ meeting_id                   │
│ owner_id (FK) → users.id     │
│ shared_with_user_id (FK)     │
│ permission                   │
└──────────────────────────────┘
        ↑
        │ N
        │
        └─── users.id (1:N 관계)
```

**핵심 관계**:
1. **users 1:N meeting_dialogues**: 한 사용자가 여러 회의 생성
2. **meeting_id로 연결**: dialogues, minutes, mindmap이 동일 meeting_id로 묶임
3. **meeting_shares 다대다**: users ↔ meetings (공유 관계 테이블)

---

## 4️⃣ ChromaDB 컬렉션 (2개)

### 4.1 meeting_chunks (스마트 청킹 결과)

**목적**: 원본 전사 내용을 의미 단위로 청킹하여 벡터 저장

**생성 위치**: `utils/vector_db_manager.py:106-319`

**저장 구조**:
```python
{
  "id": "abc123_chunk_0",
  "document": "안녕하세요. 회의 시작하겠습니다. [화자 1, 00:00] ...",
  "embedding": [0.234, -0.123, ...],  # 1536 차원 벡터
  "metadata": {
    "meeting_id": "abc123",
    "title": "팀 회의",
    "meeting_date": "2025-11-08 14:00:00",
    "audio_file": "abc123_audio.wav",
    "chunk_index": 0,
    "start_time": 0.0,
    "end_time": 120.5,
    "speakers": "1, 2"
  }
}
```

**임베딩 생성**: OpenAI `text-embedding-ada-002` (1536차원)

**검색 예시**:
```python
# 사용자 질문: "예산 논의 내용은?"
# → 임베딩 생성 → 코사인 유사도 검색 → 상위 3개 반환
results = vdb_manager.search(
    db_type="chunks",
    query="예산 논의 내용은?",
    k=3
)
```

---

### 4.2 meeting_subtopic (문단 요약)

**목적**: Gemini로 생성한 주제별 요약을 벡터 저장

**생성 위치**: `utils/vector_db_manager.py:734-850`

**저장 구조**:
```python
{
  "id": "abc123_subtopic",
  "document": "### 예산 논의\n* 초기 제안: 500만원 [cite: 1]\n* 최종 결정: 400만원 [cite: 3]",
  "embedding": [0.456, -0.789, ...],  # 1536 차원 벡터
  "metadata": {
    "meeting_id": "abc123",
    "meeting_title": "팀 회의",
    "meeting_date": "2025-11-08 14:00:00",
    "audio_file": "abc123_audio.wav",
    "main_topic": "예산 논의"
  }
}
```

**특징**:
- 회의당 1개 문서 (전체 요약)
- `### 제목` 마크다운으로 주제 구분
- `[cite: N]` 형식으로 출처 표시

---

### 4.3 ChromaDB vs SQLite 저장 비교

| 데이터 | SQLite 저장 여부 | ChromaDB 저장 여부 | 이유 |
|--------|------------------|---------------------|------|
| **원본 전사 세그먼트** | ✅ meeting_dialogues | ✅ meeting_chunks | SQLite: 정확한 조회, ChromaDB: 유사도 검색 |
| **문단 요약** | ❌ | ✅ meeting_subtopic | 검색용으로만 사용 (RAG 챗봇) |
| **회의록** | ✅ meeting_minutes | ❌ | meeting_id로만 조회 (벡터 검색 불필요) |
| **마인드맵** | ✅ meeting_mindmap | ❌ | meeting_id로만 조회 |

---

## 5️⃣ 데이터 일관성 보장

### 5.1 트랜잭션 관리

**DatabaseManager의 트랜잭션** (`utils/db_manager.py:102-129`):
```python
def execute_query(self, query, params=None, commit=True):
    """
    SQL 쿼리 실행

    Args:
        commit (bool): True면 즉시 커밋, False면 명시적 커밋 필요
    """
    with self.lock:
        try:
            result = self.cursor.execute(query, params)
            if commit:
                self.conn.commit()
            return result
        except Exception as e:
            logger.error(f"❌ SQL 에러: {e}")
            self.conn.rollback()
            raise
```

**일괄 삽입 트랜잭션** (`utils/db_manager.py:165-201`):
```python
def save_meeting_data(self, meeting_id, segments, ...):
    # 1. 기존 데이터 삭제
    self.execute_query(
        "DELETE FROM meeting_dialogues WHERE meeting_id = ?",
        (meeting_id,),
        commit=False  # 아직 커밋하지 않음
    )

    # 2. 새 데이터 일괄 삽입
    for segment in segments:
        self.execute_query(
            "INSERT INTO meeting_dialogues (...) VALUES (...)",
            (...),
            commit=False  # 아직 커밋하지 않음
        )

    # 3. 모든 작업 완료 후 한 번에 커밋
    self.conn.commit()
```

---

### 5.2 삭제 시 연쇄 삭제

**회의 삭제 로직** (`utils/db_manager.py:227-284`):
```python
def delete_meeting(self, meeting_id):
    # 1. SQLite 삭제
    self.execute_query(
        "DELETE FROM meeting_dialogues WHERE meeting_id = ?",
        (meeting_id,)
    )
    self.execute_query(
        "DELETE FROM meeting_minutes WHERE meeting_id = ?",
        (meeting_id,)
    )
    self.execute_query(
        "DELETE FROM meeting_mindmap WHERE meeting_id = ?",
        (meeting_id,)
    )

    # 2. ChromaDB 삭제
    vdb_manager.delete_meeting(meeting_id)  # chunks + subtopic 모두 삭제
```

---

## 6️⃣ 성능 최적화

### 6.1 인덱스 전략

**생성된 인덱스** (`init_db.py:139-145`):
```sql
-- meeting_id로 검색 (가장 빈번)
CREATE INDEX idx_meeting_id ON meeting_dialogues(meeting_id);

-- 사용자별 회의 목록 조회
CREATE INDEX idx_owner_id ON meeting_dialogues(owner_id);

-- 공유된 회의 검색
CREATE INDEX idx_shares_meeting ON meeting_shares(meeting_id);
```

**인덱스 효과**:
- `SELECT * FROM meeting_dialogues WHERE meeting_id = 'abc123'`
  - Without index: O(N) 전체 스캔
  - With index: O(log N) 이진 탐색

---

### 6.2 쿼리 최적화 패턴

**나쁜 예**:
```python
# N+1 문제
for meeting_id in meeting_ids:
    segments = db.execute_query(
        "SELECT * FROM meeting_dialogues WHERE meeting_id = ?",
        (meeting_id,)
    )  # 총 N번의 쿼리
```

**좋은 예**:
```python
# 한 번의 쿼리로 모든 데이터 조회
meeting_ids_str = ','.join(['?'] * len(meeting_ids))
segments = db.execute_query(
    f"SELECT * FROM meeting_dialogues WHERE meeting_id IN ({meeting_ids_str})",
    tuple(meeting_ids)
)  # 총 1번의 쿼리
```

---

## 7️⃣ 주요 CRUD 패턴

### 7.1 회의 목록 조회 (사용자별)

**코드 위치**: `utils/db_manager.py:344-390`

```python
def get_user_meetings(self, user_id):
    """사용자가 소유한 회의 목록 조회"""
    query = """
        SELECT DISTINCT
            meeting_id,
            title,
            meeting_date,
            audio_file,
            owner_id
        FROM meeting_dialogues
        WHERE owner_id = ?
        ORDER BY meeting_date DESC
    """
    return self.execute_query(query, (user_id,)).fetchall()
```

**결과 예시**:
```python
[
    {"meeting_id": "abc123", "title": "팀 회의", "meeting_date": "2025-11-08 14:00:00", ...},
    {"meeting_id": "def456", "title": "임원 회의", "meeting_date": "2025-11-07 10:00:00", ...}
]
```

---

### 7.2 회의 상세 조회 (세그먼트 포함)

**코드 위치**: `utils/db_manager.py:326-342`

```python
def get_meeting_by_id(self, meeting_id):
    """회의의 모든 세그먼트 조회 (시간 순 정렬)"""
    query = """
        SELECT *
        FROM meeting_dialogues
        WHERE meeting_id = ?
        ORDER BY start_time ASC
    """
    return self.execute_query(query, (meeting_id,)).fetchall()
```

---

### 7.3 공유받은 회의 목록 조회

**코드 위치**: `utils/user_manager.py:211-229`

```python
def get_shared_meetings_for_user(user_id):
    """사용자가 공유받은 회의 목록"""
    query = """
        SELECT
            ms.meeting_id,
            md.title,
            md.meeting_date,
            ms.permission,
            u.name AS owner_name
        FROM meeting_shares ms
        JOIN meeting_dialogues md ON ms.meeting_id = md.meeting_id
        JOIN users u ON ms.owner_id = u.id
        WHERE ms.shared_with_user_id = ?
        GROUP BY ms.meeting_id
        ORDER BY md.meeting_date DESC
    """
    return db.execute_query(query, (user_id,)).fetchall()
```

---

## 8️⃣ 데이터 마이그레이션

### 8.1 새 컬럼 추가

**예시**: `meeting_dialogues`에 `language` 컬럼 추가

```python
# utils/db_manager.py에 마이그레이션 메서드 추가
def migrate_add_language_column(self):
    try:
        self.execute_query("""
            ALTER TABLE meeting_dialogues
            ADD COLUMN language TEXT DEFAULT 'ko'
        """)
        logger.info("✅ language 컬럼 추가 완료")
    except Exception as e:
        logger.warning(f"⚠️  컬럼이 이미 존재하거나 에러: {e}")
```

---

### 8.2 데이터 정합성 검증

**검증 스크립트** (예시):
```python
# scripts/validate_db.py
def validate_orphaned_minutes():
    """고아 회의록 검증 (meeting_dialogues에 없는 meeting_id)"""
    query = """
        SELECT m.meeting_id
        FROM meeting_minutes m
        LEFT JOIN meeting_dialogues d ON m.meeting_id = d.meeting_id
        WHERE d.meeting_id IS NULL
    """
    orphans = db.execute_query(query).fetchall()
    if orphans:
        logger.warning(f"⚠️  고아 회의록 발견: {len(orphans)}개")
```

---

## 9️⃣ 백업 및 복구

### 9.1 SQLite 백업

**전체 백업**:
```bash
# CLI에서 실행
sqlite3 database/minute_ai.db ".backup database/minute_ai_backup.db"
```

**Python 스크립트**:
```python
import sqlite3
import shutil

def backup_database():
    shutil.copy('database/minute_ai.db', 'database/minute_ai_backup.db')
    logger.info("✅ SQLite 백업 완료")
```

---

### 9.2 ChromaDB 백업

**디렉토리 전체 복사**:
```bash
cp -r database/chroma_data database/chroma_data_backup
```

**Python 스크립트**:
```python
import shutil

def backup_chromadb():
    shutil.copytree('database/chroma_data', 'database/chroma_data_backup')
    logger.info("✅ ChromaDB 백업 완료")
```

---

## 🔟 보안 고려사항

### 10.1 SQL Injection 방지

**나쁜 예**:
```python
# ❌ SQL Injection 취약
query = f"SELECT * FROM users WHERE email = '{email}'"
cursor.execute(query)
```

**좋은 예**:
```python
# ✅ Parameterized Query 사용
query = "SELECT * FROM users WHERE email = ?"
cursor.execute(query, (email,))
```

**모든 쿼리가 파라미터화되어 있음** (`utils/db_manager.py`)

---

### 10.2 권한 체크 레이어

**데이터베이스 레벨에서 권한 체크하지 않음**:
```python
# ❌ DB 레벨 권한 체크 없음
def get_meeting_by_id(self, meeting_id):
    # user_id 체크 없이 바로 조회
    return self.execute_query(
        "SELECT * FROM meeting_dialogues WHERE meeting_id = ?",
        (meeting_id,)
    )
```

**애플리케이션 레벨에서 권한 체크**:
```python
# ✅ 라우트에서 권한 체크
@meetings_bp.route("/api/meetings/<meeting_id>")
@login_required
def get_meeting(meeting_id):
    if not can_access_meeting(user_id, meeting_id):
        return 403
    return db.get_meeting_by_id(meeting_id)
```

→ **레이어 분리 원칙**: DB는 데이터 접근만, 권한은 비즈니스 로직에서

---

## 📈 주요 메트릭

| 항목 | SQLite | ChromaDB |
|------|--------|----------|
| **테이블/컬렉션 수** | 5개 | 2개 |
| **평균 레코드 크기** | ~500 bytes | ~2KB (임베딩 포함) |
| **조회 속도 (meeting_id)** | <10ms | <100ms (벡터 검색) |
| **저장 공간 (회의 1개)** | ~50KB | ~500KB (임베딩 포함) |
| **백업 소요 시간** | <1초 | ~5초 (디렉토리 복사) |

---

## 🎓 학습 포인트

### 핵심 개념 정리

1. **이중 DB 전략**: 관계형(정확한 조회) + 벡터(의미 검색) 병행
2. **정규화 vs 비정규화**: meeting_dialogues는 title을 비정규화하여 조인 최소화
3. **인덱스 최적화**: 빈번한 쿼리 패턴에 맞춘 인덱스 설계
4. **트랜잭션 관리**: 일괄 작업 시 원자성 보장
5. **권한 레이어 분리**: DB는 데이터만, 권한은 애플리케이션에서

---

### 코드 리뷰 체크리스트

- [ ] 모든 SQL 쿼리가 파라미터화되어 있는가?
- [ ] 트랜잭션이 필요한 작업에 커밋 제어가 있는가?
- [ ] 인덱스가 빈번한 WHERE 절에 맞춰 생성되었는가?
- [ ] ChromaDB 삭제 시 SQLite도 함께 삭제되는가?
- [ ] UNIQUE 제약 조건이 적절히 설정되어 있는가?
- [ ] 외래 키(FK) 관계가 명확히 정의되어 있는가?

---

## 📞 다음 단계

- **라우트 상세 분석**: `08_routes_detail.md`로 이동
- **유틸리티 함수 심화**: `09_utils_detail.md` 참고
- **API 전체 문서**: `11_api_specification.md` 참고

---

## 🔗 관련 파일

### 초기화
- `init_db.py` - 데이터베이스 스키마 정의 및 초기화

### 데이터 관리
- `utils/db_manager.py` - SQLite CRUD 작업
- `utils/vector_db_manager.py` - ChromaDB 벡터 작업

### 권한 관리
- `utils/user_manager.py` - 사용자 및 공유 관련 DB 작업
