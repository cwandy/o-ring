# Notes for Claude Code

- Read `SPEC.md` at the start of every session. §13 (decisions) overrides earlier sections.
- Work phase by phase; stop at the end of each phase, summarise, and wait for approval.
- Never invent material data: unsure values are `placeholder` and go on the "DOĞRULANMALI" list.
- Code / identifiers / comments in English; UI text in Turkish via `src/oring_designer/i18n/tr.yaml`.
- Core (`src/oring_designer`, except `i18n`/`viz`) has no UI dependency; SI floats with unit suffixes.
- Run tests: `uv run pytest`. Run app: `uv run streamlit run app/streamlit_app.py`.
