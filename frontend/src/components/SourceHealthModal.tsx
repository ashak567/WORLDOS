import React, { useEffect, useState } from 'react';
import { SourceHealth, fetchSourceHealth } from '../api';
import { X, Activity, RefreshCw, CheckCircle2, AlertTriangle, AlertOctagon } from 'lucide-react';

interface SourceHealthModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const SourceHealthModal: React.FC<SourceHealthModalProps> = ({
  isOpen,
  onClose,
}) => {
  const [sources, setSources] = useState<SourceHealth[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadHealth = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchSourceHealth();
      setSources(data);
    } catch (err: any) {
      setError(err?.message || 'Failed to fetch source health telemetry');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      loadHealth();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Activity size={16} color="var(--cy)" />
            <span className="modal-title">REGISTERED DATA SOURCE HEALTH</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              className="hud-btn"
              onClick={loadHealth}
              disabled={loading}
              title="Refresh source health"
              style={{ padding: '4px 8px' }}
            >
              <RefreshCw size={12} className={loading ? 'spinning' : ''} />
              <span>REFRESH</span>
            </button>
            <button
              className="details-close-btn"
              onClick={onClose}
              title="Close modal"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        <div className="modal-body">
          {error && (
            <div style={{ color: 'var(--red)', fontSize: '12px', padding: '8px', background: 'rgba(255, 77, 77, 0.1)', borderRadius: '4px' }}>
              {error}
            </div>
          )}

          <table className="source-health-table">
            <thead>
              <tr>
                <th>SOURCE ADAPTER</th>
                <th>KIND / PROTOCOL</th>
                <th>STATUS</th>
                <th>LAST POLLED / INGESTION</th>
                <th>RECORDS</th>
              </tr>
            </thead>
            <tbody>
              {sources.length > 0 ? (
                sources.map((src) => {
                  const isHealthy = src.status ? src.status === 'healthy' : (src.is_healthy ?? true);
                  const isDegraded = src.status === 'degraded' || (src.last_run_status === 'degraded');
                  const statusClass = !isHealthy ? 'unhealthy' : isDegraded ? 'degraded' : 'healthy';
                  const statusLabel = src.status?.toUpperCase() || (isHealthy ? 'HEALTHY' : 'UNHEALTHY');
                  const lastSync = src.last_polled_at || src.last_successful_ingest || src.freshness_observed_at || src.last_observation_at;
                  const recordCount = src.records_count ?? src.total_records_persisted;

                  return (
                    <tr key={src.source_slug}>
                      <td>
                        <strong style={{ color: 'var(--text-primary)' }}>
                          {src.source_name || src.source_slug}
                        </strong>
                        <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                          {src.source_slug}
                        </div>
                      </td>
                      <td>
                        <span style={{ fontFamily: 'var(--font-mono)' }}>
                          {src.source_kind || src.publisher || 'REST / GeoJSON'}
                        </span>
                      </td>
                      <td>
                        <span className={`health-status-badge ${statusClass}`}>
                          {statusClass === 'healthy' ? (
                            <CheckCircle2 size={10} />
                          ) : statusClass === 'degraded' ? (
                            <AlertTriangle size={10} />
                          ) : (
                            <AlertOctagon size={10} />
                          )}
                          {statusLabel}
                        </span>
                      </td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: '10px' }}>
                        {lastSync
                          ? new Date(lastSync).toUTCString()
                          : 'Operational'}
                      </td>
                      <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--cy)' }}>
                        {recordCount !== undefined
                          ? recordCount.toLocaleString()
                          : 'Live Stream'}
                      </td>
                    </tr>
                  );
                })

              ) : (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
                    {loading ? 'Polling active backend adapter contracts...' : 'No source adapters currently registered.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

