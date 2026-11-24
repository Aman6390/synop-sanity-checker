import React, { useState } from 'react';
import { 
  CheckCircle2, 
  AlertOctagon, 
  Clock, 
  ChevronRight, 
  AlertCircle
} from 'lucide-react';

const SYNOPTIC_HOURS = ["0000", "0300", "0600", "0900", "1200", "1500", "1800", "2100"];

export default function StationGrid({ stations, onSelectStation }) {
  const [hoveredSlot, setHoveredSlot] = useState(null);

  if (!stations || stations.length === 0) {
    return (
      <div className="bg-white dark:bg-[#1C1C1E] rounded-3xl border border-apple-gray-200/80 dark:border-white/10 p-12 text-center shadow-sm">
        <AlertCircle className="w-8 h-8 text-apple-gray-400 mx-auto mb-2.5" />
        <h3 className="text-sm font-semibold text-apple-gray-800 dark:text-neutral-200">No stations match criteria</h3>
        <p className="text-xs text-apple-gray-400 mt-1 max-w-sm mx-auto">
          Adjust your filters, search terms, or add stations via the top-center settings menu.
        </p>
      </div>
    );
  }

  // Attention-First Sorting: Put Red Alert stations first!
  const attentionStations = stations.filter(s => s.overall_severity === 'red');
  const normalStations = stations.filter(s => s.overall_severity !== 'red');

  const renderStationCard = (stn) => {
    const isRed = stn.overall_severity === 'red';
    const isYellow = stn.overall_severity === 'yellow';

    return (
      <div 
        key={stn.station_id}
        onClick={() => onSelectStation(stn)}
        className={`group bg-white dark:bg-[#1C1C1E] rounded-2xl border p-4 transition-all duration-150 cursor-pointer hover:shadow-apple-hover ${
          isRed 
            ? 'border-red-300 dark:border-red-800/80 bg-gradient-to-r from-red-50/50 via-white to-white dark:from-red-950/20 dark:via-[#1C1C1E] dark:to-[#1C1C1E]' 
            : isYellow
              ? 'border-amber-200 dark:border-amber-700/60 hover:border-amber-300'
              : 'border-apple-gray-200/70 dark:border-white/10 hover:border-apple-gray-300 dark:hover:border-white/20'
        }`}
      >
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          
          {/* Left: Station Identity */}
          <div className="flex items-center space-x-3.5 min-w-[220px]">
            <span className={`w-10 h-10 rounded-xl flex items-center justify-center font-mono font-bold text-xs shadow-sm flex-shrink-0 ${
              isRed 
                ? 'bg-apple-red text-white' 
                : isYellow
                  ? 'bg-amber-500 text-white'
                  : 'bg-apple-gray-900 dark:bg-neutral-800 text-white'
            }`}>
              {stn.station_id}
            </span>
            <div>
              <div className="flex items-center space-x-2">
                <h3 className="text-sm font-semibold text-apple-gray-900 dark:text-white tracking-tight group-hover:text-apple-blue transition-colors">
                  {stn.station_name}
                </h3>
              </div>
              <p className="text-xs text-apple-gray-400 dark:text-neutral-400 mt-0.5">
                {stn.state || stn.region} • {stn.required_hours?.length || 8} synops/day
              </p>
            </div>
          </div>

          {/* Center: The Sleek 8-Pill Observation Timeline */}
          <div className="flex-1 max-w-xl">
            <div className="flex items-center justify-between sm:justify-start sm:space-x-2">
              {SYNOPTIC_HOURS.map((hour) => {
                const slot = stn.slots?.[hour];
                const hourShort = hour.slice(0, 2) + 'Z';
                const slotKey = `${stn.station_id}-${hour}`;

                let pillStyle = "bg-apple-gray-100 dark:bg-neutral-800 text-apple-gray-400 dark:text-neutral-500 border-apple-gray-200 dark:border-white/5";
                let statusLabel = "Awaiting";

                if (slot?.status === 'ON_TIME') {
                  pillStyle = "bg-emerald-500 dark:bg-emerald-600 text-white border-emerald-600 dark:border-emerald-500 shadow-sm";
                  statusLabel = "On Time";
                } else if (slot?.status === 'EARLY') {
                  pillStyle = "bg-amber-400 dark:bg-amber-500 text-white border-amber-500 shadow-sm";
                  statusLabel = "Early";
                } else if (slot?.status === 'LATE' || slot?.status === 'VERY_LATE') {
                  pillStyle = "bg-rose-500 text-white border-rose-600 shadow-sm animate-pulse";
                  statusLabel = slot.badge_text || "Late";
                } else if (slot?.status === 'MISSING' || slot?.status === 'LATE_OVERDUE') {
                  pillStyle = "bg-apple-red text-white border-red-700 shadow-sm animate-pulse font-bold";
                  statusLabel = "Missing";
                } else if (slot?.status === 'NOT_SCHEDULED') {
                  pillStyle = "bg-transparent text-apple-gray-300 dark:text-neutral-600 border-dashed border-apple-gray-200 dark:border-neutral-800";
                  statusLabel = "Not Scheduled";
                }

                return (
                  <div
                    key={hour}
                    onMouseEnter={() => setHoveredSlot({ key: slotKey, slot, hour })}
                    onMouseLeave={() => setHoveredSlot(null)}
                    className="relative flex flex-col items-center"
                  >
                    <div className={`px-2 py-1 rounded-lg border text-[11px] font-mono font-medium transition-all ${pillStyle}`}>
                      {hourShort}
                    </div>

                    {/* Interactive Tooltip on hover */}
                    {hoveredSlot?.key === slotKey && (
                      <div className="absolute bottom-full mb-2 z-30 px-2.5 py-1.5 rounded-xl bg-apple-gray-900 dark:bg-neutral-800 text-white text-[11px] font-sans shadow-xl border border-transparent dark:border-white/10 whitespace-nowrap pointer-events-none animate-in fade-in zoom-in-95">
                        <div className="font-semibold">{slot?.utc_label} ({slot?.ist_label})</div>
                        <div className="text-apple-gray-300 dark:text-neutral-300 text-[10px] mt-0.5">
                          Status: {statusLabel} {slot?.duplicate_count > 0 ? `(${slot.duplicate_count + 1}x ${slot?.duplicate_badge || 'Echo'})` : ''}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Right: Status Pill & Action */}
          <div className="flex items-center justify-between lg:justify-end space-x-3 pt-2 lg:pt-0 border-t lg:border-t-0 border-apple-gray-100 dark:border-white/5">
            <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold ${
              isRed 
                ? 'bg-red-100 dark:bg-red-950/60 text-apple-red dark:text-red-300 border border-red-200 dark:border-red-900/60' 
                : isYellow
                  ? 'bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-900/60'
                  : 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-900/60'
            }`}>
              {isRed && <AlertOctagon className="w-3.5 h-3.5 mr-1" />}
              {isYellow && <Clock className="w-3.5 h-3.5 mr-1" />}
              {!isRed && !isYellow && <CheckCircle2 className="w-3.5 h-3.5 mr-1" />}
              {stn.status_desc}
            </span>

            <span className="p-1 rounded-full text-apple-gray-400 group-hover:text-apple-gray-700 dark:group-hover:text-white group-hover:translate-x-0.5 transition-all">
              <ChevronRight className="w-4 h-4" />
            </span>
          </div>

        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      
      {/* 1. Attention-First Section */}
      {attentionStations.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-apple-red dark:text-red-400 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-apple-red animate-ping"></span>
              Needs Attention ({attentionStations.length})
            </h3>
            <span className="text-xs text-apple-gray-400 dark:text-neutral-500">
              Late or missing observations detected
            </span>
          </div>

          <div className="space-y-2.5">
            {attentionStations.map(renderStationCard)}
          </div>
        </section>
      )}

      {/* 2. Normal / Up-to-date Stations */}
      {normalStations.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-apple-gray-500 dark:text-neutral-400">
              Up to Date Stations ({normalStations.length})
            </h3>
            <span className="text-xs text-apple-gray-400 dark:text-neutral-500">
              All scheduled synops received on time
            </span>
          </div>

          <div className="space-y-2.5">
            {normalStations.map(renderStationCard)}
          </div>
        </section>
      )}

    </div>
  );
}
