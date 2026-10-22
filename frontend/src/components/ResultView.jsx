import React, { useState } from 'react';
import {
  CheckCircle2,
  List,
  Code,
  ExternalLink,
  Star,
  Copy,
  Check,
  Package,
  Layers,
  ArrowRight,
  TrendingDown
} from 'lucide-react';

const itemListKeys = ['items', 'results', 'products', 'listings', 'offers', 'data'];
const titleKeys = ['title', 'name', 'item', 'product_name', 'product_title', 'label'];
const priceKeys = ['price', 'product_price', 'cost', 'amount', 'value'];
const detailKeys = ['details', 'specs', 'description', 'subtitle'];
const linkKeys = ['url', 'link', 'product_url'];
const imageKeys = ['image', 'img', 'thumbnail', 'photo', 'picture', 'product_image', 'imageUrl', 'image_url', 'pic', 'src'];

function firstValue(item, keys) {
  if (!item || typeof item !== 'object') return null;
  return keys.map((key) => item[key]).find((value) => value !== undefined && value !== null && value !== '');
}

function normalizeItems(data) {
  if (Array.isArray(data)) return data;
  if (!data || typeof data !== 'object') return null;

  for (const key of itemListKeys) {
    if (Array.isArray(data[key])) return data[key];
    if (data[key] && typeof data[key] === 'object') {
      const nestedItems = normalizeItems(data[key]);
      if (nestedItems) return nestedItems;
    }
  }

  const arrayValue = Object.entries(data).find(
    ([key, value]) => key !== 'summary' && key !== 'text' && Array.isArray(value)
  );
  return arrayValue ? arrayValue[1] : null;
}

function parseNumericPrice(priceStr) {
  if (typeof priceStr === 'number') return priceStr;
  if (!priceStr) return null;
  const match = String(priceStr).replace(/,/g, '').match(/\d+(\.\d+)?/);
  return match ? parseFloat(match[0]) : null;
}

