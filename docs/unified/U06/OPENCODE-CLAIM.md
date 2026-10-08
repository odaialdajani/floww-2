# OpenCode CLAIM — U06 probe slice (2026-10-08, human-authorized assist)

Human explicitly authorized OpenCode to accelerate Cline's queue without
breaking anything. Claim terms (narrow, collision-proof):

- Scope: NEW probe file ONLY —
  `backend/tests/unified/test_related_admission_opencode_probes.py`
  (distinct name; Cline's `test_related_admission.py` untouched/reserved).
- NO source edits: no routes/services/docs changes, no repairs. Failing
  probes are handed to Cline; design and repair stay Cline's.
- Cline files observed dirty at claim time (`routes/trinity.py`,
  `server.py`) are excluded by definition — probes don't touch them.
- If Cline starts U06 probes under the same name, this file loses: OpenCode
  deletes/renames on Cline's word. One writer per path, always.
- Probes use injected fakes + isolated stores only. No provider calls, no
  writes outside the new test file.
