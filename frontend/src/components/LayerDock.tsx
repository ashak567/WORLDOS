import React, { useState } from 'react';
import { LayerCategory, LayerDefinition, LayerId } from '../types/layers';
import { ChevronLeft, ChevronRight, Layers, Search, Filter } from 'lucide-react';

interface LayerDockProps {
  layers: LayerDefinition[];
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
  infrastructure: 'CRITICAL INFRASTRUCTURE',
  intelligence: 'DERIVED INTELLIGENCE',
};

export const LayerDock: React.FC<LayerDockProps> = ({
  layers,
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
    'infrastructure',
    'geography',
    'intelligence',
  ];

  return (
    <aside
      className={`layer-dock ${isCollapsed ? 'collapsed' : ''}`}
      aria-label="Intelligence Layer Dock"
    >
      <div className="layer-dock-header">
        <div className="layer-dock-title">
          <Layers size={13} color="var(--cy)" />
          <span>INTELLIGENCE DOCK</span>
        </div>
        <button
          className="layer-dock-collapse-btn"
          onClick={onToggleCollapse}
          title={isCollapsed ? 'Expand Dock' : 'Collapse Dock'}
          aria-label={isCollapsed ? 'Expand Dock' : 'Collapse Dock'}
        >
          {isCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
        </button>
      </div>

      {!isCollapsed && (
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
      )}

      <div className="layer-list">
        {categories.map((cat) => {
          const catLayers = filteredLayers.filter((l) => l.category === cat);
          if (catLayers.length === 0) return null;

          return (
            <div key={cat} style={{ marginBottom: '8px' }}>
              {!isCollapsed && (
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
              )}

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
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </aside>
  );
};
