# 05. 요약 및 회의록 생성 시스템 (30분 읽기)

> **레벨 3**: AI 기반 문서 자동 생성 시스템의 구현 원리와 프롬프트 엔지니어링

---

## 🎯 이 문서에서 다루는 내용

1. **문단 요약 (Paragraph Summary)**: 대화 → 주제별 요약
2. **회의록 (Meeting Minutes)**: 요약 → 정식 문서
3. **마인드맵 (Mindmap)**: 요약 → 시각화용 키워드
4. **프롬프트 엔지니어링**: Gemini에게 정확한 출력을 받는 방법
5. **데이터 저장 전략**: ChromaDB vs SQLite

---

## 📊 전체 플로우 다이어그램

```
[STT 완료 + ChromaDB 저장]
    ↓
┌─────────────────────────────────────┐
│  1. 문단 요약 생성                  │
│     - API: POST /api/summarize      │
│     - 함수: subtopic_generate()     │
│     - 모델: Gemini 2.5 Pro          │
│     - 저장: ChromaDB (meeting_subtopic) │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  2. 마인드맵 키워드 추출            │
│     - 함수: extract_mindmap_keywords() │
│     - 모델: Gemini 2.5 Flash        │
│     - 저장: SQLite (meeting_mindmap) │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  3. 회의록 생성                     │
│     - API: POST /api/generate_minutes │
│     - 함수: generate_minutes()      │
│     - 모델: Gemini 2.5 Pro          │
│     - 저장: SQLite (meeting_minutes) │
└─────────────────────────────────────┘
```

---

## 1️⃣ 문단 요약 생성 (Paragraph Summary)

### 1.1 개요

**목적**: 화자 중심의 구어체 대화를 주제별로 정리된 문어체 요약으로 변환

