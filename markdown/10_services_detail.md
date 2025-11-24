# 10. 서비스 레이어 분석 (30분 읽기)

> **레벨 4**: services/ 디렉토리의 비즈니스 로직 심층 분석

---

## 🎯 이 문서에서 다루는 내용

1. **UploadService 클래스**: 파일 업로드 및 변환 처리
2. **파일 검증 로직**: 확장자, 크기, MIME 타입 체크
3. **ffmpeg 비디오 변환**: MP4 → WAV 오디오 추출
4. **UUID 파일명 관리**: 충돌 방지 전략

---

## 📊 services/ 디렉토리 구조

```
services/
└── upload_service.py     # 파일 업로드 서비스 (280 lines)
```

**NOTE**: 현재 프로젝트에는 upload_service.py만 존재하며, 향후 추가 서비스 확장 가능

---

## 1️⃣ UploadService 클래스 (싱글톤)

### 1.1 클래스 개요

**위치**: `services/upload_service.py:20-280`

**핵심 역할**:
- 파일 업로드 및 저장
- 파일 확장자 및 크기 검증
- 비디오 파일 → 오디오 파일 변환 (ffmpeg)
- UUID 기반 파일명 충돌 방지

**싱글톤 초기화** (lines 20-44):
```python
class UploadService:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # 업로드 디렉토리 설정
        self.upload_folder = config.UPLOAD_FOLDER
        self.allowed_extensions = config.ALLOWED_EXTENSIONS
        self.max_file_size_mb = config.MAX_FILE_SIZE_MB

        # 디렉토리 생성
        os.makedirs(self.upload_folder, exist_ok=True)

        self._initialized = True
```

---

## 2️⃣ 파일 검증 로직

### 2.1 allowed_file() (lines 46-61)

**확장자 검증**:
```python
def allowed_file(self, filename):
    """
    허용된 파일 확장자인지 확인

    Args:
        filename (str): 파일명

    Returns:
        bool: 허용 여부
    """
    return ('.' in filename and
            filename.rsplit('.', 1)[1].lower() in self.allowed_extensions)
```

**허용된 확장자** (`config.py:43`):
```python
ALLOWED_EXTENSIONS = {'wav', 'mp3', 'm4a', 'flac', 'mp4'}
```

---

### 2.2 validate_file() (lines 63-115)

**전체 검증 프로세스**:
```python
def validate_file(self, file):
    """
    파일 검증 (확장자 + 크기)

    Returns:
        tuple: (is_valid, error_message, file_size_mb)
    """
    # 1. 파일 존재 여부
    if not file or file.filename == '':
        return False, "파일이 선택되지 않았습니다.", 0

    # 2. 확장자 체크
    if not self.allowed_file(file.filename):
        return False, f"허용되지 않은 파일 형식입니다. ({', '.join(self.allowed_extensions)}만 가능)", 0

    # 3. 파일 크기 체크
    file.seek(0, os.SEEK_END)  # 파일 끝으로 이동
    file_size = file.tell()     # 현재 위치 = 파일 크기
    file.seek(0)                # 다시 처음으로 이동

    file_size_mb = file_size / (1024 * 1024)  # MB 단위 변환

    # 4. 최대 크기 체크 (500MB)
    if file_size_mb > self.max_file_size_mb:
        return False, f"파일 크기가 너무 큽니다. (최대 {self.max_file_size_mb}MB)", file_size_mb

    return True, None, file_size_mb
```

**검증 흐름**:
```
파일 업로드
    ↓
파일 존재 여부 → No → "파일이 선택되지 않았습니다."
    ↓ Yes
확장자 체크 → No → "허용되지 않은 파일 형식입니다."
    ↓ Yes
파일 크기 계산 (file.tell())
    ↓
크기 체크 (500MB 이하) → No → "파일 크기가 너무 큽니다."
    ↓ Yes
검증 완료 ✅
```

---

## 3️⃣ 파일 저장

### 3.1 save_file() (lines 117-165)

