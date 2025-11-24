# Utils 디렉토리 리팩토링 계획

> 실제 코드 수정은 하지 않고, 개선 가능한 부분만 분석한 문서입니다.

---

## 📊 현재 상태 분석

### 파일별 코드 현황

| 파일 | 줄 수 | print 문 | class 수 | 주요 역할 |
|------|-------|----------|----------|----------|
| **vector_db_manager.py** | 1,069줄 | **128개** | 1개 | ChromaDB 벡터 검색 |
| **stt.py** | 530줄 | **29개** | 1개 | Gemini STT 처리 |
| **db_manager.py** | 645줄 | ✅ 0개 | 1개 | SQLite DB (리팩토링 완료) |
| **user_manager.py** | 483줄 | **5개** | 0개 | 사용자/권한 관리 |
| **chat_manager.py** | 387줄 | **15개** | 1개 | RAG 챗봇 로직 |
| **firebase_auth.py** | 107줄 | **6개** | 0개 | Firebase 인증 |
| **decorators.py** | 92줄 | ✅ 0개 | 0개 | 데코레이터 |
| **validation.py** | 55줄 | ✅ 0개 | 0개 | 입력 검증 |
| **analysis.py** | 45줄 | **1개** | 0개 | 회의 분석 |
| **document_converter.py** | 25줄 | ✅ 0개 | 0개 | 문서 변환 |

**총 184개의 print 문이 남아있음** (routes와 services는 이미 리팩토링 완료)

---

## 🔍 리팩토링 포인트

### 1. 로깅 시스템 미적용 ⚠️ (최우선)

#### 문제점
- **총 184개 print문**이 utils 파일들에 남아있음
- 시간 정보 없음, 로그 레벨 구분 불가
- 운영 환경에서 로그 파일로 저장 어려움

#### 영향이 큰 파일
1. **vector_db_manager.py (128개)** - 가장 심각
   ```python
   # 현재
   print(f"✅ meeting_chunks 컬렉션에 {len(chunks_to_add)}개 청크 추가")
   print(f"❌ 청킹 중 오류: {e}")

   # 개선 필요
   logger.info(f"✅ meeting_chunks 컬렉션에 {len(chunks_to_add)}개 청크 추가")
   logger.error(f"❌ 청킹 중 오류: {e}", exc_info=True)
   ```

2. **stt.py (29개)**
   ```python
   # 현재
   print(f"🎧 Gemini STT API로 음성 인식 중: {audio_path}")
   print(f"❌ JSON 파싱 실패: {e}")

   # 개선 필요
   logger.info(f"🎧 Gemini STT API로 음성 인식 중: {audio_path}")
   logger.error(f"❌ JSON 파싱 실패: {e}", exc_info=True)
   ```

3. **chat_manager.py (15개)**
   ```python
   # 현재
   print(f"✅ ChatManager 초기화 완료: retriever_type='{self.retriever_type}'")

   # 개선 필요
   logger.info(f"✅ ChatManager 초기화 완료: retriever_type='{self.retriever_type}'")
   ```

#### 개선 방법
```python
# 각 파일 상단에 추가
import logging
logger = logging.getLogger(__name__)

# 모든 print()를 적절한 로그 레벨로 변경
# ✅ 성공 메시지 → logger.info()
# ⚠️ 경고 → logger.warning()
# ❌ 에러 → logger.error(..., exc_info=True)
```

#### 예상 효과
- 로그 레벨별 필터링 가능
- 타임스탬프 자동 기록
- 운영 환경 로그 파일 저장 가능

---

### 2. Singleton 패턴 미적용 🔄

#### 문제점
**VectorDBManager**, **STTManager**, **ChatManager**가 여러 곳에서 중복 생성됨

#### 현재 상황
```python
# routes/summary.py
stt_manager = STTManager()

# routes/admin.py
stt_manager = STTManager()

# services/upload_service.py
self.stt_manager = STTManager()

# routes/chat.py
chat_manager = ChatManager(vdb_manager, retriever_type="similarity")
```
→ **각 인스턴스가 내부에서 API 클라이언트를 새로 생성** (메모리 낭비)

#### 개선 방법
**db_manager.py처럼 Singleton 패턴 적용**

```python
class VectorDBManager:
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, persist_directory="./database/vector_db", ...):
        if self._initialized:
            return

        # 초기화 코드
        self._initialized = True
```

#### 적용 대상
1. **VectorDBManager** - ChromaDB 클라이언트 재사용
2. **STTManager** - Gemini 클라이언트 재사용
3. **ChatManager** - Gemini 클라이언트 재사용

#### 예상 효과
- 메모리 사용량 감소 (인스턴스 3개 → 1개씩)
- API 클라이언트 초기화 오버헤드 제거
- 일관된 설정 유지

---

### 3. 환경 변수 로딩 중복 🔁

#### 문제점
여러 파일에서 `load_dotenv()` 반복 호출

```python
# utils/vector_db_manager.py
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

# utils/chat_manager.py
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

# utils/stt.py
load_dotenv()
```

→ **config.py에서 이미 로드했는데 중복 로딩**

#### 개선 방법
**환경 변수 로딩은 config.py에서만 수행**

```python
# utils 파일들에서 제거
# load_dotenv() 호출 삭제

# 대신 config.py에서 가져오기
from config import config
api_key = config.GOOGLE_API_KEY  # os.getenv() 대신
```

#### 예상 효과
- 코드 중복 제거
- 환경 변수 관리 중앙화
- 설정 변경 시 config.py만 수정

---

### 4. 의존성 주입 부족 💉

#### 문제점
클래스가 내부에서 직접 의존성을 생성함

