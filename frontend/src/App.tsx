import React, { useEffect, useState } from 'react';

interface Listing {
  title: string;
  price: number;
  description?: string;
  location?: string;
  url?: string;
}

export default function App(): JSX.Element {
  const [listings, setListings] = useState<Listing[]>([]);

  useEffect(() => {
    fetch('http://localhost:8000/api/listings')
      .then((r) => r.json())
      .then((data) => setListings(data))
      .catch(() => setListings([]));
  }, []);

  return (
    <div style={{ fontFamily: 'sans-serif', padding: '1rem' }}>
      <h1>DBA Listings</h1>
      <ul>
        {listings.map((l, idx) => (
          <li key={idx} style={{ marginBottom: '1rem' }}>
            {l.url ? (
              <a href={l.url} target="_blank" rel="noreferrer">
                {l.title}
              </a>
            ) : (
              <span>{l.title}</span>
            )}
            <div>
              ${l.price.toFixed(2)} - {l.location}
            </div>
            {l.description && <p>{l.description}</p>}
          </li>
        ))}
      </ul>
    </div>
  );
}
