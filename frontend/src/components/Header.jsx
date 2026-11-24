import React, { useState, useEffect } from 'react';
import { 
  RefreshCw, 
  Volume2, 
  VolumeX, 
  SlidersHorizontal, 
  Radio, 
  Clock,
  Sun,
  Moon,
  Zap,
  MoonStar
} from 'lucide-react';

export default function Header({ 
  statusData, 
  onFetchNow, 
  isFetching, 
  onOpenSettings,
  isAudioEnabled,
  onToggleAudio,
  theme,
  onToggleTheme
}) {
  const [currentUtc, setCurrentUtc] = useState('');
  const [currentIst, setCurrentIst] = useState('');

  // Dual clock ticker
  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      // UTC
      const utcHours = String(now.getUTCHours()).padStart(2, '0');
      const utcMins = String(now.getUTCMinutes()).padStart(2, '0');
      const utcSecs = String(now.getUTCSeconds()).padStart(2, '0');
      setCurrentUtc(`${utcHours}:${utcMins}:${utcSecs} UTC`);

      // IST (UTC + 5:30)
      const istDate = new Date(now.getTime() + (5.5 * 60 * 60 * 1000));
      const istHours = String(istDate.getUTCHours()).padStart(2, '0');
      const istMins = String(istDate.getUTCMinutes()).padStart(2, '0');
      const istSecs = String(istDate.getUTCSeconds()).padStart(2, '0');
      setCurrentIst(`${istHours}:${istMins}:${istSecs} IST`);
    };

    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  const formatLastFetch = (iso) => {
    if (!iso) return 'Just now';
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return 'Recent';
    }
  };

  const dynamicWindow = statusData?.dynamic_window;
  const isActiveWindow = dynamicWindow?.is_active;

  return (
    <header className="sticky top-0 z-40 glass-header border-b border-apple-gray-200/60 dark:border-white/10 transition-colors duration-200">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-2.5">
        <div className="flex items-center justify-between gap-3">
          
          {/* 1. Left: Brand & Live Indicator */}
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-xl bg-apple-gray-900 dark:bg-apple-blue flex items-center justify-center text-white shadow-sm">
              <Radio className="w-4 h-4 text-apple-blue dark:text-white" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h1 className="text-sm font-semibold text-apple-gray-900 dark:text-white tracking-tight">
                  SYNOP Monitor
                </h1>
                <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 border border-emerald-200/60 dark:border-emerald-800/40">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1 animate-pulse"></span>
                  AMSS Delhi Live
                </span>
              </div>
              <p className="text-[11px] text-apple-gray-400 dark:text-neutral-400">
                Checked {formatLastFetch(statusData?.last_fetch_time)}
              </p>
            </div>
          </div>

          {/* 2. Top-Center: Settings & Stations Hub Button (As requested by user!) */}
          <div className="flex items-center">
            <button
              onClick={onOpenSettings}
              className="inline-flex items-center px-3.5 py-1.5 rounded-full bg-apple-gray-100 hover:bg-apple-gray-200/80 dark:bg-neutral-800/80 dark:hover:bg-neutral-700/80 border border-apple-gray-200/80 dark:border-white/10 text-apple-gray-800 dark:text-neutral-200 text-xs font-semibold shadow-sm active:scale-95 transition-all gap-1.5"
              title="Open Settings, Station Watchlist, and Dynamic Polling Rules"
            >
              <SlidersHorizontal className="w-3.5 h-3.5 text-apple-blue" />
              <span>Settings & Stations</span>
              <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-apple-blue/10 dark:bg-apple-blue/20 text-apple-blue font-mono font-bold">
                {statusData?.total_stations_monitored || 16}
              </span>
            </button>
          </div>

          {/* 3. Right: Dynamic Window, Dual Clocks, Theme, Audio, Refresh */}
          <div className="flex items-center space-x-2">
            
            {/* Dynamic Synoptic Window Badge */}
            <div 
              title={dynamicWindow?.description || "Dynamic Synoptic Window Polling"}
              className={`hidden md:inline-flex items-center px-2.5 py-1 rounded-full text-[11px] font-medium border transition-all ${
                isActiveWindow
                  ? 'bg-amber-50 dark:bg-amber-950/40 border-amber-300/80 dark:border-amber-700/50 text-amber-800 dark:text-amber-300'
                  : 'bg-apple-gray-100/90 dark:bg-neutral-800/70 border-apple-gray-200 dark:border-white/5 text-apple-gray-600 dark:text-neutral-400'
              }`}
            >
              {isActiveWindow ? (
                <Zap className="w-3 h-3 mr-1 text-amber-500 animate-pulse" />
              ) : (
                <MoonStar className="w-3 h-3 mr-1 text-apple-gray-400" />
              )}
              <span>{isActiveWindow ? `${dynamicWindow.cycle} (1m poll)` : 'Idle (30m)'}</span>
            </div>

            {/* Dual Clock Pill */}
            <div className="hidden sm:flex items-center space-x-1.5 bg-apple-gray-100/80 dark:bg-neutral-800/80 rounded-full px-3 py-1 text-xs font-mono text-apple-gray-700 dark:text-neutral-300 border border-apple-gray-200/50 dark:border-white/5">
              <Clock className="w-3.5 h-3.5 text-apple-gray-400 mr-0.5" />
              <span>{currentUtc || '--:-- UTC'}</span>
              <span className="text-apple-gray-300 dark:text-neutral-600">•</span>
              <span className="font-semibold text-apple-blue-dark dark:text-apple-blue">{currentIst || '--:-- IST'}</span>
            </div>

            {/* Dark Mode Toggle */}
            <button
              onClick={onToggleTheme}
              title={theme === 'dark' ? "Switch to Light Mode" : "Switch to Dark Mode"}
              className="p-1.5 rounded-full text-xs text-apple-gray-600 dark:text-neutral-300 hover:bg-apple-gray-100 dark:hover:bg-neutral-800 transition-all"
            >
              {theme === 'dark' ? (
                <Sun className="w-4 h-4 text-amber-400" />
              ) : (
                <Moon className="w-4 h-4 text-apple-gray-700" />
              )}
            </button>

            {/* Audio Chime Button */}
            <button
              onClick={onToggleAudio}
              title={isAudioEnabled ? "Sound alerts active" : "Sound alerts muted"}
              className={`p-1.5 rounded-full text-xs transition-all ${
                isAudioEnabled 
                  ? 'text-apple-blue hover:bg-apple-blue/10' 
                  : 'text-apple-gray-400 dark:text-neutral-500 hover:bg-apple-gray-100 dark:hover:bg-neutral-800'
              }`}
            >
              {isAudioEnabled ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
            </button>

            {/* Fetch Now Primary Button */}
            <button
              onClick={onFetchNow}
              disabled={isFetching}
              className="inline-flex items-center px-3 py-1.5 rounded-full bg-apple-blue hover:bg-apple-blue-dark active:scale-[0.98] text-white text-xs font-semibold shadow-sm transition-all disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${isFetching ? 'animate-spin' : ''}`} />
              {isFetching ? 'Checking...' : 'Refresh'}
            </button>

          </div>

        </div>
      </div>
    </header>
  );
}
