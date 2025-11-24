# 04. 파일 업로드 & STT 처리 (30분 읽기)

> **레벨 3**: 파일 업로드부터 Gemini STT까지 전체 프로세스

---

## 🎯 프로세스 개요

```
사용자 파일 업로드
    ↓
파일 검증 (형식, 크기)
    ↓
UUID 추가하여 uploads/ 폴더에 저장
    ↓
MP4인 경우 → ffmpeg로 WAV 변환
    ↓
Gemini 2.5 Pro STT 처리
    ↓
화자 분리 + 타임스탬프 + 신뢰도 추출
    ↓
SQLite DB 저장 (meeting_dialogues)
    ↓
스마트 청킹 + OpenAI Embeddings
    ↓
ChromaDB 저장 (meeting_chunks)
    ↓
완료
```

---

## 📤 1. 파일 업로드 (SSE 스트리밍)

### 엔드포인트

**URL**: `POST /upload`
**파일**: `routes/meetings.py:432`

**Form Data**:
```
title: 회의 제목
audio_file: 오디오/비디오 파일 (multipart/form-data)
```

### SSE (Server-Sent Events) 스트리밍

**왜 SSE를 사용하나?**
- STT 처리에 시간이 오래 걸림 (1-2분 이상)
- 사용자에게 실시간 진행상황 전달 필요
- 프론트엔드에서 프로그레스바 표시 가능

**핵심 코드**:
```python
@meetings_bp.route("/upload", methods=["POST"])
@login_required
def upload_and_process():
    owner_id = session['user_id']

    # 제목 검증
    title = request.form.get('title', '').strip()
    is_valid, error_message = validate_title(title)
    if not is_valid:
        return render_template("index.html", error=error_message)

    # 파일 검증
    if 'audio_file' not in request.files:
        return render_template("index.html", error="오디오 파일이 없습니다.")

    file = request.files['audio_file']
    is_valid, error_message = upload_service.validate_file(file.filename)
    if not is_valid:
        return render_template("index.html", error=error_message)

    # 파일 저장 (generator 시작 전에 완료)
    meeting_id = uuid.uuid4().hex
    file_path, original_filename, is_video = upload_service.save_uploaded_file(file, meeting_id)
    meeting_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # SSE Generator 함수
    def generate():
        temp_audio_path = None

        try:
            # Step 1: 파일 업로드 완료
            yield f"data: {json.dumps({'step': 'upload', 'message': '파일 업로드가 완료되었습니다...', 'icon': '📤'})}\n\n"

            # Step 2: 비디오 변환 (필요 시)
            audio_path_for_stt = file_path
            if is_video:
                yield f"data: {json.dumps({'step': 'convert', 'message': '비디오를 오디오로 변환 중...', 'icon': '🎬'})}\n\n"

                success, temp_audio_path, error_msg = upload_service.convert_video_to_audio(file_path)
                if not success:
                    yield f"data: {json.dumps({'step': 'error', 'message': f'비디오 변환 실패: {error_msg}'})}\n\n"
                    return

                audio_path_for_stt = temp_audio_path

            # Step 3: STT 처리
            yield f"data: {json.dumps({'step': 'stt', 'message': '회의 음성을 텍스트로 변환하고 있습니다...', 'icon': '🎤'})}\n\n"

            result = upload_service.process_audio_file(
                audio_path=audio_path_for_stt,
                meeting_id=meeting_id,
                title=title,
                meeting_date=meeting_date,
                owner_id=owner_id
            )

            if not result['success']:
                yield f"data: {json.dumps({'step': 'error', 'message': 'STT 처리 실패'})}\n\n"
                return

            actual_meeting_id = result['meeting_id']

            # 임시 WAV 파일 삭제
            if temp_audio_path:
                upload_service.cleanup_temp_files(temp_audio_path)

            # Step 4: 문단 요약 생성
            yield f"data: {json.dumps({'step': 'summary', 'message': '회의 내용을 분석하고 요약하고 있습니다...', 'icon': '📝'})}\n\n"

            try:
                result = upload_service.generate_summary(actual_meeting_id)
                logger.info(f"✅ 문단 요약 생성 완료 (meeting_id: {actual_meeting_id})")

                # Step 5: 마인드맵 생성
                if result.get('success'):
                    yield f"data: {json.dumps({'step': 'mindmap', 'message': '마인드맵을 생성하고 있습니다...', 'icon': '🗺️'})}\n\n"

            except Exception as e:
                logger.warning(f"⚠️  문단 요약 생성 실패: {e}")

            # Step 6: 완료
            redirect_url = f"/view/{actual_meeting_id}"
            yield f"data: {json.dumps({'step': 'complete', 'message': '노트 생성이 완료되었습니다!', 'redirect': redirect_url, 'icon': '✅'})}\n\n"

        except Exception as e:
            logger.error(f"❌ 업로드 처리 실패: {e}", exc_info=True)
            yield f"data: {json.dumps({'step': 'error', 'message': f'서버 처리 중 오류가 발생했습니다: {str(e)}'})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')
```

