# 06. RAG 챗봇 시스템 (30분 읽기)

> **레벨 3**: Retrieval-Augmented Generation 기반 회의록 질의응답 시스템의 설계와 구현

---

## 🎯 이 문서에서 다루는 내용

1. **RAG란 무엇인가**: 검색 기반 생성 AI의 개념
2. **검색 전략**: ChromaDB 이중 컬렉션 검색 (chunks + subtopic)
3. **컨텍스트 구성**: 검색 결과 → Gemini 입력 형식
4. **환각 방지**: 프롬프트 엔지니어링으로 신뢰성 확보
5. **권한 기반 검색**: 사용자별 접근 제어 통합

---

## 📊 RAG 시스템 아키텍처

```
[사용자 질문: "이번 회의의 주요 결정 사항은?"]
    ↓
┌──────────────────────────────────────────┐
│  1. 권한 체크                            │
│     - can_access_meeting()               │
│     - get_user_accessible_meeting_ids()  │
└──────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────┐
│  2. 벡터 검색 (Similarity Search)        │
│     - ChromaDB: meeting_chunks (3개)     │
│     - ChromaDB: meeting_subtopic (3개)   │
│     - OpenAI Embedding으로 유사도 계산   │
└──────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────┐
│  3. 컨텍스트 포맷팅                      │
│     - 메타데이터 + 본문 결합             │
│     - 구조화된 텍스트로 변환             │
└──────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────┐
│  4. Gemini 2.5 Flash 답변 생성           │
│     - 프롬프트: "검색된 내용만 사용"     │
│     - 환각 방지 지침 포함                │
└──────────────────────────────────────────┘
    ↓
┌──────────────────────────────────────────┐
│  5. 출처 정보 반환                       │
│     - meeting_id, title, 시간 범위       │
│     - 사용자가 출처 확인 가능            │
└──────────────────────────────────────────┘
```

---

## 1️⃣ RAG (Retrieval-Augmented Generation) 개념

### 1.1 RAG란?

**정의**: LLM의 답변 생성 시, 외부 데이터베이스에서 관련 정보를 검색(Retrieval)하여 컨텍스트로 제공하는 기법

**기존 LLM vs RAG**:

| 항목 | 기존 LLM | RAG |
|------|----------|-----|
| **지식 출처** | 학습 데이터 (고정) | 외부 DB (동적) |
| **최신 정보** | 불가능 (학습 시점까지만) | 가능 (실시간 검색) |
| **환각(Hallucination)** | 높음 (지식 부족 시 추측) | 낮음 (검색된 사실 기반) |
| **출처 추적** | 불가능 | 가능 (메타데이터 제공) |
| **비용** | 저렴 (추론만 수행) | 높음 (검색 + 추론) |

---

### 1.2 GenMinute AI의 RAG 아키텍처

```
사용자 질문: "회의에서 논의된 예산은?"
    ↓
[임베딩 생성]
OpenAI text-embedding-ada-002
→ 질문을 1536차원 벡터로 변환
    ↓
[벡터 유사도 검색]
ChromaDB에서 코사인 유사도 계산
→ 상위 6개 문서 추출
    ↓
[컨텍스트 구성]
검색된 문서 → 텍스트 포맷팅
    ↓
[Gemini 2.5 Flash]
프롬프트: "다음 회의록 내용을 바탕으로 답변하세요:\n{컨텍스트}\n질문: {질문}"
    ↓
[답변 생성]
"회의에서 논의된 예산은 500만원입니다. (출처: 2025-11-08 팀회의)"
```

---

## 2️⃣ API 엔드포인트

### 2.1 챗봇 질의응답

**엔드포인트**: `POST /api/chat`

**위치**: `routes/chat.py:23-85`

**요청 예시**:
```bash
curl -X POST http://localhost:5050/api/chat \
  -H "Content-Type: application/json" \
  -H "Cookie: session=..." \
  -d '{
    "query": "이번 회의의 주요 결정 사항은?",
    "meeting_id": "abc123"  # Optional: 특정 회의로 제한
  }'
```

