# Warframe Planner

A local browser application. FastAPI + SQLite backend, dependency-free frontend.
Everything stays on your disk: no network calls, no account, no cloud.

## Running from source

### Windows (PowerShell)

```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

If activation is blocked by the execution policy, run
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first. That affects
the current window only.

### Linux / macOS

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

The app picks a free port, prints the address and opens your default browser.
Closing the terminal stops the server.

The executable is built windowed. On Windows that means the process starts with
no stdout or stderr at all, so anything printed goes to `planner.log` beside the
database instead. If the browser does not open, the address is also in
`session.json` in the same folder (see the table below).

**One instance only.** Launching the executable again does not start a second
server: it finds the running one, opens a browser tab pointing at it, and exits.
Closing the tab leaves the process running. To actually stop it, use the red
quit button at the right of the toolbar.

### Test environment

```
python main.py --run-test-env
```

Runs the same application against a fresh, empty database, so you can see what
a first launch looks like. The banner shows a large `TEST ENV` marker; nothing
else differs.

The test environment is fully separate from your own data. It lives in the
system temp directory, keeps its own session record and prefers its own port
(8732, against 8731 for production), so it can run alongside a normal instance
without either noticing the other. Launching with the flag again returns to the
running test instance; launching without it always opens production.

The quit button deletes the test environment. Deletion is refused unless the
directory carries the test prefix, sits directly in the temp root, contains a
marker file written at creation, and does not overlap your data directory. A
test run killed rather than quit leaves its directory behind; the next
`--run-test-env` sweeps it away.

The flag works on the built executable too:
`WarframePlanner-0.2.0.exe --run-test-env`.

## Building the executable

```
pip install -r requirements-build.txt
pyinstaller WarframePlanner.spec
```

Output: `dist/WarframePlanner-<version>.exe` (or a bare binary on Linux/macOS),
for example `dist/WarframePlanner-0.0.0.exe`. The version comes from
`__version__` in `planner/__init__.py`, which the spec reads at build time, so a
release only needs that one line bumped.

The spec sets `console=False`; flip it to `True` if you need to see logs while
debugging.

PyInstaller only builds for the platform it runs on.

## Where the data lives

| Platform | Path                                                       |
|----------|------------------------------------------------------------|
| Windows  | `%APPDATA%\WarframePlanner\planner.db`                     |
| macOS    | `~/Library/Application Support/WarframePlanner/planner.db` |
| Linux    | `~/.local/share/WarframePlanner/planner.db`                |

The database survives replacing the executable. Set `WARFRAME_PLANNER_DATA` to
override the directory. For backups, copy `planner.db` or use **Export**.

## Features

- Task grid: ID, Activity, Category, Description, Priority, Status, Dependencies,
  Prereq Status, Last Updated, Recurrence
- New tasks land at the top; ids are assigned automatically from 1000
- Changing a status stamps `Last Updated` with today's date
- **Multiple dependencies per task.** Prereq Status resolves to `Ready`,
  `Blocked`, `Invalid ID` or `Self-reference`, and hovering it lists the blockers
- **Completion gate.** A task cannot be set to the completion status while any of
  its dependencies is still open. The rejection names the offending tasks and
  their current status. Turn it off under Definitions if you want to override it
- Cycle detection across the whole dependency graph, not just direct self-reference
- Status / Priority / Category values are editable in the UI **together with their
  colours**, so a new value is coloured everywhere immediately
- Recurrence: `One-off`, `Daily`, `Weekly`. Resets happen at 01:00 UTC and are
  computed in UTC, so behaviour is identical in every timezone. The last reset
  boundary is recorded, so a reset fires exactly once per window even after a
  long gap
- Two layouts, switchable from the tab strip under the toolbar and persisted
  per user:
  - **Table** — the full spreadsheet-style grid
  - **Board** — cards showing title, description and an editable status. Group by
    status, priority, category, recurrence or nothing; drag a card between
    columns to write that field; card size is a density control that drives
    padding, title size, description height and column width together. Each card has a jump button that switches to the table and highlights
    the row
- Five dark themes, persisted per user: **Zariman** (neutral greys with
  sea-green accents, the default), **Orokin**, **Corpus**, **Grineer** and
  **Infested**. A theme removed by an update silently falls back to the default
  instead of leaving the app unstyled
- JSON export and import, in replace or merge mode. Merging renumbers colliding
  ids and rewrites every dependency reference accordingly
- A quit button that shuts the process down from the page, since closing the tab
  does not stop the server
- Sorting, text filter, multi-row selection, duplicate and delete. A duplicate
  keeps every field and the dependency list, clears status and Last Updated,
  and lands directly below its source
- **Descriptions support Markdown**: headings, bullet and ordered lists,
  blockquotes, fenced and inline code, horizontal rules, bold, italic,
  strikethrough and links. The cell shows the rendered result clamped to two
  lines; the hover tooltip shows all of it. Click to edit the raw source
- Custom tooltips that reveal clipped values on hover. They appear only when the
  text actually does not fit, measured against the cell's own font, so cells that
  already show everything stay quiet. Dependency chips and Prereq Status always
  show one, since their detail is never rendered inline

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
smoke_test.py              end-to-end API tests
```

