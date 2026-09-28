export class Api {
  async request(url, options = {}) {
    const response = await fetch(url, options);
    if (!response.ok) {
      let detail = response.statusText;
      try {
        detail = (await response.json()).detail || detail;
      } catch (_) { /* response carried no JSON body */ }
      throw new Error(detail);
    }
    return response.json();
  }

  json(url, method, body) {
    return this.request(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  state() { return this.request("/api/state"); }
  environment() { return this.request("/api/environment"); }
  createTask(changes) {
    return this.json("/api/tasks?at_top=true", "POST", changes ? { changes } : {});
  }
  updateTask(id, changes) { return this.json(`/api/tasks/${id}`, "PATCH", { changes }); }
  deleteTasks(ids) { return this.json("/api/tasks/delete", "POST", { ids }); }
  duplicateTasks(ids) { return this.json("/api/tasks/duplicate", "POST", { ids }); }
  shutdown() { return this.request("/api/shutdown", { method: "POST" }); }
  saveDefinitions(kind, entries) { return this.json("/api/definitions", "PUT", { kind, entries }); }
  saveSettings(settings) { return this.json("/api/settings", "PUT", { settings }); }

  importFile(file, merge) {
    const form = new FormData();
    form.append("file", file);
    return this.request(`/api/import?merge=${merge}`, { method: "POST", body: form });
  }
}

/** Snapshot holder with change notification. Layouts read from it, never write. */