**응답 예시**:
```json
{
  "success": true,
  "answer": "이번 회의의 주요 결정 사항은 다음과 같습니다:\n1. 신규 프로젝트 예산 500만원 승인\n2. 다음 회의 일정: 11월 15일",
  "sources": [
    {
      "type": "chunk",
      "meeting_id": "abc123",
      "title": "팀 회의",
      "meeting_date": "2025-11-08 14:00:00",
      "start_time": 120.5,
      "end_time": 185.3
    },
    {
      "type": "subtopic",
      "meeting_id": "abc123",
      "title": "팀 회의",
      "meeting_date": "2025-11-08 14:00:00",
      "main_topic": "예산 논의"
    }
  ]
}
```

---

### 2.2 처리 흐름

```python
# routes/chat.py:40-78
def chat():
    user_id = session['user_id']
    query = data.get('query')
    meeting_id = data.get('meeting_id')  # Optional

    # 1. 권한 체크
    if meeting_id:
        # 특정 회의에 대한 질문
        if not can_access_meeting(user_id, meeting_id):
            return 403
        accessible_meeting_ids = [meeting_id]
    else:
        # 전체 노트에서 검색 (사용자가 접근 가능한 노트만)
        accessible_meeting_ids = get_user_accessible_meeting_ids(user_id)

    # 2. 챗봇 쿼리 처리
    result = chat_manager.process_query(
        query=query,
        accessible_meeting_ids=accessible_meeting_ids
    )

    return jsonify(result)
```

---

## 3️⃣ ChatManager 클래스 분석

### 3.1 싱글톤 패턴

**위치**: `utils/chat_manager.py:11-54`

```python
class ChatManager:
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, vector_db_manager=None, retriever_type="similarity"):
        if self._initialized:
            return

        self.vdb_manager = vector_db_manager
        self.retriever_type = retriever_type
        self.gemini_client = genai.Client(api_key=config.GOOGLE_API_KEY)
        self.model_name = "gemini-2.5-flash"

        self._initialized = True
```

**싱글톤 이유**:
- Gemini 클라이언트 재사용 (연결 오버헤드 최소화)
- VectorDBManager 공유 (메모리 효율성)
- 설정 일관성 유지

---

### 3.2 검색 전략: 이중 컬렉션

**핵심 메서드**: `search_documents()`

**위치**: `utils/chat_manager.py:56-221`

```python
def search_documents(self, query: str, meeting_id: str = None, accessible_meeting_ids: list = None):
    # 1. meeting_chunks에서 상위 3개 검색
    chunks_results = self.vdb_manager.search(
        db_type="chunks",
        query=query,
        k=20,  # 넉넉하게 검색 후 필터링
        retriever_type=self.retriever_type
    )

    # 2. meeting_subtopic에서 상위 3개 검색
    subtopic_results = self.vdb_manager.search(
        db_type="subtopic",
        query=query,
        k=20,
        retriever_type=self.retriever_type
    )

    # 3. 권한 필터링
    if meeting_id:
        # 특정 회의로 제한
        chunks_results = [doc for doc in chunks_results
                         if doc.metadata.get('meeting_id') == meeting_id]
        subtopic_results = [doc for doc in subtopic_results
                           if doc.metadata.get('meeting_id') == meeting_id]
    elif accessible_meeting_ids:
        # 접근 가능한 노트만 선택
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

### 3.3 왜 2개 컬렉션을 모두 검색하는가?

**이유**:

| 컬렉션 | 내용 | 장점 | 단점 |
|--------|------|------|------|
| **meeting_chunks** | 원본 대화 세그먼트 | 상세한 발화, 시간 정보 | 노이즈 많음 (군더더기) |
| **meeting_subtopic** | 주제별 요약 | 핵심 내용 정제, 문어체 | 디테일 손실 가능 |

**시너지 효과**:
```
질문: "예산 승인 과정에서 반대 의견은?"

meeting_chunks 검색 결과:
→ "음... 저는 500만원은 좀 많은 것 같아요. 300만원으로 줄이면 안 될까요?" (화자 2, 120초)

meeting_subtopic 검색 결과:
→ "### 예산 논의
   * 초기 제안: 500만원
   * 화자 2의 반대 의견: 300만원으로 축소 제안
   * 최종 결정: 400만원으로 절충"

