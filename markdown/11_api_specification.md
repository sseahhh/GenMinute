# 11. API 명세서 (실용 참고 자료)

> **레벨 5**: 모든 API 엔드포인트의 완전한 명세 및 curl 예시

---

## 🎯 이 문서의 목적

1. **API 전체 목록**: 모든 엔드포인트 한눈에 파악
2. **요청/응답 예시**: 실제 사용 가능한 curl 명령어
3. **에러 코드**: 각 상황별 HTTP 상태 코드
4. **인증 방식**: 세션 기반 인증 설명

---

## 📊 API 개요

### Base URL

```
http://localhost:5050
```

### 인증 방식

**세션 기반 인증 (Flask Session + Cookie)**

```bash
# 로그인 후 쿠키가 자동으로 설정됨
curl -c cookies.txt -X POST http://localhost:5050/api/login \
  -H "Content-Type: application/json" \
  -d '{"idToken": "..."}'

# 이후 요청 시 쿠키 사용
curl -b cookies.txt http://localhost:5050/api/meetings
```

---

## 1️⃣ 인증 API (Auth)

### 1.1 로그인 페이지

```
GET /auth/login_page
```

**응답**: HTML 페이지 (Firebase Auth UI)

**curl 예시**:
```bash
curl http://localhost:5050/auth/login_page
```

---

### 1.2 로그인 (Firebase ID Token)

```
POST /api/login
```

**요청 헤더**:
```
Content-Type: application/json
```

**요청 본문**:
```json
{
  "idToken": "eyJhbGciOiJSUzI1NiIsImtpZCI6IjY4N..."
}
```

**응답 (200 OK)**:
```json
{
  "success": true,
  "user": {
    "name": "홍길동",
    "email": "user@example.com",
    "role": "user"
  }
}
```

**에러 응답 (401 Unauthorized)**:
```json
{
  "error": "유효하지 않은 인증 토큰입니다."
}
```

**curl 예시**:
```bash
curl -c cookies.txt -X POST http://localhost:5050/api/login \
  -H "Content-Type: application/json" \
  -d '{
    "idToken": "eyJhbGciOiJSUzI1NiIsImtpZCI6IjY4N..."
  }'
```

---

### 1.3 로그아웃

```
POST /api/logout
```

**요청 헤더**:
```
Cookie: session=...
```

**응답 (200 OK)**:
```json
{
  "success": true,
  "message": "로그아웃되었습니다."
}
```

**curl 예시**:
```bash
curl -b cookies.txt -X POST http://localhost:5050/api/logout
```

---

## 2️⃣ 회의 API (Meetings)

### 2.1 회의 목록 조회

```
GET /api/meetings
```

**요청 헤더**:
```
Cookie: session=...
```

**응답 (200 OK)**:
```json
{
  "owned_meetings": [
    {
      "meeting_id": "abc-123-def-456",
      "title": "팀 회의",
      "meeting_date": "2025-11-08 14:00:00",
      "audio_file": "abc-123-def-456_audio.wav",
      "has_summary": true,
      "has_minutes": true
    }
  ],
  "shared_meetings": [
    {
      "meeting_id": "xyz-789-uvw-012",
      "title": "임원 회의",
      "owner_name": "김철수",
      "permission": "read",
      "meeting_date": "2025-11-07 10:00:00"
    }
  ]
}
```

**curl 예시**:
```bash
curl -b cookies.txt http://localhost:5050/api/meetings
```

---

### 2.2 회의 상세 조회

```
GET /api/meetings/<meeting_id>
```

**Path Parameters**:
- `meeting_id` (required): 회의 ID

**응답 (200 OK)**:
```json
{
  "meeting_id": "abc-123-def-456",
  "title": "팀 회의",
  "meeting_date": "2025-11-08 14:00:00",
  "audio_file": "abc-123-def-456_audio.wav",
  "segments": [
    {
      "speaker_label": "1",
      "start_time": 0.0,
      "segment": "안녕하세요. 회의 시작하겠습니다.",
      "confidence": 0.95
    },
    {
      "speaker_label": "2",
      "start_time": 5.2,
      "segment": "네, 좋습니다.",
      "confidence": 0.92
    }
  ],
  "speaker_stats": {
    "labels": ["화자 1", "화자 2", "화자 3"],
    "data": [45.32, 38.15, 16.53]
  }
}
```

**에러 응답 (403 Forbidden)**:
```json
{
  "error": "접근 권한이 없습니다."
}
```

**curl 예시**:
```bash
curl -b cookies.txt http://localhost:5050/api/meetings/abc-123-def-456
```

