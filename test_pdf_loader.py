"""
서울시의회 회의록 PDF 로더 테스트
PyPDF2와 pdfplumber를 사용하여 PDF 내용을 추출하고 구조 분석
Gemini 2.5 Flash를 사용하여 AI 기반 회의록 구조 분석
"""
import os
from typing import Dict, List, Tuple
import json
from datetime import datetime
from google import genai
from google.genai import types
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()


def test_pypdf2(pdf_path: str) -> Dict:
    """PyPDF2를 사용한 PDF 텍스트 추출"""
    try:
        import PyPDF2

        result = {
            "library": "PyPDF2",
            "success": False,
            "total_pages": 0,
            "text_sample": "",
            "full_text": "",
            "metadata": {}
        }

        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            result["total_pages"] = len(pdf_reader.pages)
            result["metadata"] = pdf_reader.metadata

            # 모든 페이지 텍스트 추출
            full_text = []
            for page_num, page in enumerate(pdf_reader.pages):
                text = page.extract_text()
                full_text.append(text)

            result["full_text"] = "\n".join(full_text)
            result["text_sample"] = result["full_text"][:1000]  # 처음 1000자
            result["success"] = True

        return result

    except ImportError:
        return {"library": "PyPDF2", "success": False, "error": "PyPDF2가 설치되지 않았습니다"}
    except Exception as e:
        return {"library": "PyPDF2", "success": False, "error": str(e)}


def test_pdfplumber(pdf_path: str) -> Dict:
    """pdfplumber를 사용한 PDF 텍스트 추출 (테이블 포함)"""
    try:
        import pdfplumber

        result = {
            "library": "pdfplumber",
            "success": False,
            "total_pages": 0,
            "text_sample": "",
            "full_text": "",
            "tables": [],
            "metadata": {}
        }

        with pdfplumber.open(pdf_path) as pdf:
            result["total_pages"] = len(pdf.pages)
            result["metadata"] = pdf.metadata

            # 모든 페이지 텍스트 추출
            full_text = []
            all_tables = []

            for page_num, page in enumerate(pdf.pages):
                # 텍스트 추출
                text = page.extract_text()
                if text:
                    full_text.append(f"--- Page {page_num + 1} ---\n{text}")

                # 테이블 추출
                tables = page.extract_tables()
                if tables:
                    for table_idx, table in enumerate(tables):
                        all_tables.append({
                            "page": page_num + 1,
                            "table_index": table_idx,
                            "data": table
                        })

            result["full_text"] = "\n".join(full_text)
            result["text_sample"] = result["full_text"][:1000]
            result["tables"] = all_tables
            result["success"] = True

        return result

    except ImportError:
        return {"library": "pdfplumber", "success": False, "error": "pdfplumber가 설치되지 않았습니다"}
    except Exception as e:
        return {"library": "pdfplumber", "success": False, "error": str(e)}


def analyze_meeting_structure_with_gemini(text: str) -> Dict:
    """Gemini 2.5 Flash를 사용한 AI 기반 회의록 구조 분석"""
    try:
        # Google API 키 가져오기
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            return {
                "success": False,
                "error": "GOOGLE_API_KEY가 설정되지 않았습니다"
            }

        # Gemini 클라이언트 생성
        client = genai.Client(api_key=api_key)

        # 텍스트가 너무 길면 앞부분만 사용 (토큰 제한 고려)
        text_sample = text[:30000] if len(text) > 30000 else text

        # 프롬프트 작성
        prompt = f"""다음은 서울시의회 회의록 텍스트입니다. 이 회의록을 분석하여 아래 정보를 JSON 형식으로 추출해주세요.

회의록 텍스트:
{text_sample}

추출할 정보:
1. title: 회의록 제목 (예: "제325회 정례회", "행정자치위원회 회의록")
2. date: 회의 날짜 (YYYY년 MM월 DD일 형식)
3. meeting_type: 회의 종류 (예: "정례회", "임시회", "위원회")
4. committee: 위원회명 (해당되는 경우)
5. attendees: 참석자 목록 (이름과 직책을 포함)
6. speakers: 발언자 목록 (중복 제거, 이름만)
7. agenda_items: 안건 목록
8. location: 회의 장소

응답은 반드시 다음과 같은 JSON 형식으로만 작성해주세요:
{{
    "title": "회의록 제목",
    "date": "YYYY년 MM월 DD일",
    "meeting_type": "회의 종류",
    "committee": "위원회명",
    "attendees": [
        {{"name": "이름", "position": "직책"}},
        ...
    ],
    "speakers": ["발언자1", "발언자2", ...],
    "agenda_items": ["안건1", "안건2", ...],
    "location": "회의 장소"
}}

JSON만 응답하고 다른 설명은 포함하지 마세요."""

        # Gemini API 호출 (google-genai 방식)
        response = client.models.generate_content(
            model='gemini-2.0-flash-exp',
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
        structure["total_length"] = len(text)

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
            "error": f"Gemini API 호출 실패: {str(e)}"
        }