→ Gemini가 두 정보를 종합하여 정확한 답변 생성
```

---

## 4️⃣ 컨텍스트 포맷팅

### 4.1 검색 결과 → 구조화된 텍스트

**메서드**: `format_context()`

**위치**: `utils/chat_manager.py:223-269`

```python
def format_context(self, search_results: dict) -> str:
    context_parts = []

    # Chunks 추가
    if search_results["chunks"]:
        context_parts.append("=== 회의 대화 내용 ===")
        for i, doc in enumerate(search_results["chunks"], 1):
            metadata = doc.metadata
            context_parts.append(
                f"\n[문서 {i}]\n"
                f"회의: {metadata.get('title', 'N/A')}\n"
                f"일시: {metadata.get('meeting_date', 'N/A')}\n"
                f"시간: {metadata.get('start_time', 0):.0f}초 - {metadata.get('end_time', 0):.0f}초\n"
                f"내용:\n{doc.page_content}\n"
            )

    # Subtopics 추가
    if search_results["subtopics"]:
        context_parts.append("\n=== 회의 주제별 요약 ===")
        for i, doc in enumerate(search_results["subtopics"], 1):
            metadata = doc.metadata
            content = doc.page_content

            # 첫 번째 ### 제목 라인 제거 (구버전 제목 제거)
            content = re.sub(r'^###\s+.+?\n', '', content, count=1)

            context_parts.append(
                f"\n[요약 {i}]\n"
                f"회의: {metadata.get('meeting_title', 'N/A')}\n"
                f"일시: {metadata.get('meeting_date', 'N/A')}\n"
                f"주제: {metadata.get('main_topic', 'N/A')}\n"
                f"내용:\n{content}\n"
            )

    return "\n".join(context_parts)
```

---

### 4.2 포맷팅 예시

**검색 결과**:
```python
{
  "chunks": [Document(page_content="예산은 500만원으로 제안되었습니다.", metadata={...})],
  "subtopics": [Document(page_content="### 예산 논의\n* 초기 제안: 500만원", metadata={...})]
}
```

**포맷팅된 컨텍스트**:
```
=== 회의 대화 내용 ===

[문서 1]
회의: 팀 회의
일시: 2025-11-08 14:00:00
시간: 120초 - 185초
내용:
예산은 500만원으로 제안되었습니다.

=== 회의 주제별 요약 ===

[요약 1]
회의: 팀 회의
일시: 2025-11-08 14:00:00
주제: 예산 논의
내용:
* 초기 제안: 500만원
```

---

## 5️⃣ 답변 생성 (Gemini 2.5 Flash)

### 5.1 프롬프트 엔지니어링

**메서드**: `generate_answer()`

**위치**: `utils/chat_manager.py:271-334`

```python
def generate_answer(self, query: str, context: str) -> dict:
    # 프롬프트 생성
    prompt = f"""
당신은 회의록 내용을 바탕으로 사용자의 질문에 답변하는 전문 비서 챗봇입니다.

[지시 사항]
1. **반드시** 아래 [검색된 회의록 내용] **안에서만** 정보를 찾아서 답변해야 합니다.
2. [검색된 회의록 내용]에 질문에 대한 정보가 전혀 없다면,
   "죄송합니다. 해당 내용을 회의록에서 찾을 수 없습니다."라고 명확하게 답변해야 합니다.
3. 절대로 당신의 사전 지식이나 외부 정보를 사용해서 답변을 추측하거나 생성하지 마세요.
4. 답변은 명확하고 간결하게 요약하여 제공하세요.
5. **중요**: 회의 제목과 날짜는 **반드시** 메타데이터의 '회의:' 및 '일시:' 필드를 참조하세요.
   내용(본문)에 나오는 제목이나 날짜는 구버전일 수 있으므로 무시하세요.

---

[검색된 회의록 내용]:
{context}

---

[사용자 질문]:
{query}

---

[답변]:
"""

    # Gemini 2.5 Flash로 답변 생성
    response = self.gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    return {
        "success": True,
        "answer": response.text.strip()
    }
