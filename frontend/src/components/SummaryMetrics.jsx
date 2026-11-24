import React from 'react';
import { CheckCircle2, AlertOctagon, Clock, Zap } from 'lucide-react';

export default function SummaryMetrics({ statusData, onFilterBySeverity }) {
  const redAlerts = statusData?.red_alert_stations || 0;
  const onTimeSlots = statusData?.total_on_time_slots || 0;
  const totalStations = statusData?.total_stations_monitored || 0;
  const totalMissing = statusData?.total_missing_slots || 0;
  const totalLate = statusData?.total_late_slots || 0;
  const dynamicWindow = statusData?.dynamic_window;

  const hasIssues = redAlerts > 0;

  return (
    <div className="mb-6">
      
      {/* Calm Human Status Banner */}
      <div className={`p-5 rounded-3xl border transition-all ${
        hasIssues 
          ? 'bg-gradient-to-b from-red-50/90 to-white dark:from-red-950/30 dark:to-[#1C1C1E] border-red-200/80 dark:border-red-900/50 shadow-sm' 
          : 'bg-gradient-to-b from-emerald-50/70 to-white dark:from-emerald-950/20 dark:to-[#1C1C1E] border-emerald-200/70 dark:border-emerald-900/40 shadow-sm'
      }`}>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          
          <div className="flex items-start sm:items-center space-x-3.5">
            <div className={`w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0 ${
              hasIssues ? 'bg-apple-red text-white shadow-sm' : 'bg-emerald-600 dark:bg-emerald-500 text-white shadow-sm'
            }`}>
              {hasIssues ? <AlertOctagon className="w-5 h-5" /> : <CheckCircle2 className="w-5 h-5" />}
            </div>
            <div>
              <h2 className="text-base font-semibold text-apple-gray-900 dark:text-white tracking-tight">
                {hasIssues 
                  ? `${redAlerts} station${redAlerts > 1 ? 's' : ''} require attention right now` 
                  : 'All stations are reporting on schedule'}
              </h2>
              <p className="text-xs text-apple-gray-500 dark:text-neutral-400 mt-0.5">
                {hasIssues
                  ? `${totalMissing} observation slot${totalMissing > 1 ? 's are' : ' is'} missing and ${totalLate} late. Check the alerts below.`
                  : `All ${totalStations} monitored meteorological stations have submitted their observations on time.`}
              </p>
              {dynamicWindow && (
                <div className="flex items-center gap-1.5 mt-2 text-[11px] font-medium text-apple-gray-600 dark:text-neutral-300">
                  <span className={`w-1.5 h-1.5 rounded-full ${dynamicWindow.is_active ? 'bg-amber-500 animate-ping' : 'bg-apple-gray-400'}`}></span>
                  <span>{dynamicWindow.description}</span>
                </div>
              )}
            </div>
          </div>

          {/* Quick Metrics Pills */}
          <div className="flex items-center space-x-2 pt-2 sm:pt-0 border-t sm:border-t-0 border-apple-gray-100 dark:border-white/5">
            {hasIssues && (
              <button
                onClick={() => onFilterBySeverity('red')}
                className="px-3 py-1.5 rounded-full bg-apple-red text-white text-xs font-semibold shadow-sm hover:opacity-90 transition-all flex items-center gap-1.5"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse"></span>
                View {redAlerts} Issue{redAlerts > 1 ? 's' : ''}
              </button>
            )}

            <button
              onClick={() => onFilterBySeverity('green')}
              className="px-3 py-1.5 rounded-full bg-emerald-50 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800/60 text-xs font-medium hover:bg-emerald-100 transition-all"
            >
              {onTimeSlots} On Time
            </button>

            <button
              onClick={() => onFilterBySeverity('ALL')}
              className="px-3 py-1.5 rounded-full bg-apple-gray-100 dark:bg-neutral-800 text-apple-gray-700 dark:text-neutral-300 border border-transparent dark:border-white/5 text-xs font-medium hover:bg-apple-gray-200 transition-all"
            >
              {totalStations} Stations Total
            </button>
          </div>

        </div>
      </div>

    </div>
  );
}
