# SDD Progress: AI Dialogue Extraction

Plan: docs/superpowers/plans/2026-07-01-ai-dialogue-extraction.md
Base branch: main (c181f9f)

Task 1: complete (remove_inline_directions helper; 5 tests green)
Task 2: complete (commits be61807..512fa25, review clean after fixture-skip fix)
  - Minor (final-review triage): assemble_dialogue `if not (core and core in line)` guard is effectively unreachable — plan-mandated defensive, harmless.
Task 3: complete (commits 881e26c..780b620, review clean after fallback speaker-strip fix)
  - Fixed (Important): regex fallback now runs data_processing so speaker prefixes are stripped (regression test added).
  - Minor (final-review triage): no dedup guard on duplicate ids within a chunk response (low risk).
  - Minor (final-review triage): no test simulates _classify_chunk raising (except-branch verified analytically).
  - Open (final-review / live): confirm gpt-5.4 accepts chat.completions.parse(response_format=...) and rejects temperature — only checkable against real API (Task 6 AI-ON verification).
Task 4: complete (commit 315f8ee, self-verified: 3 files, openai>=2.0 pinned @2.44.0, split model gpt-5.4, 21 passed)
Task 5: complete (commit 8434794, review Spec✅/Quality Approved)
  - Verified by controller: AI-OFF CLI extraction is BYTE-IDENTICAL (675/675 lines) to committed _converted.docx → fallback path unchanged.
  - Env note: ~/Downloads write blocked by macOS TCC for automated process (works in user terminal). AI-ON live run needs user's key.
  - Minor (final-review triage): CHUNK_SIZE=4000 duplicated in main.py and convert_cli.py.
  - Minor (final-review triage): convert_cli.py hand-rolled flag scan silently ignores typo'd flags (e.g. --slpit).
  - Minor (final-review triage): convert_cli --split is sequential vs GUI parallel (perf only).
Task 6: complete (commits ff11dd0..HEAD; docs for AI-ON path + local CLI; 21 passed)
  - Controller fix: corrected stale CLAUDE.md gpt-4o -> gpt-5.4 reference.
  - Deferred to user (needs live key): AI-ON end-to-end run verifying the 3 bug fixes on the real docx (Task 6 Step 5).

FINAL REVIEW: READY-WITH-NITS (opus). All 3 bugs structurally fixed; constraints hold.
  - Fixed (High H1): dropped temperature from gpt-5.4 split call in utils/openai.py (commit eaedf84).
  - Fixed (Low L1): added comment noting fallback narration re-leak.
  - DEFERRED minors (ship-as-is): unreachable assemble guard; no dup-id/chunk-raise tests; CHUNK_SIZE dup; CLI flag parsing; sequential --split.
  - REMAINING (user, needs live key): AI-ON end-to-end run in a real terminal (~/Downloads writable there) to confirm the 3 fixes on the docx.
BRANCH COMPLETE — feat/ai-dialogue-extraction.

CODEX REVIEW (adversarial triage via receiving-code-review):
  - FIXED (Medium): colon-form speaker slice — added ':' to _BOUNDARY + lstrip(": \t"); test_strips_colon_form_speaker.
  - FIXED (Medium): xlsx AI bypass now runs data_processing (parity with OFF path); test_xlsx_bypass_strips_speaker_and_directions_like_off_path.
  - PUSHBACK (High): split-output not validated — pre-existing LLM-reflow step, outside the extraction invariant; offered as optional follow-up (whitespace-insensitive subsequence guard on request_to_openai output).
  - PUSHBACK (Low): dup-id last-write-wins — YAGNI (strict schema makes it moot, no crash).
  Full suite: 24 passed.

=== PATTERN-AWARE CHUNKING (plan: docs/superpowers/plans/2026-07-02-pattern-aware-chunking.md) ===
Spec: docs/superpowers/specs/2026-07-02-pattern-aware-chunking-design.md (approved: 접근안1, 정확도 우선, xlsx 바이패스 유지)
PC-Task 1: complete (commits 7c856bd..d5b1d35, review clean; Minor: unused `import re` in test file — used by Task 2/3 tests, no action)
PC-Task 2: complete (commits 2441933..ecb3bc8, review clean)
  - Minor (final-review triage): no test at exact ratio boundaries 0.05/0.60.
  - Minor (final-review triage): validate_pattern lacks return type annotation (plan code omitted it).
  - Minor (accepted risk, in spec): no ReDoS guard beyond length cap.
PC-Task 3: complete (commits 46d09e8..21f75bb, review clean after off-by-one fix)
  - Fixed (Important): extension scan now includes base+extend line (regression test added).
  - Minor (final-review triage): no guard against base<=0 infinite loop (unreachable via current callers).
  - Minor (final-review triage): 1 blank line vs 2 before _SYSTEM_PROMPT (style).
PC-Task 4: complete (commits 122d805..1468a85, review clean)
  - Minor (fix in Task 5 wiring): analyze_pattern constructs client/sample before try — bad api_key could raise instead of returning None.
  - Minor (final-review triage): fake swallows extra kwargs — no self-enforcing "no temperature" assertion.
  - Minor (accepted, threat-model): pattern_description echoed into system prompt unsanitized (single-user, own-key app).