**핵심 특징**:
- 화자 표시(`A:`, `B:`) 제거
- 구어체 → 문어체 변환
- 주제별 그룹화 (### 마크다운 헤더)
- 출처 인용 (`[cite: 1, 2]`)
- ChromaDB에 벡터 저장 → RAG 검색 가능

---

### 1.2 API 엔드포인트

#### POST `/api/summarize/<meeting_id>`

**요청 예시**:
```bash
curl -X POST http://localhost:5050/api/summarize/abc123 \
  -H "Cookie: session=..."
```

**응답 예시**:
```json
{
  "success": true,
  "message": "요약이 성공적으로 생성 및 저장되었습니다.",
  "summary": "### 대주주 주식 양도세 기준 논란\n* 현행 10억원 기준의 문제점 [cite: 1]\n..."
}
```

**코드 위치**: `routes/summary.py:25-90`

---

### 1.3 처리 흐름

```python
# routes/summary.py:46-77
def summarize(meeting_id):
    # 1. 권한 체크
    if not can_access_meeting(user_id, meeting_id):
        return 403

    # 2. meeting_id로 전사 내용 조회
    rows = db.get_meeting_by_id(meeting_id)
    transcript_text = " ".join([row['segment'] for row in rows])

    # 3. Gemini로 요약 생성
    summary_content = stt_manager.subtopic_generate(title, transcript_text)

    # 4. ChromaDB의 meeting_subtopic 컬렉션에 저장
    vdb_manager.add_meeting_as_subtopic(
        meeting_id=meeting_id,
        title=title,
        meeting_date=meeting_date,
        audio_file=audio_file,
        summary_content=summary_content
    )
```

---

### 1.4 프롬프트 엔지니어링 분석

**위치**: `utils/stt.py:171-239`

#### 프롬프트 구조

```python
prompt_text = f"""당신은 제공된 대화 스크립트 내용을 분석하여,
구조화된 주제별 요약본으로 변환하는 AI 어시스턴트입니다.

**출력 요구사항:**

1. 회의 제목 : {title}
2. 주제별 그룹화 : 스크립트 전체 내용을 분석하여 주요 논의 주제를 파악합니다.
3. 소주제 제목 형식 (중요): 각 주요 주제별로 핵심 내용을 요약하는 제목을
   **반드시 "### 제목" 형식**으로 생성합니다.
4. 내용 요약: 각 주제 제목 아래에 관련된 핵심 주장, 사실, 의견을
   글머리 기호(`*`)를 사용하여 요약합니다.
5. 문체 변환: 원본의 구어체(대화체)를 간결하고 공식적인 서술형 문어체로 변경합니다.
6. 화자 및 군더더기 제거: 'A:', 'B:'와 같은 화자 표시와 '그러니까', '어,', '자,' 등
   대화의 군더더기를 모두 제거하고 내용만 정제하여 요약합니다.
7. 정확한 인용 (필수):
   * 요약된 모든 문장이나 구절 끝에는 반드시 원본 스크립트의 번호를
     형식으로 변환하여 삽입해야 합니다. (예: `[cite: 1, 2]`)

**출력 예시:**
### 첫 번째 주요 주제
* 첫 번째 논의 내용 요약 [cite: 1]
* 두 번째 논의 내용 요약 [cite: 2, 3]

### 두 번째 주요 주제
* 관련 논의 내용 요약 [cite: 4]

{transcript_text}
"""
```

#### 프롬프트 엔지니어링 핵심 원칙

| 원칙 | 설명 | 이유 |
|------|------|------|
| **명확한 역할 정의** | "당신은 ~~ AI 어시스턴트입니다" | LLM의 페르소나 설정 |
| **구조화된 출력 형식** | "### 제목" + "* 내용" 강제 | 일관된 파싱 가능 |
| **금지 사항 명시** | "절대 ~하지 마세요" | 환각 방지 |
| **예시 제공** | 실제 출력 예시 포함 | Few-shot learning 효과 |
| **변수 주입** | `{title}`, `{transcript_text}` | 동적 컨텍스트 제공 |

---

### 1.5 ChromaDB 저장 로직

**위치**: `utils/vector_db_manager.py:734-850`

```python
def add_meeting_as_subtopic(self, meeting_id, title, meeting_date, audio_file, summary_content):
    # 1. 기존 데이터 삭제 (중복 방지)
    self.meeting_subtopic_collection.delete(
        where={"meeting_id": meeting_id}
    )

    # 2. OpenAI 임베딩 생성
    embeddings = self._get_embedding([summary_content])

    # 3. ChromaDB에 저장
    self.meeting_subtopic_collection.add(
        ids=[f"{meeting_id}_subtopic"],
        embeddings=embeddings,
        documents=[summary_content],
        metadatas=[{
            "meeting_id": meeting_id,
            "title": title,
            "meeting_date": meeting_date,
            "audio_file": audio_file
        }]
    )
```

**저장 이유**: RAG 챗봇이 `meeting_chunks` (원본) + `meeting_subtopic` (요약)을 함께 검색하여 더 정확한 답변 생성

---

## 2️⃣ 마인드맵 키워드 추출

### 2.1 개요

**목적**: 문단 요약 → Markmap 라이브러리 호환 마크다운 형식

**출력 형식**:
```markdown
# 회의 제목
## 주제 1
- 키워드 1
- 키워드 2
## 주제 2
- 키워드 3
```

**모델**: Gemini 2.5 Flash (Pro보다 빠르고 저렴, 간단한 작업에 적합)

---

### 2.2 함수 분석

**위치**: `utils/stt.py:449-543`

```python
def extract_mindmap_keywords(self, summary_content: str, title: str) -> str:
    prompt_text = f"""당신은 회의 요약을 마인드맵용 키워드로 변환하는 AI 어시스턴트입니다.

**작업 요구사항**:

1. **출력 형식**: 마크다운 계층 구조로 변환
   - 1단계: # {title} (회의 제목을 중심 노드로)
   - 2단계: ## [주제명] (### 제목들을 2단계 노드로)
   - 3단계: - [키워드] (* 항목들을 간결한 키워드로)

2. **키워드 추출 규칙**:
   - 각 * 항목을 5-7단어 이내의 핵심 키워드로 축약
   - [cite: N, M] 같은 인용 표시는 모두 제거
   - 문장형 → 체언형/명사구로 변환
   - 중복되거나 유사한 내용은 하나로 통합

{summary_content}
"""

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",  # Flash 모델 사용
        contents=[...]
    )
    return response.text.strip()
```

---

### 2.3 Markmap 렌더링

**프론트엔드 통합** (`templates/summary_template.html`):
```html
<div id="mindmap"></div>

<script>
// 마크다운 문자열을 Markmap으로 변환
const { root } = markmap.Transformer.transform(markdownContent);
const mm = markmap.Markmap.create(
    document.querySelector('#mindmap'),
    null,
    root
);
</script>
```

**Markmap 라이브러리**:
- CDN: `https://cdn.jsdelivr.net/npm/markmap-view@0.15.4`
- 마크다운 계층 구조 → 인터랙티브 SVG 트리 자동 생성

---

## 3️⃣ 회의록 생성 (Meeting Minutes)

### 3.1 개요

**목적**: 요약 → 공식 회의록 문서 (템플릿 기반)

**특징**:
- 정형화된 형식 (일시, 참석자, 요약, 논의 내용, 액션 아이템)
- 문단 요약 + 원본 전사 내용 모두 활용
- SQLite에 저장 (벡터 DB 불필요)

---

### 3.2 API 엔드포인트

#### POST `/api/generate_minutes/<meeting_id>`

**코드 위치**: `routes/summary.py:139-211`

```python
def generate_minutes(meeting_id):
    # 1. 전사 내용 조회
    rows = db.get_meeting_by_id(meeting_id)
    transcript_text = " ".join([row['segment'] for row in rows])

    # 2. ChromaDB에서 청킹된 문서 가져오기
    chunks_content = vdb_manager.get_chunks_by_meeting_id(meeting_id)

    # 3. Gemini로 회의록 생성
    minutes_content = stt_manager.generate_minutes(
        title,
        transcript_text,
        chunks_content,  # 요약된 청크들
        meeting_date
    )

    # 4. SQLite DB에 저장
    db.save_minutes(meeting_id, title, meeting_date, minutes_content)
```

---

### 3.3 회의록 생성 프롬프트 분석

**위치**: `utils/stt.py:241-361`

#### 템플릿 구조

```python
prompt_text = f"""당신은 회의록을 전문적으로 작성하는 AI 어시스턴트입니다.
아래 제공되는 "회의 스크립트"와 "문단 요약"을 분석하여,
주어진 "마크다운 템플릿"의 각 항목을 채워주세요.

--- 회의 제목 ---
{title}

--- 문단 요약 ---
{summary_content}

--- 회의 스크립트 ---
{transcript_text}

--- 마크다운 템플릿 (이 형식 정확히 따르세요) ---

# {{{{회의명}}}}

**일시**: {meeting_date_formatted}
**참석자**: {{{{참석자}}}}

## 회의 요약
{{회의의 핵심 주제, 논의 방향, 주요 결론이 모두 포함되도록
전체 내용을 **하나의 간결한 문단으로 요약**}}

## 핵심 논의 내용

### {{첫 번째 핵심 주제}}
{{해당 주제에 대한 논의 내용}}

### {{두 번째 핵심 주제}}
{{해당 주제에 대한 논의 내용}}

## 액션 아이템
* {{수행할 과제 1 (**담당자:** OOO, **기한:** OOO)}}
* {{수행할 과제 2 (**담당자:** OOO, **기한:** OOO)}}

## 향후 계획
{{결정 사항에 따른 후속 단계, 우선순위, 마감일 등을 간결히 정리}}

[중요 출력 규칙]
- 절대로 서론, 인사, 부연 설명을 포함하지 마세요.
- 응답은 반드시 마크다운 제목인 '#'으로 시작해야 합니다.
- 모든 내용은 회의록 양식에 맞게, 구어체가 아닌 간결하고 명료한 서술체로 작성하세요.
"""
```

#### 날짜 포맷 변환

```python
# utils/stt.py:254-260
from datetime import datetime
dt_obj = datetime.strptime(meeting_date, "%Y-%m-%d %H:%M:%S")
meeting_date_formatted = dt_obj.strftime("%Y년 %m월 %d일 %H시 %M분")
# 결과: "2025년 11월 08일 14시 30분"
```

---

### 3.4 SQLite 저장 로직

**위치**: `utils/db_manager.py:467-503`

```python
def save_minutes(self, meeting_id, title, meeting_date, minutes_content):
    # 1. 기존 회의록 조회
    existing = self.get_minutes_by_meeting_id(meeting_id)

    if existing:
        # UPDATE: 기존 회의록 업데이트
        self.execute_query("""
            UPDATE meeting_minutes
            SET minutes_content = ?, updated_at = CURRENT_TIMESTAMP
            WHERE meeting_id = ?
        """, (minutes_content, meeting_id))
    else:
        # INSERT: 새 회의록 생성
        self.execute_query("""
            INSERT INTO meeting_minutes
            (meeting_id, title, meeting_date, minutes_content)
            VALUES (?, ?, ?, ?)
        """, (meeting_id, title, meeting_date, minutes_content))
```

**테이블 스키마**:
```sql
CREATE TABLE meeting_minutes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    meeting_date TEXT,
    minutes_content TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

---

## 4️⃣ 데이터 저장 전략 비교

### 4.1 ChromaDB vs SQLite

| 항목 | ChromaDB (meeting_subtopic) | SQLite (meeting_minutes) |
|------|----------------------------|--------------------------|
| **저장 대상** | 문단 요약 | 회의록 |
| **목적** | RAG 벡터 검색 | 문서 저장 및 조회 |
| **임베딩** | OpenAI text-embedding-ada-002 | 없음 |
| **검색 방식** | 의미 기반 유사도 검색 | meeting_id 기반 조회 |
| **업데이트** | 삭제 후 재생성 | UPDATE 문으로 수정 |
| **사용 시점** | 챗봇 질문 답변 시 | 회의록 뷰어 페이지 렌더링 |

---

### 4.2 왜 문단 요약은 ChromaDB에 저장하는가?

**이유**: RAG 챗봇이 다음 2가지를 함께 검색하기 위함

1. **meeting_chunks** (원본 전사 청크): 상세한 발화 내용
2. **meeting_subtopic** (문단 요약): 주제별 요약

```python
# utils/chat_manager.py:189-203
# 챗봇 답변 생성 시 검색 로직
results_chunks = self.vector_db.similarity_search(
    collection_name="meeting_chunks",
    query_text=question,
    meeting_id=meeting_id,
    n_results=3  # 상위 3개 청크
)

results_subtopic = self.vector_db.similarity_search(
    collection_name="meeting_subtopic",
    query_text=question,
    meeting_id=meeting_id,
    n_results=3  # 상위 3개 요약
)

# 총 6개 문서를 컨텍스트로 Gemini에게 전달
```

---

### 4.3 왜 회의록은 SQLite에 저장하는가?

**이유**:

1. **벡터 검색 불필요**: 회의록은 `meeting_id`로만 조회
2. **문서 무결성**: 한 번 생성된 회의록은 전체 내용을 그대로 조회
3. **업데이트 용이**: 재생성 시 UPDATE 문으로 효율적 수정
4. **관계형 데이터**: `meeting_dialogues`와 FK로 연결

---

## 5️⃣ 프롬프트 엔지니어링 Best Practices

### 5.1 일관된 출력 형식 강제하기

**문제**: LLM이 자유 형식으로 답변 → 파싱 실패

**해결**:
```python
# 프롬프트에 명확한 형식 지정
"출력 형식:
[
    {
        \"speaker\": 1,
        \"start_time_mmss\": \"0:00:000\",
        \"confidence\": 0.95,
        \"text\": \"안녕하세요\"
    }
]
JSON 배열만 출력하고, 추가 설명이나 마크다운 코드 블록은 포함하지 마세요."
```

**검증**:
```python
# utils/stt.py:127
cleaned_response = response.text.strip().replace("```json", "").replace("```", "").strip()
```

---

### 5.2 금지 사항 명시

**프롬프트 예시**:
```
[중요 출력 규칙]
- 절대로 서론, 인사, 부연 설명을 포함하지 마세요.
- 응답은 반드시 마크다운 제목인 '#'으로 시작해야 합니다.
- {{}}는 실제 내용으로 채워서 표시하지 마세요.
```

→ "절대로 ~하지 마세요" 문구가 환각 방지에 효과적

---

### 5.3 변수 주입 vs 하드코딩

**나쁜 예**:
```python
prompt = "회의 제목은 '팀 회의'입니다."  # 고정된 값
```

**좋은 예**:
```python
prompt = f"회의 제목은 '{title}'입니다."  # 동적 주입
```

→ 템플릿 재사용성 향상

---

### 5.4 Few-shot Learning 활용

**프롬프트에 예시 포함**:
```
**출력 예시:**
### 첫 번째 주요 주제
* 첫 번째 논의 내용 요약 [cite: 1]
* 두 번째 논의 내용 요약 [cite: 2, 3]
```

→ LLM이 패턴을 학습하여 동일한 형식으로 출력

---

## 6️⃣ 에러 핸들링

### 6.1 JSON 파싱 에러 처리

**위치**: `utils/stt.py:130-150`

```python
try:
    result_list = json.loads(cleaned_response)
except json.JSONDecodeError as e:
    logger.error(f"❌ JSON 파싱 실패: {e}")
    logger.info(f"📝 오류 위치: line {e.lineno}, column {e.colno}")

    # 오류 발생 줄 출력
    lines = cleaned_response.split('\n')
    if e.lineno <= len(lines):
        error_line = lines[e.lineno - 1]
        logger.info(f"📄 오류 발생 줄: {error_line}")

    # 전체 응답 저장 (디버깅용)
    error_log_path = os.path.join(os.path.dirname(__file__), '..', 'gemini_error_response.txt')
    with open(error_log_path, 'w', encoding='utf-8') as f:
        f.write(cleaned_response)

    raise ValueError(f"Gemini 응답이 올바른 JSON 형식이 아닙니다: {e}")
```

---

### 6.2 Gemini 안전 필터링 체크

**위치**: `utils/stt.py:116-125`

```python
if response.text is None:
    logger.warning("⚠️ Gemini 응답이 비어있습니다.")
    logger.warning(f"   -candidates: {response.candidates if hasattr(response, 'candidates') else 'N/A'}")
    logger.warning(f"   -prompt_feedback: {response.prompt_feedback if hasattr(response, 'prompt_feedback') else 'N/A'}")

    # 안전 필터링 체크
    if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
        logger.warning(f"⚠️ 프롬프트가 차단되었을 수 있습니다: {response.prompt_feedback}")

    raise ValueError("Gemini API가 빈 응답을 반환했습니다.")
```

---

## 7️⃣ 성능 최적화

### 7.1 모델 선택 전략

| 작업 | 모델 | 이유 |
|------|------|------|
| **STT** | Gemini 2.5 Pro | 고정밀 음성 인식 + 화자 분리 필요 |
| **문단 요약** | Gemini 2.5 Pro | 긴 텍스트 이해 + 정확한 인용 필요 |
| **회의록 생성** | Gemini 2.5 Pro | 템플릿 준수 + 구조화된 출력 |
| **마인드맵** | Gemini 2.5 Flash | 간단한 키워드 추출 (빠르고 저렴) |

**비용 절감**:
- Flash 모델은 Pro 대비 **20배 저렴**
- 마인드맵은 1회성 작업 → Flash로 충분

---

### 7.2 캐싱 전략

**현재 미구현, 향후 개선 가능**:
```python
# 동일 meeting_id에 대한 재요청 시 캐시 활용
def summarize(meeting_id):
    # 캐시 체크
    cached = cache.get(f"summary_{meeting_id}")
    if cached:
        return cached

    # 생성 후 캐시 저장
    summary = stt_manager.subtopic_generate(...)
    cache.set(f"summary_{meeting_id}", summary, ttl=3600)
```

---

## 8️⃣ 테스트 및 검증

### 8.1 요약 존재 여부 확인 API

**위치**: `routes/summary.py:93-136`

```python
@summary_bp.route("/api/check_summary/<string:meeting_id>")
@login_required
def check_summary(meeting_id):
    # ChromaDB에서 문단 요약 조회
    summary_content = vdb_manager.get_summary_by_meeting_id(meeting_id)

    if summary_content:
        return jsonify({
            "success": True,
            "has_summary": True,
            "summary": summary_content
        })
    else:
        return jsonify({
            "success": True,
            "has_summary": False,
            "message": "문단 요약이 아직 생성되지 않았습니다."
        })
```

---

### 8.2 회의록 조회 API

**위치**: `routes/summary.py:214-259`

```python
@summary_bp.route("/api/get_minutes/<string:meeting_id>")
@login_required
def get_minutes(meeting_id):
    minutes_data = db.get_minutes_by_meeting_id(meeting_id)

    if minutes_data:
        return jsonify({
            "success": True,
            "has_minutes": True,
            "minutes": minutes_data['minutes_content'],
            "created_at": minutes_data['created_at'],
            "updated_at": minutes_data['updated_at']
        })
```

---

## 9️⃣ 권한 관리 통합

### 9.1 접근 권한 체크

**모든 요약/회의록 API에서 권한 체크 수행**:

```python
# routes/summary.py:40-44
user_id = session['user_id']
if not can_access_meeting(user_id, meeting_id):
    return jsonify({
        "success": False,
        "error": "접근 권한이 없습니다."
    }), 403
```

**권한 체크 로직** (`utils/user_manager.py:335-385`):
```python
def can_access_meeting(user_id, meeting_id):
    # 1. 본인이 생성한 노트인가?
    if is_owner:
        return True

    # 2. 공유받은 노트인가?
    if is_shared:
        return True

    # 3. Admin 권한이 있는가?
    if is_admin:
        return True

    return False
```

---

## 🔟 실제 사용 시나리오

### 시나리오 1: 문단 요약 생성

1. **사용자**: 회의 업로드 완료 후 "요약 생성" 버튼 클릭
2. **프론트엔드**: `POST /api/summarize/{meeting_id}` 호출
3. **백엔드**:
   - `db.get_meeting_by_id()` → 전사 내용 조회
   - `stt_manager.subtopic_generate()` → Gemini 2.5 Pro로 요약 생성
   - `vdb_manager.add_meeting_as_subtopic()` → ChromaDB에 벡터 저장
4. **응답**: `{"success": true, "summary": "### 주제1\n* 내용..."}`
5. **프론트엔드**: 마크다운 렌더링 후 사용자에게 표시

---

### 시나리오 2: 회의록 생성

1. **사용자**: "회의록 생성" 버튼 클릭
2. **프론트엔드**: `POST /api/generate_minutes/{meeting_id}` 호출
3. **백엔드**:
   - `db.get_meeting_by_id()` → 전사 내용 조회
   - `vdb_manager.get_chunks_by_meeting_id()` → 청크 조회
   - `stt_manager.generate_minutes()` → Gemini 2.5 Pro로 회의록 생성
   - `db.save_minutes()` → SQLite에 저장
4. **응답**: `{"success": true, "minutes": "# 팀 회의\n**일시**: ..."}`
5. **프론트엔드**: 회의록 뷰어로 표시

---

## 📈 주요 메트릭

| 항목 | 수치/설명 |
|------|-----------|
| **문단 요약 생성 시간** | 10~30초 (전사 길이에 비례) |
| **회의록 생성 시간** | 15~40초 |
| **마인드맵 생성 시간** | 3~8초 (Flash 모델 사용) |
| **프롬프트 길이 (요약)** | ~500 토큰 + 전사 내용 |
| **프롬프트 길이 (회의록)** | ~600 토큰 + 전사 + 요약 |
| **출력 토큰 (요약)** | 500~2000 토큰 |
| **출력 토큰 (회의록)** | 800~3000 토큰 |

---

## 🎓 학습 포인트

### 핵심 개념 정리

1. **프롬프트 엔지니어링**: LLM에게 정확한 출력을 받기 위한 지침 설계
2. **Few-shot Learning**: 예시를 제공하여 출력 패턴 학습
3. **템플릿 기반 생성**: 고정된 형식에 동적 내용 주입
4. **이중 저장 전략**: ChromaDB (검색용) + SQLite (문서 저장용)
5. **모델 선택 최적화**: Pro (정밀) vs Flash (빠름) 전략적 사용

---

### 코드 리뷰 체크리스트

- [ ] 프롬프트에 명확한 출력 형식이 지정되어 있는가?
- [ ] JSON 파싱 실패 시 디버깅 로직이 있는가?
- [ ] Gemini 안전 필터링 체크가 포함되어 있는가?
- [ ] 권한 체크가 모든 API에 적용되어 있는가?
- [ ] ChromaDB vs SQLite 저장 기준이 명확한가?
- [ ] 에러 발생 시 사용자 친화적인 메시지를 반환하는가?

---

## 📞 다음 단계

- **챗봇 시스템 이해**: `06_chatbot_rag.md`로 이동
- **데이터베이스 스키마**: `07_database.md` 참고
- **API 전체 문서**: `11_api_specification.md` 참고

---

## 🔗 관련 파일

### 라우트
- `routes/summary.py` - 요약/회의록 API 엔드포인트

### 비즈니스 로직
- `utils/stt.py:171-239` - `subtopic_generate()` (문단 요약)
- `utils/stt.py:241-361` - `generate_minutes()` (회의록 생성)
- `utils/stt.py:449-543` - `extract_mindmap_keywords()` (마인드맵)

### 데이터 관리
- `utils/vector_db_manager.py:734-850` - `add_meeting_as_subtopic()` (ChromaDB 저장)
- `utils/db_manager.py:467-503` - `save_minutes()` (SQLite 저장)

### 프론트엔드
- `templates/summary_template.html` - 요약/회의록 렌더링
- `static/js/markmap.js` - 마인드맵 시각화
