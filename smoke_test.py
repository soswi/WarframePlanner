"""End-to-end checks against the real API surface."""
import json
import os
import sys
import socket
import sqlite3
import tempfile

os.environ["WARFRAME_PLANNER_DATA"] = tempfile.mkdtemp()

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from planner.api import create_app
from planner.config import database_path
from planner.repository import SqliteRepository
from planner.service import PlannerService

service = PlannerService(SqliteRepository(database_path()))
client = TestClient(create_app(service))

state = client.get("/api/state").json()
assert state["tasks"] == []
assert [d["value"] for d in state["definitions"]["status"]] == ["Done", "In Progress", "Stuck"]
category_colours = {d["value"]: d["color"] for d in state["definitions"]["category"]}
assert category_colours["Credits"] == "#0f97ff"
assert category_colours["Platinum"] == "#c7eeff"
assert [d["value"] for d in state["definitions"]["category"]][-2:] == ["Kuva", "Grind"]
assert len(state["definitions"]["category"]) == 14
assert [d["value"] for d in state["definitions"]["priority"]] == [
    "High", "Medium", "Low", "Very High"]
assert [d["value"] for d in state["definitions"]["status"]] == ["Done", "In Progress", "Stuck"]
assert [r["key"] for r in state["recurrence"]] == ["One-off", "Daily", "Weekly"]
assert [t["key"] for t in state["themes"]] == ["zariman", "orokin", "corpus",
                                              "grineer", "infested"]
assert [l["key"] for l in state["layouts"]] == ["table", "board"]
assert all("tokens" in t and t["tokens"]["bg"] for t in state["themes"])
print(" 1. empty state, definitions, recurrence, themes, layouts: OK")

client.post("/api/tasks")
client.post("/api/tasks")
r = client.post("/api/tasks").json()
assert [t["id"] for t in r["tasks"]] == [1002, 1001, 1000]
print(" 2. newest task on top, ids from 1000: OK")

r = client.patch("/api/tasks/1002", json={"changes": {"dependencies": [1000, 1001]}}).json()
task = next(t for t in r["tasks"] if t["id"] == 1002)
assert task["dependencies"] == [1000, 1001]
assert task["prereq_status"] == "Blocked"
assert task["blocked_by"] == [1000, 1001]
print(" 3. multiple dependencies, Blocked while open: OK")

resp = client.patch("/api/tasks/1002", json={"changes": {"status": "Done"}})
assert resp.status_code == 400
assert "1000" in resp.json()["detail"] and "1001" in resp.json()["detail"]
assert next(t for t in service.list_tasks() if t["id"] == 1002)["status"] == ""
print(" 4. completion blocked while any dependency is open: OK")

client.patch("/api/tasks/1000", json={"changes": {"status": "Done"}})
resp = client.patch("/api/tasks/1002", json={"changes": {"status": "Done"}})
assert resp.status_code == 400, "one dependency still open"
r = client.patch("/api/tasks/1001", json={"changes": {"status": "Done"}}).json()
assert next(t for t in r["tasks"] if t["id"] == 1002)["prereq_status"] == "Ready"
r = client.patch("/api/tasks/1002", json={"changes": {"status": "Done"}}).json()
task = next(t for t in r["tasks"] if t["id"] == 1002)
assert task["status"] == "Done"
assert task["last_updated"] == datetime.now().date().isoformat()
print(" 5. completion allowed once every dependency is Done: OK")

client.put("/api/settings", json={"settings": {"enforce_dependency_gate": "false"}})
client.patch("/api/tasks/1000", json={"changes": {"status": "Stuck"}})
assert client.patch("/api/tasks/1002", json={"changes": {"status": "Done"}}).status_code == 200
client.put("/api/settings", json={"settings": {"enforce_dependency_gate": "true"}})
client.patch("/api/tasks/1000", json={"changes": {"status": "Done"}})
print(" 6. gate can be switched off in settings: OK")