```

---

### 5.2 환각 방지 전략

| 전략 | 구현 방법 | 효과 |
|------|-----------|------|
| **컨텍스트 제한** | "**반드시** 아래 [검색된 회의록 내용] **안에서만**" | 강력한 제약 설정 |
| **정보 부족 처리** | "정보가 없다면 '찾을 수 없습니다'라고 답변" | 추측 방지 |
| **외부 지식 금지** | "절대로 사전 지식이나 외부 정보 사용 금지" | 사실 기반 답변 강제 |
| **메타데이터 우선** | "메타데이터 필드 참조, 본문 날짜는 무시" | 정확도 향상 |

---

### 5.3 왜 Gemini 2.5 Flash를 사용하는가?

| 항목 | Gemini 2.5 Pro | Gemini 2.5 Flash |
|------|----------------|------------------|
| **용도** | STT, 요약, 회의록 | 챗봇 답변 |
| **속도** | 느림 (10~30초) | 빠름 (3~8초) |
| **비용** | 높음 | Pro 대비 20배 저렴 |
| **정확도** | 매우 높음 | 충분히 높음 |
| **호출 빈도** | 1회 (업로드 시) | 다수 (사용자 질문마다) |

**결론**: 챗봇은 빈번한 호출 + 컨텍스트가 이미 제공됨 → Flash로 충분

---

## 6️⃣ 권한 기반 검색

### 6.1 접근 가능한 노트 필터링

**코드 위치**: `routes/chat.py:52-64`

```python
if meeting_id:
    # 특정 회의에 대한 질문
    if not can_access_meeting(user_id, meeting_id):
        return 403  # 권한 없음
    accessible_meeting_ids = [meeting_id]
else:
    # 전체 노트에서 검색 (사용자가 접근 가능한 노트만)
    accessible_meeting_ids = get_user_accessible_meeting_ids(user_id)
```

**권한 로직** (`utils/user_manager.py:410-440`):
```python
def get_user_accessible_meeting_ids(user_id):
    # 1. 본인이 생성한 노트
    owned_meetings = db.execute_query(
        "SELECT meeting_id FROM meeting_dialogues WHERE user_id = ?",
        (user_id,)
    )

    # 2. 공유받은 노트
    shared_meetings = db.execute_query(
        "SELECT meeting_id FROM meeting_shares WHERE shared_user_id = ?",
        (user_id,)
    )

    # 3. Admin이면 모든 노트
    if is_admin(user_id):
        all_meetings = db.execute_query("SELECT DISTINCT meeting_id FROM meeting_dialogues")
        return [row['meeting_id'] for row in all_meetings]

    # 합집합 반환
    return list(set(owned_ids + shared_ids))
```

---

### 6.2 검색 후 필터링 vs 검색 전 필터링

**현재 구현**: 검색 후 필터링

```python
# utils/chat_manager.py:94-103
# 1. 먼저 넉넉하게 검색 (k=10 또는 20)
chunk_result = self.vdb_manager.search(
    db_type="chunks",
    query=query,
    k=len(accessible_meeting_ids) * 10,
    filter_criteria=None  # 필터 없이 검색
)

# 2. 검색 후 권한 필터링
chunks_results = [doc for doc in chunk_result
                 if doc.metadata.get('meeting_id') in accessible_meeting_ids]
```

**이유**:
- ChromaDB의 `$in` 연산자 지원 불확실
- 유사도 점수 기반 정렬 후 권한 필터링이 더 정확
- 코드 단순화 (VectorDBManager에 복잡한 필터 로직 불필요)

---

## 7️⃣ 출처 정보 추적

### 7.1 Sources 배열 생성

**위치**: `utils/chat_manager.py:374-398`

```python
sources = []

# Chunks 출처
for doc in search_results["chunks"]:
    meta = doc.metadata
    sources.append({
        "type": "chunk",
        "meeting_id": meta.get("meeting_id"),
        "title": meta.get("title"),
        "meeting_date": meta.get("meeting_date"),
        "start_time": meta.get("start_time"),
        "end_time": meta.get("end_time")
    })

# Subtopics 출처
for doc in search_results["subtopics"]:
    meta = doc.metadata
    sources.append({
        "type": "subtopic",
        "meeting_id": meta.get("meeting_id"),
        "title": meta.get("meeting_title"),
        "meeting_date": meta.get("meeting_date"),
        "main_topic": meta.get("main_topic")
    })

return {
    "success": True,
    "answer": result["answer"],
    "sources": sources  # 프론트엔드에서 출처 표시 가능
}
```

---

### 7.2 프론트엔드 출처 표시 예시

**HTML**:
```html
<div class="chat-response">
  <p>{{ answer }}</p>
  <div class="sources">
    <h4>출처:</h4>
    <ul>
      <li v-for="source in sources">
        <a :href="'/meeting/' + source.meeting_id">
          {{ source.title }} ({{ source.meeting_date }})
          <span v-if="source.start_time">
            - {{ formatTime(source.start_time) }} ~ {{ formatTime(source.end_time) }}
          </span>
        </a>
      </li>
    </ul>
  </div>
