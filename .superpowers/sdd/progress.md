# SDD Progress: AI Dialogue Extraction

Plan: docs/superpowers/plans/2026-07-01-ai-dialogue-extraction.md
Base branch: main (c181f9f)

Task 1: complete (remove_inline_directions helper; 5 tests green)
Task 2: complete (commits be61807..512fa25, review clean after fixture-skip fix)
  - Minor (final-review triage): assemble_dialogue `if not (core and core in line)` guard is effectively unreachable — plan-mandated defensive, harmless.