assert client.patch("/api/tasks/1002", json={"changes": {"dependencies": [1002]}}).status_code == 400
assert client.patch("/api/tasks/1000", json={"changes": {"dependencies": [1002]}}).status_code == 400
assert client.patch("/api/tasks/1002", json={"changes": {"dependencies": [4242]}}).status_code == 400
assert client.patch("/api/tasks/1002", json={"changes": {"recurrence": "Yearly"}}).status_code == 400
assert client.put("/api/settings", json={"settings": {"theme": "nope"}}).status_code == 400
assert client.put("/api/settings", json={"settings": {"layout": "nope"}}).status_code == 400
print(" 7. rejects self-ref, cycles, unknown ids/recurrence/theme/layout: OK")

client.put("/api/settings", json={"settings": {"theme": "corpus"}})
assert client.get("/api/state").json()["settings"]["theme"] == "corpus"
# A theme removed by an update must degrade to the default, not stick around.
service.repo.set_setting("theme", "midnight")
assert client.get("/api/state").json()["settings"]["theme"] == "zariman"
print(" 8. theme selection persists, unknown theme falls back: OK")

client.patch("/api/tasks/1000", json={"changes": {"recurrence": "Weekly"}})
service.repo.set_setting("reset_marker:Weekly", "stale")
service.repo.set_setting("reset_marker:Daily", "stale")
assert service.apply_recurrence_resets() == 1
assert next(t for t in service.list_tasks() if t["id"] == 1000)["status"] == "In Progress"
assert service.apply_recurrence_resets() == 0
print(" 9. weekly reset fires once per window: OK")

from planner.recurrence import WeeklyRule
weekly = WeeklyRule()
probe = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
assert weekly.last_boundary(probe) == datetime(2026, 9, 7, 1, 0, tzinfo=timezone.utc)
assert weekly.last_boundary(datetime(2026, 9, 7, 0, 30, tzinfo=timezone.utc)) == \
       datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc)
assert weekly.last_boundary(probe.astimezone(timezone(timedelta(hours=9)))) == \
       datetime(2026, 9, 7, 1, 0, tzinfo=timezone.utc)
print("10. Monday 01:00 UTC boundary is timezone independent: OK")

payload = client.get("/api/export").json()
assert payload["schema_version"] == 2 and len(payload["tasks"]) == 3
files = {"file": ("dump.json", json.dumps(payload), "application/json")}
merged = client.post("/api/import?merge=true", files=files).json()
ids = sorted(t["id"] for t in merged["tasks"])
assert len(ids) == 6 and len(set(ids)) == 6
clone = next(t for t in merged["tasks"] if t["id"] > 1002 and t["dependencies"])
assert all(d > 1002 for d in clone["dependencies"]), clone
assert len(clone["dependencies"]) == 2
print("11. merge import renumbers ids and rewrites every dependency: OK")

r = client.post("/api/tasks/delete", json={"ids": [d for d in clone["dependencies"]]}).json()
survivor = next(t for t in r["tasks"] if t["id"] == clone["id"])
assert survivor["dependencies"] == [] and survivor["prereq_status"] == "Ready"
print("12. deleting a task strips it from dependency lists: OK")

legacy = os.path.join(tempfile.mkdtemp(), "legacy.db")
conn = sqlite3.connect(legacy)
conn.executescript("""
CREATE TABLE tasks (id INTEGER PRIMARY KEY, activity TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
  priority TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT '',
  dependency INTEGER, recurrence TEXT NOT NULL DEFAULT 'One-off', last_updated TEXT,
  position INTEGER NOT NULL DEFAULT 0, extra TEXT NOT NULL DEFAULT '{}');
CREATE TABLE definitions (kind TEXT NOT NULL, value TEXT NOT NULL,
  color TEXT NOT NULL DEFAULT '#94a3b8', position INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (kind, value));
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO tasks (id, activity, dependency) VALUES (1000, 'root', NULL), (1001, 'child', 1000);
PRAGMA user_version = 1;
""")
conn.commit()
conn.close()

from pathlib import Path
migrated = SqliteRepository(Path(legacy))
tasks = {t.id: t for t in migrated.list_tasks()}
assert tasks[1000].dependencies == [] and tasks[1001].dependencies == [1000], tasks
from planner.repository import DB_SCHEMA_VERSION
assert sqlite3.connect(legacy).execute("PRAGMA user_version").fetchone()[0] \
       == DB_SCHEMA_VERSION
