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
