// Task Manager - a simple, framework-free frontend.
// All requests go to a relative path (/api/...): to the same Nginx, which
// forwards them to the backend. The browser knows nothing about the internal network.

const STATUS_LABEL = { todo: "To do", in_progress: "In progress", done: "Done" };
const NEXT_STATUS = { todo: "in_progress", in_progress: "done", done: "todo" };
let currentFilter = "all";

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  // The frontend replica name comes from a header set by Nginx.
  const fe = res.headers.get("X-Frontend-Host");
  if (fe) document.getElementById("fe-host").textContent = fe;
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  if (data.served_by) document.getElementById("api-host").textContent = data.served_by;
  return data;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function loadTasks() {
  try {
    const data = await api("/api/tasks");
    const list = document.getElementById("tasks");
    const tasks = data.tasks.filter((t) => currentFilter === "all" || t.status === currentFilter);
    list.innerHTML = tasks
      .map(
        (t) => `
        <li class="task ${t.status}">
          <button class="status" data-id="${t.id}" data-next="${NEXT_STATUS[t.status]}"
                  title="Click to change the status">${STATUS_LABEL[t.status]}</button>
          <span class="title">${escapeHtml(t.title)}</span>
          <span class="meta">#${t.id} · created by: ${t.created_by.slice(0, 12)}</span>
          <button class="delete" data-id="${t.id}" title="Delete">✕</button>
        </li>`
      )
      .join("");
    document.getElementById("empty").hidden = tasks.length > 0;
  } catch (e) {
    document.getElementById("tasks").innerHTML = `<li class="error">Failed to load tasks: ${e.message}</li>`;
  }
}

async function loadInfo() {
  try {
    const info = await api("/api/info");
    document.getElementById("api-version").textContent = info.version;
    document.getElementById("db-status").textContent = info.db_ok ? "reachable ✔" : "NOT reachable ✖";
  } catch (e) {
    document.getElementById("db-status").textContent = "API not reachable";
  }
}

// 20 consecutive requests: count how many times each API replica answered.
async function probe() {
  const counts = {};
  for (let i = 0; i < 20; i++) {
    try {
      const info = await api("/api/info");
      counts[info.served_by] = (counts[info.served_by] || 0) + 1;
    } catch {
      counts["error"] = (counts["error"] || 0) + 1;
    }
  }
  document.getElementById("probe-result").innerHTML = Object.entries(counts)
    .map(([host, n]) => `<li><code>${escapeHtml(host)}</code>: ${n} requests</li>`)
    .join("");
}

document.getElementById("new-task").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.getElementById("title");
  const title = input.value.trim();
  if (!title) return;
  await api("/api/tasks", { method: "POST", body: JSON.stringify({ title }) });
  input.value = "";
  loadTasks();
});

document.getElementById("tasks").addEventListener("click", async (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  if (btn.classList.contains("status")) {
    await api(`/api/tasks/${btn.dataset.id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: btn.dataset.next }),
    });
  } else if (btn.classList.contains("delete")) {
    await api(`/api/tasks/${btn.dataset.id}`, { method: "DELETE" });
  }
  loadTasks();
});

document.querySelectorAll(".filters button").forEach((b) =>
  b.addEventListener("click", () => {
    document.querySelectorAll(".filters button").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    currentFilter = b.dataset.filter;
    loadTasks();
  })
);

document.getElementById("probe").addEventListener("click", probe);

loadTasks();
loadInfo();