SqliteRepository(Path(legacy))  # rerunning the migration must be a no-op
assert {t.id: t.dependencies for t in migrated.list_tasks()}[1001] == [1000]
print("13. v1 database migrates to multi-dependency schema, idempotently: OK")

def legacy_v2(definitions):
    """Build a v2 database carrying the given {kind: {value: colour}} palettes."""
    path = os.path.join(tempfile.mkdtemp(), "v2.db")
    conn = sqlite3.connect(path)
    conn.executescript("""
    CREATE TABLE tasks (id INTEGER PRIMARY KEY, activity TEXT NOT NULL DEFAULT '',
      category TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
      priority TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT '',
      dependencies TEXT NOT NULL DEFAULT '[]', recurrence TEXT NOT NULL DEFAULT 'One-off',
      last_updated TEXT, position INTEGER NOT NULL DEFAULT 0, extra TEXT NOT NULL DEFAULT '{}');
    CREATE TABLE definitions (kind TEXT NOT NULL, value TEXT NOT NULL,
      color TEXT NOT NULL DEFAULT '#94a3b8', position INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (kind, value));
    CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    PRAGMA user_version = 2;
    """)
    for kind, palette in definitions.items():
        for pos, (value, color) in enumerate(palette.items()):
            conn.execute(
                "INSERT INTO definitions (kind, value, color, position) VALUES (?,?,?,?)",
                (kind, value, color, pos))
    conn.commit()
    conn.close()
    return Path(path)


def palette_after_migration(path, kind):
    repo = SqliteRepository(path)
    return {d.value: d.color for d in repo.list_definitions() if d.kind == kind}


from planner.config import DEFAULT_DEFINITIONS
from planner.repository import STOCK_PALETTES

# Every palette ever shipped must be recognised and refreshed.
for kind, shipped_sets in STOCK_PALETTES.items():
    expected = dict(DEFAULT_DEFINITIONS[kind])
    for shipped in shipped_sets:
        got = palette_after_migration(legacy_v2({kind: shipped}), kind)
        assert got == expected, (kind, got)

# Same names, one recoloured entry: touched, so it must survive untouched.
recoloured = dict(STOCK_PALETTES["status"][0])
recoloured["Done"] = "#123456"
got = palette_after_migration(legacy_v2({"status": recoloured}), "status")
assert got == recoloured, got

# A renamed entry is equally a customisation.
custom = {"My own": "#ffffff", "Second one": "#000000"}
got = palette_after_migration(legacy_v2({"category": custom}), "category")
assert got == custom, got

# Kinds are judged independently: a customised status must not freeze categories.
mixed = legacy_v2({"status": recoloured, "category": STOCK_PALETTES["category"][0]})
repo = SqliteRepository(mixed)
by_kind = {}
for d in repo.list_definitions():
    by_kind.setdefault(d.kind, {})[d.value] = d.color
assert by_kind["status"] == recoloured
assert by_kind["category"] == dict(DEFAULT_DEFINITIONS["category"])

print("13b. every shipped palette refreshes; any customised one is kept: OK")

import subprocess, shutil
if shutil.which("node"):
    harness = """
const fs=require("fs"),vm=require("vm");
const sb={window:{},document:{addEventListener(){}}};sb.globalThis=sb;vm.createContext(sb);
for(const f of ["markdown.js","tooltip.js","themes.js","layouts.js","board.js","app.js"])
  vm.runInContext(fs.readFileSync("planner/static/"+f,"utf8"),sb,{filename:f});
if(!sb.window.PlannerThemes||!sb.window.PlannerLayouts||!sb.window.PlannerTooltip
   ||!sb.window.PlannerMarkdown)
  throw new Error("missing namespace");
"""
    subprocess.run(["node", "-e", harness], check=True)
    print("14. the six scripts coexist in one global scope: OK")
else:
    print("14. script-collision check skipped (node not installed)")