```python
# utils/vector_db_manager.py
class VectorDBManager:
    def __init__(self, persist_directory="./database/vector_db", ...):
        self.client = chromadb.PersistentClient(path=persist_directory)  # 내부 생성
        self.embedding_function = OpenAIEmbeddings()  # 내부 생성
        self.llm = ChatOpenAI(api_key=os.getenv("OPENAI_API_KEY"), temperature=0)  # 내부 생성

# utils/chat_manager.py
class ChatManager:
    def __init__(self, vector_db_manager, retriever_type="similarity"):
        api_key = os.environ.get("GOOGLE_API_KEY")
        self.gemini_client = genai.Client(api_key=api_key)  # 내부 생성
```

→ **테스트하기 어렵고, 의존성 교체 불가능**

#### 개선 방법 (선택적)
**의존성을 외부에서 주입받도록 변경**

```python
class VectorDBManager:
    def __init__(
        self,
        persist_directory="./database/vector_db",
        client=None,  # 외부 주입 가능
        embedding_function=None,  # 외부 주입 가능
        ...
    ):
        self.client = client or chromadb.PersistentClient(path=persist_directory)
        self.embedding_function = embedding_function or OpenAIEmbeddings()
```

#### 예상 효과
- 테스트 시 Mock 객체 주입 가능
- 유연성 증가 (다른 임베딩 모델로 교체 가능)

---

### 5. 에러 처리 개선 필요 ⚠️

#### 문제점
많은 곳에서 `except:` (bare except) 사용

```python
# utils/stt.py
try:
    parts = time_str.split(":")
    # ...
except:  # ❌ 모든 예외를 잡아버림 (KeyboardInterrupt도!)
    return 0.0
```

#### 개선 방법
**구체적인 예외 타입 지정**

```python
try:
    parts = time_str.split(":")
    # ...
except (ValueError, AttributeError) as e:  # ✅ 구체적인 예외만
    logger.warning(f"시간 파싱 실패: {e}")
    return 0.0
```

#### 예상 효과
- 예상치 못한 에러 감지 가능
- 디버깅 용이
- 안전성 향상

---

## 🎯 우선순위별 리팩토링 계획

### 🔴 최우선 (High Priority)

1. **로깅 시스템 도입** - 184개 print문 교체
   - vector_db_manager.py (128개)
   - stt.py (29개)
   - chat_manager.py (15개)
   - 나머지 파일들 (12개)

### 🟡 중간 우선순위 (Medium Priority)

2. **Singleton 패턴 적용**
   - VectorDBManager
   - STTManager
   - ChatManager

3. **환경 변수 로딩 중복 제거**
   - load_dotenv() 호출 제거
   - config.py에서 import

### 🟢 낮은 우선순위 (Low Priority)

4. **의존성 주입** (선택적)
   - 테스트가 필요한 경우만 적용

5. **에러 처리 개선**
   - bare except 제거
   - 구체적인 예외 타입 지정

---

## 📈 예상 개선 효과

### 성능
- **메모리**: VectorDBManager, STTManager, ChatManager 인스턴스 통합 (약 50% 절감)
- **초기화 시간**: API 클라이언트 중복 생성 제거

### 개발자 경험
- **디버깅**: 타임스탬프와 로그 레벨로 문제 추적 용이
- **테스트**: Singleton + 의존성 주입으로 테스트 가능성 향상
- **유지보수**: 로그 레벨별 필터링으로 원하는 정보만 확인

### 운영
- **모니터링**: 표준 logging 모듈로 로그 수집 도구 연동 가능
- **환경 관리**: config.py 중앙 관리로 설정 변경 용이

---

## 💡 결론

### 🚨 가장 시급한 작업
**로깅 시스템 도입 (184개 print문 교체)**
- vector_db_manager.py의 128개 print문이 가장 큰 문제
- 운영 환경 대비를 위해 필수적

### 🎯 단계별 실행 순서 (권장)

1. **1단계**: 로깅 시스템 도입 (1-2시간)
   - 각 utils 파일에 `import logging` + `logger` 추가
   - 184개 print문을 logger로 교체

2. **2단계**: Singleton 패턴 적용 (30분)
   - VectorDBManager, STTManager, ChatManager
   - db_manager.py와 동일한 패턴 적용

3. **3단계**: 환경 변수 중복 제거 (15분)
   - load_dotenv() 호출 제거
   - config.py에서 import로 변경

4. **4단계**: 에러 처리 개선 (선택적)
   - bare except 찾아서 구체적인 예외로 변경

### ⏱️ 총 예상 시간
**약 2-3시간 소요** (로깅 시스템이 대부분)

---

## ✅ 체크리스트

리팩토링 시 확인할 사항:

- [ ] 모든 print문을 적절한 로그 레벨로 변경했는가?
  - [ ] ✅ 성공 메시지 → `logger.info()`
  - [ ] ⚠️ 경고 → `logger.warning()`
  - [ ] ❌ 에러 → `logger.error(..., exc_info=True)`

- [ ] Singleton 패턴이 올바르게 동작하는가?
  - [ ] `_instance`, `_initialized` 변수 사용
  - [ ] `__new__` 메서드 구현
  - [ ] 여러 번 호출해도 같은 인스턴스 반환

- [ ] 환경 변수를 config.py에서만 로드하는가?
  - [ ] utils 파일에서 `load_dotenv()` 제거
  - [ ] `from config import config` 사용

- [ ] 모든 코드가 문법 검증을 통과하는가?
  - [ ] `python3 -m py_compile utils/*.py` 실행

- [ ] 기존 기능이 정상 동작하는가?
  - [ ] 로그인 테스트
  - [ ] 노트 생성 테스트
  - [ ] 챗봇 테스트
