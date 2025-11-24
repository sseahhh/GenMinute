import pydot
import os
from IPython.display import SVG, display # 이미지를 화면에 표시하기 위한 핵심 모듈
import sys

# IPython 환경 체크 (Jupyter, Colab 등)
IS_IPYTHON = 'ipykernel' in sys.modules

# --- 💡 1. 폰트 절대 경로 설정 (가장 중요!) ---
# 사용자의 OS와 폰트 설치 위치에 따라 이 경로를 반드시 수정해 주세요.

# ▼▼▼ Windows 사용자용 추천 경로 ▼▼▼
KOREAN_FONT_PATH = "C:/Windows/Fonts/malgun.ttf"

# ▼▼▼ macOS 사용자용 추천 경로 ▼▼▼
# KOREAN_FONT_PATH = "/System/Library/Fonts/Supplemental/AppleGothic.ttf"

# --------------------------------------------------------

if not os.path.exists(KOREAN_FONT_PATH):
    print(f"경고: 폰트 파일을 찾을 수 없습니다! -> {KOREAN_FONT_PATH}")

# --- 2. 색상 및 스타일 정의 (생략) ---
COLOR_CENTER_BG = "#FAFAFA"    # 밝은 회색 (거의 흰색)
COLOR_CENTER_BORDER = "#B2EBF2"  # 밝은 하늘색
COLOR_BRANCH_MAIN_BG = "#F0F4C3" # 옅은 라임색
COLOR_BRANCH_MAIN_BORDER = "#AED581" # 밝은 녹색
COLOR_BRANCH_SUB_BG = "#F8F8F8"  # 아주 옅은 회색
COLOR_BRANCH_SUB_BORDER = "#E0E0E0" # 옅은 회색
COLOR_EDGE_ORANGE = "#FFAB91"   # 밝은 코랄색
COLOR_EDGE_BLUE = "#81D4FA"    # 밝은 파랑색

# --- 3. 그래프 객체 생성 (SVG에 최적화 및 인코딩 강제) ---
graph = pydot.Dot("MindMap_Styled", graph_type="digraph",
                  encoding="UTF-8",
                  charset="UTF-8", # 인코딩 명시
                  rankdir="LR",
                  splines="curved",
                  nodesep="0.6",
                  ranksep="1.2",
                  bgcolor="transparent")

# --- 4. 노드 스타일 정의 (절대 경로 적용) ---
common_node_attrs = dict(fontname=KOREAN_FONT_PATH)

# 중심 노드 정의
graph.add_node(pydot.Node("중심", label="회의록 애플리케이션 개발 계획",
                          shape="box", style="filled, rounded",
                          fillcolor=COLOR_CENTER_BG,
                          color=COLOR_CENTER_BORDER,
                          penwidth=2.0,
                          **common_node_attrs))

# 주/하위/잎 노드 스타일 정의
style_main_branch = dict(shape="box", style="filled, rounded", fillcolor=COLOR_BRANCH_MAIN_BG, color=COLOR_BRANCH_MAIN_BORDER, penwidth=2.0, **common_node_attrs)
style_sub_branch = dict(shape="box", style="filled, rounded", fillcolor=COLOR_BRANCH_SUB_BG, color=COLOR_BRANCH_SUB_BORDER, fontcolor="#424242", penwidth=1.5, **common_node_attrs)
style_leaf = dict(shape="box", style="filled", fillcolor="#FAFAFA", color="#E0E0E0", fontcolor="#333333", penwidth=1.0, **common_node_attrs)

# --- 5. 노드 추가 (가독성을 위해 일부 생략하고 연결만 포함) ---
# [주 가지 노드]
graph.add_node(pydot.Node("핵심_기능_역할", label="핵심 기능 및 역할 분담", **style_main_branch))
graph.add_node(pydot.Node("실행_단계_책임", label="실행 단계 및 담당 역할", **style_main_branch))
graph.add_node(pydot.Node("책임_분담_협업", label="책임 분담 및 협업 구조", **style_main_branch))
graph.add_node(pydot.Node("향후_계획_방향", label="향후 계획 및 진행 방향", **style_main_branch))

# [하위 가지 노드: 핵심 기능]
graph.add_node(pydot.Node("우선순위", label="핵심 기능 우선순위", **style_sub_branch))
graph.add_node(pydot.Node("요약_검색", label="회의록 요약 및 검색", **style_sub_branch))
graph.add_node(pydot.Node("검색_챗봇", label="검색 및 챗봇 기능 분리", **style_sub_branch))
graph.add_node(pydot.Node("벡터_전략", label="벡터 스토어 저장 전략", **style_sub_branch))
graph.add_node(pydot.Node("추가_검토", label="추가 기능 검토", **style_sub_branch))