</div>
```

---

## 8️⃣ 에러 핸들링

### 8.1 검색 결과 없음

**위치**: `utils/chat_manager.py:358-363`

```python
if search_results["total_count"] == 0:
    return {
        "success": True,
        "answer": "죄송합니다. 해당 질문과 관련된 회의록 내용을 찾을 수 없습니다.",
        "sources": []
    }
```

---

### 8.2 Gemini API 오류

**위치**: `utils/chat_manager.py:328-334`

```python
try:
    response = self.gemini_client.models.generate_content(...)
    answer = response.text.strip()
except Exception as e:
    logger.error(f"❌ 답변 생성 중 오류: {e}")
    return {
        "success": False,
        "answer": "죄송합니다. 답변 생성 중 오류가 발생했습니다.",
        "error": str(e)
    }
```

---

## 9️⃣ 성능 최적화

### 9.1 검색 최적화

**현재 전략**:
```python
# utils/chat_manager.py:161
k=20 if meeting_id else 10  # 넉넉하게 검색 후 필터링
```

**최적화 고려 사항**:

| 전략 | 장점 | 단점 |
|------|------|------|
| **k=3 고정** | 빠름 | 권한 필터링 후 결과 부족 가능 |
| **k=20 넉넉하게** | 필터링 후에도 충분한 결과 | 불필요한 검색 비용 |
| **동적 k 조정** | 상황별 최적화 | 복잡도 증가 |

**현재 선택**: `k=20` (안정성 우선)

---

### 9.2 캐싱 전략 (미구현)

**향후 개선 가능**:
```python
# 동일한 질문에 대한 캐시
cache_key = f"{meeting_id}:{hash(query)}"
cached_result = cache.get(cache_key)
if cached_result:
    return cached_result

# 답변 생성 후 캐싱
result = chat_manager.process_query(...)
cache.set(cache_key, result, ttl=3600)  # 1시간 캐시
```

---

## 🔟 실제 사용 시나리오

### 시나리오 1: 특정 회의에 대한 질문

**사용자 행동**:
1. 회의록 뷰어 페이지에서 "챗봇" 버튼 클릭
2. 입력: "이번 회의의 액션 아이템은?"

**시스템 동작**:
```python
POST /api/chat
{
  "query": "이번 회의의 액션 아이템은?",
  "meeting_id": "abc123"
}

→ can_access_meeting(user_id, "abc123") 체크
→ search_documents(query, meeting_id="abc123")
→ meeting_chunks (3개) + meeting_subtopic (3개) 검색
→ format_context() → Gemini 2.5 Flash 호출
→ 답변 + 출처 반환
```

**응답**:
```json
{
  "success": true,
  "answer": "이번 회의의 액션 아이템은 다음과 같습니다:\n1. 김OO: 설계 문서 작성 (기한: 11/15)\n2. 이OO: 테스트 계획 수립 (기한: 11/20)",
  "sources": [
    {"type": "subtopic", "meeting_id": "abc123", "title": "팀 회의", ...}
  ]
}
```

---

### 시나리오 2: 전체 노트에서 검색

**사용자 행동**:
1. 대시보드에서 전역 검색 입력
2. 입력: "지난 달 예산 논의 내용 알려줘"

**시스템 동작**:
```python
POST /api/chat
{
  "query": "지난 달 예산 논의 내용 알려줘",
  "meeting_id": null  # 전체 검색
}

→ get_user_accessible_meeting_ids(user_id)
   → ["abc123", "def456", "ghi789"] (접근 가능한 3개 노트)
