import React, { useState } from 'react';

export function ScrapeForm() {
  const [urls, setUrls] = useState('');
  const [workers, setWorkers] = useState('2');
  const [concurrency, setConcurrency] = useState('16');
  const [pages, setPages] = useState('');
  const [newestFirst, setNewestFirst] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    setSubmitting(true);
    try {
      await fetch('http://localhost:8000/api/scrape/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ start_urls: urls, workers: +workers || 1, concurrency: +(concurrency || 0) || null, pages: +(pages || 0) || null, newest_first: newestFirst })
      });
    } catch {}
    setSubmitting(false);
  };

  return (
    <div className="card p-4">
      <h2 className="text-lg font-semibold mb-2">Start Scrape</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <input className="input" placeholder="Start URLs (space or comma separated)" value={urls} onChange={e => setUrls(e.target.value)} />
        <div className="flex items-center gap-2">
          <input className="input w-24" placeholder="Workers" value={workers} onChange={e => setWorkers(e.target.value)} />
          <input className="input w-28" placeholder="Concurrency" value={concurrency} onChange={e => setConcurrency(e.target.value)} />
          <input className="input w-24" placeholder="Pages" value={pages} onChange={e => setPages(e.target.value)} />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={newestFirst} onChange={e => setNewestFirst(e.target.checked)} />
          Newest first
        </label>
        <div className="flex items-center gap-2">
          <button className="btn" disabled={submitting || !urls.trim()} onClick={submit}>{submitting ? 'Starting…' : 'Start'}</button>
        </div>
      </div>
    </div>
  );
}

