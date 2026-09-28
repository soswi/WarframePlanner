# Contributing

Thanks for looking. This file covers how the code is organised, how to extend
it, and how changes reach a release. For what the application does, see the
[README](README.md).

## Setting up

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py --run-test-env
```

Working in `--run-test-env` keeps experiments away from your own planner.

## Code layout

```
main.py                    entry point
planner/
  config.py                where the app runs: bundled resources, user data
  defaults.py              what a fresh database contains
  models/                  plain records: task, definition, errors
  storage/                 persistence
    base.py                the Repository contract
    sqlite.py              the SQLite backend
    schema.py              tables and the schema version
    migrations.py          forward-only migration steps
  domain/                  business rules, independent of storage and transport
    planner.py             PlannerService, the facade the web layer uses
    tasks.py               lifecycle, ordering, duplication, recurrence resets
    dependencies.py        prerequisites, cycle detection, completion gate
    definitions.py         the editable vocabularies
    settings.py            typed settings access and validation
    recurrence.py          recurrence rules and their registry
    transfer.py            export and import
  presentation/            catalogues the user picks from but cannot author
    base.py  layouts.py  themes.py
  web/                     HTTP transport
    app.py                 application assembly
    schemas.py             request bodies
    routes/                one module per area
  runtime/
    server.py              launch modes, single-instance handover, shutdown
    environment.py         production and test environments, guarded cleanup
  static/
    index.html
    css/                   split by area, assembled by main.css with @import
    js/                    ES modules, entry point app.js
      core/                api, store, toast, html escaping
      ui/                  dropdown, tooltip, dot select, markdown renderer
      layouts/             base, registry, selection, table, board
      modals/              definitions dialog
smoke_test.py              end-to-end checks
```

## Principles

**Dependencies point one way.** `domain` knows the `Repository` interface,
`web` knows `domain`. The domain layer never sees HTTP, and nothing above
storage sees SQL.

**One entry point into the domain.** `PlannerService` composes the domain
services and every route goes through it, so the split behind it can change
without touching the routes.

**Every mutation returns the full state.** Endpoints respond with a complete
snapshot, so the client never reconciles a partial update against what it
holds.

**No build step.** The frontend is plain ES modules loaded from one
`<script type="module">`, and CSS is assembled with `@import`. What is in the
repository is what runs.

**The test environment never touches real data.** Anything in
`runtime/environment.py` that deletes files must keep every safety check in
`assert_safe_to_delete`.

## Style

- Python: PEP 8, type hints on every signature, Google-style docstrings on
  classes and public methods.
- Comments explain why, not what. If a comment restates the code, remove it.
- Everything in the codebase is in English.

## Extending

**A theme.** Subclass `Theme` in `presentation/themes.py`, fill in `tokens`,
register it in `default_themes()`. The token map reaches the client through
`/api/state` and becomes CSS custom properties, so no frontend change is
needed.

**A layout.** Subclass `Layout` in `js/layouts/`, implement `mount()` and
`render()`, register it with `LayoutRegistry` in `js/app.js`, and add a matching
subclass in `presentation/layouts.py` so the backend accepts its key.
`js/layouts/board.js` is the worked example. A layout receives a context with
`store`, `api`, `toast`, `selection`, `markdown`, `tooltip`, `commit()`,
`commitDelayed()`, `persist()` and `focusTask()`, and should reach for nothing
else.

**A recurrence rule.** One class in `domain/recurrence.py`:

```python
class MonthlyRule(RecurrenceRule):
    key = "Monthly"
    label = "First of the month at 01:00 UTC"

    def last_boundary(self, now):
        now = now.astimezone(timezone.utc)
        anchor = now.replace(day=1, hour=RESET_HOUR_UTC, minute=0, second=0, microsecond=0)
        return anchor if anchor <= now else (anchor - timedelta(days=1)).replace(day=1)
```

Register it in `default_registry()`. The client reads the list from the API, so
the dropdown updates by itself.

**A task field.** Add it to `Task` in `models/task.py` and to
`Task.EDITABLE_FIELDS`, add the column to `SCHEMA` in `storage/schema.py`, add a
migration step, and add a column descriptor in `TableLayout.buildColumns()`.
For data that does not need its own column, the `extra` JSON field takes it
without a schema change.

**Markdown syntax.** Push onto `MarkdownRenderer.inlineRules` in
`js/ui/markdown.js`, or add a branch in `renderBlocks()`. The renderer escapes
its input before any rule runs and emits only tags it builds itself; new rules
must never pass user text through unescaped.

**A storage backend.** Implement `Repository` from `storage/base.py` and change
the one line in `build_service()` in `runtime/server.py`.

## Migrations

Forward only. Bump `DB_SCHEMA_VERSION` in `storage/schema.py` and add an
idempotent step to `storage/migrations.py`.

When the shipped definitions change, add the outgoing palette to
`STOCK_PALETTES`. A migration replaces a palette only when it matches a shipped
one on both value and colour, so a list the user has touched is never
overwritten.

## Tests

```powershell
pip install httpx
python smoke_test.py
```

The JavaScript checks need `node` on the path and are skipped without it.

## Branches and releases

Work happens on short-lived branches off `dev`, named by kind:
`feat/…`, `fix/…`, `refactor/…`, `docs/…`. They merge into `dev` with
`--no-ff`.

Versions follow [Semantic Versioning](https://semver.org). The version changes
only when `dev` is merged into `main` for a release, and the number is decided
before that merge. Bump `__version__` in `planner/__init__.py` as its own commit
on `dev` first, so the tag points at code that declares the right version. The
build reads the same value to name the executable.

```powershell
git checkout main
git merge --no-ff dev -m "Merge dev: release X.Y.Z"
git tag -a vX.Y.Z -m "Warframe Planner X.Y.Z"
git push --follow-tags
pyinstaller WarframePlanner.spec
gh release create vX.Y.Z --title "Warframe Planner X.Y.Z" --notes-file notes.md dist\WarframePlanner-X.Y.Z.exe
```

Add `--prerelease` for anything not yet ready for general use.