**UUID 기반 파일명 생성**:
```python
def save_file(self, file, meeting_id):
    """
    파일 저장 (UUID 접두사 추가)

    Args:
        file: FileStorage 객체
        meeting_id (str): 회의 ID (UUID)

    Returns:
        str: 저장된 파일 경로
    """
    # 1. 원본 파일명에서 확장자 추출
    original_filename = secure_filename(file.filename)
    file_extension = original_filename.rsplit('.', 1)[1].lower()

    # 2. UUID 접두사 파일명 생성
    filename = f"{meeting_id}_audio.{file_extension}"

    # 3. 전체 경로 생성
    file_path = os.path.join(self.upload_folder, filename)

    # 4. 파일 저장
    file.save(file_path)

    logger.info(f"✅ 파일 저장 완료: {file_path} ({file_size_mb:.2f} MB)")

    return file_path
```

**파일명 예시**:
```
원본: "team_meeting.mp3"
저장: "abc-123-def-456_audio.mp3"
```

**장점**:
- UUID로 충돌 방지
- meeting_id와 파일명 일치로 추적 용이

---

### 3.2 secure_filename() (Werkzeug)

**보안 기능**:
```python
from werkzeug.utils import secure_filename

# 악의적인 파일명 방지
secure_filename("../../etc/passwd")  # → "etc_passwd"
secure_filename("파일.txt")          # → "_.txt" (ASCII만 허용)
```

---

## 4️⃣ 비디오 변환 (ffmpeg)

### 4.1 is_video_file() (lines 167-179)

**비디오 파일 여부 확인**:
```python
def is_video_file(self, file_path):
    """
    비디오 파일인지 확인 (현재는 MP4만 지원)
    """
    _, ext = os.path.splitext(file_path)
    return ext.lower() in ['.mp4']
```

---

### 4.2 convert_video_to_audio() (lines 181-252)

**ffmpeg를 이용한 WAV 변환**:
```python
def convert_video_to_audio(self, video_path, progress_callback=None):
    """
    MP4 비디오 → WAV 오디오 변환

    Args:
        video_path (str): 입력 비디오 파일 경로
        progress_callback (callable): 진행률 콜백 함수

    Returns:
        str: 변환된 오디오 파일 경로
    """
    # 1. 출력 파일명 생성
    base_name = os.path.splitext(video_path)[0]
    audio_path = f"{base_name}_converted.wav"

    # 2. ffmpeg 명령어 구성
    command = [
        'ffmpeg',
        '-y',                      # 덮어쓰기 허용
        '-i', video_path,          # 입력 파일
        '-vn',                     # 비디오 스트림 제거
        '-acodec', 'pcm_s16le',    # 오디오 코덱: PCM 16-bit LE
        '-ar', '16000',            # 샘플레이트: 16kHz (STT 최적화)
        '-ac', '1',                # 채널: 모노
        audio_path                 # 출력 파일
    ]

    # 3. ffmpeg 실행
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=True
        )

        logger.info(f"✅ 비디오 변환 완료: {audio_path}")

        # 4. 원본 비디오 파일 삭제 (공간 절약)
        if os.path.exists(video_path):
            os.remove(video_path)
            logger.info(f"🗑️  원본 비디오 파일 삭제: {video_path}")

        return audio_path

    except subprocess.CalledProcessError as e:
        logger.error(f"❌ ffmpeg 변환 실패: {e.stderr}")
        raise RuntimeError(f"비디오 변환 중 오류 발생: {e.stderr}")
```

---

### 4.3 ffmpeg 파라미터 설명

| 파라미터 | 값 | 설명 |
|----------|-----|------|
| `-y` | - | 기존 파일 덮어쓰기 허용 |
| `-i` | video_path | 입력 파일 경로 |
| `-vn` | - | 비디오 스트림 제거 (오디오만 추출) |
| `-acodec` | pcm_s16le | 오디오 코덱: PCM 16-bit Little Endian |
| `-ar` | 16000 | 샘플레이트: 16kHz (STT 최적화) |
| `-ac` | 1 | 오디오 채널: 모노 (Stereo 대신) |

**왜 16kHz 모노인가?**:
- Gemini STT가 16kHz 샘플레이트에 최적화
- 모노 변환으로 파일 크기 절반 감소
- 음성 인식에는 스테레오 불필요

---

### 4.4 변환 예시

**입력**:
```
파일: team_meeting.mp4
크기: 120 MB
포맷: H.264 비디오 + AAC 오디오
```

**ffmpeg 실행**:
```bash
ffmpeg -y -i team_meeting.mp4 \
  -vn \
  -acodec pcm_s16le \
  -ar 16000 \
  -ac 1 \
  team_meeting_converted.wav
```

