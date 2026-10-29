import React, { useEffect } from 'react';
import { Command } from 'cmdk';
import { LayerDefinition, LayerId } from '../types/layers';
import { Globe, Map, Layers, Activity, Compass, ShieldAlert, Sparkles, X } from 'lucide-react';

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  viewMode: '2d' | '3d';
  onSetViewMode: (mode: '2d' | '3d') => void;
  layers: LayerDefinition[];
  onToggleLayer: (id: LayerId) => void;
  onOpenSourceHealth: () => void;
  onToggleDock: () => void;
  onJumpToRegion?: (coords: [number, number], zoom: number) => void;
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({
  isOpen,
  onClose,
  viewMode,
  onSetViewMode,
  layers,
  onToggleLayer,
  onOpenSourceHealth,
  onToggleDock,
  onJumpToRegion,
}) => {
  // Global shortcut Ctrl+K / Cmd+K listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (isOpen) {
          onClose();
        } else {
          // Trigger open via parent state
        }
      } else if (e.key === 'Escape' && isOpen) {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const runAction = (action: () => void) => {
    action();
    onClose();
  };

  return (
    <div className="command-backdrop" onClick={onClose}>
      <div className="command-dialog" onClick={(e) => e.stopPropagation()}>
        <Command label="WORLDOS Command Palette">
          <div className="command-input-wrapper">
            <Sparkles size={16} color="var(--cy)" />
            <Command.Input
              className="command-input"
              placeholder="Type a command, layer, or spatial focal action..."
              autoFocus
            />
            <button
              onClick={onClose}
              style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
            >
              <X size={15} />
            </button>
          </div>

          <Command.List className="command-list">
            <Command.Empty className="command-empty">No matching commands found.</Command.Empty>

            {/* Projection Mode Commands */}
            <Command.Group heading="GEOSPATIAL PROJECTION">
              <Command.Item
                className="command-item"
                onSelect={() => runAction(() => onSetViewMode('2d'))}
              >
                <div className="command-item-left">
                  <Map size={14} color="var(--cy)" />
                  <span>Switch to 2D Flat Map (MapLibre + Deck.gl)</span>
                </div>
                {viewMode === '2d' && <span className="command-shortcut">CURRENT</span>}
              </Command.Item>

              <Command.Item
                className="command-item"
                onSelect={() => runAction(() => onSetViewMode('3d'))}
              >
                <div className="command-item-left">
                  <Globe size={14} color="var(--blue)" />
                  <span>Switch to 3D Globe (CesiumJS)</span>
                </div>
                {viewMode === '3d' && <span className="command-shortcut">CURRENT</span>}
              </Command.Item>
            </Command.Group>

            {/* Layer Toggle Commands */}
            <Command.Group heading="INTELLIGENCE LAYERS">
              {layers.map((layer) => (
                <Command.Item
                  key={layer.id}
                  className="command-item"
                  onSelect={() => runAction(() => onToggleLayer(layer.id))}
                >
                  <div className="command-item-left">
                    <div
                      style={{
                        width: '8px',
                        height: '8px',
                        borderRadius: '2px',
                        backgroundColor: layer.color,
                      }}
                    />
                    <span>Toggle {layer.name}</span>
                  </div>
                  <span className="command-shortcut">
                    {layer.enabled ? 'ENABLED' : 'DISABLED'}
                  </span>
                </Command.Item>
              ))}
            </Command.Group>

            {/* Regional Navigation Focal Points */}
            <Command.Group heading="REGIONAL NAVIGATION & FOCAL POINTS">
              <Command.Item
                className="command-item"
                onSelect={() => runAction(() => onJumpToRegion && onJumpToRegion([78.9629, 20.5937], 4.2))}
              >
                <div className="command-item-left">
                  <Compass size={14} color="var(--cy)" />
                  <span>Jump to India (Operational Baseline Hub)</span>
                </div>
                <span className="command-shortcut">[78.96°E, 20.59°N]</span>
              </Command.Item>

              <Command.Item
                className="command-item"
                onSelect={() => runAction(() => onJumpToRegion && onJumpToRegion([138.2529, 36.2048], 4.8))}
              >
                <div className="command-item-left">
                  <Compass size={14} color="var(--gold)" />
                  <span>Jump to Japan (Pacific Ring Seismic Zone)</span>
                </div>
                <span className="command-shortcut">[138.25°E, 36.20°N]</span>
              </Command.Item>

              <Command.Item
                className="command-item"
                onSelect={() => runAction(() => onJumpToRegion && onJumpToRegion([-98.5795, 39.8283], 3.8))}
              >
                <div className="command-item-left">
                  <Compass size={14} color="var(--blue)" />
                  <span>Jump to North America (USGS Primary Scope)</span>
                </div>
                <span className="command-shortcut">[-98.58°W, 39.83°N]</span>
              </Command.Item>

              <Command.Item
                className="command-item"
                onSelect={() => runAction(() => onJumpToRegion && onJumpToRegion([10.4515, 51.1657], 4.2))}
              >
                <div className="command-item-left">
                  <Compass size={14} color="var(--purple)" />
                  <span>Jump to Europe (Continental Scope)</span>
                </div>
                <span className="command-shortcut">[10.45°E, 51.17°N]</span>
              </Command.Item>

              <Command.Item
                className="command-item"
                onSelect={() => runAction(() => onJumpToRegion && onJumpToRegion([20.0, 15.0], 2.0))}
              >
                <div className="command-item-left">
                  <Globe size={14} color="var(--text-muted)" />
                  <span>Reset to Global Macro View</span>
                </div>
                <span className="command-shortcut">WORLD</span>
              </Command.Item>
            </Command.Group>

            {/* Operational Diagnostics & Interface */}
            <Command.Group heading="OPERATIONAL DIAGNOSTICS & SYSTEM">
              <Command.Item
                className="command-item"
                onSelect={() => runAction(onOpenSourceHealth)}
              >
                <div className="command-item-left">
                  <Activity size={14} color="var(--grn)" />
                  <span>Inspect Registered Source Adapters & Freshness</span>
                </div>
                <span className="command-shortcut">GET /sources/health</span>
              </Command.Item>

              <Command.Item
                className="command-item"
                onSelect={() => runAction(onToggleDock)}
              >
                <div className="command-item-left">
                  <Layers size={14} color="var(--gold)" />
                  <span>Toggle Layer Management Dock</span>
                </div>
                <span className="command-shortcut">UI</span>
              </Command.Item>
            </Command.Group>
          </Command.List>

        </Command>
      </div>
    </div>
  );
};

