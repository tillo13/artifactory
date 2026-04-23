// Template artifact for Artifactory. Copy this into Claude (after pasting
// the preamble) and ask Claude to iterate on it. Submit the result at /submit.
//
// This example is a minimal kanban — shows fetch, useState, useEffect,
// window.CURRENT_USER, and a PATCH call. Good starting point for any view.

function App() {
  const [tasks, setTasks] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const me = window.CURRENT_USER;

  React.useEffect(() => {
    fetch('/api/v1/tasks')
      .then(r => r.json())
      .then(data => { setTasks(data); setLoading(false); });
  }, []);

  const moveTask = (id, newColumn) => {
    fetch(`/api/v1/tasks/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ column_name: newColumn }),
    }).then(r => r.json()).then(updated => {
      setTasks(ts => ts.map(t => t.id === id ? updated : t));
    });
  };

  const columns = [
    { key: 'todo',       title: 'To Do',       color: 'bg-slate-100' },
    { key: 'sourcing',   title: 'Sourcing',    color: 'bg-amber-100' },
    { key: 'inprogress', title: 'In Progress', color: 'bg-blue-100' },
    { key: 'blocked',    title: 'Blocked',     color: 'bg-red-100' },
    { key: 'done',       title: 'Done',        color: 'bg-emerald-100' },
  ];

  if (loading) return <div className="p-12 text-center text-slate-500">Loading…</div>;

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">
          Hey {me.name} — here's the build
        </h1>
        <p className="text-sm text-slate-500">
          Role: {me.role} · {tasks.length} total tasks
        </p>
      </header>

      <div className="grid grid-cols-5 gap-3">
        {columns.map(col => (
          <div key={col.key} className={`${col.color} rounded-lg p-3 min-h-[400px]`}>
            <h2 className="font-semibold text-sm mb-3 text-slate-700">{col.title}</h2>
            {tasks.filter(t => t.column_name === col.key).map(t => (
              <div key={t.id} className="bg-white rounded p-3 mb-2 shadow-sm">
                <div className="text-sm font-medium text-slate-900">{t.title}</div>
                {t.tag && <div className="text-xs text-slate-500 mt-1">{t.tag}</div>}
                {t.assigned_role && (
                  <div className="text-xs text-slate-400 mt-1">→ {t.assigned_role}</div>
                )}
                <div className="flex gap-1 mt-2">
                  {columns.map(c => (
                    c.key !== col.key && (
                      <button key={c.key}
                              onClick={() => moveTask(t.id, c.key)}
                              className="text-xs text-slate-400 hover:text-slate-900">
                        → {c.title}
                      </button>
                    )
                  ))}
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