if shutil.which("node"):
    markdown_checks = """
const fs=require("fs"),vm=require("vm");
const sb={window:{},document:{addEventListener(){},createElement:()=>({getContext:()=>({font:"",
  measureText:t=>({width:t.length*7})})})}};
sb.globalThis=sb;vm.createContext(sb);
for(const f of ["markdown.js","tooltip.js"])
  vm.runInContext(fs.readFileSync("planner/static/"+f,"utf8"),sb,{filename:f});
const md=new sb.window.PlannerMarkdown.MarkdownRenderer();
const eq=(got,want,label)=>{ if(got!==want) throw new Error(label+"\\n got: "+got+"\\nwant: "+want); };

eq(md.render("**b** and *i*"),"<p><strong>b</strong> and <em>i</em></p>","inline emphasis");
eq(md.render("- a\\n- b"),"<ul><li>a</li><li>b</li></ul>","bullet list");
eq(md.render("1. a\\n2. b"),"<ol><li>a</li><li>b</li></ol>","ordered list");
eq(md.render("## H"),'<h4 class="md-h">H</h4>',"heading");

// Raw HTML must survive only as inert text.
if(md.render("<script>alert(1)</script>").includes("<script"))
  throw new Error("script tag not escaped");
if(md.render("<img src=x onerror=alert(1)>").includes("<img"))
  throw new Error("img tag not escaped");
if(md.render("[x](javascript:alert(1))").includes("<a "))
  throw new Error("javascript: link was rendered");
if(md.render("`**x**`").includes("<strong>"))
  throw new Error("inline rules leaked into code span");

// Clamp detection must not trust scrollHeight, which lies for -webkit-line-clamp.
const tip=new sb.window.PlannerTooltip.TooltipController();
sb.window.getComputedStyle=()=>({webkitLineClamp:"2",paddingLeft:"7px",paddingRight:"7px",
  borderLeftWidth:"0px",borderRightWidth:"0px",font:"12px Inter"});
const cell={tagName:"DIV",clientWidth:300,clientHeight:40,scrollHeight:40};
if(tip.isClipped(cell,"Run Hepit")) throw new Error("short text flagged as clipped");
if(!tip.isClipped(cell,"Run Apollo Lua Disruption rotation B and C with Nekros or Khora, "+
  "then radshare the relic in recruit chat until the Prime Chassis drops"))
  throw new Error("long text not flagged as clipped");
"""
    subprocess.run(["node", "-e", markdown_checks], check=True)
    print("15. markdown rendering, HTML escaping and clamp detection: OK")
else:
    print("15. markdown checks skipped (node not installed)")

assert client.put("/api/settings", json={"settings": {"layout": "board"}}).status_code == 200
assert client.get("/api/state").json()["settings"]["layout"] == "board"
client.put("/api/settings", json={"settings": {"board_group_by": "priority",
                                               "board_card_size": "roomy"}})
saved = client.get("/api/state").json()["settings"]
assert saved["board_group_by"] == "priority" and saved["board_card_size"] == "roomy"
client.put("/api/settings", json={"settings": {"layout": "table"}})
print("16. board layout accepted and its view settings persist: OK")

before = {t["id"] for t in client.get("/api/state").json()["tasks"]}
source = sorted(before)[0]
client.patch(f"/api/tasks/{source}", json={"changes": {
    "activity": "Farm relics", "description": "notes", "priority": "High",
    "category": "Credits", "recurrence": "Weekly"}})
snap = client.post("/api/tasks/duplicate", json={"ids": [source]}).json()
created = [t for t in snap["tasks"] if t["id"] not in before]
assert len(created) == 1, created
copy = created[0]
original = next(t for t in snap["tasks"] if t["id"] == source)
assert copy["activity"] == "Farm relics (copy)"
assert copy["description"] == "notes" and copy["priority"] == "High"
assert copy["category"] == "Credits" and copy["recurrence"] == "Weekly"
assert copy["dependencies"] == original["dependencies"]
# A copy has not been worked on, so it starts with no status and no timestamp.
assert copy["status"] == "" and copy["last_updated"] is None
order = [t["id"] for t in snap["tasks"]]
assert order.index(copy["id"]) == order.index(source) + 1, order
assert client.post("/api/tasks/duplicate", json={"ids": [999999]}).status_code == 200
client.post("/api/tasks/delete", json={"ids": [copy["id"]]})
print("17. duplicating copies every field, clears status, lands below source: OK")

