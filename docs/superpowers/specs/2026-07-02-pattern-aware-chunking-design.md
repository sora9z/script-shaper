# Pattern-Aware Chunking & Classification Design

날짜: 2026-07-02 · 브랜치: `feat/ai-dialogue-extraction` 후속 · 상태: 승인(접근안 1)

## 배경 / 목적

AI 분류 추출(`utils/openai_extract.py`)은 원문을 50줄 고정 청크로 나눠 gpt-5.4에 보낸다. 청크 경계가 화자 블록 중간(연속 대사)에 걸리면 앞 5줄 context만으로 화자를 상속해야 하고, 화자줄이 5줄보다 앞이면 오분류(누락) 위험이 있다.

관찰: **한 문서 안에서는 화자명·지문 표기 패턴이 일관된다** (같은 작가/포맷). 따라서 문서당 1회 "패턴 분석" AI 호출로 화자줄 형식을 학습하면:
1. **청킹 경계**를 화자줄 직전으로 정렬해 블록이 잘리지 않게 하고,
2. **분류 프롬프트에 문서 고유 패턴을 주입**해 매 청크의 분류 정확도를 높인다.

우선순위: 정확도 > 비용 (문서당 +1 호출 수용).

## 결정 사항 (사용자 확정)

- 매 줄 AI 분류는 유지한다 (패턴 기반 regex 추출로 대체하지 않음 — 그건 비용 최적화 방향).
- 패턴 분석 결과는 청킹 경계 **및** 분류 프롬프트 주입 양쪽에 쓴다.
- `.xlsx`/`.xls`는 현행 바이패스 유지 (패턴 분석/청킹 미적용).
- 샘플링: "앞/중간/끝 한 페이지씩" 취지를 docx에 맞게 **줄 윈도우 3개 × 40줄**로 구현 (python-docx에는 페이지 개념이 없음; PDF는 미지원 포맷이라 범위 밖).

## 아키텍처

모든 신규 코드는 `utils/openai_extract.py`에 추가 (기존 분류기와 응집). 파이프라인:

```
extract_dialogue_ai
  ├─ .xlsx/.xls → data_processing (기존 바이패스, 불변)
  ├─ analyze_pattern(샘플 3윈도우 → gpt-5.4 1회) ──실패→ None
  ├─ validate_pattern(regex 컴파일+매치율 검증) ──실패→ None
  ├─ classify_lines(..., pattern)
  │    ├─ pattern 있음: chunk_by_speaker_boundaries + 프롬프트 패턴 블록 주입
  │    └─ pattern None: 현행 고정 50줄 + 일반 프롬프트  ← 폴백 바닥
  └─ (이하 기존과 동일: 폴백/assemble_dialogue)
```

**불변 조건:** 패턴 경로의 어떤 실패도 현행 동작으로 폴백한다 — 이 기능으로 인해 기존보다 나빠지는 경우는 없어야 한다. 대사 텍스트 무변형 원칙(라벨만 AI, 글자는 slice)은 그대로.

## 컴포넌트

### 1. `ScriptPattern` (pydantic, structured output)
```python
class ScriptPattern(BaseModel):
    speaker_line_regex: str            # 화자줄 판정 regex, ^ 앵커 필수
    scene_header_regex: Optional[str]  # 씬헤더 regex (없으면 None)
    pattern_description: str           # 분류 프롬프트 주입용 한국어 설명
    speaker_examples: list[str]        # 샘플에서 뽑은 실제 화자줄 (2~5개)
```

### 2. `sample_windows(lines: list[str], n_windows=3, window=40) -> list[str]`
앞/중간/끝 3개 윈도우. 문서가 `n_windows*window`보다 짧으면 전체 반환(중복 없음). 순수 함수.

### 3. `analyze_pattern(api_key, lines, model=CLASSIFY_MODEL, *, _client=None) -> Optional[ScriptPattern]`
`sample_windows` 결과를 붙여 1회 structured-output 호출(`response_format=ScriptPattern`, temperature 미전달). 예외/파싱 실패 → `None` + 로그.

**프롬프트 요구사항 (2026-07-02 코퍼스 분석 반영 — `docs/analysis/2026-07-02-대본샘플-형식분석.md`):**
- 목표는 **화자줄 regex 하나** — 지문(내레이션) regex는 요구하지 않음(형식으로 구분 불가, 분류기 몫).
- 구분자 3형 명시: 콜론형 / 공백·탭형 / **붙음형**(`은수(N)대사` — 구분자 없음).
- **화자줄 없는 문서**(자막 리스트/SRT)면 빈 regex 반환 지시 — 순번·타임코드·컷번호는 화자줄이 아님을 명시. 빈 regex는 `validate_pattern`이 거부 → 전면 폴백 (사용자 확정: 화자명 없으면 패턴 기능 불필요).
- 씬헤더-인명 충돌 경고 (`은수 집, 주방 (D)`는 화자줄이 아님).
- 화자명 문자 집합 확장: 숫자 접미·콤마 다중·`/`·언더스코어. 태그 `(E)(N)(F)(O.L)` 붙음/띄움 모두.
- `speaker_examples`는 실존 줄만, 노이즈(페이지 헤더 파일명 등) 금지. 매치율 5~60% 검산 힌트 포함.

