import React, { useState, useEffect } from 'react';
import { 
  X, 
  CheckCircle2, 
  AlertOctagon, 
  Clock, 
  FileText, 
  Layers, 
  Copy, 
  Check, 
  Filter,
  RefreshCw,
  ChevronDown,
  ChevronUp
} from 'lucide-react';

export default function StationDrawer({ station, onClose }) {
  const [activeTab, setActiveTab] = useState('synops'); // 'synops' | 'activity'
  const [activityRecords, setActivityRecords] = useState([]);
  const [isLoadingActivity, setIsLoadingActivity] = useState(false);
  const [selectedTypeFilter, setSelectedTypeFilter] = useState('ALL');
  const [copiedIndex, setCopiedIndex] = useState(null);
  const [expandedDuplicates, setExpandedDuplicates] = useState({});

  const toggleDuplicateExpand = (hour) => {
    setExpandedDuplicates(prev => ({
      ...prev,
      [hour]: !prev[hour]
    }));
  };

  useEffect(() => {
    if (!station) return;
    
    const fetchActivity = async () => {
      setIsLoadingActivity(true);
      try {
        const res = await fetch(`/api/station/${station.station_id}/activity`);
        if (res.ok) {
          const data = await res.json();
          setActivityRecords(data.records || []);
        }
      } catch (err) {
        console.error("Failed to fetch activity log:", err);
      } finally {
        setIsLoadingActivity(false);
      }
    };

    fetchActivity();
  }, [station]);

  if (!station) return null;

  const handleCopy = (text, idx) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(idx);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const filteredActivity = selectedTypeFilter === 'ALL'
    ? activityRecords
    : activityRecords.filter(r => r.type === selectedTypeFilter);

  const availableTypes = Array.from(new Set(activityRecords.map(r => r.type)));

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-black/40 backdrop-blur-sm transition-opacity">
      <div className="absolute inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-2xl bg-white dark:bg-[#161618] border-l border-apple-gray-200 dark:border-white/10 shadow-2xl flex flex-col">
          
          {/* Drawer Header */}
          <div className="p-6 border-b border-apple-gray-200/80 dark:border-white/10 bg-white/80 dark:bg-[#161618]/90">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <span className="w-10 h-10 rounded-2xl bg-apple-gray-900 dark:bg-apple-blue text-white font-mono font-bold text-sm flex items-center justify-center shadow-sm">
                  {station.station_id}
                </span>
                <div>
                  <h2 className="text-xl font-bold text-apple-gray-900 dark:text-white tracking-tight">
                    {station.station_name}
                  </h2>
                  <p className="text-xs text-apple-gray-500 dark:text-neutral-400 mt-0.5">
                    {station.state || station.region} • Required: {station.required_hours?.length || 8} synops/day
                  </p>
                </div>
              </div>

              <button
                onClick={onClose}
                className="p-2 rounded-xl text-apple-gray-400 hover:text-apple-gray-700 dark:hover:text-white hover:bg-apple-gray-100 dark:hover:bg-neutral-800 transition-all"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Tab Navigation */}
            <div className="flex items-center space-x-2 mt-5 border-b border-apple-gray-200/60 dark:border-white/10 pb-1">
              <button
                onClick={() => setActiveTab('synops')}
                className={`px-4 py-2 text-xs font-semibold rounded-lg transition-all flex items-center gap-2 ${
                  activeTab === 'synops'
                    ? 'bg-apple-gray-900 dark:bg-white text-white dark:text-neutral-900 shadow-sm'
                    : 'text-apple-gray-600 dark:text-neutral-400 hover:text-apple-gray-900 dark:hover:text-white hover:bg-apple-gray-100 dark:hover:bg-neutral-800'
                }`}
              >
                <Layers className="w-3.5 h-3.5" />
                Synoptic Observations Matrix
              </button>

              <button
                onClick={() => setActiveTab('activity')}
                className={`px-4 py-2 text-xs font-semibold rounded-lg transition-all flex items-center gap-2 ${
                  activeTab === 'activity'
                    ? 'bg-apple-gray-900 dark:bg-white text-white dark:text-neutral-900 shadow-sm'
                    : 'text-apple-gray-600 dark:text-neutral-400 hover:text-apple-gray-900 dark:hover:text-white hover:bg-apple-gray-100 dark:hover:bg-neutral-800'
                }`}
              >
                <FileText className="w-3.5 h-3.5" />
                All Station Messages ({activityRecords.length})
              </button>
            </div>
          </div>

          {/* Drawer Body */}
          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            
            {/* TAB 1: SYNOP Observation Breakdown */}
            {activeTab === 'synops' && (
              <div className="space-y-4">
                <div className="text-xs text-apple-gray-500 dark:text-neutral-400 flex items-center justify-between pb-2 border-b border-apple-gray-100 dark:border-white/5">
                  <span>8 Scheduled Synoptic Slots (UTC & IST)</span>
                  <span className="font-semibold text-apple-gray-700 dark:text-neutral-200">{station.status_desc}</span>
                </div>

                {Object.entries(station.slots || {}).map(([hour, slot]) => (
                  <div 
                    key={hour}
                    className={`p-4 rounded-2xl border transition-all ${
                      slot.status === 'ON_TIME'
                        ? 'bg-emerald-50/40 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-800/40'
                        : slot.status === 'EARLY'
                          ? 'bg-amber-50/40 dark:bg-amber-950/20 border-amber-200 dark:border-amber-800/40'
                          : slot.status === 'LATE' || slot.status === 'VERY_LATE' || slot.status === 'MISSING'
                            ? 'bg-rose-50/50 dark:bg-rose-950/20 border-rose-300 dark:border-rose-800/50'
                            : 'bg-white dark:bg-neutral-800/60 border-apple-gray-200 dark:border-white/5'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <span className="text-sm font-bold font-mono text-apple-gray-900 dark:text-white">
                          {slot.utc_label}
                        </span>
                        <span className="text-xs text-apple-gray-400 font-mono">/</span>
                        <span className="text-xs font-mono font-medium text-apple-blue-dark dark:text-apple-blue">
                          {slot.ist_label}
                        </span>
                      </div>

                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                        slot.severity === 'green'
                          ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/70 dark:text-emerald-300'
                          : slot.severity === 'yellow'
                            ? 'bg-amber-100 text-amber-800 dark:bg-amber-950/70 dark:text-amber-300'
                            : slot.severity === 'red'
                              ? 'bg-red-100 text-apple-red dark:bg-red-950/70 dark:text-red-300'
                              : 'bg-apple-gray-100 text-apple-gray-500 dark:bg-neutral-700 dark:text-neutral-400'
                      }`}>
                        {slot.badge_text}
                      </span>
                    </div>

                    {/* Report details if received */}
                    {slot.received && slot.primary_report ? (
                      <div className="mt-3 bg-white/90 dark:bg-neutral-800 rounded-xl p-3 border border-apple-gray-200/70 dark:border-white/10">
                        <div className="flex items-center justify-between text-[11px] text-apple-gray-500 dark:text-neutral-400 mb-2">
                          <div className="flex items-center gap-2">
                            <span>Origin: <strong>{slot.primary_report.originating_center}</strong></span>
                            <span>•</span>
                            <span>Bulletin: <strong>{slot.primary_report.bulletin_id}</strong></span>
                            <span>•</span>
                            <span>Seq: <strong>{slot.primary_report.seq_num}</strong></span>
                          </div>
                          {slot.duplicate_count > 0 && (
                            <button
                              onClick={() => toggleDuplicateExpand(hour)}
                              className={`inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-md transition-all ${
                                slot.has_discrepancy
                                  ? 'bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300 border border-amber-300 dark:border-amber-800'
                                  : 'bg-apple-blue/10 dark:bg-apple-blue/20 text-apple-blue hover:bg-apple-blue/20'
                              }`}
                              title="Click to view all transmissions"
                            >
                              <Layers className="w-3 h-3" />
                              <span>{slot.duplicate_badge || `${slot.duplicate_count + 1} transmissions`}</span>
                              {expandedDuplicates[hour] ? <ChevronUp className="w-3 h-3 ml-0.5" /> : <ChevronDown className="w-3 h-3 ml-0.5" />}
                            </button>
                          )}
                        </div>

                        {/* Duplicate description banner */}
                        {slot.duplicate_count > 0 && slot.duplicate_description && (
                          <div className="mb-2 text-[11px] text-apple-gray-600 dark:text-neutral-300 bg-apple-gray-100/70 dark:bg-neutral-900/60 px-2.5 py-1 rounded-md flex items-center justify-between">
                            <span>{slot.duplicate_description}</span>
                            <span className="text-[10px] text-apple-blue font-medium">SLA scored on earliest Seq {slot.earliest_report?.seq_num}</span>
                          </div>
                        )}

                        <div className="relative group">
                          <pre className="font-mono text-xs text-apple-gray-800 dark:text-neutral-200 bg-apple-gray-50 dark:bg-neutral-900 p-2.5 rounded-lg overflow-x-auto border border-apple-gray-200/60 dark:border-white/5 leading-relaxed">
                            {slot.primary_report.raw_text}
                          </pre>
                          <button
                            onClick={() => handleCopy(slot.primary_report.raw_text, hour)}
                            className="absolute top-2 right-2 p-1.5 rounded-md bg-white dark:bg-neutral-800 border border-apple-gray-200 dark:border-white/10 text-apple-gray-600 dark:text-neutral-300 hover:text-apple-gray-900 opacity-0 group-hover:opacity-100 transition-all shadow-sm"
                            title="Copy SYNOP text"
                          >
                            {copiedIndex === hour ? <Check className="w-3.5 h-3.5 text-apple-green" /> : <Copy className="w-3.5 h-3.5" />}
                          </button>
                        </div>

                        {/* Expandable all transmissions audit list */}
                        {slot.duplicate_count > 0 && expandedDuplicates[hour] && slot.reports && (
                          <div className="mt-3 pt-3 border-t border-apple-gray-200/60 dark:border-white/10 space-y-2">
                            <div className="text-[11px] font-semibold text-apple-gray-600 dark:text-neutral-400 flex items-center justify-between">
                              <span>Transmission Audit Trail ({slot.transmission_count} received):</span>
                              <span className="text-[10px] text-apple-gray-400">Chronological Order</span>
                            </div>
                            {slot.reports.map((rep, rIdx) => (
                              <div 
                                key={rIdx} 
                                className={`p-2.5 rounded-lg border text-xs transition-all ${
                                  rep.is_primary 
                                    ? 'bg-blue-50/60 dark:bg-blue-950/20 border-blue-200 dark:border-blue-800' 
                                    : 'bg-neutral-50 dark:bg-neutral-900/40 border-neutral-200 dark:border-neutral-800'
                                }`}
                              >
                                <div className="flex items-center justify-between text-[11px] text-apple-gray-500 dark:text-neutral-400 mb-1.5">
                                  <div className="flex items-center gap-1.5">
                                    <span className="font-semibold text-apple-gray-800 dark:text-neutral-200">
                                      #{rep.transmission_index || (rIdx + 1)}:
                                    </span>
                                    <span>Bulletin <strong>{rep.bulletin_id}</strong> (Seq {rep.seq_num})</span>
                                    <span>via <strong>{rep.originating_center}</strong></span>
                                    {rep.is_primary && (
                                      <span className="ml-1 px-1.5 py-0.2 bg-emerald-100 dark:bg-emerald-950/80 text-emerald-700 dark:text-emerald-300 rounded font-semibold text-[10px]">
                                        Authoritative
                                      </span>
                                    )}
                                    {rep.is_collective && (
                                      <span className="px-1.5 py-0.2 bg-neutral-200 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300 rounded text-[10px]">
                                        Collective
                                      </span>
                                    )}
                                  </div>
                                  <span className="font-mono text-[10px] text-apple-gray-400">Header: {rep.header_timestamp}</span>
                                </div>
                                <pre className="font-mono text-[11px] text-apple-gray-700 dark:text-neutral-300 overflow-x-auto whitespace-pre-wrap leading-relaxed">
                                  {rep.raw_text}
                                </pre>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="mt-2 text-xs text-apple-gray-400 dark:text-neutral-500 italic">
                        {slot.status === 'NOT_SCHEDULED' ? 'Not configured for observation' : 'No synoptic report received in this bulletin cycle'}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* TAB 2: Full Activity Log & Filter */}
            {activeTab === 'activity' && (
              <div className="space-y-4">
                
                {/* Type Filter Chips */}
                <div className="flex flex-wrap items-center gap-1.5 pb-2 border-b border-apple-gray-200/60 dark:border-white/10">
                  <span className="text-xs text-apple-gray-500 dark:text-neutral-400 mr-1 flex items-center gap-1">
                    <Filter className="w-3 h-3" /> Filter:
                  </span>
                  <button
                    onClick={() => setSelectedTypeFilter('ALL')}
                    className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${
                      selectedTypeFilter === 'ALL'
                        ? 'bg-apple-gray-900 dark:bg-white text-white dark:text-neutral-900 shadow-sm'
                        : 'bg-apple-gray-100 dark:bg-neutral-800 text-apple-gray-600 dark:text-neutral-400 hover:bg-apple-gray-200'
                    }`}
                  >
                    All Messages ({activityRecords.length})
                  </button>
                  {availableTypes.map((t) => (
                    <button
                      key={t}
                      onClick={() => setSelectedTypeFilter(t)}
                      className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${
                        selectedTypeFilter === t
                          ? 'bg-apple-blue text-white shadow-sm'
                          : 'bg-apple-gray-100 dark:bg-neutral-800 text-apple-gray-600 dark:text-neutral-400 hover:bg-apple-gray-200'
                      }`}
                    >
                      {t}
                    </button>
                  ))}
                </div>

                {isLoadingActivity ? (
                  <div className="text-center py-10">
                    <RefreshCw className="w-6 h-6 animate-spin text-apple-blue mx-auto mb-2" />
                    <p className="text-xs text-apple-gray-500">Loading records...</p>
                  </div>
                ) : filteredActivity.length === 0 ? (
                  <div className="text-center py-10 text-apple-gray-400 text-xs">
                    No records found for this filter.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {filteredActivity.map((rec, idx) => (
                      <div 
                        key={idx}
                        className="bg-white dark:bg-neutral-800 rounded-2xl p-3.5 border border-apple-gray-200/80 dark:border-white/10 shadow-sm"
                      >
                        <div className="flex items-center justify-between mb-2">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold ${
                            rec.type.includes('SYNOP') 
                              ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/40' 
                              : rec.type.includes('TEMP')
                                ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800/40'
                                : rec.type.includes('PILOT')
                                  ? 'bg-cyan-50 text-cyan-700 dark:bg-cyan-950/60 dark:text-cyan-300 border border-cyan-200 dark:border-cyan-800/40'
                                  : 'bg-apple-gray-100 text-apple-gray-700 dark:bg-neutral-700 dark:text-neutral-300'
                          }`}>
                            {rec.type}
                          </span>

                          <div className="flex items-center space-x-2 text-[11px] font-mono text-apple-gray-500 dark:text-neutral-400">
                            <span>{rec.bulletin_id}</span>
                            <span>•</span>
                            <span>{rec.originating_center}</span>
                            <span>•</span>
                            <span>{rec.timestamp}</span>
                          </div>
                        </div>

                        <div className="relative group">
                          <pre className="font-mono text-xs text-apple-gray-800 dark:text-neutral-200 bg-apple-gray-50 dark:bg-neutral-900 p-2.5 rounded-lg overflow-x-auto border border-apple-gray-200/60 dark:border-white/5 leading-relaxed whitespace-pre-wrap">
                            {rec.raw_text}
                          </pre>
                          <button
                            onClick={() => handleCopy(rec.raw_text, `act-${idx}`)}
                            className="absolute top-2 right-2 p-1.5 rounded-md bg-white dark:bg-neutral-800 border border-apple-gray-200 dark:border-white/10 text-apple-gray-600 dark:text-neutral-300 hover:text-apple-gray-900 opacity-0 group-hover:opacity-100 transition-all shadow-sm"
                            title="Copy snippet"
                          >
                            {copiedIndex === `act-${idx}` ? <Check className="w-3.5 h-3.5 text-apple-green" /> : <Copy className="w-3.5 h-3.5" />}
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

              </div>
            )}

          </div>

        </div>
      </div>
    </div>
  );
}
