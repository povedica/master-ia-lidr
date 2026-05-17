# Estimation prompt bundle v2

Edit templates here only. After changes, run from repo root:

```bash
./scripts/sync-estimation-prompt-v1-from-v2.sh
```

## Layout

- `system.j2` / `user.j2` / `examples.j2` — main LLM prompts
- `partials/guided_request.md.j2` — guided form Markdown body
- `partials/assessment_surface.md.j2` — narrow guardrail/mode surface (no section headers)
- `partials/modes/*.md.j2` — per-mode system instructions
- `partials/preprocessing/` — inline cleaning and two-phase extraction system text

Use Jinja conditionals on context **flags** from Python (`has_attachments`, `has_out_of_scope`, etc.). Do not embed business rules as Python string concatenation.

## Assessment surface

Keep `assessment_surface.md.j2` free of Spanish `##` section titles so keyword heuristics in `estimation_engine` stay aligned with user-authored text.
