# utils/document_converter.py

def convert_segments_to_documents(segments: list, meeting_id: str, title: str, audio_file: str) -> list[dict]:
    """
    STT segments를 도큐먼트 형태로 변환합니다.
    각 세그먼트는 하나의 도큐먼트가 되며, 텍스트는 page_content로,
    나머지 정보는 metadata로 포함됩니다.
    """
    documents = []
    for segment in segments:
        doc_metadata = {
            "id": segment.get("id"),
            "speaker": segment.get("speaker"),
            "start_time": segment.get("start_time"),
            "confidence": segment.get("confidence"),
            "meeting_id": meeting_id,
            "title": title,
            "audio_file": audio_file,
        }
        document = {
            "page_content": segment.get("text", ""),
            "metadata": doc_metadata,
        }
        documents.append(document)
    return documents
