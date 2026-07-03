# CLAUDE.md

Claude Code(claude.ai/code)가 이 저장소에서 작업할 때 따르는 지침.

## ★ 위임 원칙 (최우선)

**모든 코드 수정은 메인 대화에서 직접 하지 않고 superpowers 워크플로 또는 서브에이전트에 위임한다.**

**허용 (메인 대화)**

- 코드·상태 읽기: Read, Grep, Glob, 조회용 Bash
- 사용자에게 질문, 분석·수정 계획 제시
- superpowers 스킬 실행 / 구현용 서브에이전트(general-purpose) 직접 spawn
- 문서 수정: CLAUDE.md, `docs/`, README.md, `.superpowers/` 산출물 (소스 코드가 아님)

**금지 (메인 대화)**

- Edit/Write 로 `main.py`, `convert_cli.py`, `utils/`, `tests/`, `constants.py` 등 **프로젝트 소스를 직접 수정**

**코드 수정 라우팅**

- 신규 기능·복잡·멀티파일 → 표준 파이프라인:
  1. `superpowers:brainstorming` — 요구·설계 탐색
  2. `superpowers:writing-plans` — 구현 계획 작성
  3. `/codex:adversarial-review` — 계획·접근에 대한 Codex 적대적 리뷰
  4. `superpowers:subagent-driven-development` — SDD 구현 (태스크별 구현 서브에이전트 + 태스크 리뷰 + 최종 브랜치 리뷰)
- 단순·국소 수정 → general-purpose 서브에이전트에 구현 위임 (분석·계획은 메인 대화에서 제시)
- 버그 조사 → `superpowers:systematic-debugging`
- 코드 리뷰 → `superpowers:requesting-code-review` (+ 필요 시 `/codex:adversarial-review`)

**승인 게이트**

- 위임 전, 분석과 수정 계획을 사용자에게 제시하고 승인을 받는다.
- 요청이 모호하면 임의로 한쪽을 고르지 않는다. 가정을 명시하고, 해석이 둘 이상이면 선택지를 제시한다. 더 단순한 대안이 보이면 함께 제시한다.

## 언어

- 모든 응답·분석·리포트·산출물(`.md`)은 한글로 작성한다.
- 코드 식별자·타입 힌트·import 는 영어를 유지한다. 코드 주석·커밋 메시지는 한글로 작성한다(저장소 기존 컨벤션).

## 코드 작성 방침

### 1. 코딩 전에 생각하기

- 가정을 명시적으로 밝히고, 불확실하면 질문한다.
- 여러 해석이 가능하면 조용히 선택하지 말고 선택지를 제시한다.
- 더 간단한 접근이 있으면 제안한다.
- 혼란스러운 요소는 넘어가지 말고 명확히 짚는다.

### 2. 단순성 우선

- 요청된 것 이상의 기능을 추가하지 않는다.
- 한 번만 쓰이는 코드에 추상화를 만들지 않는다.
- 불필요한 "유연성" 이나 "설정 가능성" 을 넣지 않는다.
- 발생할 수 없는 시나리오에 대한 에러 핸들링을 하지 않는다.
- 50줄이면 될 것을 200줄로 만들지 않는다.

### 3. 외과적 변경

- 관련 없는 코드·주석·포맷을 개선하지 않는다.
- 동작하는 코드를 "정리 차원" 으로 리팩토링하지 않는다.
- 기존 스타일을 따른다.
- 내 변경으로 생긴 미사용 코드만 정리한다(기존 dead code 는 건드리지 않는다).
- 변경된 모든 줄은 사용자의 요청에 직접 연결되어야 한다.

### 4. 목표 기반 실행

- 모호한 태스크를 측정 가능한 목표와 검증 단계로 변환한다.
- 다단계 작업에는 각 단계별 체크포인트가 있는 구조화된 계획을 수립한다.
- 강한 기준은 독립적 반복을 가능하게 하고, 약한 기준은 끊임없는 확인을 필요로 한다.

