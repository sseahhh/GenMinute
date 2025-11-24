"""
서울시의회 회의록 텍스트 분석 - Gemini API 사용
minute_txt.txt 파일을 읽어서 Gemini API로 구조 분석 및 JSON 변환
"""
import os
import json
from datetime import datetime
from google import genai
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()


def read_text_file(txt_path: str) -> dict:
    """
    텍스트 파일 읽기

    Args:
        txt_path: 텍스트 파일 경로

    Returns:
        읽기 결과 딕셔너리 (success, text, length 또는 error 포함)
    """
    try:
        with open(txt_path, 'r', encoding='utf-8') as f:
            text = f.read()

        return {
            "success": True,
            "text": text,
            "length": len(text)
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"텍스트 파일 읽기 실패: {str(e)}"
        }


def analyze_meeting_with_gemini(text: str) -> dict:
    """
    Gemini 2.5 Pro를 사용하여 회의록 텍스트 구조 분석

    회의록 텍스트 내용을 분석하여 제목, 날짜, 참석자, 안건 등 메타데이터를
    JSON 형식으로 추출합니다.

    Args:
        text: 회의록 텍스트 내용

    Returns:
        분석 결과 딕셔너리 (success, 각종 메타데이터 또는 error 포함)
    """
    try:
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            return {
                "success": False,
                "error": "GOOGLE_API_KEY가 설정되지 않았습니다"
            }

        client = genai.Client(api_key=api_key)

        prompt = """다음은 서울시의회 회의록 텍스트입니다.
내용을 분석하여 다음 정보를 JSON 형식으로 추출해주세요.

추출할 정보:
1. title: 회의록 제목 (예: "제325회 정례회", "행정자치위원회 회의록")
2. date: 회의 날짜 (YYYY년 MM월 DD일 형식)
3. meeting_type: 회의 종류 (예: "정례회", "임시회", "위원회")
4. committee: 위원회명 (해당되는 경우)
5. attendees: 참석자 목록 (이름과 직책을 포함, 배열 형태)
6. speakers: 발언자 목록 (중복 제거, 이름만, 배열 형태)
7. agenda_items: 안건 목록 (배열 형태)
8. location: 회의 장소
9. content: 회의록 전체 텍스트 내용 (원본 그대로)

응답은 반드시 다음과 같은 JSON 형식으로만 작성해주세요:
{
    "title": "회의록 제목",
    "date": "YYYY년 MM월 DD일",
    "meeting_type": "회의 종류",
    "committee": "위원회명",
    "attendees": [
        {"name": "이름", "position": "직책"},
        ...
    ],
    "speakers": ["발언자1", "발언자2", ...],
    "agenda_items": ["안건1", "안건2", ...],
    "location": "회의 장소",
    "content": "회의록 전체 텍스트 내용"
}

JSON만 응답하고 다른 설명은 포함하지 마세요.

=== 회의록 텍스트 ===
""" + text

        # Gemini 2.5 Pro로 텍스트 구조 분석
        response = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=prompt
        )

        response_text = response.text.strip()

        # JSON 파싱 (코드 블록 제거)
        if response_text.startswith("```json"):
            response_text = response_text.replace("```json", "").replace("```", "").strip()
        elif response_text.startswith("```"):
            response_text = response_text.replace("```", "").strip()

        # JSON 파싱
        structure = json.loads(response_text)
        structure["success"] = True

        return structure

    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"JSON 파싱 실패: {str(e)}",
            "raw_response": response_text if 'response_text' in locals() else None
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"구조 분석 실패: {str(e)}"
        }


def save_text_to_markdown(text: str, timestamp: str, upload_folder: str = "uploads") -> str:
    """
    추출된 텍스트를 타임스탬프 기반 파일명으로 마크다운 파일로 저장

    Args:
        text: 저장할 텍스트 내용
        timestamp: 파일명에 사용할 타임스탬프 (예: "20250113_143025")
        upload_folder: 저장할 폴더명 (기본값: "uploads")

    Returns:
        저장된 파일의 전체 경로
    """
    # 현재 스크립트 위치 기준 uploads 폴더 경로
    current_dir = os.path.dirname(os.path.abspath(__file__))
    upload_dir = os.path.join(current_dir, upload_folder)

    # uploads 폴더가 없으면 생성
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)

    # 마크다운 파일명 생성 (예: 20250113_143025.md)
    filename = f"{timestamp}.md"
    filepath = os.path.join(upload_dir, filename)

    # 마크다운 파일로 저장
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(text)

    return filepath