---

### 2.3 회의 생성 (메타데이터만)

```
POST /api/meetings
```

**요청 본문**:
```json
{
  "title": "팀 회의",
  "meeting_date": "2025-11-08T14:00"
}
```

**응답 (201 Created)**:
```json
{
  "success": true,
  "meeting_id": "abc-123-def-456"
}
```

**에러 응답 (400 Bad Request)**:
```json
{
  "error": "제목을 입력해 주세요."
}
```

**curl 예시**:
```bash
curl -b cookies.txt -X POST http://localhost:5050/api/meetings \
  -H "Content-Type: application/json" \
  -d '{
    "title": "팀 회의",
    "meeting_date": "2025-11-08T14:00"
  }'
```

---

### 2.4 파일 업로드 (SSE Streaming)

```
POST /api/upload
```

**요청 (multipart/form-data)**:
- `audio` (file, required): 오디오/비디오 파일
- `title` (string, required): 회의 제목
- `meeting_date` (string, optional): 회의 일시 (YYYY-MM-DDTHH:MM)

**응답 (200 OK, text/event-stream)**:
```
data: {"step":"upload","message":"파일 업로드 중...","icon":"📤","progress":0}

data: {"step":"validation","message":"파일 검증 중...","icon":"🔍","progress":10}

data: {"step":"conversion","message":"비디오 변환 중...","icon":"🎬","progress":20}

data: {"step":"stt","message":"음성 인식 중...","icon":"🎤","progress":40}

data: {"step":"db","message":"데이터베이스 저장 중...","icon":"💾","progress":60}

data: {"step":"chunking","message":"스마트 청킹 중...","icon":"📝","progress":70}

data: {"step":"mindmap","message":"마인드맵 생성 중...","icon":"🗺️","progress":90}

data: {"step":"complete","message":"완료!","meeting_id":"abc-123-def-456","progress":100}
```

**에러 응답 (SSE)**:
```
data: {"step":"error","message":"파일 크기가 너무 큽니다. (최대 500MB)"}
```

**curl 예시**:
```bash
curl -b cookies.txt -X POST http://localhost:5050/api/upload \
  -F "audio=@meeting.mp3" \
  -F "title=팀 회의" \
  -F "meeting_date=2025-11-08T14:00"
```

---

### 2.5 회의 수정

```
PATCH /api/meetings/<meeting_id>
```

**요청 본문**:
```json
{
  "title": "수정된 팀 회의 제목"
}
```

**응답 (200 OK)**:
```json
{
  "success": true,
  "message": "회의 정보가 수정되었습니다."
}
```

**curl 예시**:
```bash
curl -b cookies.txt -X PATCH http://localhost:5050/api/meetings/abc-123-def-456 \
  -H "Content-Type: application/json" \
  -d '{"title": "수정된 팀 회의 제목"}'
```

---

### 2.6 회의 삭제

```
DELETE /api/meetings/<meeting_id>
```

**응답 (200 OK)**:
```json
{
  "success": true,
  "message": "회의가 삭제되었습니다."
}
```

**curl 예시**:
```bash
curl -b cookies.txt -X DELETE http://localhost:5050/api/meetings/abc-123-def-456
```

---

### 2.7 회의 공유

```
POST /api/meetings/<meeting_id>/share
```

**요청 본문**:
```json
{
  "email": "colleague@example.com",
  "permission": "read"
}
```

**응답 (200 OK)**:
```json
{
  "success": true,
  "message": "colleague@example.com에게 공유되었습니다."
}
```

**에러 응답 (404 Not Found)**:
```json
{
  "error": "해당 이메일의 사용자를 찾을 수 없습니다."
}
```

**curl 예시**:
```bash
curl -b cookies.txt -X POST http://localhost:5050/api/meetings/abc-123-def-456/share \
  -H "Content-Type: application/json" \
  -d '{
    "email": "colleague@example.com",
    "permission": "read"
  }'
```

---

### 2.8 회의 공유 해제

```
DELETE /api/meetings/<meeting_id>/share/<user_id>
```

**응답 (200 OK)**:
```json
{
  "success": true,
  "message": "공유가 해제되었습니다."
}
```

**curl 예시**:
```bash
curl -b cookies.txt -X DELETE http://localhost:5050/api/meetings/abc-123-def-456/share/5
```

---

## 3️⃣ 요약 & 회의록 API (Summary)

### 3.1 문단 요약 생성

```
POST /api/summarize/<meeting_id>
```

