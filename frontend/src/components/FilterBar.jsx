import React from 'react';
import { Search, Filter, X } from 'lucide-react';

export default function FilterBar({
  searchQuery,
  onSearchChange,
  selectedSeverity,
  onSelectSeverity,
  selectedRegion,
  onSelectRegion,
  regions,
  counts
}) {
  return (
    <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 mb-5">
      
      {/* Segmented Filter Pills */}
      <div className="inline-flex p-1 bg-apple-gray-200/60 dark:bg-neutral-800/80 rounded-xl space-x-1 shadow-inner">
        <button
          onClick={() => onSelectSeverity('ALL')}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150 ${
            selectedSeverity === 'ALL'
              ? 'bg-white dark:bg-neutral-700 text-apple-gray-900 dark:text-white shadow-sm'
              : 'text-apple-gray-600 dark:text-neutral-400 hover:text-apple-gray-900 dark:hover:text-white'
          }`}
        >
          All Stations
          <span className="ml-1.5 px-1.5 py-0.2 rounded-full text-[10px] bg-apple-gray-100 dark:bg-neutral-600 text-apple-gray-600 dark:text-neutral-300">
            {counts.all}
          </span>
        </button>

        <button
          onClick={() => onSelectSeverity('red')}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150 flex items-center gap-1 ${
            selectedSeverity === 'red'
              ? 'bg-apple-red text-white shadow-sm'
              : 'text-apple-red dark:text-red-400 hover:bg-apple-red/10'
          }`}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-current"></span>
          Extreme Alerts
          <span className={`ml-1 px-1.5 py-0.2 rounded-full text-[10px] ${
            selectedSeverity === 'red' ? 'bg-white/20 text-white' : 'bg-red-100 dark:bg-red-950/60 text-apple-red dark:text-red-300'
          }`}>
            {counts.red}
          </span>
        </button>

        <button
          onClick={() => onSelectSeverity('green')}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150 flex items-center gap-1 ${
            selectedSeverity === 'green'
              ? 'bg-apple-green dark:bg-emerald-600 text-white shadow-sm'
              : 'text-emerald-700 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-950/40'
          }`}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-current"></span>
          All Normal
          <span className={`ml-1 px-1.5 py-0.2 rounded-full text-[10px] ${
            selectedSeverity === 'green' ? 'bg-white/20 text-white' : 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300'
          }`}>
            {counts.green}
          </span>
        </button>

        <button
          onClick={() => onSelectSeverity('yellow')}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150 flex items-center gap-1 ${
            selectedSeverity === 'yellow'
              ? 'bg-amber-500 text-white shadow-sm'
              : 'text-amber-700 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-950/40'
          }`}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-current"></span>
          Early Only
          <span className={`ml-1 px-1.5 py-0.2 rounded-full text-[10px] ${
            selectedSeverity === 'yellow' ? 'bg-white/20 text-white' : 'bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300'
          }`}>
            {counts.yellow}
          </span>
        </button>
      </div>

      {/* Search & Region Selector */}
      <div className="flex items-center gap-2.5">
        
        {/* Region Dropdown */}
        <div className="relative">
          <select
            value={selectedRegion}
            onChange={(e) => onSelectRegion(e.target.value)}
            className="appearance-none bg-white dark:bg-neutral-800 border border-apple-gray-200/90 dark:border-white/10 rounded-xl px-3 py-1.5 pr-8 text-xs font-medium text-apple-gray-700 dark:text-neutral-200 focus:outline-none focus:ring-2 focus:ring-apple-blue/20 shadow-sm cursor-pointer"
          >
            <option value="ALL">All Regions</option>
            {regions.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
          <Filter className="w-3.5 h-3.5 text-apple-gray-400 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
        </div>

        {/* Search Input */}
        <div className="relative flex-1 md:w-64">
          <Search className="w-4 h-4 text-apple-gray-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search Station ID or Name..."
            className="w-full bg-white dark:bg-neutral-800 border border-apple-gray-200/90 dark:border-white/10 rounded-xl pl-9 pr-8 py-1.5 text-xs text-apple-gray-800 dark:text-white placeholder-apple-gray-400 focus:outline-none focus:ring-2 focus:ring-apple-blue/20 shadow-sm transition-all"
          />
          {searchQuery && (
            <button
              onClick={() => onSearchChange('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-apple-gray-400 hover:text-apple-gray-600"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

      </div>

    </div>
  );
}
