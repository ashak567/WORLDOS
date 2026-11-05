import React, { useState } from 'react';
import { LayerCategory, LayerDefinition, LayerId } from '../types/layers';
import { LiveContextResponse } from '../api';
import { ChevronLeft, ChevronRight, Layers, Search, Filter } from 'lucide-react';

interface LayerDockProps {
  layers: LayerDefinition[];
  liveContext: LiveContextResponse | null;
  contextError: boolean;
  onToggleLayer: (id: LayerId) => void;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

const CATEGORY_TITLES: Record<LayerCategory, string> = {
  geography: 'GEOGRAPHY & REFERENCE',
  aviation: 'AIRSPACE & AVIATION',
  maritime: 'MARITIME AIS',
  space: 'SPACE & ORBITAL',
  surveillance: 'OPTICAL & SENSORS',
  disasters: 'DISASTERS & SEVERE EVENTS',
};

export const LayerDock: React.FC<LayerDockProps> = ({
  layers,
  liveContext,
  contextError,
  onToggleLayer,
  isCollapsed,
  onToggleCollapse,
}) => {
  const [filterQuery, setFilterQuery] = useState('');

  const filteredLayers = layers.filter(
    (l) =>
      l.name.toLowerCase().includes(filterQuery.toLowerCase()) ||
      l.source.toLowerCase().includes(filterQuery.toLowerCase()) ||
      l.category.toLowerCase().includes(filterQuery.toLowerCase())
  );

  // Group by category
  const categories: LayerCategory[] = [
    'aviation',
    'maritime',
    'space',
    'surveillance',
    'disasters',
    'geography',
  ];

  // When collapsed, show a sleek floating trigger button instead of sliced-off dock contents
  if (isCollapsed) {
    return (
      <button
        className="layer-dock-floating-btn"
        onClick={onToggleCollapse}
        title="Open Intelligence Layers Dock"
        aria-label="Open Layers Dock"
      >
        <Layers size={14} color="var(--cy)" />
        <span className="layer-dock-floating-text">LAYERS</span>
        <ChevronRight size={13} color="var(--text-muted)" />
      </button>
    );
  }

  return (
    <aside
      className="layer-dock expanded"
      aria-label="Intelligence Layer Dock"
    >
      <div className="layer-dock-header">
        <div className="layer-dock-title">
          <Layers size={14} color="var(--cy)" />
          <span>INTELLIGENCE DOCK</span>
        </div>
        <button
          className="layer-dock-collapse-btn"
          onClick={onToggleCollapse}
          title="Collapse Layer Dock"
          aria-label="Collapse Layer Dock"
        >
          <ChevronLeft size={15} />
        </button>
      </div>

      <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--border-subtle)' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            background: 'rgba(0,0,0,0.3)',
            borderRadius: '4px',
            padding: '4px 8px',
            border: '1px solid var(--border-subtle)',
          }}
        >
          <Search size={12} color="var(--text-muted)" />
          <input
            type="text"
            placeholder="Filter layers & feeds..."
            value={filterQuery}
            onChange={(e) => setFilterQuery(e.target.value)}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-primary)',
              fontSize: '11px',
              width: '100%',
              outline: 'none',
            }}
          />
        </div>
      </div>

      <div className="layer-list">
        {contextError && !liveContext && (
          <div role="status" style={{ padding: '8px 10px', color: '#fbbf24', fontSize: 10 }}>
            Public news and climate feeds are currently unavailable.
          </div>
        )}
        {liveContext && (
          <section aria-label="Live global context" style={{ padding: '6px 4px 10px', marginBottom: '8px', borderBottom: '1px solid var(--border-subtle)' }}>
            {liveContext.climate && (
              <div style={{ padding: '7px 10px', marginBottom: '7px', border: '1px solid var(--border-subtle)', borderRadius: 4 }}>
                <div style={{ fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.08em' }}>
                  GLOBAL CLIMATE · MONTHLY{liveContext.sources.climate?.status !== 'fresh' ? ` · ${liveContext.sources.climate?.status?.toUpperCase() || 'UNAVAILABLE'}` : ''}
                </div>
                <div style={{ fontSize: 15, color: '#fbbf24', marginTop: 3 }}>
                  {liveContext.climate.global_temperature_anomaly_c > 0 ? '+' : ''}{liveContext.climate.global_temperature_anomaly_c.toFixed(2)} °C
                  <span style={{ fontSize: 10, color: 'var(--text-secondary)' }}> · {liveContext.climate.period}</span>
                </div>
                <a href={liveContext.climate.source_url} target="_blank" rel="noreferrer" style={{ fontSize: 9, color: 'var(--text-muted)' }}>
                  NASA GISTEMP · relative to {liveContext.climate.baseline}
                </a>
              </div>
            )}
            {!liveContext.climate && (
              <div role="status" style={{ padding: '6px 10px', color: '#fbbf24', fontSize: 10 }}>
                NASA monthly climate data unavailable.
              </div>
            )}
            <div style={{ fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.08em', padding: '2px 6px 5px' }}>
              GLOBAL NEWS · GDELT · 24H{liveContext.sources.news?.status !== 'fresh' ? ` · ${liveContext.sources.news?.status?.toUpperCase() || 'UNAVAILABLE'}` : ''}
            </div>
            {liveContext.news.slice(0, 8).map((article) => (
              <a key={article.url} href={article.url} target="_blank" rel="noreferrer" title={article.title}
                style={{ display: 'block', padding: '5px 6px', color: 'var(--text-primary)', fontSize: 10, lineHeight: 1.35, textDecoration: 'none', borderRadius: 3 }}>
                {article.title}
                <span style={{ display: 'block', color: 'var(--text-muted)', fontSize: 9, marginTop: 2 }}>
                  {article.domain}{article.published_at ? ` · ${article.published_at.replace(/^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$/, '$1-$2-$3 $4:$5 UTC')}` : ''}
                </span>
              </a>
            ))}
            {liveContext.news.length === 0 && (
              <div style={{ padding: '5px 6px', color: 'var(--text-muted)', fontSize: 10 }}>No matching headlines returned.</div>
            )}
          </section>
        )}
        {categories.map((cat) => {
          const catLayers = filteredLayers.filter((l) => l.category === cat);
          if (catLayers.length === 0) return null;

          return (
            <div key={cat} style={{ marginBottom: '8px' }}>
              <div
                style={{
                  fontSize: '9px',
                  fontWeight: 600,
                  letterSpacing: '0.08em',
                  color: 'var(--text-muted)',
                  padding: '4px 14px',
                  textTransform: 'uppercase',
                }}
              >
                {CATEGORY_TITLES[cat]}
              </div>

              {catLayers.map((layer) => (
                <div
                  key={layer.id}
                  className={`layer-item ${layer.enabled ? 'active' : ''}`}
                >
                  <div className="layer-item-top">
                    <div
                      className="layer-item-main"
                      onClick={() => onToggleLayer(layer.id)}
                    >
                      <div
                        className="layer-indicator"
                        style={{
                          backgroundColor: layer.color,
                          boxShadow: layer.enabled ? `0 0 8px ${layer.color}66` : 'none',
                        }}
                      />
                      <span className="layer-label">{layer.name}</span>
                    </div>

                    <button
                      className={`layer-toggle-btn ${layer.enabled ? 'enabled' : ''}`}
                      onClick={() => onToggleLayer(layer.id)}
                      aria-pressed={layer.enabled}
                      title={`Toggle ${layer.name}`}
                    >
                      <div className="layer-toggle-knob" />
                    </button>
                  </div>

                  <div className="layer-item-meta">
                    <span className="layer-source" title={layer.source}>
                      {layer.source}
                    </span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span className={`badge-truth ${layer.truthClass.toLowerCase()}`}>
                        {layer.truthClass}
                      </span>
                      <span className="layer-count-badge">
                        {layer.loading ? '...' : layer.count.toLocaleString()}
                      </span>
                    </div>
                  </div>
                  {layer.feedStatus && (
                    <div style={{ fontSize: '9px', padding: '2px 14px 4px', color: layer.feedStatus === 'fresh' ? '#34d399' : layer.feedStatus === 'unavailable' ? '#f87171' : '#fbbf24' }}>
                      {layer.feedStatus === 'fresh' ? 'FRESH SOURCE DATA' : layer.feedStatus === 'stale' ? 'SOURCE DATA · STALE' : layer.feedStatus === 'partial' ? 'PARTIAL FEEDS' : 'FEED UNAVAILABLE'}
                      {layer.lastUpdated && ` · ${new Date(layer.lastUpdated).toLocaleTimeString()}`}
                    </div>
                  )}
                  {layer.error && <div role="status" style={{ color: '#f87171', fontSize: '10px', padding: '2px 14px 6px' }}>{layer.error}</div>}
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </aside>
  );
};