def save_structure_to_json(structure: dict, timestamp: str, upload_folder: str = "uploads") -> str:
    """
    분석된 구조 데이터를 타임스탬프 기반 파일명으로 JSON 파일로 저장

    Args:
        structure: 저장할 구조 데이터
        timestamp: 파일명에 사용할 타임스탬프 (예: "20250113_143025")
        upload_folder: 저장할 폴더명 (기본값: "uploads")

    Returns:
        저장된 파일의 전체 경로
    """
    # 현재 스크립트 위치 기준 uploads 폴더 경로
    current_dir = os.path.dirname(os.path.abspath(__file__))
    upload_dir = os.path.join(current_dir, upload_folder)

    # uploads 폴더가 없으면 생성
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)

    # JSON 파일명 생성 (예: 20250113_143025.json)
    filename = f"{timestamp}.json"
    filepath = os.path.join(upload_dir, filename)

    # JSON 파일로 저장
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(structure, f, ensure_ascii=False, indent=2)

    return filepath


def main():
    """
    메인 테스트 함수

    minute_txt.txt 파일을 읽어서 Gemini API로 구조 분석 및 JSON 변환을 수행합니다.
    """
    # 현재 스크립트와 같은 디렉토리에 있는 텍스트 파일 경로
    current_dir = os.path.dirname(os.path.abspath(__file__))
    txt_path = os.path.join(current_dir, "minute_txt.txt")

    if not os.path.exists(txt_path):
        print(f"❌ 파일을 찾을 수 없습니다: {txt_path}")
        return

    print("=" * 80)
    print("📄 서울시의회 회의록 텍스트 분석 - Gemini API")
    print("=" * 80)
    print()

    # 현재 시간으로 타임스탬프 생성 (모든 파일에 동일한 타임스탬프 사용)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. 텍스트 파일 읽기
    print("1️⃣ minute_txt.txt 파일 읽기")
    print("-" * 80)

    read_result = read_text_file(txt_path)

    if not read_result["success"]:
        print(f"❌ 파일 읽기 실패: {read_result['error']}")
        return

    meeting_text = read_result["text"]
    print(f"✅ 파일 읽기 성공")
    print(f"   텍스트 길이: {read_result['length']} 문자")
    print(f"   텍스트 샘플 (처음 500자):")
    print(f"   {meeting_text[:500]}...")

    # 2. 회의록 구조 분석
    print("\n")
    print("2️⃣ 회의록 구조 분석 (Gemini 2.5 Pro)")
    print("-" * 80)
    print("AI 분석 중... (1-2분 소요될 수 있습니다)")

    structure = analyze_meeting_with_gemini(meeting_text)

    if structure.get('success'):
        print(f"✅ 분석 성공")
        print(f"\n제목: {structure.get('title', 'N/A')}")
        print(f"날짜: {structure.get('date', 'N/A')}")
        print(f"회의 종류: {structure.get('meeting_type', 'N/A')}")
        print(f"위원회: {structure.get('committee', 'N/A')}")
        print(f"장소: {structure.get('location', 'N/A')}")

        attendees = structure.get('attendees', [])
        print(f"\n참석자 수: {len(attendees)}")
        if attendees:
            print("참석자 목록 (처음 5명):")
            for i, attendee in enumerate(attendees[:5], 1):
                name = attendee.get('name', 'N/A')
                position = attendee.get('position', 'N/A')
                print(f"  {i}. {name} ({position})")

        speakers = structure.get('speakers', [])
        print(f"\n발언자 수: {len(speakers)}")
        if speakers:
            print(f"발언자 목록 (처음 10명): {', '.join(speakers[:10])}")

        agenda_items = structure.get('agenda_items', [])
        print(f"\n안건 수: {len(agenda_items)}")
        if agenda_items:
            print("안건 목록:")
            for i, agenda in enumerate(agenda_items[:5], 1):
                print(f"  {i}. {agenda}")

        # JSON 파일로 저장 (uploads 폴더에 동일한 타임스탬프로)
        json_filepath = save_structure_to_json(structure, timestamp)
        print(f"\n💾 구조 분석 결과 저장: {json_filepath}")
    else:
        print(f"❌ 분석 실패: {structure.get('error', 'Unknown error')}")
        if 'raw_response' in structure and structure['raw_response']:
            print(f"\n원본 응답:\n{structure['raw_response'][:500]}...")

    print("\n" + "=" * 80)
    print("✅ 테스트 완료")
    print("=" * 80)
    print("\n📌 생성된 파일:")
    print(f"   - uploads/{timestamp}.json : 구조 분석 결과")


if __name__ == "__main__":
    main()