---

## 📁 2. 파일 검증 및 저장

### 파일 검증

**파일**: `services/upload_service.py:27`

```python
def validate_file(self, filename: str) -> tuple[bool, str]:
    """
    파일 검증

    Args:
        filename: 파일명

    Returns:
        (is_valid, error_message): 검증 결과
    """
    if not filename:
        return False, "파일이 없습니다."

    if '.' not in filename:
        return False, "파일 확장자가 없습니다."

    extension = filename.rsplit('.', 1)[1].lower()
    if extension not in config.ALLOWED_EXTENSIONS:
        return False, f"허용되지 않는 파일 형식입니다. (허용: {', '.join(config.ALLOWED_EXTENSIONS)})"

    return True, ""
```

**허용 확장자** (config.py:47):
```python
ALLOWED_EXTENSIONS = {"wav", "mp3", "m4a", "flac", "mp4"}
MAX_FILE_SIZE_MB = 500
```

---

### 파일 저장

**파일**: `services/upload_service.py:49`

```python
def save_uploaded_file(self, file, meeting_id: str) -> tuple[str, str, bool]:
    """
    업로드된 파일 저장

    Args:
        file: Werkzeug FileStorage 객체
        meeting_id: 회의 ID

    Returns:
        (file_path, original_filename, is_video): 저장된 파일 경로, 원본 파일명, 비디오 여부
    """
    # 파일명 보안 처리
    original_filename = secure_filename(file.filename)

    # UUID 추가 (파일명 충돌 방지)
    unique_id = uuid.uuid4().hex[:8]
    filename = f"{unique_id}_{original_filename}"

    # 파일 저장
    file_path = config.UPLOAD_FOLDER / filename
    file.save(str(file_path))

    # 비디오 파일 여부 확인
    extension = original_filename.rsplit('.', 1)[1].lower()
    is_video = (extension == 'mp4')

    print(f"✅ 파일 저장: {file_path} (비디오: {is_video})")

    return str(file_path), original_filename, is_video
```

**보안 조치**:
- `secure_filename()`: 경로 탐색 공격 방지 (../../../etc/passwd 등)
- UUID 추가: 파일명 충돌 방지

---

## 🎬 3. 비디오 → 오디오 변환 (ffmpeg)

### MP4 파일 처리

**파일**: `services/upload_service.py:79`

```python
def convert_video_to_audio(self, video_path: str) -> tuple[bool, str, str]:
    """
    비디오 파일을 오디오 파일로 변환 (ffmpeg 사용)

    Args:
        video_path: 비디오 파일 경로

    Returns:
        (success, audio_path, error_message): 변환 결과
    """
    try:
        # 출력 파일 경로 (같은 위치에 .wav로 저장)
        audio_path = video_path.rsplit('.', 1)[0] + '_converted.wav'

        # ffmpeg 명령어
        command = [
            'ffmpeg',
            '-y',  # 덮어쓰기
            '-i', video_path,
            '-vn',  # 비디오 스트림 제거
            '-acodec', 'pcm_s16le',  # 16-bit PCM
            '-ar', '16000',  # 16kHz (Gemini 최적)
            '-ac', '1',  # 모노 채널
            audio_path
        ]

        # 실행 (20분 타임아웃)
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=config.UPLOAD_TIMEOUT_SECONDS  # 1200초 = 20분
        )

        if result.returncode == 0:
            print(f"✅ 비디오 → 오디오 변환 성공: {audio_path}")
            return True, audio_path, ""
        else:
            error_msg = f"ffmpeg 실패: {result.stderr}"
            print(f"❌ {error_msg}")
            return False, "", error_msg

    except subprocess.TimeoutExpired:
        error_msg = "변환 타임아웃 (20분 초과)"
        print(f"❌ {error_msg}")
        return False, "", error_msg

    except Exception as e:
        error_msg = f"변환 중 오류: {str(e)}"
        print(f"❌ {error_msg}")
        return False, "", error_msg
```

**ffmpeg 설정**:
- `-vn`: 비디오 스트림 제거 (오디오만 추출)
- `-acodec pcm_s16le`: 16-bit PCM 형식 (무손실)
- `-ar 16000`: 샘플링 레이트 16kHz (Gemini 권장)
- `-ac 1`: 모노 채널 (파일 크기 절반)