### 5. 문서 동기화

- 코드 변경이 README.md 내용(공개 API, 새 기능, 설정 키, 사용법, CLI 예시, 환경변수)에 영향을 줄 때는 같은 변경에서 README.md 도 함께 갱신한다.
- 특히 대사 인식 규칙(어미 목록·캐스케이드)을 수정하면 README.md 의 **"대사 인식 조건"** 절을 같은 변경에서 동기화한다 — 이 절이 규칙의 권위 있는 사람용 스펙이다.
- 코드 수정이 동반되는 워크플로의 마무리 단계에서 README.md 동기화 여부를 점검한다. 영향 있으면 같은 라운드에서 갱신, 없으면 "README 영향 없음" 으로 명시한다.

## 프로젝트 개요

ScriptShaper(자막제작자를 위한 대본 변환 프로젝트) — 대본 문서에서 대사만 추출(화자명·지문 제거)하고, 옵션으로 OpenAI(`gpt-5.4`)를 사용해 20자 이하 자막 줄로 재구성한 뒤 `~/Downloads` 에 Word 문서로 저장하는 한국어 Tkinter 데스크톱 앱. **macOS** 대상이며 CI 가 PyInstaller 단일 바이너리로 빌드해 배포한다.

파이프라인: `import_file_to_text` → `extract_speaker_and_dialogue`(규칙 기반 first-match-wins 캐스케이드, `utils/extract_speaker_and_dialogue.py`) → `data_processing` → (옵션 AI 분할) → `save_to_word_file`. "AI 사용" ON 이면 추출이 `utils/openai_extract.py` 의 구조화 출력 분류기로 라우팅되고, 분류 전 문서별 패턴 분석(`analyze_pattern` → `validate_pattern`)이 청크 경계를 화자 줄에 정렬하고 분류 프롬프트에 문서 형식을 주입한다(실패 시 고정 50줄 청크·일반 프롬프트로 폴백). 헤드리스 실행은 `convert_cli.py`.

주의: 실제 지원 포맷은 `.docx`/`.xlsx` 뿐(파일 선택기에 보이는 나머지 확장자는 미구현), `.xlsx` 는 대사 감지를 건너뛴다(셀 = 대사 1줄 가정). 설정(API 키)은 `~/Library/Application Support/ScriptShaper/settings.json`(GUI `설정` 버튼으로 등록, 구버전 `~/Downloads/settings.json` 은 발견 시 자동 이관 — `utils/json_service.py`), 출력물은 기본 `~/Downloads/<이름>_converted.docx`(CLI 는 `--out` 으로 변경 가능).

## 명령어

```bash
pipenv install                        # 의존성 설치 (Python 3.11)
pipenv run python main.py             # GUI 실행

pipenv run python -m pytest -q        # 전체 테스트

# 헤드리스 변환 (stdout 미리보기 + ~/Downloads 저장)
pipenv run python convert_cli.py "경로/파일.docx"                # 규칙 기반 추출
pipenv run python convert_cli.py "경로/파일.docx" --ai           # AI 분류 추출
pipenv run python convert_cli.py "경로/파일.docx" --ai --split   # AI 추출 + 20자 분할

pyinstaller main.spec                 # 로컬 단일 바이너리 빌드 → dist/
# CI(main push)는 main.spec 이 아니라 `pyinstaller --onefile main.py` 로 빌드하고,
# 릴리스 태그는 `git describe --tags` 에서 가져온다 — 버전 올리기 = 새 git 태그 push
```

## CLAUDE.md 관리 원칙

- 이 파일은 최대한 간결하고 명확하게 유지한다.
- 중복된 지침을 작성하지 않는다 — 상세는 `docs/` 로 분리하고 여기서는 포인터만 둔다.
- 불필요하거나 오래된 지침은 삭제한다.
- 진행 상태·작업 히스토리는 `.superpowers/sdd/progress.md` 가 담당한다. CLAUDE.md 에 누적하지 않는다.