**출력**:
```
파일: team_meeting_converted.wav
크기: 15 MB
포맷: PCM 16-bit 모노 16kHz
```

**크기 감소**: 120MB → 15MB (87.5% 감소)

---

## 5️⃣ 파일 삭제

### 5.1 delete_file() (lines 254-280)

**파일 안전 삭제**:
```python
def delete_file(self, file_path):
    """
    파일 삭제 (존재 여부 체크)

    Args:
        file_path (str): 삭제할 파일 경로

    Returns:
        bool: 삭제 성공 여부
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"✅ 파일 삭제 완료: {file_path}")
            return True
        else:
            logger.warning(f"⚠️  파일이 존재하지 않습니다: {file_path}")
            return False

    except Exception as e:
        logger.error(f"❌ 파일 삭제 실패: {file_path}, 에러: {e}")
        return False
```

---

## 6️⃣ 전체 업로드 흐름

### 6.1 라우트와의 통합

**`routes/meetings.py:249-429`에서 사용**:
```python
@meetings_bp.route("/api/upload", methods=["POST"])
@login_required
def upload():
    def generate():
        # 1. 파일 검증
        is_valid, error, file_size_mb = upload_service.validate_file(audio_file)
        if not is_valid:
            yield sse_error(error)
            return

        # 2. 파일 저장
        yield sse_event("upload", "파일 업로드 중...", progress=0)
        audio_path = upload_service.save_file(audio_file, meeting_id)

        # 3. 비디오 변환 (MP4인 경우)
        if upload_service.is_video_file(audio_path):
            yield sse_event("conversion", "비디오 변환 중...", progress=20)
            audio_path = upload_service.convert_video_to_audio(audio_path)

        # 4. STT 처리
        yield sse_event("stt", "음성 인식 중...", progress=40)
        segments = stt_manager.transcribe_audio(audio_path)

        # ... (후속 처리)

    return Response(generate(), mimetype='text/event-stream')
```

---

### 6.2 에러 처리 패턴

**검증 실패 시**:
```python
is_valid, error, file_size_mb = upload_service.validate_file(audio_file)
if not is_valid:
    return jsonify({"error": error}), 400
```

**ffmpeg 변환 실패 시**:
```python
try:
    audio_path = upload_service.convert_video_to_audio(video_path)
except RuntimeError as e:
    logger.error(f"❌ 변환 실패: {e}")
    return jsonify({"error": "비디오 변환 중 오류 발생"}), 500
```

---

## 7️⃣ 보안 고려사항

### 7.1 파일 확장자 위조 방지

**문제**: 악의적인 사용자가 `.exe` 파일을 `.mp3`로 위장

**현재 방어**:
- `secure_filename()`으로 파일명 정제
- 서버 측 확장자 재검증

**개선 가능**:
```python
import mimetypes

def validate_mime_type(self, file_path, expected_extension):
    """MIME 타입 검증"""
    mime_type, _ = mimetypes.guess_type(file_path)

    # MP3 파일이라고 주장하지만 실제 MIME 타입이 다른 경우
    if expected_extension == 'mp3' and mime_type != 'audio/mpeg':
        raise ValueError("파일 형식이 일치하지 않습니다.")
```

---

### 7.2 경로 순회 공격 방지

**문제**: `../../etc/passwd` 같은 경로로 시스템 파일 접근

**방어**:
```python
from werkzeug.utils import secure_filename

# secure_filename()이 자동으로 ".."와 "/" 제거
filename = secure_filename(user_input)  # "../../passwd" → "passwd"

# 추가 검증: 업로드 폴더 외부로 나가지 않도록
file_path = os.path.join(self.upload_folder, filename)
if not file_path.startswith(self.upload_folder):
    raise ValueError("잘못된 파일 경로입니다.")
```

---

### 7.3 디스크 공간 관리

**현재 전략**:
- 최대 파일 크기: 500MB
- 비디오 변환 후 원본 삭제

**개선 가능**:
```python
def cleanup_old_files(self, days=30):
    """30일 이상 된 파일 자동 삭제"""
    import time

    now = time.time()
    for filename in os.listdir(self.upload_folder):
        file_path = os.path.join(self.upload_folder, filename)
        if os.path.isfile(file_path):
            file_age_days = (now - os.path.getmtime(file_path)) / 86400
            if file_age_days > days:
                os.remove(file_path)
                logger.info(f"🗑️  오래된 파일 삭제: {filename}")
```