**응답 (200 OK)**:
```json
{
  "success": true,
  "message": "요약이 성공적으로 생성 및 저장되었습니다.",
  "summary": "### 예산 논의\n* 초기 제안: 500만원 [cite: 1]\n* 최종 결정: 400만원 [cite: 3]\n\n### 다음 회의 일정\n* 11월 15일 오후 2시 [cite: 5]"
}
```

**curl 예시**:
```bash
curl -b cookies.txt -X POST http://localhost:5050/api/summarize/abc-123-def-456
```

---

### 3.2 요약 존재 여부 확인

```
GET /api/check_summary/<meeting_id>
```

**응답 (200 OK - 요약 있음)**:
```json
{
  "success": true,
  "has_summary": true,
  "summary": "### 예산 논의\n* ..."
}
```

**응답 (200 OK - 요약 없음)**:
```json
{
  "success": true,
  "has_summary": false,
  "message": "문단 요약이 아직 생성되지 않았습니다."
}
```

**curl 예시**:
```bash
curl -b cookies.txt http://localhost:5050/api/check_summary/abc-123-def-456
```

---

### 3.3 회의록 생성

```
POST /api/generate_minutes/<meeting_id>
```

**응답 (200 OK)**:
```json
{
  "success": true,
  "message": "회의록이 성공적으로 생성 및 저장되었습니다.",
  "minutes": "# 팀 회의\n\n**일시**: 2025년 11월 08일 14시 00분\n**참석자**: 홍길동, 김철수, 이영희\n\n## 회의 요약\n이번 회의에서는 프로젝트 예산 및 일정에 대해 논의하였습니다..."
}
```

**curl 예시**:
```bash
curl -b cookies.txt -X POST http://localhost:5050/api/generate_minutes/abc-123-def-456
```

---

### 3.4 회의록 조회

```
GET /api/get_minutes/<meeting_id>
```

**응답 (200 OK)**:
```json
{
  "success": true,
  "has_minutes": true,
  "minutes": "# 팀 회의\n\n**일시**: ...",
  "created_at": "2025-11-08 15:30:25",
  "updated_at": "2025-11-08 15:30:25"
}
```

**curl 예시**:
```bash
curl -b cookies.txt http://localhost:5050/api/get_minutes/abc-123-def-456
```

---

## 4️⃣ 챗봇 API (Chat)

### 4.1 질의응답

```
POST /api/chat
```

**요청 본문**:
```json
{
  "query": "이번 회의의 주요 결정 사항은?",
  "meeting_id": "abc-123-def-456"
}
```

**Note**: `meeting_id`는 선택 사항. 없으면 전체 노트에서 검색

**응답 (200 OK)**:
```json
{
  "success": true,
  "answer": "이번 회의의 주요 결정 사항은 다음과 같습니다:\n1. 프로젝트 예산 400만원 승인\n2. 다음 회의 일정: 11월 15일 오후 2시",
  "sources": [
    {
      "type": "chunk",
      "meeting_id": "abc-123-def-456",
      "title": "팀 회의",
      "meeting_date": "2025-11-08 14:00:00",
      "start_time": 120.5,
      "end_time": 185.3
    },
    {
      "type": "subtopic",
      "meeting_id": "abc-123-def-456",
      "title": "팀 회의",
      "meeting_date": "2025-11-08 14:00:00",
      "main_topic": "예산 논의"
    }
  ]
}
```

**에러 응답 (400 Bad Request)**:
```json
{
  "success": false,
  "error": "질문을 입력해주세요."
}
```

**curl 예시**:
```bash
curl -b cookies.txt -X POST http://localhost:5050/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "이번 회의의 주요 결정 사항은?",
    "meeting_id": "abc-123-def-456"
  }'
```

---

## 5️⃣ 관리자 API (Admin)

### 5.1 벡터 검색 테스트

```
POST /admin/api/search_vector
```

**권한**: Admin only

**요청 본문**:
```json
{
  "query": "예산",
  "db_type": "chunks",
  "k": 5
}
```

**응답 (200 OK)**:
```json
{
  "success": true,
  "results": [
    {
      "content": "예산은 500만원으로 제안되었습니다...",
      "metadata": {
        "meeting_id": "abc-123-def-456",
        "title": "팀 회의",
        "chunk_index": 2,
        "start_time": 120.5,
        "end_time": 185.3
      },
      "score": 0.87
    }
  ]
}
```

**curl 예시**:
```bash
curl -b cookies.txt -X POST http://localhost:5050/admin/api/search_vector \
  -H "Content-Type: application/json" \
  -d '{
    "query": "예산",
    "db_type": "chunks",
    "k": 5
  }'
```

