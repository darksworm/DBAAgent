import React, { useEffect, useState } from 'react';

type Schedule = {
  id: number;
  name: string;
  urls: string;
  cadence_minutes: number;
  max_pages?: number | null;
  workers?: number | null;
  concurrency?: number | null;
  newest_first: boolean;
  enabled: boolean;
  last_run?: string | null;
  last_pub_ts?: string | null;
};

export function SchedulesPanel() {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [running, setRunning] = useState<number[]>([]);

  const load = () => {
    fetch('http://localhost:8000/api/schedules')
      .then(r => r.json())
      .then(({ schedules, running }) => { setSchedules(schedules); setRunning(running || []); })
      .catch(() => { setSchedules([]); setRunning([]); });
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, []);

  const toggle = async (sid: number, enabled: boolean) => {
    await fetch('http://localhost:8000/api/schedules/toggle', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sid, enabled })
    }).catch(() => {});
    load();
  };

  const runNow = async (sid: number) => {
    await fetch('http://localhost:8000/api/schedules/run', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sid })
    }).catch(() => {});
    load();
  };

  const del = async (sid: number) => {
    if (!confirm('Delete this schedule?')) return;
    await fetch('http://localhost:8000/api/schedules/delete', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sid })
    }).catch(() => {});
    load();
  };

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-lg font-semibold">Schedules</h2>
      </div>
      <div className="space-y-2">
        {schedules.map(s => {
          const isRunning = running.includes(s.id);
          return (
            <div key={s.id} className="border border-slate-200 dark:border-slate-800 rounded-lg p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="font-medium">{s.name}</div>
                <div className="text-sm">every {s.cadence_minutes}m · pages: {s.max_pages ?? '∞'} · workers: {s.workers ?? 1} · conc: {s.concurrency ?? 'default'} · newest: {s.newest_first ? 'yes' : 'no'}</div>
              </div>
              <div className="text-sm text-slate-600 dark:text-slate-300 mt-1 truncate">{s.urls}</div>
              <div className="text-xs text-slate-500">last: {s.last_run || 'never'} · watermark: {s.last_pub_ts || 'none'}</div>
              <div className="flex items-center gap-2 mt-2">
                <button className="btn" disabled={isRunning} onClick={() => runNow(s.id)}>{isRunning ? 'Running…' : 'Run now'}</button>
                <button className="btn bg-slate-600 hover:bg-slate-500" onClick={() => toggle(s.id, !s.enabled)}>{s.enabled ? 'Disable' : 'Enable'}</button>
                <button className="btn bg-red-600 hover:bg-red-500" onClick={() => del(s.id)}>Delete</button>
              </div>
            </div>
          );
        })}
        {schedules.length === 0 && <div className="text-sm text-slate-500">No schedules yet.</div>}
      </div>
    </div>
  );
}