---

## 8️⃣ 성능 최적화

### 8.1 ffmpeg 변환 속도 개선

**현재**: 실시간 처리 (약 1배속)

**개선안**: 멀티스레드 인코딩
```bash
ffmpeg -i input.mp4 \
  -threads 4 \        # CPU 코어 4개 사용
  -vn \
  -acodec pcm_s16le \
  -ar 16000 \
  -ac 1 \
  output.wav
```

---

### 8.2 파일 크기 최적화

**현재**: PCM 무손실 (파일 크기 큼)

**대안**: Opus 코덱 (손실 압축)
```bash
ffmpeg -i input.mp4 \
  -vn \
  -acodec libopus \   # Opus 코덱 (음성 최적화)
  -b:a 32k \          # 비트레이트: 32kbps
  -ar 16000 \
  output.opus
```

**비교**:
- PCM WAV: 15 MB
- Opus: 2 MB (87% 감소)

---

## 9️⃣ 테스트 시나리오

### 9.1 단위 테스트 예시

```python
import pytest
from services.upload_service import UploadService

def test_allowed_file():
    service = UploadService()

    assert service.allowed_file("meeting.mp3") == True
    assert service.allowed_file("meeting.wav") == True
    assert service.allowed_file("meeting.exe") == False

def test_validate_file_size():
    # 600MB 파일 시뮬레이션
    class FakeFile:
        def seek(self, pos, whence=0):
            pass
        def tell(self):
            return 600 * 1024 * 1024  # 600MB

    service = UploadService()
    is_valid, error, size = service.validate_file(FakeFile())

    assert is_valid == False
    assert "크기가 너무 큽니다" in error
```

---

### 9.2 통합 테스트 시나리오

**시나리오 1**: MP3 파일 업로드
```
1. 5MB MP3 파일 업로드
2. validate_file() → 검증 통과
3. save_file() → UUID 파일명으로 저장
4. is_video_file() → False
5. STT 처리 바로 진행
```

**시나리오 2**: MP4 비디오 파일 업로드
```
1. 50MB MP4 파일 업로드
2. validate_file() → 검증 통과
3. save_file() → UUID 파일명으로 저장
4. is_video_file() → True
5. convert_video_to_audio() → WAV 변환 (5MB)
6. 원본 MP4 삭제
7. STT 처리 진행
```

---

## 🔟 에러 핸들링 Best Practices

### 10.1 파일 업로드 실패

**원인**: 네트워크 중단, 디스크 용량 부족

**처리**:
```python
try:
    file.save(file_path)
except IOError as e:
    logger.error(f"❌ 파일 저장 실패: {e}")
    return False, "파일 저장 중 오류가 발생했습니다."
```

---

### 10.2 ffmpeg 없음

**원인**: ffmpeg가 시스템에 설치되지 않음

**처리**:
```python
def check_ffmpeg_installed(self):
    """ffmpeg 설치 여부 확인"""
    try:
        subprocess.run(['ffmpeg', '-version'],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE,
                      check=True)
        return True
    except FileNotFoundError:
        logger.error("❌ ffmpeg가 설치되지 않았습니다.")
        return False
```

---

## 📈 주요 메트릭

| 항목 | 수치/설명 |
|------|-----------|
| **최대 파일 크기** | 500 MB |
| **허용 확장자** | wav, mp3, m4a, flac, mp4 |
| **ffmpeg 변환 속도** | 약 1배속 (10분 영상 → 10분 소요) |
| **평균 변환 후 크기** | 원본의 10~15% (압축 효과) |
| **파일명 충돌 확률** | 0% (UUID 사용) |

---

## 🎓 학습 포인트

1. **싱글톤 패턴**: 서비스 클래스 단일 인스턴스
2. **secure_filename**: 경로 순회 공격 방지
3. **ffmpeg 활용**: 비디오 → 오디오 변환
4. **파일 크기 체크**: file.tell()로 메모리 효율적 측정
5. **에러 핸들링**: subprocess 실패 시 적절한 예외 발생

---

## 📞 다음 단계

- **API 전체 명세**: `11_api_specification.md`로 이동
- **코드 리뷰 체크리스트**: `12_code_review_checklist.md` 참고
