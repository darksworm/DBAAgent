import React, { useEffect, useMemo, useState } from 'react';

interface Listing {
  title: string;
  price: number;
  description?: string;
  location?: string;
  url?: string;
  image_src?: string;
}

export default function App(): JSX.Element {
  const [listings, setListings] = useState<Listing[]>([]);
  const [q, setQ] = useState('');
  const [qx, setQx] = useState('');
  const [loc, setLoc] = useState('');
  const [locx, setLocx] = useState('');
  const [minPrice, setMinPrice] = useState('');
  const [maxPrice, setMaxPrice] = useState('');

  const api = useMemo(() => new URL('http://localhost:8000/api/listings'), []);

  const fetchListings = () => {
    const url = new URL(api.toString());
    if (q) url.searchParams.set('q', q);
    if (qx) url.searchParams.set('qx', qx);
    if (loc) url.searchParams.set('loc', loc);
    if (locx) url.searchParams.set('locx', locx);
    if (minPrice) url.searchParams.set('min_price', minPrice);
    if (maxPrice) url.searchParams.set('max_price', maxPrice);
    fetch(url.toString())
      .then((r) => r.json())
      .then((data) => setListings(data))
      .catch(() => setListings([]));
  };

  useEffect(() => {
    fetchListings();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="app min-h-screen">
      <div className="max-w-6xl mx-auto p-4">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-2xl font-semibold">DBA Listings</h1>
          <button
            className="btn"
            onClick={() => {
              const isDark = document.documentElement.classList.toggle('dark');
              localStorage.setItem('theme', isDark ? 'dark' : 'light');
            }}
          >
            Toggle Theme
          </button>
        </div>

        <div className="card p-4 mb-4">
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-3">
            <input className="input" placeholder="Keywords include" value={q} onChange={(e) => setQ(e.target.value)} />
            <input className="input" placeholder="Keywords exclude" value={qx} onChange={(e) => setQx(e.target.value)} />
            <input className="input" placeholder="Location include" value={loc} onChange={(e) => setLoc(e.target.value)} />
            <input className="input" placeholder="Location exclude" value={locx} onChange={(e) => setLocx(e.target.value)} />
            <input className="input" placeholder="Min price" value={minPrice} onChange={(e) => setMinPrice(e.target.value)} />
            <input className="input" placeholder="Max price" value={maxPrice} onChange={(e) => setMaxPrice(e.target.value)} />
            <div className="flex items-center gap-2">
              <button className="btn" onClick={fetchListings}>Search</button>
              <button className="btn bg-slate-600 hover:bg-slate-500" onClick={() => { setQ(''); setQx(''); setLoc(''); setLocx(''); setMinPrice(''); setMaxPrice(''); }}>Clear</button>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {listings.map((l, idx) => (
            <div key={idx} className="card p-4">
              {l.image_src && (
                <img src={l.image_src} alt="" className="w-full h-40 object-cover rounded-lg mb-2" />
              )}
              <div className="text-sm text-slate-500 dark:text-slate-400 mb-1">{l.location || '—'}</div>
              <div className="font-medium text-lg">
                {l.url ? (
                  <a href={l.url} target="_blank" rel="noreferrer" className="hover:underline">
                    {l.title}
                  </a>
                ) : (
                  <span>{l.title}</span>
                )}
              </div>
              <div className="text-blue-600 dark:text-blue-400 font-semibold">{l.price.toFixed(2)} DKK</div>
              {l.description && <p className="mt-2 text-sm text-slate-600 dark:text-slate-300 line-clamp-3">{l.description}</p>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