# [잎 노드]
graph.add_node(pydot.Node("음성_텍스트", label="음성->텍스트 변환(1순위)", **style_leaf))
graph.add_node(pydot.Node("화자_분리", label="화자분리(2순위)", **style_leaf))
graph.add_node(pydot.Node("표준_템플릿", label="Pydantic 기반 표준 템플릿 설계", **style_leaf))
graph.add_node(pydot.Node("형식_유지", label="일관된 형식 유지", **style_leaf))
graph.add_node(pydot.Node("키워드_검색", label="키워드/날짜 검색", **style_leaf))
graph.add_node(pydot.Node("응답_챗봇", label="자연어 질의응답 챗봇", **style_leaf))
graph.add_node(pydot.Node("Parent_Child", label="Parent-Child 구조로 전체 회의록 연결", **style_leaf))
graph.add_node(pydot.Node("회의록_저장", label="회의록 청킹 후 저장", **style_leaf))
graph.add_node(pydot.Node("메타데이터_포함", label="메타데이터 포함 (날짜, 참여자 등)", **style_leaf))
graph.add_node(pydot.Node("Self_Query", label="Self-Query와 Vector Search 지원", **style_leaf))
graph.add_node(pydot.Node("수기_수정", label="수기 수정, 다시 듣기, 검토 및 수정 모드", **style_leaf))

# [하위 가지 노드: 실행 단계]
graph.add_node(pydot.Node("시나리오_제작", label="시나리오 및 샘플 데이터 제작", **style_sub_branch))
graph.add_node(pydot.Node("템플릿_정의", label="표준 템플릿 정의", **style_sub_branch))
graph.add_node(pydot.Node("음성_화자_개발", label="음성-텍스트 변환과 화자분리 개발", **style_sub_branch))
graph.add_node(pydot.Node("요약_메타데이터", label="회의록 요약 및 메타데이터 생성", **style_sub_branch))
graph.add_node(pydot.Node("벡터_저장_검색", label="벡터 저장 및 검색 시스템 구축", **style_sub_branch))
graph.add_node(pydot.Node("Gradio_구축", label="Gradio 인터페이스 설계", **style_sub_branch))
graph.add_node(pydot.Node("챗봇_통합", label="챗봇 및 검색 기능 통합", **style_sub_branch))

# [하위 가지 노드: 책임 분담]
graph.add_node(pydot.Node("공동_작업", label="공동 작업: 시나리오, 템플릿, 시스템 통합", **style_sub_branch))
graph.add_node(pydot.Node("개발_담당", label="개발 담당: 음성처리, 요약, 벡터 저장, 인터페이스", **style_sub_branch))
graph.add_node(pydot.Node("간트_차트", label="간트 차트 작성: 역할과 일정 명확화", **style_sub_branch))

# [하위 가지 노드: 향후 계획]
graph.add_node(pydot.Node("샘플_우선", label="샘플 데이터 우선 제작: 품질 공유", **style_sub_branch))
graph.add_node(pydot.Node("인터페이스_설계", label="인터페이스 설계: 사용자 경험 구체화", **style_sub_branch))
graph.add_node(pydot.Node("테스트_범위", label="테스트 범위 확장: 복잡한 회의 시나리오 적용", **style_sub_branch))