---

## 🎤 4. Gemini STT 처리

### Gemini API 호출

**파일**: `utils/stt.py:45`

```python
def transcribe_audio(self, audio_path):
    """Google Gemini STT API로 음성 인식"""
    try:
        api_key = config.GOOGLE_API_KEY
        client = genai.Client(api_key=api_key)

        # 오디오 파일 읽기
        with open(audio_path, "rb") as f:
            file_bytes = f.read()

        # MIME 타입 결정
        file_ext = os.path.splitext(audio_path)[1].lower()
        mime_type_map = {
            ".wav": "audio/wav", ".mp3": "audio/mp3",
            ".m4a": "audio/mp4", ".flac": "audio/flac",
        }
        mime_type = mime_type_map.get(file_ext, "audio/wav")

        # 프롬프트 (화자 분리 지침 포함)
        prompt = """
        당신은 최고 수준의 정확도를 가진 전문적인 회의록 STT 시스템입니다.

        I. 핵심 지침
        1. 충실도 우선: 실제 발화된 내용만 인식
        2. 금지 사항: 문장 보정 오류, 동사 생성, 불필요한 단어 추가 금지
        3. 단어 정확성: 문맥 기반 보정 (예: '지구' → '지분')
        4. 불확실성 처리: 들리지 않으면 공란

        II. 화자 분리
        5. 음색이 다른 화자는 분리, 톤/음량 변화는 같은 화자 유지
        6. 화자 구분: 등장 순서대로 번호 부여
        7. 끼어들기: 짧은 맞장구는 직전 화자와 동일 가능성 고려
        8. 겹침 처리: 두 화자 모두 start_time 기록

        III. 출력 형식
        10. 신뢰도: 0.0~1.0
        11. start_time_mmss: "분:초:밀리초" (예: "0:05:200")
        12. 같은 화자는 하나의 행으로, 문장 5개 초과 시 분리

        출력 형식:
        [
            {
                "speaker": 1,
                "start_time_mmss": "0:00:000",
                "confidence": 0.95,
                "text": "안녕하세요. 회의를 시작하겠습니다."
            },
            ...
        ]

        JSON 배열만 출력하고, 마크다운 코드 블록은 포함하지 마세요.
        """

        logger.info("🤖 Gemini 2.5 Pro로 음성 인식 중...")

        # Gemini API 호출
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=[prompt, types.Part.from_bytes(data=file_bytes, mime_type=mime_type)],
        )

        # 응답 검증
        if response.text is None:
            logger.warning("⚠️ Gemini 응답이 비어있습니다.")
            raise ValueError("Gemini API가 빈 응답을 반환했습니다.")

        # JSON 파싱
        cleaned_response = response.text.strip().replace("```json", "").replace("```", "").strip()

        try:
            result_list = json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON 파싱 실패: {e}")
            # 에러 로그 저장
            error_log_path = os.path.join(os.path.dirname(__file__), '..', 'gemini_error_response.txt')
            with open(error_log_path, 'w', encoding='utf-8') as f:
                f.write(cleaned_response)
            raise ValueError(f"Gemini 응답이 올바른 JSON 형식이 아닙니다: {e}")

        # 정규화 (MM:SS:mmm → 초 단위 변환)
        normalized_segments = []
        for idx, segment in enumerate(result_list):
            normalized_segments.append({
                "id": idx,
                "speaker": segment.get("speaker", 1),
                "start_time": self._parse_mmss_to_seconds(segment.get("start_time_mmss", "0:00:000")),
                "confidence": segment.get("confidence", 0.0),
                "text": segment.get("text", ""),
            })

        logger.info("✅ Gemini 음성 인식 완료")
        return normalized_segments

    except Exception as e:
        logger.error(f"❌ Gemini 오류 발생: {e}")
        return None
```

**주요 기능**:
1. **화자 분리**: SPEAKER_00, SPEAKER_01, ... 자동 할당
2. **타임스탬프**: MM:SS:mmm 형식 → 초 단위 변환
3. **신뢰도**: 0.0~1.0 (음성 인식 정확도)

---

### 타임스탬프 파싱

**파일**: `utils/stt.py:28`

```python
@staticmethod
def _parse_mmss_to_seconds(time_str):
    """
    '분:초:밀리초' 형태의 문자열을 초 단위로 변환

    예: "1:23:450" → 83.450
    """
    try:
        parts = time_str.split(":")
        if len(parts) == 3:
            minutes = int(parts[0])
            seconds = int(parts[1])
            milliseconds = int(parts[2])
            return minutes * 60 + seconds + milliseconds / 1000.0
        else:
            return 0.0
    except:
        return 0.0
```