---

### 5.2 스크립트 입력 (테스트용)

```
POST /admin/api/script_input
```

**권한**: Admin only

**요청 본문**:
```json
{
  "title": "테스트 회의",
  "script_text": "화자1: 안녕하세요. 회의 시작하겠습니다.\n화자2: 네, 좋습니다.",
  "meeting_date": "2025-11-08T14:00"
}
```

**응답 (200 OK)**:
```json
{
  "success": true,
  "meeting_id": "test-abc-123",
  "message": "스크립트 입력이 완료되었습니다."
}
```

**curl 예시**:
```bash
curl -b cookies.txt -X POST http://localhost:5050/admin/api/script_input \
  -H "Content-Type: application/json" \
  -d '{
    "title": "테스트 회의",
    "script_text": "화자1: 안녕하세요\\n화자2: 네, 좋습니다",
    "meeting_date": "2025-11-08T14:00"
  }'
```

---

## 📊 HTTP 상태 코드 정리

| 코드 | 의미 | 설명 |
|------|------|------|
| **200 OK** | 성공 | 요청 성공적으로 처리 |
| **201 Created** | 생성 | 새 리소스 생성됨 (회의 생성) |
| **400 Bad Request** | 잘못된 요청 | 필수 파라미터 누락, 검증 실패 |
| **401 Unauthorized** | 인증 실패 | 로그인 필요, 토큰 무효 |
| **403 Forbidden** | 권한 없음 | 로그인했지만 접근 권한 없음 |
| **404 Not Found** | 리소스 없음 | 회의 ID 존재하지 않음 |
| **500 Internal Server Error** | 서버 오류 | 예상치 못한 서버 에러 |

---

## 🔒 인증 흐름

### 전체 흐름 다이어그램

```
1. [사용자] 로그인 페이지 접속
    ↓ GET /auth/login_page
2. [서버] Firebase Auth UI 렌더링
    ↓
3. [사용자] Google 로그인
    ↓
4. [Firebase] ID Token 발급
    ↓
5. [클라이언트] POST /api/login (ID Token 전송)
    ↓
6. [서버] Firebase Admin SDK로 토큰 검증
    ↓
7. [서버] SQLite에서 사용자 조회/생성
    ↓
8. [서버] Flask 세션 생성 (Cookie 발급)
    ↓
9. [클라이언트] 이후 모든 요청에 Cookie 자동 포함
```

---

## 🧪 Postman 컬렉션 예시

### 환경 변수 설정

```json
{
  "base_url": "http://localhost:5050",
  "id_token": "eyJhbGciOiJSUzI1NiIsImtpZCI6...",
  "meeting_id": "abc-123-def-456"
}
```

### 요청 예시 (Postman)

**1. 로그인**
```
POST {{base_url}}/api/login
Content-Type: application/json

{
  "idToken": "{{id_token}}"
}
```

**2. 회의 목록**
```
GET {{base_url}}/api/meetings
```

**3. 파일 업로드**
```
POST {{base_url}}/api/upload
Content-Type: multipart/form-data

audio: [파일 선택]
title: "팀 회의"
meeting_date: "2025-11-08T14:00"
```

---

## 📈 API 사용 통계 (예시)

| 엔드포인트 | 평균 응답 시간 | 호출 빈도 |
|-----------|----------------|-----------|
| `POST /api/upload` | 120초 (STT 포함) | 낮음 |
| `GET /api/meetings` | 50ms | 높음 |
| `POST /api/chat` | 3.77초 | 중간 |
| `POST /api/summarize` | 25초 | 낮음 |
| `GET /api/meetings/<id>` | 80ms | 중간 |

---

## 🎓 Best Practices

### API 호출 순서

**신규 회의 생성 시**:
```
1. POST /api/upload (파일 업로드 + STT)
   → meeting_id 획득
2. POST /api/summarize/<meeting_id> (문단 요약 생성)
3. POST /api/generate_minutes/<meeting_id> (회의록 생성)
4. GET /api/meetings/<meeting_id> (전체 내용 조회)
```

**챗봇 질문 시**:
```
1. POST /api/chat (질문 전송)
2. sources 필드에서 출처 확인
3. 필요 시 GET /api/meetings/<meeting_id> (상세 조회)
```

---

## 📞 관련 문서

- **라우트 상세 분석**: `08_routes_detail.md`
- **코드 리뷰 체크리스트**: `12_code_review_checklist.md`