# --- 6. 엣지 정의 (모든 엣지 추가) ---
common_edge_attrs = dict(penwidth=2.0)
leaf_edge_attrs = dict(color=COLOR_EDGE_BLUE, penwidth=1.5, style="dashed")
graph.add_edge(pydot.Edge("중심", "핵심_기능_역할", color=COLOR_EDGE_ORANGE, **common_edge_attrs))
graph.add_edge(pydot.Edge("중심", "실행_단계_책임", color=COLOR_EDGE_ORANGE, **common_edge_attrs))
graph.add_edge(pydot.Edge("중심", "책임_분담_협업", color=COLOR_EDGE_ORANGE, **common_edge_attrs))
graph.add_edge(pydot.Edge("중심", "향후_계획_방향", color=COLOR_EDGE_ORANGE, **common_edge_attrs))
graph.add_edge(pydot.Edge("핵심_기능_역할", "우선순위", color=COLOR_EDGE_BLUE, **common_edge_attrs))
graph.add_edge(pydot.Edge("핵심_기능_역할", "요약_검색", color=COLOR_EDGE_BLUE, **common_edge_attrs))
graph.add_edge(pydot.Edge("핵심_기능_역할", "검색_챗봇", color=COLOR_EDGE_BLUE, **common_edge_attrs))
graph.add_edge(pydot.Edge("핵심_기능_역할", "벡터_전략", color=COLOR_EDGE_BLUE, **common_edge_attrs))
graph.add_edge(pydot.Edge("핵심_기능_역할", "추가_검토", color=COLOR_EDGE_BLUE, **common_edge_attrs))
graph.add_edge(pydot.Edge("실행_단계_책임", "시나리오_제작", color=COLOR_EDGE_BLUE, **common_edge_attrs))
graph.add_edge(pydot.Edge("실행_단계_책임", "템플릿_정의", color=COLOR_EDGE_BLUE, **common_edge_attrs))
graph.add_edge(pydot.Edge("실행_단계_책임", "음성_화자_개발", color=COLOR_EDGE_BLUE, **common_edge_attrs))
graph.add_edge(pydot.Edge("실행_단계_책임", "요약_메타데이터", color=COLOR_EDGE_BLUE, **common_edge_attrs))
graph.add_edge(pydot.Edge("실행_단계_책임", "벡터_저장_검색", color=COLOR_EDGE_BLUE, **common_edge_attrs))
graph.add_edge(pydot.Edge("실행_단계_책임", "Gradio_구축", color=COLOR_EDGE_BLUE, **common_edge_attrs))
graph.add_edge(pydot.Edge("실행_단계_책임", "챗봇_통합", color=COLOR_EDGE_BLUE, **common_edge_attrs))
graph.add_edge(pydot.Edge("책임_분담_협업", "공동_작업", color=COLOR_EDGE_BLUE, **common_edge_attrs))
graph.add_edge(pydot.Edge("책임_분담_협업", "개발_담당", color=COLOR_EDGE_BLUE, **common_edge_attrs))
graph.add_edge(pydot.Edge("책임_분담_협업", "간트_차트", color=COLOR_EDGE_BLUE, **common_edge_attrs))
graph.add_edge(pydot.Edge("향후_계획_방향", "샘플_우선", color=COLOR_EDGE_BLUE, **common_edge_attrs))
graph.add_edge(pydot.Edge("향후_계획_방향", "인터페이스_설계", color=COLOR_EDGE_BLUE, **common_edge_attrs))
graph.add_edge(pydot.Edge("향후_계획_방향", "테스트_범위", color=COLOR_EDGE_BLUE, **common_edge_attrs))
graph.add_edge(pydot.Edge("우선순위", "음성_텍스트", **leaf_edge_attrs))
graph.add_edge(pydot.Edge("우선순위", "화자_분리", **leaf_edge_attrs))
graph.add_edge(pydot.Edge("요약_검색", "표준_템플릿", **leaf_edge_attrs))
graph.add_edge(pydot.Edge("요약_검색", "형식_유지", **leaf_edge_attrs))
graph.add_edge(pydot.Edge("검색_챗봇", "키워드_검색", **leaf_edge_attrs))
graph.add_edge(pydot.Edge("검색_챗봇", "응답_챗봇", **leaf_edge_attrs))
graph.add_edge(pydot.Edge("검색_챗봇", "Parent_Child", **leaf_edge_attrs))
graph.add_edge(pydot.Edge("벡터_전략", "회의록_저장", **leaf_edge_attrs))
graph.add_edge(pydot.Edge("벡터_전략", "메타데이터_포함", **leaf_edge_attrs))
graph.add_edge(pydot.Edge("벡터_전략", "Self_Query", **leaf_edge_attrs))
graph.add_edge(pydot.Edge("추가_검토", "수기_수정", **leaf_edge_attrs))


# --- 7. SVG 데이터 생성 및 화면 출력 ---
try:
    # 1. SVG 데이터를 생성합니다. (메모리에 저장)
    svg_data = graph.create_svg(prog='dot')

    # 2. IPython 환경(Jupyter/Colab)에서 바로 출력합니다.
    if IS_IPYTHON:
        print("✅ 그래프를 화면에 바로 출력합니다:")
        display(SVG(svg_data))
    else:
        print("\n💡 IPython 환경(Jupyter/Colab)이 아닙니다. SVG 파일을 생성합니다.")

    # 3. SVG 파일로 저장
    output_svg_file = 'mindmap_rendered_output.svg'
    with open(output_svg_file, 'wb') as f:
        f.write(svg_data)
    print(f"이미지는 '{output_svg_file}' 파일로도 저장되었습니다.")


except Exception as e:
    print(f"\n❌ 오류 발생: {e}")
    print("Graphviz 실행에 실패했습니다. 다음 사항을 확인해주세요:")
    print(f"1. 폰트 경로: '{KOREAN_FONT_PATH}'가 정확한가요?")
    print("2. Graphviz 설치: 'dot' 명령어가 작동하나요?")
    print("3. 환경: 일반 파이썬 스크립트에서는 'pip install IPython'을 해야 화면 출력을 시도할 수 있습니다.")

    # 디버깅을 위해 DOT 파일 저장
    output_dot_file = 'mindmap_rendered_output.dot'
    graph.write(output_dot_file)
    print(f"디버깅을 위해 DOT 파일 '{output_dot_file}'을 저장했습니다.")