---

## 💾 5. 데이터베이스 저장

### SQLite 저장 (meeting_dialogues)

**파일**: `utils/db_manager.py:37`

```python
def save_stt_to_db(self, segments, audio_filename, title, meeting_date=None, owner_id=None):
    """
    음성 인식 결과를 데이터베이스에 저장

    Args:
        segments (list): 음성 인식 결과 세그먼트 리스트
        audio_filename (str): 오디오 파일명
        title (str): 회의 제목
        meeting_date (str, optional): 회의 일시 (YYYY-MM-DD HH:MM:SS)
        owner_id (int, optional): 회의 소유자 ID

    Returns:
        str: 생성된 meeting_id (UUID)
    """
    meeting_id = str(uuid.uuid4())

    # meeting_date가 제공되지 않으면 현재 시간 사용
    if meeting_date is None:
        meeting_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = self._get_connection()
    cursor = conn.cursor()

    for segment in segments:
        cursor.execute("""
            INSERT INTO meeting_dialogues
            (meeting_id, meeting_date, speaker_label, start_time, segment, confidence, audio_file, title, owner_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            meeting_id, meeting_date, str(segment['speaker']), segment['start_time'],
            segment['text'], segment['confidence'], audio_filename, title, owner_id
        ))

    conn.commit()
    conn.close()

    logger.info(f"✅ DB 저장 완료: meeting_id={meeting_id}, owner_id={owner_id}")
    return meeting_id
```

**저장 내용**:
- meeting_id: UUID (전체 회의 그룹화)
- meeting_date: 회의 일시
- speaker_label: 화자 번호 (1, 2, 3, ...)
- start_time: 시작 시간 (초)
- segment: 전사 텍스트
- confidence: 신뢰도 (0.0~1.0)
- audio_file: 오디오 파일명
- title: 회의 제목
- owner_id: 소유자 ID

---

### ChromaDB 저장 (meeting_chunks)

**파일**: `utils/vector_db_manager.py:127`

```python
def add_meeting_as_chunk(self, meeting_id, title, meeting_date, audio_file, segments):
    """
    회의 대화 내용을 스마트하게 청크로 묶어 DB에 저장

    Process:
    1. 스마트 청킹 (화자 변경, 시간 간격 고려)
    2. 정규표현식으로 화자/타임스탬프 제거
    3. OpenAI Embeddings
    4. ChromaDB 저장
    """
    chunk_vdb = self.vectorstores['chunks']

    try:
        # 1. 스마트 청킹
        chunks = self._create_smart_chunks(segments, max_chunk_size=1000, time_gap_threshold=60)

        logger.info(f"📦 스마트 청킹으로 {len(chunks)}개의 청크 생성 완료")

        # 2. 정규표현식으로 텍스트 정제 (화자/시간 정보 제거)
        for chunk in chunks:
            chunk['text'] = self._clean_text(chunk['text'])

        # 3. ChromaDB에 저장
        chunk_texts = []
        chunk_metadatas = []
        chunk_ids = []

        for i, chunk_info in enumerate(chunks):
            chunk_texts.append(chunk_info['text'])
            chunk_metadatas.append({
                "meeting_id": meeting_id,
                "dialogue_id": f"{meeting_id}_chunk_{i}",
                "chunk_index": i,
                "title": title,
                "meeting_date": str(meeting_date),
                "audio_file": audio_file,
                "start_time": chunk_info['start_time'],
                "end_time": chunk_info['end_time'],
                "speaker_count": chunk_info['speaker_count']
            })
            chunk_ids.append(f"{meeting_id}_chunk_{i}")

        # OpenAI Embeddings + ChromaDB 저장
        chunk_vdb.add_texts(
            texts=chunk_texts,
            metadatas=chunk_metadatas,
            ids=chunk_ids
        )

        logger.info(f"✅ {len(chunks)}개의 스마트 청크를 meeting_chunks DB에 저장 완료")

    except Exception as e:
        logger.warning(f"⚠️ 스마트 청킹 중 오류 발생: {e}")
        # 폴백: RecursiveCharacterTextSplitter 사용
```

---

### 스마트 청킹 알고리즘

**파일**: `utils/vector_db_manager.py:241`