### 4. `validate_pattern(pattern, lines) -> Optional[re.Pattern]`
- regex 문자열 길이 ≤ 200, `re.compile` 성공해야 함 (`re.error` → None).
- 전체 `lines`에 `match` 적용, 매치율이 **[0.05, 0.60]** 이어야 함 — 화자줄은 "일부"라는 상식 검증(0%≈쓸모없음, >60%≈과잉매치).
- 통과 시 컴파일된 regex 반환, 아니면 `None`.
- `scene_header_regex`도 동일하게 컴파일 시도하되 실패 시 그것만 버림(전체 폴백 아님).

### 5. `chunk_by_speaker_boundaries(lines, speaker_re, scene_re=None, base=CLASSIFY_CHUNK_LINES, extend=30) -> list[tuple[int,int]]`

**(2026-07-02 추가) 경계 판정은 union 사용:** `classify_lines`는 학습 regex를 그대로 쓰지 않고 `_boundary_union(speaker_re)` — 학습 regex + baseline `SPEAKER_DIALOGUE_REGEX_LIST`(콜론형·3+공백형)의 alternation — 을 전달한다. 경계 오탐(이른 절단)/미탐(50줄 폴백)은 비용이 낮아 넓은 판정이 안전. 단 **매치율 검증은 학습 regex 단독** — baseline 콜론형은 SRT 타임코드까지 무는 과잉 패턴임이 실증되어 검증에 섞으면 학습 실패가 가려진다.
- `end = start + base`에서 시작해 `end+extend` 지점까지(**포함**, 상한 `n`) 스캔, **처음 만나는 화자줄/씬헤더의 직전**을 경계로 확정(그 줄부터 다음 청크).
- 범위 내 경계 없으면 `end` 그대로(현행 50줄과 동일 — 80줄로 늘려봤자 블록 중간이긴 마찬가지).
- 반환은 `[start, end)` 목록, 전 줄 커버·중복 없음. 순수 함수.

### 6. 프롬프트 주입
검증 통과 시 `_SYSTEM_PROMPT` 뒤에 블록 추가:
```
[이 문서의 확인된 패턴]
- 화자줄 형식: {pattern_description}
- 화자줄 예시: {speaker_examples}
- 참고 regex: {speaker_line_regex}
- 화자줄 형식이 아닌데 대사로 판단되는 줄은 앞 화자의 '연속 대사'다 (speaker=null).
```

### 7. `classify_lines` / `extract_dialogue_ai` 변경
- `classify_lines(..., pattern: Optional[ScriptPattern] = None, speaker_re=None, scene_re=None)` — pattern 존재 시 경계 청킹+주입, 아니면 현행. `CONTEXT_LINES=5` 유지(이중 안전망).
- `extract_dialogue_ai` — xlsx 분기 뒤에 `analyze_pattern`→`validate_pattern` 수행, 결과를 `classify_lines`에 전달. 실패 시 None 전달(=현행).

## 에러 처리

| 실패 지점 | 처리 |
|---|---|
| 패턴 분석 API 예외/타임아웃 | `None` → 현행 경로, 로그(print — 프로젝트 관례) |
| regex 컴파일 실패/길이 초과 | `None` → 현행 경로 |
| 매치율 범위 밖 | `None` → 현행 경로 |
| scene regex만 실패 | scene만 버리고 speaker regex는 사용 |
| 분류 청크 실패 | 기존과 동일(해당 id들 regex 폴백) |

## 테스트 전략 (API 없이)

- `sample_windows`: 긴/짧은/정확히 경계 길이 문서.
- `validate_pattern`: 정상 regex 통과, 컴파일 불가·과잉매치(`^.*`)·무매치 각각 None.
- `chunk_by_speaker_boundaries`: 합성 대본(화자줄 regex `^[가-힣A-Za-z0-9/]+...`)으로 — 경계가 화자줄 직전 정렬, 경계 없음 시 50 유지, 전체 커버리지·비중복 속성.
- `analyze_pattern` 실패 폴백: 예외 던지는 fake client → 결과가 현행 경로와 동일.
- 프롬프트 주입: fake client가 받은 messages 캡처해 패턴 블록 포함 확인.
- `extract_dialogue_ai` 통합: fake client가 `response_format`으로 분기(ScriptPattern이면 패턴, Classification이면 라벨) — 기존 `_FakeClient` 확장.
- 기존 24개 테스트 전부 그린 유지 (pattern=None 폴백이 현행과 동일함을 보장).

## 수용 리스크 / 비고

- **LLM 산출 regex의 병리적 백트래킹(ReDoS)**: 길이 상한 200자 + 대상이 짧은 대본 줄(수백 개)이라 영향 제한적. 표준 `re`에는 타임아웃이 없음을 인지하고 수용. (필요 시 후속으로 `regex` 모듈 타임아웃 도입 가능.)
- 문서당 +1 API 호출 (비용 우선순위 낮음 — 사용자 확정).
- PDF/HWP는 리더 자체가 미구현이라 범위 밖. 구현되면 `sample_windows`가 그대로 적용됨.