if shutil.which("node"):
    board_checks = """
const fs=require("fs"),vm=require("vm");
function el(){return {classList:{add(){},remove(){},toggle(){}},dataset:{},style:{},innerHTML:"",
  value:"",textContent:"",hidden:false,addEventListener(){},querySelector:()=>el(),
  querySelectorAll:()=>[],appendChild(){}};}
const sb={window:{},document:{addEventListener(){},body:el(),createElement:(t)=>t==="canvas"
  ?{getContext:()=>({font:"",measureText:s=>({width:s.length*7})})}:el()}};
sb.globalThis=sb;vm.createContext(sb);
for(const f of ["markdown.js","tooltip.js","themes.js","layouts.js","board.js","app.js"])
  vm.runInContext(fs.readFileSync("planner/static/"+f,"utf8"),sb,{filename:f});

const L=sb.window.PlannerLayouts;
const reg=new L.LayoutRegistry("table");
reg.register(L.TableLayout); reg.register(L.BoardLayout);
if(reg.list().length!==2) throw new Error("both layouts must register");

const store={
  tasks:[{id:1,activity:"A",status:"Done",priority:"High",category:"Foundry",recurrence:"Weekly"},
         {id:2,activity:"B",status:"Stuck",priority:"High",category:"",recurrence:"One-off"},
         {id:3,activity:"C",status:"",priority:"Low",category:"Ghost",recurrence:"One-off"}],
  definitions:{status:[{value:"Done"},{value:"In Progress"},{value:"Stuck"}],
               priority:[{value:"High"},{value:"Low"}],category:[{value:"Foundry"}]},
  recurrence:[{key:"One-off"},{key:"Weekly"}],settings:{},
  valuesFor(k){return (this.definitions[k]||[]).map(d=>d.value);},colorFor(){return null;}};
const b=new L.BoardLayout({store,markdown:new sb.window.PlannerMarkdown.MarkdownRenderer(),
  selection:{has:()=>false},commit(){},persist(){}});
const shape=()=>b.buildColumns(b.visibleTasks()).map(c=>c.label+":"+c.tasks.length).join(",");

b.groupBy="status";
if(shape()!=="Done:1,In Progress:0,Stuck:1,Unset:1")
  throw new Error("status grouping keeps empty columns and an Unset bucket: "+shape());
b.groupBy="category";
if(shape()!=="Foundry:1,Ghost (undefined):1,Unset:1")
  throw new Error("orphaned value needs its own column: "+shape());
b.groupBy="recurrence";
if(shape()!=="One-off:2,Weekly:1") throw new Error("recurrence grouping: "+shape());
if(!b.canDrag()) throw new Error("drag must be on while grouped");
b.groupBy="\\u0000none";
if(shape()!=="All tasks:3") throw new Error("ungrouped board is one bucket: "+shape());
"""
    subprocess.run(["node", "-e", board_checks], check=True)
    print("18. board grouping across every axis: OK")
else:
    print("18. board grouping checks skipped (node not installed)")

for path in ("/", "/static/app.js", "/static/layouts.js", "/static/themes.js",
             "/static/tooltip.js", "/static/markdown.js", "/static/board.js",
             "/static/styles.css"):
    assert client.get(path).status_code == 200, path
print("19. frontend assets served: OK")

html = client.get("/").text
required = ["btnAdd", "btnDuplicate", "btnDelete", "btnExport", "btnImport", "btnDefs"]
for element_id in required:
    assert f'id="{element_id}"' in html, element_id
    # Every icon-only control needs a tooltip and a label, or it is unreadable.
    block = html.split(f'id="{element_id}"')[1].split("</button>")[0]
    assert "data-tooltip=" in block, element_id
    assert "aria-label=" in html.split(f'id="{element_id}"')[0].rsplit("<button", 1)[1] \
        or "aria-label=" in block, element_id
    assert "<svg" in block, element_id
assert 'id="layoutTabs"' in html
print("20. every toolbar action is an icon with a tooltip and a label: OK")

# A windowed PyInstaller build on Windows starts with sys.stdout and sys.stderr
# set to None. Uvicorn's default logging config inspects them and dies before
# the server exists, so both the guard and the log_config bypass must hold.
import uvicorn
from planner.app import ensure_streams