```python
def _create_smart_chunks(self, segments, max_chunk_size=1000, time_gap_threshold=60):
    """
    화자 변경, 시간 간격을 고려한 스마트 청킹

    청크 분리 조건:
    1. 청크 크기 > max_chunk_size (1000자)
    2. 시간 간격 > time_gap_threshold (60초) → 주제 전환 가능성
    3. 화자 변경 AND 청크 크기 > 500자

    Returns:
        list: [{'text': str, 'start_time': float, 'end_time': float, 'speaker_count': int}]
    """
    chunks = []
    current_chunk = []
    current_chunk_text = ""
    current_speaker = None
    last_time = 0
    speakers_in_chunk = set()

    for seg in segments:
        speaker = seg.get('speaker_label', 'Unknown')
        start_time = seg.get('start_time', 0)
        text = seg.get('segment', '')

        # 포맷팅
        minutes = int(start_time // 60)
        seconds = int(start_time % 60)
        time_str = f"{minutes:02d}:{seconds:02d}"
        formatted_text = f"[Speaker {speaker}, {time_str}] {text}"

        # 분리 조건 체크
        time_gap = start_time - last_time
        should_split = False

        if len(current_chunk_text) + len(formatted_text) > max_chunk_size:
            should_split = True
        elif time_gap > time_gap_threshold and len(current_chunk_text) > 200:
            should_split = True  # 긴 침묵 = 주제 전환
        elif speaker != current_speaker and len(current_chunk_text) > 500:
            should_split = True

        if should_split and current_chunk:
            # 청크 저장
            chunks.append({
                'text': current_chunk_text.strip(),
                'start_time': current_chunk[0].get('start_time', 0),
                'end_time': current_chunk[-1].get('start_time', 0),
                'speaker_count': len(speakers_in_chunk)
            })

            # 새 청크 시작
            current_chunk = []
            current_chunk_text = ""
            speakers_in_chunk = set()

        # 현재 청크에 추가
        current_chunk.append(seg)
        current_chunk_text += formatted_text + "\n"
        speakers_in_chunk.add(speaker)
        current_speaker = speaker
        last_time = start_time

    # 마지막 청크 저장
    if current_chunk:
        chunks.append({
            'text': current_chunk_text.strip(),
            'start_time': current_chunk[0].get('start_time', 0),
            'end_time': current_chunk[-1].get('start_time', 0),
            'speaker_count': len(speakers_in_chunk)
        })

    return chunks
```

---

### 화자/타임스탬프 제거

**파일**: `utils/vector_db_manager.py:106`

```python
def _clean_text(self, formatted_text: str) -> str:
    """
    정규표현식으로 [Speaker X, MM:SS] 형식 제거

    예:
    "[Speaker 1, 00:05] 안녕하세요." → "안녕하세요."
    """
    # [Speaker X, MM:SS] 패턴 제거
    pattern = r'\[Speaker [^,]+, \d{2}:\d{2}\]\s*'
    cleaned_text = re.sub(pattern, '', formatted_text)

    # 빈 줄 제거
    cleaned_text = '\n'.join(line for line in cleaned_text.split('\n') if line.strip())

    return cleaned_text.strip()
```

**왜 제거하나?**
- 벡터 검색 시 순수 대화 내용만 유사도 계산
- 화자 번호, 시간 정보는 메타데이터에 저장

---

## 🧪 테스트 시나리오

### 1. 오디오 파일 업로드
```bash
POST /upload
Content-Type: multipart/form-data

title: "팀 회의"
audio_file: meeting.wav (10MB, 5분 길이)

# SSE 스트리밍 응답
data: {"step": "upload", "message": "파일 업로드가 완료되었습니다...", "icon": "📤"}

data: {"step": "stt", "message": "회의 음성을 텍스트로 변환하고 있습니다...", "icon": "🎤"}

data: {"step": "summary", "message": "회의 내용을 분석하고 요약하고 있습니다...", "icon": "📝"}

data: {"step": "mindmap", "message": "마인드맵을 생성하고 있습니다...", "icon": "🗺️"}

data: {"step": "complete", "message": "노트 생성이 완료되었습니다!", "redirect": "/view/abc123", "icon": "✅"}
```

### 2. 비디오 파일 업로드
```bash
POST /upload
Content-Type: multipart/form-data

title: "제품 데모"
audio_file: demo.mp4 (50MB, 10분 길이)

# SSE 스트리밍 응답
data: {"step": "upload", ...}

data: {"step": "convert", "message": "비디오를 오디오로 변환 중...", "icon": "🎬"}

data: {"step": "stt", ...}
...
```

---

## 🚀 다음 단계

- **요약 & 회의록 생성**: `05_summarization_minutes.md`
- **RAG 챗봇**: `06_chatbot_rag.md`
- **API 명세서**: `11_api_specification.md`
