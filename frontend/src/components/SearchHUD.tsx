import React from 'react';

export interface SearchHUDProps {
  active: boolean;
  platform: 'reddit' | 'exa' | 'tavily' | 'google' | 'wikipedia' | string;
  query: string;
  onDismiss?: () => void;
}

export const SearchHUD: React.FC<SearchHUDProps> = ({
  active,
  platform,
  query,
  onDismiss,
}) => {
  if (!active) return null;

  const getPlatformMeta = (p: string) => {
    switch (p.toLowerCase()) {
      case 'reddit':
        return {
          label: 'REDDIT INTEL',
          color: 'text-orange-400',
          borderColor: 'border-orange-500/40',
          bgGlow: 'bg-orange-500/10',
          icon: (
            <svg className="w-5 h-5 text-orange-400" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0zm5.01 4.744c.688 0 1.25.561 1.25 1.249a1.25 1.25 0 0 1-2.498.056l-2.597-.547-.8 3.747c1.824.07 3.48.632 4.674 1.488.308-.309.73-.491 1.207-.491.968 0 1.754.786 1.754 1.754 0 .716-.435 1.333-1.01 1.614a3.111 3.111 0 0 1 .042.52c0 2.694-3.13 4.87-7.004 4.87-3.874 0-7.004-2.176-7.004-4.87 0-.183.015-.366.043-.534A1.748 1.748 0 0 1 4.028 12c0-.968.786-1.754 1.754-1.754.463 0 .898.196 1.207.49 1.207-.883 2.878-1.43 4.744-1.487l.885-4.182a.342.342 0 0 1 .14-.197.35.35 0 0 1 .238-.042l2.906.617a1.214 1.214 0 0 1 1.108-.703zM9.25 12C8.56 12 8 12.56 8 13.25c0 .69.56 1.25 1.25 1.25.69 0 1.25-.56 1.25-1.25 0-.69-.56-1.25-1.25-1.25zm5.5 0c-.69 0-1.25.56-1.25 1.25 0 .69.56 1.25 1.25 1.25.69 0 1.25-.56 1.25-1.25 0-.69-.56-1.25-1.25-1.25zm-5.465 4.542a.36.36 0 0 0-.25.105.361.361 0 0 0 0 .509c.773.774 2.015 1.154 3.015 1.154 1.001 0 2.242-.38 3.016-1.154a.361.361 0 0 0-.51-.51c-.628.627-1.637.935-2.506.935-.87 0-1.879-.308-2.506-.935a.36.36 0 0 0-.259-.099z"/>
            </svg>
          ),
        };
      case 'exa':
        return {
          label: 'EXA NEURAL',
          color: 'text-cyan-300',
          borderColor: 'border-cyan-500/40',
          bgGlow: 'bg-cyan-500/10',
          icon: (
            <svg className="w-5 h-5 text-cyan-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"/>
              <path d="M12 2a14.5 14.5 0 0 0 0 20M2 12h20"/>
            </svg>
          ),
        };
      case 'tavily':
        return {
          label: 'TAVILY SEARCH',
          color: 'text-emerald-400',
          borderColor: 'border-emerald-500/40',
          bgGlow: 'bg-emerald-500/10',
          icon: (
            <svg className="w-5 h-5 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polygon points="12 2 2 7 12 12 22 7 12 2"/>
              <polyline points="2 17 12 22 22 17"/>
              <polyline points="2 12 12 17 22 12"/>
            </svg>
          ),
        };
      case 'wikipedia':
        return {
          label: 'WIKIPEDIA ARCHIVE',
          color: 'text-amber-300',
          borderColor: 'border-amber-500/40',
          bgGlow: 'bg-amber-500/10',
          icon: (
            <span className="font-serif font-black text-amber-300 text-lg leading-none">W</span>
          ),
        };
      default:
        return {
          label: 'LIVE WEB INTEL',
          color: 'text-sky-400',
          borderColor: 'border-sky-500/40',
          bgGlow: 'bg-sky-500/10',
          icon: (
            <svg className="w-5 h-5 text-sky-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8"/>
              <line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
          ),
        };
    }
  };

  const meta = getPlatformMeta(platform);

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-6 right-6 z-50 pointer-events-auto transition-all duration-300 transform animate-in fade-in slide-in-from-bottom-2"
    >
      {/* 13 by 4 Glassroom Brick Format */}
      <div
        className={`w-[13rem] h-[4rem] rounded-xl backdrop-blur-md bg-slate-950/85 border ${meta.borderColor} ${meta.bgGlow} shadow-2xl p-2.5 flex items-center gap-2.5 select-none overflow-hidden relative`}
      >
        {/* Scanning Radar Ping Animation */}
        <div className="relative flex-shrink-0 w-9 h-9 rounded-lg bg-slate-900/90 border border-slate-700/50 flex items-center justify-center overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-tr from-transparent via-cyan-400/10 to-transparent animate-spin" />
          {meta.icon}
          <span className="absolute -top-0.5 -right-0.5 flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500" />
          </span>
        </div>

        {/* Intelligence Stream Content */}
        <div className="flex-1 min-w-0 flex flex-col justify-center">
          <div className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className={`text-[10px] font-mono font-bold tracking-wider uppercase truncate ${meta.color}`}>
              {meta.label}
            </span>
          </div>
          <div
            className="text-[11px] text-slate-200 font-medium truncate mt-0.5"
            title={query}
          >
            {query || 'Synthesizing global feeds...'}
          </div>
        </div>

        {/* Optional Dismiss button */}
        {onDismiss && (
          <button
            onClick={onDismiss}
            aria-label="Dismiss search notification"
            className="text-slate-400 hover:text-slate-100 text-xs px-1 py-0.5"
          >
            ×
          </button>
        )}
      </div>
    </div>
  );
};