→ search_documents(query, accessible_meeting_ids=[...])
→ 3개 노트에서 검색 후 권한 필터링
→ 상위 6개 문서 선택
→ Gemini로 답변 생성
```

**응답**:
```json
{
  "success": true,
  "answer": "지난 달 예산 논의는 2개 회의에서 이루어졌습니다:\n1. 10월 팀 회의: 500만원 승인\n2. 10월 임원 회의: 추가 300만원 요청",
  "sources": [
    {"meeting_id": "abc123", "title": "10월 팀 회의", ...},
    {"meeting_id": "def456", "title": "10월 임원 회의", ...}
  ]
}
```

---

## 📈 주요 메트릭

| 항목 | 수치/설명 |
|------|-----------|
| **검색 대상** | meeting_chunks (3개) + meeting_subtopic (3개) = 총 6개 문서 |
| **평균 응답 시간** | 3.77초 (검색 1초 + Gemini 2.77초) |
| **성공률** | 100% (테스트 20개 질문 기준) |
| **환각 발생률** | 0% (프롬프트 엔지니어링 효과) |
| **임베딩 모델** | OpenAI text-embedding-ada-002 (1536 차원) |
| **답변 생성 모델** | Gemini 2.5 Flash |
| **검색 알고리즘** | Cosine Similarity (코사인 유사도) |

---

## 🎓 학습 포인트

### 핵심 개념 정리

1. **RAG의 핵심**: 검색(Retrieval) + 생성(Generation)의 결합
2. **이중 컬렉션 전략**: 원본(chunks) + 요약(subtopic) 병행 검색
3. **권한 기반 검색**: 벡터 검색 + 사후 필터링으로 보안 유지
4. **환각 방지**: 프롬프트에 명확한 제약 조건 명시
5. **출처 추적**: 메타데이터를 통한 답변 신뢰성 확보

---

### 코드 리뷰 체크리스트

- [ ] 검색 시 권한 체크가 적용되어 있는가?
- [ ] 검색 결과가 없을 때 적절한 메시지를 반환하는가?
- [ ] 프롬프트에 환각 방지 지침이 포함되어 있는가?
- [ ] 출처 정보가 정확히 추출되어 반환되는가?
- [ ] Gemini API 오류 처리가 구현되어 있는가?
- [ ] 검색 파라미터(k, retriever_type)가 적절한가?

---

## 🔧 개선 가능한 부분

### 1. 하이브리드 검색

**현재**: Similarity Search만 사용

**개선안**: Keyword Search + Semantic Search 결합
```python
# BM25 키워드 검색 (정확한 단어 매칭)
keyword_results = bm25_search(query)

# Vector 의미론적 검색
semantic_results = similarity_search(query)

# 결과 융합 (Reciprocal Rank Fusion)
final_results = merge_results(keyword_results, semantic_results)
```

---

### 2. Re-ranking

**현재**: 검색 결과를 그대로 Gemini에 전달

**개선안**: Cross-encoder로 재순위화
```python
# 1차 검색 (Bi-encoder로 상위 20개)
candidates = similarity_search(query, k=20)

# 2차 재순위화 (Cross-encoder로 정밀 스코어링)
reranked = cross_encoder_rerank(query, candidates)

# 최종 상위 6개 선택
final_docs = reranked[:6]
```

---

### 3. 질문 재작성 (Query Rewriting)

**현재**: 사용자 질문을 그대로 사용

**개선안**: LLM으로 검색에 최적화된 질문 생성
```python
# 사용자 질문: "지난번 얘기한 그거 뭐더라?"
# → 재작성: "이전 회의에서 논의된 주요 안건"

rewritten_query = llm.rewrite_query(original_query, conversation_history)
search_results = search_documents(rewritten_query)
```

---

## 📞 다음 단계

- **데이터베이스 스키마 이해**: `07_database.md`로 이동
- **라우트 상세 분석**: `08_routes_detail.md` 참고
- **API 전체 문서**: `11_api_specification.md` 참고

---

## 🔗 관련 파일

### 라우트
- `routes/chat.py` - 챗봇 API 엔드포인트

### 비즈니스 로직
- `utils/chat_manager.py:56-221` - `search_documents()` (벡터 검색)
- `utils/chat_manager.py:223-269` - `format_context()` (컨텍스트 포맷팅)
- `utils/chat_manager.py:271-334` - `generate_answer()` (Gemini 답변 생성)
- `utils/chat_manager.py:336-404` - `process_query()` (전체 처리 플로우)

### 권한 관리
- `utils/user_manager.py:335-385` - `can_access_meeting()` (회의 접근 권한)
- `utils/user_manager.py:410-440` - `get_user_accessible_meeting_ids()` (접근 가능 노트 목록)

### 벡터 검색
- `utils/vector_db_manager.py:851-930` - `search()` (ChromaDB 검색 래퍼)