def save_text_to_markdown(text: str, upload_folder: str = "uploads") -> str:
    """
    추출된 텍스트를 현재 시간 기반 파일명으로 마크다운 파일로 저장

    Args:
        text: 저장할 텍스트
        upload_folder: 저장할 폴더 경로

    Returns:
        저장된 파일 경로
    """
    # 현재 스크립트 위치 기준 uploads 폴더 경로
    current_dir = os.path.dirname(os.path.abspath(__file__))
    upload_dir = os.path.join(current_dir, upload_folder)

    # uploads 폴더가 없으면 생성
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)

    # 현재 시간으로 파일명 생성 (예: 20250113_143025.md)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}.md"
    filepath = os.path.join(upload_dir, filename)

    # 마크다운 파일로 저장
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(text)

    return filepath


def main():
    """메인 테스트 함수"""
    # 현재 스크립트와 같은 디렉토리에 있는 PDF 파일 경로
    current_dir = os.path.dirname(os.path.abspath(__file__))
    pdf_path = os.path.join(current_dir, "minute_pdf.pdf")

    if not os.path.exists(pdf_path):
        print(f"❌ 파일을 찾을 수 없습니다: {pdf_path}")
        return

    print("=" * 80)
    print("📄 서울시의회 회의록 PDF 로더 테스트")
    print("=" * 80)
    print()

    # pdfplumber 테스트 (가장 좋은 성능)
    print("1️⃣ pdfplumber로 PDF 텍스트 추출")
    print("-" * 80)
    pdfplumber_result = test_pdfplumber(pdf_path)

    if pdfplumber_result["success"]:
        print(f"✅ 성공")
        print(f"   총 페이지: {pdfplumber_result['total_pages']}")
        print(f"   추출된 텍스트 길이: {len(pdfplumber_result['full_text'])} 문자")
        print(f"   발견된 테이블 수: {len(pdfplumber_result['tables'])}")

        # 마크다운 파일로 저장
        print("\n")
        print("2️⃣ 추출된 텍스트를 마크다운 파일로 저장")
        print("-" * 80)
        md_filepath = save_text_to_markdown(pdfplumber_result['full_text'])
        print(f"✅ 저장 성공: {md_filepath}")

        # Gemini로 구조 분석
        print("\n")
        print("3️⃣ 회의록 구조 분석 (Gemini 2.0 Flash)")
        print("-" * 80)
        print("AI 분석 중... (30초 정도 소요될 수 있습니다)")
        structure = analyze_meeting_structure_with_gemini(pdfplumber_result['full_text'])

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

            # JSON 파일로 저장
            structure_file = "meeting_structure.json"
            with open(structure_file, 'w', encoding='utf-8') as f:
                json.dump(structure, f, ensure_ascii=False, indent=2)
            print(f"\n💾 구조 분석 결과를 {structure_file}에 저장했습니다")
        else:
            print(f"❌ 분석 실패: {structure.get('error', 'Unknown error')}")
            if 'raw_response' in structure and structure['raw_response']:
                print(f"\n원본 응답:\n{structure['raw_response'][:500]}...")

    else:
        print(f"❌ 실패: {pdfplumber_result.get('error', 'Unknown error')}")

    print("\n" + "=" * 80)
    print("✅ 테스트 완료")
    print("=" * 80)


if __name__ == "__main__":
    main()