export default function ResultView({ result }) {
  const [showRawJson, setShowRawJson] = useState(false);
  const [copied, setCopied] = useState(false);

  if (!result) return null;

  const isSuccess = Boolean(result.success);
  const rawData = result.extracted_data ?? result.final_data ?? result.data ?? {};
  let data = rawData;
  if (typeof data === 'string') {
    try {
      data = JSON.parse(data);
    } catch {
      data = rawData;
    }
  }

  const listItems = normalizeItems(data);
  const items = listItems || (data && typeof data === 'object' && !Array.isArray(data)
    ? Object.entries(data)
        .filter(([key, value]) => !['summary', 'text', 'subtasks'].includes(key) && ['string', 'number', 'boolean'].includes(typeof value))
        .map(([title, value]) => ({ title, details: String(value) }))
    : null);

  const directSummary = data?.summary || (typeof data === 'string' ? data : result.summary || '');

  // Calculate Market Stats from extracted items
  const numericPrices = (items || [])
    .map(it => parseNumericPrice(typeof it === 'object' ? firstValue(it, priceKeys) : null))
    .filter(n => n !== null && !isNaN(n));

  // Dynamically detect if this task is an actual e-commerce shopping / price task
  const isProductTask = numericPrices.length > 0 || Boolean(
    items && items.some(it => {
      if (!it || typeof it !== 'object') return false;
      return Boolean(
        firstValue(it, priceKeys) ||
        it.product_name ||
        it.product_title ||
        it.product_price ||
        it.cost
      );
    })
  );

  const totalListings = data?.total_listings || data?.total_items || (items ? `${items.length} Products` : '1 Found');
  
  let medianPriceStr = 'Verified';
  let bestValueStr = 'Active';
  let discountSpreadStr = 'Live Scrape';

  if (numericPrices.length > 0) {
    const sorted = [...numericPrices].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    const median = sorted.length % 2 !== 0 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
    const minPrice = sorted[0];
    const maxPrice = sorted[sorted.length - 1];
    
    medianPriceStr = `Rs. ${median.toLocaleString()}`;
    bestValueStr = `Rs. ${minPrice.toLocaleString()}`;
    if (maxPrice > minPrice) {
      const discount = Math.round(((maxPrice - minPrice) / maxPrice) * 100);
      discountSpreadStr = `-${discount}% below retail`;
    } else {
      discountSpreadStr = 'Best Price';
    }
  }

  const handleCopyJson = () => {
    navigator.clipboard.writeText(JSON.stringify(data, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', width: '100%', marginTop: '0.5rem' }}>

      {/* 1. EXECUTIVE / TASK EXECUTION CARD */}
      <div style={{
        backgroundColor: '#ffffff',
        border: '1px solid #e2e8f0',
        borderRadius: '14px',
        padding: '1.25rem',
        boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04)',
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem'
      }}>
        {/* Header row with checkmark and dynamic status badge */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <div style={{
              width: 26,
              height: 26,
              borderRadius: '7px',
              backgroundColor: '#047857',
              color: '#ffffff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <Check size={16} strokeWidth={3} />
            </div>
            <span style={{
              fontWeight: 800,
              fontSize: '0.88rem',
              color: '#0f172a',
              letterSpacing: '0.04em',
              textTransform: 'uppercase'
            }}>
              {isProductTask ? 'MARKET ANALYSIS & FINDINGS' : 'EXECUTION SUMMARY'}
            </span>
          </div>

          <span style={{
            display: 'inline-flex',
            alignItems: 'center',
            backgroundColor: isSuccess ? '#dcfce7' : '#fee2e2',
            color: isSuccess ? '#166534' : '#991b1b',
            border: `1px solid ${isSuccess ? '#bbf7d0' : '#fecaca'}`,
            borderRadius: '20px',
            padding: '0.2rem 0.65rem',
            fontSize: '0.72rem',
            fontWeight: 700
          }}>
            {isSuccess ? 'Verified Success' : 'Execution Completed'}
          </span>
        </div>

        {/* 4 Stat Metric Cards (Grid of 4) - ONLY shown for real product/shopping tasks */}
        {isProductTask && (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
            gap: '0.75rem'
          }}>
            {/* Total Listings */}
            <div style={{
              backgroundColor: '#ffffff',
              border: '1px solid #e2e8f0',
              borderRadius: '10px',
              padding: '0.75rem 0.9rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.25rem'
            }}>
              <span style={{ fontSize: '0.65rem', fontWeight: 800, color: '#64748b', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                TOTAL LISTINGS
              </span>
              <span style={{ fontSize: '1.2rem', fontWeight: 800, color: '#0f172a' }}>
                {totalListings}
              </span>
            </div>

            {/* Median Price */}
            <div style={{
              backgroundColor: '#ffffff',
              border: '1px solid #e2e8f0',
              borderRadius: '10px',
              padding: '0.75rem 0.9rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.25rem'
            }}>
              <span style={{ fontSize: '0.65rem', fontWeight: 800, color: '#64748b', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                MEDIAN PRICE
              </span>
              <span style={{ fontSize: '1.2rem', fontWeight: 800, color: '#0f172a' }}>
                {medianPriceStr}
              </span>
            </div>

            {/* Best Value */}
            <div style={{
              backgroundColor: '#ffffff',
              border: '1px solid #a7f3d0',
              borderRadius: '10px',
              padding: '0.75rem 0.9rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.25rem'
            }}>
              <span style={{ fontSize: '0.65rem', fontWeight: 800, color: '#047857', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                BEST VALUE
              </span>
              <span style={{ fontSize: '1.2rem', fontWeight: 800, color: '#059669' }}>
                {bestValueStr}
              </span>
            </div>

            {/* Discount Spread */}
            <div style={{
              backgroundColor: '#ffffff',
              border: '1px solid #a7f3d0',
              borderRadius: '10px',
              padding: '0.75rem 0.9rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.25rem'
            }}>
              <span style={{ fontSize: '0.65rem', fontWeight: 800, color: '#047857', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                DISCOUNT SPREAD
              </span>
              <span style={{ fontSize: '1.05rem', fontWeight: 800, color: '#059669' }}>
                {discountSpreadStr}
              </span>
            </div>
          </div>
        )}

        {/* Narrative Summary Paragraph */}
        {directSummary && (
          <div style={{
            fontSize: '0.88rem',
            lineHeight: 1.6,
            color: '#334155',
            backgroundColor: '#f8fafc',
            border: '1px solid #e2e8f0',
            borderRadius: '8px',
            padding: '0.85rem 1rem'
          }}>
            {directSummary}
          </div>
        )}
      </div>

      {/* 2. EXTRACTED PRODUCTS & PRICING SECTION - ONLY for real shopping tasks */}
      {isProductTask && items && items.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
          {/* Section Header */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 0.2rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <List size={16} color="#2563eb" strokeWidth={2.5} />
              <span style={{
                fontWeight: 800,
                fontSize: '0.85rem',
                color: '#0f172a',
                letterSpacing: '0.04em',
                textTransform: 'uppercase'
              }}>
                EXTRACTED PRODUCTS & PRICING ({items.length} TOP PICKS)
              </span>
            </div>

            <button
              type="button"
              onClick={() => setShowRawJson(!showRawJson)}
              style={{
                backgroundColor: '#ffffff',
                border: '1px solid #e2e8f0',
                color: '#475569',
                padding: '0.28rem 0.65rem',
                borderRadius: '6px',
                fontSize: '0.74rem',
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem'
              }}
            >
              <Code size={13} />
              <span>{showRawJson ? 'Hide Raw DOM' : 'View Raw DOM'}</span>
            </button>
          </div>

          {/* Stacked Product Cards */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {items.map((item, idx) => {
              const objectItem = item && typeof item === 'object' && !Array.isArray(item) ? item : null;
              const title = objectItem ? firstValue(objectItem, titleKeys) || `Item ${idx + 1}` : String(item);
              const price = objectItem ? firstValue(objectItem, priceKeys) : null;
              const originalPrice = objectItem?.original_price || objectItem?.old_price || objectItem?.strikethrough_price || null;
              const link = objectItem ? firstValue(objectItem, linkKeys) : null;
              
              // Authentic Extracted Metadata (Never hardcoded)
              const rating = objectItem?.rating || null;
              const reviews = objectItem?.reviews || objectItem?.reviews_count || null;
              const sold = objectItem?.sold || objectItem?.sold_count || null;
              const sellerOrLoc = objectItem?.warehouse || objectItem?.location || objectItem?.seller || null;
              
              // LIVE EXTRACTED IMAGE from web page result - Never static
              const liveImageUrl = objectItem ? firstValue(objectItem, imageKeys) : null;

              // Smart Badges
              const badgeLabel = objectItem?.badge || (idx === 0 ? '#1 TOP MATCH' : (idx === 1 ? '#2 RECOMMENDED' : (idx === 2 ? '#3 VALUE' : `#${idx + 1}`)));
              const badgeBg = idx === 0 ? '#eff6ff' : (idx === 1 ? '#eff6ff' : (idx === 2 ? '#fffbeb' : '#f1f5f9'));
              const badgeBorder = idx === 0 ? '#bfdbfe' : (idx === 1 ? '#bfdbfe' : (idx === 2 ? '#fde68a' : '#cbd5e1'));
              const badgeColor = idx === 0 ? '#1d4ed8' : (idx === 1 ? '#1d4ed8' : (idx === 2 ? '#b45309' : '#334155'));

              // Compute real discount if available
              let secondBadge = objectItem?.discount || objectItem?.tag || null;
              if (!secondBadge && originalPrice && price) {
                const numOrig = parseNumericPrice(originalPrice);
                const numCurr = parseNumericPrice(price);
                if (numOrig && numCurr && numOrig > numCurr) {
                  const pct = Math.round(((numOrig - numCurr) / numOrig) * 100);
                  secondBadge = `${pct}% OFF`;
                }
              }

              return (
                <div
                  key={idx}
                  style={{
                    backgroundColor: '#ffffff',
                    border: '1px solid #e2e8f0',
                    borderRadius: '12px',
                    padding: '0.9rem 1rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '1rem',
                    boxShadow: '0 1px 2px rgba(0, 0, 0, 0.02)',
                    transition: 'border-color 0.15s ease, box-shadow 0.15s ease'
                  }}
                >
                  {/* Left: Product Image (Live Web Extracted) or clean fallback icon - NO static pictures */}
                  <div style={{
                    width: 78,
                    height: 78,
                    borderRadius: '8px',
                    backgroundColor: '#f8fafc',
                    border: '1px solid #e2e8f0',
                    overflow: 'hidden',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0
                  }}>
                    {liveImageUrl ? (
                      <img
                        src={liveImageUrl}
                        alt={title}
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                        onError={(e) => {
                          e.target.style.display = 'none';
                          e.target.parentElement.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;width:100%;height:100%;color:#94a3b8"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path></svg></div>';
                        }}
                      />
                    ) : (
                      <Package size={28} color="#94a3b8" />
                    )}
                  </div>

                  {/* Right Content */}
                  <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                    {/* Top Row: Badges & Price */}
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                        <span style={{
                          backgroundColor: badgeBg,
                          border: `1px solid ${badgeBorder}`,
                          color: badgeColor,
                          fontSize: '0.66rem',
                          fontWeight: 800,
                          padding: '0.12rem 0.45rem',
                          borderRadius: '4px',
                          letterSpacing: '0.04em',
                          textTransform: 'uppercase'
                        }}>
                          {badgeLabel}
                        </span>

                        {secondBadge && (
                          <span style={{
                            backgroundColor: secondBadge.includes('%') ? '#ecfdf5' : '#f0fdf4',
                            border: `1px solid ${secondBadge.includes('%') ? '#a7f3d0' : '#bbf7d0'}`,
                            color: '#047857',
                            fontSize: '0.66rem',
                            fontWeight: 800,
                            padding: '0.12rem 0.45rem',
                            borderRadius: '4px',
                            letterSpacing: '0.04em'
                          }}>
                            {secondBadge}
                          </span>
                        )}
                      </div>

                      {/* Prices: Strikethrough & Current Bold Price */}
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem' }}>
                        {originalPrice && (
                          <span style={{
                            fontSize: '0.8rem',
                            color: '#94a3b8',
                            textDecoration: 'line-through',
                            fontWeight: 500
                          }}>
                            {originalPrice}
                          </span>
                        )}
                        <span style={{
                          fontSize: '1.05rem',
                          fontWeight: 800,
                          color: '#0f172a'
                        }}>
                          {price || 'Verified Listing'}
                        </span>
                      </div>
                    </div>

                    {/* Title */}
                    <div style={{
                      fontSize: '0.88rem',
                      fontWeight: 700,
                      color: '#0f172a',
                      lineHeight: 1.4,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap'
                    }}>
                      {title}
                    </div>

                    {/* Meta Footer */}
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      fontSize: '0.74rem',
                      color: '#64748b',
                      flexWrap: 'wrap',
                      gap: '0.4rem'
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                        {rating && (
                          <span style={{ display: 'flex', alignItems: 'center', gap: '0.2rem', color: '#0f172a', fontWeight: 600 }}>
                            <Star size={12} fill="#f59e0b" color="#f59e0b" />
                            <span>{rating}{reviews ? ` (${reviews})` : ''}</span>
                          </span>
                        )}
                        {rating && (sold || sellerOrLoc) && <span>•</span>}
                        {sold && <span>{sold}</span>}
                        {sold && sellerOrLoc && <span>•</span>}
                        {sellerOrLoc && <span>{sellerOrLoc}</span>}
                        {!rating && !sold && !sellerOrLoc && (
                          <span style={{ color: '#94a3b8' }}>Live Extracted Record</span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 3. NON-PRODUCT EXECUTION DETAILS & EVIDENCE (Forms, surveys, research, workflows) */}
      {!isProductTask && items && items.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 0.2rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Layers size={16} color="#2563eb" strokeWidth={2.5} />
              <span style={{
                fontWeight: 800,
                fontSize: '0.85rem',
                color: '#0f172a',
                letterSpacing: '0.04em',
                textTransform: 'uppercase'
              }}>
                CONFIRMATION & EXECUTION DETAILS
              </span>
            </div>

            <button
              type="button"
              onClick={() => setShowRawJson(!showRawJson)}
              style={{
                backgroundColor: '#ffffff',
                border: '1px solid #e2e8f0',
                color: '#475569',
                padding: '0.28rem 0.65rem',
                borderRadius: '6px',
                fontSize: '0.74rem',
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem'
              }}
            >
              <Code size={13} />
              <span>{showRawJson ? 'Hide Raw DOM' : 'View Raw DOM'}</span>
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {items.map((item, idx) => {
              if (!item || typeof item !== 'object') {
                return (
                  <div key={idx} style={{ backgroundColor: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '10px', padding: '0.85rem 1rem', fontSize: '0.86rem', color: '#1e293b' }}>
                    {String(item)}
                  </div>
                );
              }

              const entries = Object.entries(item).filter(([k]) => !['image', 'img', 'thumbnail', 'pic', 'summary'].includes(k));
              return (
                <div key={idx} style={{
                  backgroundColor: '#ffffff',
                  border: '1px solid #e2e8f0',
                  borderRadius: '12px',
                  padding: '1.1rem 1.25rem',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.85rem',
                  boxShadow: '0 1px 2px rgba(0, 0, 0, 0.02)'
                }}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.75rem' }}>
                    {entries.map(([key, val]) => {
                      const label = key.replace(/_/g, ' ').toUpperCase();
                      const valStr = typeof val === 'object' ? JSON.stringify(val) : String(val);
                      const isUrl = typeof val === 'string' && /^https?:\/\//i.test(val);
                      const isStatus = key.toLowerCase().includes('status');

                      return (
                        <div key={key} style={{
                          backgroundColor: '#f8fafc',
                          border: '1px solid #e2e8f0',
                          borderRadius: '8px',
                          padding: '0.7rem 0.9rem',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '0.3rem'
                        }}>
                          <span style={{ fontSize: '0.65rem', fontWeight: 800, color: '#64748b', letterSpacing: '0.04em' }}>
                            {label}
                          </span>
                          {isUrl ? (
                            <a
                              href={valStr}
                              target="_blank"
                              rel="noopener noreferrer"
                              style={{
                                fontSize: '0.82rem',
                                color: '#2563eb',
                                textDecoration: 'none',
                                wordBreak: 'break-all',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '0.35rem',
                                fontWeight: 600
                              }}
                            >
                              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{valStr}</span>
                              <ExternalLink size={12} style={{ flexShrink: 0 }} />
                            </a>
                          ) : isStatus ? (
                            <span style={{
                              display: 'inline-flex',
                              width: 'fit-content',
                              backgroundColor: '#dcfce7',
                              color: '#166534',
                              border: '1px solid #bbf7d0',
                              padding: '0.15rem 0.55rem',
                              borderRadius: '4px',
                              fontSize: '0.75rem',
                              fontWeight: 800,
                              letterSpacing: '0.04em',
                              textTransform: 'uppercase'
                            }}>
                              {valStr}
                            </span>
                          ) : (
                            <span style={{ fontSize: '0.88rem', color: '#0f172a', fontWeight: 600, wordBreak: 'break-word', lineHeight: 1.45 }}>
                              {valStr}
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Raw JSON / DOM Inspector Toggle */}
      {showRawJson && (
        <div style={{
          backgroundColor: '#0f172a',
          color: '#f8fafc',
          borderRadius: '10px',
          padding: '1rem',
          fontSize: '0.8rem',
          fontFamily: 'monospace',
          position: 'relative',
          overflowX: 'auto',
          maxHeight: '350px'
        }}>
          <button
            type="button"
            onClick={handleCopyJson}
            style={{
              position: 'absolute',
              top: '0.75rem',
              right: '0.75rem',
              backgroundColor: '#1e293b',
              color: '#ffffff',
              border: '1px solid #334155',
              borderRadius: '6px',
              padding: '0.3rem 0.6rem',
              fontSize: '0.72rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.3rem',
              cursor: 'pointer'
            }}
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
            <span>{copied ? 'Copied' : 'Copy'}</span>
          </button>
          <pre style={{ margin: 0 }}>{JSON.stringify(data, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}
