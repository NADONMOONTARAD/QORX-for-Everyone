"use client";

import { useState } from 'react';

interface StockLogoProps {
  ticker: string;
  companyName?: string;
  logoUrl?: string | null;  // cached from database -- preferred over API call
  size?: number;
  className?: string;
  style?: React.CSSProperties;
}

export function StockLogo({ ticker, companyName, logoUrl, size = 24, className = "", style }: StockLogoProps) {
  const [error, setError] = useState(false);
  
  const initial = companyName 
    ? companyName.charAt(0).toUpperCase() 
    : (ticker ? ticker.charAt(0).toUpperCase() : '?');

  // Use cached DB URL if available, otherwise fall back to the free API URL
  const src = logoUrl || (ticker ? `https://financialmodelingprep.com/image-stock/${ticker.toUpperCase()}.png` : null);

  if (error || !src) {
    return (
      <div 
        className={className}
        style={{ 
          width: size, 
          height: size, 
          borderRadius: '50%', 
          backgroundColor: 'rgba(15, 77, 188, 0.1)', 
          color: '#0f4dbc', 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center', 
          fontSize: size * 0.45,
          fontWeight: 'bold',
          flexShrink: 0,
          ...style
        }}
        title={companyName ?? ticker}
      >
        {initial}
      </div>
    );
  }

  return (
    <img 
      src={src} 
      alt={companyName ?? ticker} 
      title={companyName ?? ticker}
      className={className}
      onError={() => setError(true)}
      style={{ 
        width: size, 
        height: size, 
        objectFit: 'contain',
        borderRadius: '50%',
        backgroundColor: 'var(--card-bg, white)',
        padding: size > 30 ? '2px' : '1px',
        border: '1px solid rgba(15, 77, 188, 0.12)',
        flexShrink: 0,
        ...style
      }} 
    />
  );
}