real_out, real_err = sys.stdout, sys.stderr
try:
    sys.stdout = None
    try:
        uvicorn.Config(app=lambda *a: None, host="127.0.0.1", port=1)
        raise AssertionError("expected uvicorn's default log config to fail without stdout")
    except ValueError:
        pass
    uvicorn.Config(app=lambda *a: None, host="127.0.0.1", port=1, log_config=None)

    sys.stdout = None
    sys.stderr = None
    log_path = ensure_streams()
    assert sys.stdout is not None and sys.stderr is not None
    assert log_path and log_path.endswith("planner.log")
    print("probe", file=sys.stdout)
finally:
    sys.stdout, sys.stderr = real_out, real_err

assert Path(log_path).read_text(encoding="utf-8").strip().endswith("probe")
print("21. starts with no stdout/stderr, as a windowed build does: OK")

import http.server
import json as _json
import threading as _threading
from planner import app as app_module

assert app_module.probe_running_instance() is None, "no session file means no instance"

app_module.session_file().write_text("not json at all", encoding="utf-8")
assert app_module.probe_running_instance() is None, "a corrupt session file must be ignored"

# A crash leaves the file behind pointing at a port nobody is listening on.
# Reusing it would strand the user with an app that never opens.
with socket.socket() as probe:
    probe.bind(("127.0.0.1", 0))
    dead_port = probe.getsockname()[1]
app_module.write_session(f"http://127.0.0.1:{dead_port}/", dead_port)
assert app_module.probe_running_instance() is None, "a stale session file must be ignored"
assert not app_module.session_file().exists(), "a stale session file must be removed"


class Foreign(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = _json.dumps({"app": "something-else"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


foreign = http.server.HTTPServer(("127.0.0.1", 0), Foreign)
_threading.Thread(target=foreign.serve_forever, daemon=True).start()
foreign_port = foreign.server_address[1]
app_module.write_session(f"http://127.0.0.1:{foreign_port}/", foreign_port)
# Something answers, but it is not us. Handing the browser to it would be worse
# than starting fresh.
assert app_module.probe_running_instance() is None, "a foreign server must not be adopted"
foreign.shutdown()
app_module.clear_session()
print("22. instance probe rejects missing, corrupt, stale and foreign sessions: OK")

html = client.get("/").text
assert 'id="btnQuit"' in html and 'id="curtain"' in html
quit_block = html.split('id="btnQuit"')[1].split("</button>")[0]
assert "data-tooltip=" in quit_block and "<svg" in quit_block
assert client.post("/api/shutdown").status_code == 400, \
    "a build with no shutdown hook must say so rather than pretend"
ping = client.get("/api/ping").json()
assert ping["app"] == "warframe-planner" and isinstance(ping["pid"], int)
print("23. quit control present, ping identifies the app, shutdown needs a hook: OK")

# Reordering in the modal is DOM-only; the order is persisted by the ordinary
# save, so the API must honour the sequence it is handed.
reordered = [
    {"value": "Very High", "color": "#ec4657"},
    {"value": "High", "color": "#fda817"},
    {"value": "Low", "color": "#9ac4fe"},
    {"value": "Medium", "color": "#ffc370"},
]
snap = client.put("/api/definitions",
                  json={"kind": "priority", "entries": reordered}).json()
assert [d["value"] for d in snap["definitions"]["priority"]] == \
    ["Very High", "High", "Low", "Medium"]
assert [d["position"] for d in snap["definitions"]["priority"]] == [0, 1, 2, 3]
# Order must survive a round trip, not just the response that wrote it.
again = client.get("/api/state").json()["definitions"]["priority"]
assert [d["value"] for d in again] == ["Very High", "High", "Low", "Medium"]
client.put("/api/definitions", json={"kind": "priority", "entries": [
    {"value": v, "color": c} for v, c in DEFAULT_DEFINITIONS["priority"]]})

html = client.get("/").text
assert "def-grip" not in html, "the grip is rendered by app.js, not baked into the page"
grip_js = client.get("/static/app.js").text
assert "def-grip" in grip_js and 'draggable="true"' in grip_js
assert "rowAfterPointer" in grip_js and "bindReordering" in grip_js
print("24. definition order is persisted and the drag handle is wired: OK")

print("\nALL TESTS PASSED")