Dependencies point one way only: `domain` knows the `Repository` interface,
`web` knows `domain`, and neither knows about HTTP or SQL respectively.
`PlannerService` composes the domain services and is the single entry point, so
the split behind it can change without touching the routes.

The frontend loads as ES modules from a single `<script type="module">`, so
imports are explicit and nothing depends on the order of script tags.

Run the tests with `python smoke_test.py` (needs `pip install httpx`; the
JavaScript checks are skipped when `node` is absent).

## Extending

**A new theme.** Subclass `Theme` in `presentation/themes.py`, fill in
`tokens`, register it in `default_themes()`. The frontend receives the token map from `/api/state`
and writes it onto `:root` as CSS custom properties, so no frontend change is
needed. Users select themes; they cannot author them.

**A new layout.** Subclass `Layout`, implement `mount()` and `render()`, register
it with `LayoutRegistry` in `js/app.js`, and add a matching subclass in
`presentation/layouts.py` so the backend accepts the key. `js/layouts/board.js`
is the worked example.

The layout receives a context with `store`, `api`, `toast`, `selection`,
`markdown`, `tooltip`, `commit()`, `persist()` and `focusTask()`, so it never
reaches into the app. View preferences belong in settings via `persist()`, the
way the board stores `board_group_by` and `board_card_size`.

The layout picker in the toolbar hides itself while only one layout is registered
and appears automatically with the second.

**A new recurrence.** One class in `domain/recurrence.py`:

```python
class MonthlyRule(RecurrenceRule):
    key = "Monthly"
    label = "First of the month at 01:00 UTC"

    def last_boundary(self, now):
        now = now.astimezone(timezone.utc)
        anchor = now.replace(day=1, hour=RESET_HOUR_UTC, minute=0, second=0, microsecond=0)
        return anchor if anchor <= now else (anchor - timedelta(days=1)).replace(day=1)
```

Add it to `default_registry()`; the dropdown updates itself.

**A new task field.** Add it to `Task` in `models/task.py`, to
`Task.EDITABLE_FIELDS`, to `SCHEMA` in `storage/schema.py`, add a step in
`storage/migrations.py`, and add a column descriptor in
`TableLayout.buildColumns()`. The `extra` JSON field takes ad-hoc data without
any schema change.

**More Markdown syntax.** Push onto `MarkdownRenderer.inlineRules` in
`js/ui/markdown.js` for span-level
syntax, or add a branch in `renderBlocks()` for block-level. The renderer escapes
its input before any rule runs and only emits tags it builds itself, so raw HTML
in a description is inert and link targets are scheme-checked. Keep new rules
inside that model: never pass user text through unescaped.

**A tooltip somewhere new.** Put `data-tooltip="full text"` on any element; the
controller finds it through event delegation. Add `data-tooltip-always` when the
text is supplementary rather than a clipped copy of what is already on screen,
and `data-tooltip-format="markdown"` to render it through a formatter registered
on the controller.

**A different storage backend.** Implement `Repository` from `storage/base.py`
and change the one line in `build_service()` in `runtime/server.py`.

## Licence

MIT; see `LICENSE`. Third-party components, including two interface patterns
adapted from Uiverse and every packaged runtime dependency, are listed in
`THIRD-PARTY-NOTICES.md`.

Warframe is a trademark of Digital Extremes Ltd. This is an unofficial fan-made
tool, not affiliated with or endorsed by Digital Extremes.

## Limitations

- A windowed build has no console. Startup problems land in `planner.log`; there
  is nowhere else for them to go.
- Single-instance detection reads `session.json` and verifies the address over
  HTTP before reusing it, so a file left behind by a crash is discarded rather
  than trusted. Two executables launched in the same second can still both
  start; the second one takes a different port. The server binds `127.0.0.1` only, but two processes
  would write to the same database.
- Migrations are forward-only and there is no downgrade path. Opening a newer
  database with an older build will fail.
- The category migrations replace the stock list only when it is untouched.
  If you had edited it, your categories are kept and the new list is not applied;
  add the entries you want under Definitions.
- Tasks holding a category that no longer exists keep the value. The board shows
  it in a column marked `(undefined)` rather than hiding the task.
- Recurrence resets run at startup and on every page load. A closed app resets
  nothing; it catches up on the next launch.
