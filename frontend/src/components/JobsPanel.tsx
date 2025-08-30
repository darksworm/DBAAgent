import React, { useEffect, useState } from 'react';

type Job = {
  id: string;
  status: string;
  inserted: number;
  errors: number;
};

type JobGroup = {
  group_id: string;
  status: 'starting' | 'running' | 'completed' | 'failed' | 'canceled';
  inserted: number;
  errors: number;
  start_urls: string;
  count: number;
  jobs: Job[];
};

export function JobsPanel() {
  const [groups, setGroups] = useState<JobGroup[]>([]);
  const [loading, setLoading] = useState(false);

  const load = () => {
    setLoading(true);
    fetch('http://localhost:8000/api/jobs/groups')
      .then(r => r.json())
      .then(setGroups)
      .catch(() => setGroups([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, []);

  const stopGroup = async (gid: string) => {
    await fetch('http://localhost:8000/api/scrape/stop_group', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ group_id: gid }),
    }).catch(() => {});
    load();
  };

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-lg font-semibold">Jobs</h2>
        {loading && <span className="text-sm text-slate-500">Loading…</span>}
      </div>
      <div className="space-y-3">
        {groups.map(g => (
          <div key={g.group_id} className="border border-slate-200 dark:border-slate-800 rounded-lg p-3">
            <div className="flex items-center justify-between">
              <div className="font-medium">Group {g.group_id}</div>
              <div className="text-sm">{g.status} · {g.count} workers</div>
            </div>
            <div className="text-sm text-slate-600 dark:text-slate-300 mt-1 truncate">{g.start_urls}</div>
            <div className="mt-2 text-sm">Inserted: <span className="font-semibold">{g.inserted}</span> · Errors: {g.errors}</div>
            {g.status === 'running' && (
              <div className="mt-2">
                <button className="btn bg-red-600 hover:bg-red-500" onClick={() => stopGroup(g.group_id)}>Stop All</button>
              </div>
            )}
          </div>
        ))}
        {groups.length === 0 && <div className="text-sm text-slate-500">No jobs.</div>}
      </div>
    </div>
  );
}

