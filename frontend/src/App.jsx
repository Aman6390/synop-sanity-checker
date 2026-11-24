import React, { useState, useEffect, useRef } from 'react';
import Header from './components/Header';
import SummaryMetrics from './components/SummaryMetrics';
import FilterBar from './components/FilterBar';
import StationGrid from './components/StationGrid';
import StationDrawer from './components/StationDrawer';
import SettingsModal from './components/SettingsModal';
import { audioAlert } from './utils/audioAlert';
import { AlertCircle, RefreshCw } from 'lucide-react';

export default function App() {
  const [statusData, setStatusData] = useState(null);
  const [stations, setStations] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isFetchingNow, setIsFetchingNow] = useState(false);
  const [error, setError] = useState(null);

  // Theme: default to dark for modern Apple aesthetic
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('theme') || 'dark';
  });

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedSeverity, setSelectedSeverity] = useState('ALL');
  const [selectedRegion, setSelectedRegion] = useState('ALL');

  // Modals & Drawers
  const [selectedStation, setSelectedStation] = useState(null);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  // Settings
  const [pollInterval, setPollInterval] = useState(60);
  const [useDynamicPolling, setUseDynamicPolling] = useState(true);
  const [isAudioEnabled, setIsAudioEnabled] = useState(true);

  const prevRedCountRef = useRef(0);

  // Apply dark class to <html> element
  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
    localStorage.setItem('theme', theme);
  }, [theme]);

  const handleToggleTheme = () => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark');
  };

  const [isAlarmSilenced, setIsAlarmSilenced] = useState(false);
  const isFirstLoadRef = useRef(true);

  // Fetch data
  const loadData = async (showLoading = false) => {
    if (showLoading) setIsLoading(true);
    setError(null);
    try {
      const [statusRes, stationsRes] = await Promise.all([
        fetch('/api/status'),
        fetch('/api/stations')
      ]);

      if (!statusRes.ok || !stationsRes.ok) {
        throw new Error('Failed to connect to backend service');
      }

      const sData = await statusRes.json();
      const stnsData = await stationsRes.json();

      setStatusData(sData);
      setStations(stnsData.stations || []);
      setUseDynamicPolling(sData.use_dynamic_polling ?? true);
      setPollInterval(sData.poll_interval_seconds || 60);

      const currentRed = sData.red_alert_stations || 0;
      
      // On initial launch or whenever red alerts appear/increase, fire critical alert alarm
      if (currentRed > 0 && !isAlarmSilenced) {
        if (isFirstLoadRef.current || currentRed > prevRedCountRef.current) {
          audioAlert.playAlarm();
        }
      }
      isFirstLoadRef.current = false;
      prevRedCountRef.current = currentRed;

    } catch (err) {
      console.error(err);
      setError(err.message || 'Error connecting to backend');
    } finally {
      if (showLoading) setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData(true);
    // Background polling loop
    const timer = setInterval(() => {
      loadData(false);
    }, pollInterval * 1000);

    return () => clearInterval(timer);
  }, [pollInterval]);

  const handleFetchNow = async () => {
    setIsFetchingNow(true);
    try {
      const res = await fetch('/api/fetch-now', { method: 'POST' });
      if (res.ok) {
        audioAlert.playChime('success');
        await loadData(false);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setIsFetchingNow(false);
    }
  };

  const handleToggleDynamicPolling = async () => {
    const nextVal = !useDynamicPolling;
    setUseDynamicPolling(nextVal);
    try {
      await fetch('/api/poll-settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ use_dynamic_polling: nextVal, is_polling: true })
      });
      await loadData(false);
    } catch (err) {
      console.error(err);
    }
  };

  const handleUpdatePollInterval = async (val) => {
    setPollInterval(val);
    try {
      await fetch('/api/poll-settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ interval: val, is_polling: true })
      });
      await loadData(false);
    } catch (err) {
      console.error(err);
    }
  };

  const handleToggleAudio = () => {
    const nextVal = !isAudioEnabled;
    setIsAudioEnabled(nextVal);
    audioAlert.setEnabled(nextVal);
    if (nextVal) {
      audioAlert.playChime('success');
    }
  };

  const handleAddOrUpdateStation = async (stationPayload) => {
    const res = await fetch('/api/stations/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(stationPayload)
    });
    if (!res.ok) throw new Error('Failed to update station');
    await loadData(false);
  };

  const handleDeleteStation = async (stationId) => {
    const res = await fetch(`/api/stations/config/${stationId}`, {
      method: 'DELETE'
    });
    if (!res.ok) throw new Error('Failed to delete station');
    await loadData(false);
  };

  const handleUploadData = async (rawContent) => {
    const res = await fetch('/api/upload-bulletin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: rawContent })
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Upload failed');
    }
    const data = await res.json();
    audioAlert.playChime('success');
    await loadData(false);
    return data;
  };

  // Filter stations
  const regions = Array.from(new Set(stations.map(s => s.region || s.state).filter(Boolean)));

  const filteredStations = stations.filter(stn => {
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchId = stn.station_id?.toLowerCase().includes(q);
      const matchName = stn.station_name?.toLowerCase().includes(q);
      const matchState = stn.state?.toLowerCase().includes(q);
      if (!matchId && !matchName && !matchState) return false;
    }

    if (selectedSeverity !== 'ALL') {
      if (stn.overall_severity !== selectedSeverity) return false;
    }

    if (selectedRegion !== 'ALL') {
      if (stn.region !== selectedRegion && stn.state !== selectedRegion) return false;
    }

    return true;
  });

  const filterCounts = {
    all: stations.length,
    red: stations.filter(s => s.overall_severity === 'red').length,
    green: stations.filter(s => s.overall_severity === 'green').length,
    yellow: stations.filter(s => s.overall_severity === 'yellow').length
  };

  return (
    <div className="min-h-screen flex flex-col bg-apple-gray-50/80 dark:bg-[#000000] text-apple-gray-900 dark:text-neutral-100 transition-colors duration-200">
      
      {/* Sticky Apple Header with Top-Center Settings */}
      <Header
        statusData={statusData}
        onFetchNow={handleFetchNow}
        isFetching={isFetchingNow}
        onOpenSettings={() => setIsSettingsOpen(true)}
        isAudioEnabled={isAudioEnabled}
        onToggleAudio={handleToggleAudio}
        theme={theme}
        onToggleTheme={handleToggleTheme}
      />

      {/* Main Content Area */}
      <main className="flex-1 max-w-6xl w-full mx-auto px-4 sm:px-6 py-6">
        
        {/* Error notification banner if any */}
        {error && (
          <div className="mb-5 p-4 rounded-2xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/60 text-apple-red dark:text-red-300 flex items-center justify-between text-xs font-medium shadow-sm">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
            <button 
              onClick={() => loadData(true)} 
              className="text-xs underline hover:text-red-800 dark:hover:text-red-200"
            >
              Retry
            </button>
          </div>
        )}

        {/* Critical Alarm Banner on Launch / Alarm Active */}
        {statusData?.red_alert_stations > 0 && (
          <div className="mb-5 p-3.5 rounded-2xl bg-red-500/10 dark:bg-red-950/40 border border-red-300 dark:border-red-800/80 flex items-center justify-between text-xs animate-pulse">
            <div className="flex items-center space-x-2.5">
              <span className="w-2.5 h-2.5 rounded-full bg-apple-red animate-ping"></span>
              <span className="font-semibold text-apple-red dark:text-red-300">
                🚨 Critical Alert: {statusData.red_alert_stations} station(s) have late or missing SYNOP observations!
              </span>
            </div>
            <div className="flex items-center space-x-2">
              <button
                onClick={() => {
                  if (isAlarmSilenced) {
                    setIsAlarmSilenced(false);
                    audioAlert.playAlarm();
                  } else {
                    setIsAlarmSilenced(true);
                  }
                }}
                className="px-3 py-1 rounded-xl bg-apple-red text-white font-medium hover:bg-red-600 transition-all text-[11px]"
              >
                {isAlarmSilenced ? 'Re-enable Alarm' : 'Silence Alarm'}
              </button>
            </div>
          </div>
        )}

        {/* 1. Calm Hero Summary Banner */}
        <SummaryMetrics 
          statusData={statusData} 
          onFilterBySeverity={(sev) => setSelectedSeverity(sev)}
        />

        {/* 2. Filter & Search Bar */}
        <FilterBar
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          selectedSeverity={selectedSeverity}
          onSelectSeverity={setSelectedSeverity}
          selectedRegion={selectedRegion}
          onSelectRegion={setSelectedRegion}
          regions={regions}
          counts={filterCounts}
        />

        {/* 3. Streamlined Station Grid (Attention-First) */}
        {isLoading ? (
          <div className="py-20 text-center bg-white dark:bg-[#1C1C1E] rounded-3xl border border-apple-gray-200/80 dark:border-white/10">
            <RefreshCw className="w-8 h-8 animate-spin text-apple-blue mx-auto mb-3" />
            <p className="text-sm font-semibold text-apple-gray-800 dark:text-neutral-200">Connecting to AMSS Delhi & Evaluating SYNOPs...</p>
            <p className="text-xs text-apple-gray-400 mt-1">Applying observation schedules and deduplicating feeds</p>
          </div>
        ) : (
          <StationGrid
            stations={filteredStations}
            onSelectStation={(stn) => setSelectedStation(stn)}
          />
        )}

      </main>

      {/* Footer */}
      <footer className="border-t border-apple-gray-200/70 dark:border-white/5 bg-white/40 dark:bg-[#121214]/40 py-4 text-center text-xs text-apple-gray-400 dark:text-neutral-500">
        <p>IMD SYNOP Sanity & SLA Timeliness Monitor • WMO FM-12 Code Standard • AMSS Delhi Ingestion</p>
      </footer>

      {/* Slide-over Station Activity Drawer */}
      <StationDrawer
        station={selectedStation}
        onClose={() => setSelectedStation(null)}
      />

      {/* Centralized Settings & Stations Hub Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        stations={stations}
        onAddOrUpdateStation={handleAddOrUpdateStation}
        onDeleteStation={handleDeleteStation}
        statusData={statusData}
        pollInterval={pollInterval}
        onUpdatePollInterval={handleUpdatePollInterval}
        useDynamicPolling={useDynamicPolling}
        onToggleDynamicPolling={handleToggleDynamicPolling}
        onUploadData={handleUploadData}
        theme={theme}
        onToggleTheme={handleToggleTheme}
      />

    </div>
  );
}
