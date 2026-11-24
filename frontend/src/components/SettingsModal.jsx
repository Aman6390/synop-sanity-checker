import React, { useState } from 'react';
import { 
  X, 
  SlidersHorizontal, 
  Zap, 
  UploadCloud, 
  Sun, 
  Moon, 
  Plus, 
  Trash2, 
  Edit2, 
  Check, 
  Clock,
  FileText,
  CheckCircle2
} from 'lucide-react';

const ALL_HOURS = ["0000", "0300", "0600", "0900", "1200", "1500", "1800", "2100"];

const HOUR_LABELS_SHORT = {
  "0000": "00Z / 05:30 IST",
  "0300": "03Z / 08:30 IST",
  "0600": "06Z / 11:30 IST",
  "0900": "09Z / 14:30 IST",
  "1200": "12Z / 17:30 IST",
  "1500": "15Z / 20:30 IST",
  "1800": "18Z / 23:30 IST",
  "2100": "21Z / 02:30 IST"
};

export default function SettingsModal({
  isOpen,
  onClose,
  stations,
  onAddOrUpdateStation,
  onDeleteStation,
  statusData,
  pollInterval,
  onUpdatePollInterval,
  useDynamicPolling,
  onToggleDynamicPolling,
  onUploadData,
  theme,
  onToggleTheme
}) {
  const [activeTab, setActiveTab] = useState('stations'); // 'stations' | 'polling' | 'upload'
  
  // Station form states
  const [editingStation, setEditingStation] = useState(null);
  const [formId, setFormId] = useState('');
  const [formName, setFormName] = useState('');
  const [formState, setFormState] = useState('');
  const [formRegion, setFormRegion] = useState('North');
  const [formHours, setFormHours] = useState(ALL_HOURS);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Upload state
  const [uploadText, setUploadText] = useState('');
  const [uploadStatus, setUploadStatus] = useState(null);
  const [isUploading, setIsUploading] = useState(false);

  if (!isOpen) return null;

  const handleStartEdit = (stn) => {
    setEditingStation(stn);
    setFormId(stn.id || stn.station_id);
    setFormName(stn.name || stn.station_name);
    setFormState(stn.state || '');
    setFormRegion(stn.region || 'North');
    setFormHours(stn.required_hours || ALL_HOURS);
  };

  const handleResetForm = () => {
    setEditingStation(null);
    setFormId('');
    setFormName('');
    setFormState('');
    setFormRegion('North');
    setFormHours(ALL_HOURS);
  };

  const toggleHour = (h) => {
    if (formHours.includes(h)) {
      setFormHours(formHours.filter(x => x !== h));
    } else {
      setFormHours([...formHours, h]);
    }
  };

  const handleSaveStation = async (e) => {
    e.preventDefault();
    if (!formId || !formName) return;
    setIsSubmitting(true);
    try {
      await onAddOrUpdateStation({
        id: formId.trim(),
        name: formName.trim(),
        state: formState.trim(),
        region: formRegion,
        required_hours: formHours
      });
      handleResetForm();
    } catch (err) {
      console.error(err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleProcessUpload = async () => {
    if (!uploadText.trim()) return;
    setIsUploading(true);
    setUploadStatus(null);
    try {
      const res = await onUploadData(uploadText);
      setUploadStatus(`Processed ${res.total_bulletins} bulletins across ${res.stations_found} stations!`);
      setTimeout(() => {
        setUploadStatus(null);
        setUploadText('');
      }, 2000);
    } catch (err) {
      setUploadStatus(`Error: ${err.message || 'Failed to process'}`);
    } finally {
      setIsUploading(false);
    }
  };

  const dynamicWindow = statusData?.dynamic_window;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
      <div className="bg-white dark:bg-[#1C1C1E] rounded-3xl border border-apple-gray-200/90 dark:border-white/10 shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in duration-200">
        
        {/* Header */}
        <div className="px-6 py-4 border-b border-apple-gray-100 dark:border-white/10 flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-xl bg-apple-blue/10 dark:bg-apple-blue/20 text-apple-blue flex items-center justify-center">
              <SlidersHorizontal className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-base font-bold text-apple-gray-900 dark:text-white tracking-tight">
                Control Hub & Settings
              </h3>
              <p className="text-xs text-apple-gray-400">
                Manage stations, observation timings, dynamic polling, and theme
              </p>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="p-1.5 text-apple-gray-400 hover:text-apple-gray-700 dark:hover:text-white rounded-lg transition-all"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="px-6 pt-3 flex items-center space-x-2 border-b border-apple-gray-100 dark:border-white/10">
          <button
            onClick={() => setActiveTab('stations')}
            className={`px-3.5 py-2 text-xs font-semibold rounded-t-xl transition-all border-b-2 flex items-center gap-1.5 ${
              activeTab === 'stations'
                ? 'border-apple-blue text-apple-blue'
                : 'border-transparent text-apple-gray-500 hover:text-apple-gray-800 dark:hover:text-white'
            }`}
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
            Stations ({stations.length})
          </button>

          <button
            onClick={() => setActiveTab('polling')}
            className={`px-3.5 py-2 text-xs font-semibold rounded-t-xl transition-all border-b-2 flex items-center gap-1.5 ${
              activeTab === 'polling'
                ? 'border-apple-blue text-apple-blue'
                : 'border-transparent text-apple-gray-500 hover:text-apple-gray-800 dark:hover:text-white'
            }`}
          >
            <Zap className="w-3.5 h-3.5" />
            Smart Polling
          </button>

          <button
            onClick={() => setActiveTab('upload')}
            className={`px-3.5 py-2 text-xs font-semibold rounded-t-xl transition-all border-b-2 flex items-center gap-1.5 ${
              activeTab === 'upload'
                ? 'border-apple-blue text-apple-blue'
                : 'border-transparent text-apple-gray-500 hover:text-apple-gray-800 dark:hover:text-white'
            }`}
          >
            <UploadCloud className="w-3.5 h-3.5" />
            Upload / Paste
          </button>

          <div className="ml-auto pb-2 flex items-center gap-2">
            <button
              onClick={onToggleTheme}
              className="px-2.5 py-1 rounded-full text-xs font-medium bg-apple-gray-100 dark:bg-neutral-800 text-apple-gray-700 dark:text-neutral-300 border border-apple-gray-200 dark:border-white/5 flex items-center gap-1.5"
            >
              {theme === 'dark' ? <Sun className="w-3.5 h-3.5 text-amber-400" /> : <Moon className="w-3.5 h-3.5 text-apple-gray-600" />}
              <span>{theme === 'dark' ? 'Light Theme' : 'Dark Theme'}</span>
            </button>
          </div>
        </div>

        {/* Modal Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          
          {/* TAB 1: STATIONS */}
          {activeTab === 'stations' && (
            <div className="space-y-5">
              
              {/* Form */}
              <form onSubmit={handleSaveStation} className="bg-apple-gray-50 dark:bg-neutral-800/50 p-4 rounded-2xl border border-apple-gray-200 dark:border-white/5">
                <h4 className="text-xs font-bold uppercase tracking-wider text-apple-gray-600 dark:text-neutral-400 mb-3 flex items-center gap-1.5">
                  {editingStation ? <Edit2 className="w-3.5 h-3.5 text-apple-blue" /> : <Plus className="w-3.5 h-3.5 text-apple-blue" />}
                  {editingStation ? `Edit Station ${formId}` : 'Add New Station'}
                </h4>

                <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                  <div>
                    <label className="block text-[11px] font-semibold text-apple-gray-700 dark:text-neutral-300 mb-1">
                      5-Digit ID
                    </label>
                    <input
                      type="text"
                      maxLength={5}
                      value={formId}
                      disabled={!!editingStation}
                      onChange={(e) => setFormId(e.target.value.replace(/\D/g, ''))}
                      placeholder="e.g. 42027"
                      className="w-full bg-white dark:bg-neutral-700 border border-apple-gray-200 dark:border-white/10 rounded-xl px-3 py-1.5 text-xs font-mono font-bold text-apple-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-apple-blue/20"
                      required
                    />
                  </div>

                  <div className="sm:col-span-2">
                    <label className="block text-[11px] font-semibold text-apple-gray-700 dark:text-neutral-300 mb-1">
                      Station Name
                    </label>
                    <input
                      type="text"
                      value={formName}
                      onChange={(e) => setFormName(e.target.value)}
                      placeholder="e.g. Srinagar"
                      className="w-full bg-white dark:bg-neutral-700 border border-apple-gray-200 dark:border-white/10 rounded-xl px-3 py-1.5 text-xs text-apple-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-apple-blue/20"
                      required
                    />
                  </div>

                  <div>
                    <label className="block text-[11px] font-semibold text-apple-gray-700 dark:text-neutral-300 mb-1">
                      State
                    </label>
                    <input
                      type="text"
                      value={formState}
                      onChange={(e) => setFormState(e.target.value)}
                      placeholder="e.g. Jammu & Kashmir"
                      className="w-full bg-white dark:bg-neutral-700 border border-apple-gray-200 dark:border-white/10 rounded-xl px-3 py-1.5 text-xs text-apple-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-apple-blue/20"
                    />
                  </div>
                </div>

                {/* Hours Selection */}
                <div className="mt-3.5">
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-[11px] font-semibold text-apple-gray-700 dark:text-neutral-300">
                      Required Synoptic Hours ({formHours.length}/8 selected):
                    </label>
                    <div className="space-x-2 text-[10px]">
                      <button 
                        type="button" 
                        onClick={() => setFormHours(ALL_HOURS)}
                        className="text-apple-blue hover:underline font-medium"
                      >
                        All 8
                      </button>
                      <span>•</span>
                      <button 
                        type="button" 
                        onClick={() => setFormHours(["0300", "0600", "0900", "1200"])}
                        className="text-apple-blue hover:underline font-medium"
                      >
                        Daylight (03–12Z)
                      </button>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {ALL_HOURS.map((h) => {
                      const isChecked = formHours.includes(h);
                      return (
                        <button
                          type="button"
                          key={h}
                          onClick={() => toggleHour(h)}
                          className={`px-2 py-1 rounded-xl border text-[11px] font-mono transition-all flex items-center justify-between ${
                            isChecked 
                              ? 'bg-apple-blue text-white border-apple-blue shadow-sm font-semibold' 
                              : 'bg-white dark:bg-neutral-700 text-apple-gray-500 dark:text-neutral-400 border-apple-gray-200 dark:border-white/5'
                          }`}
                        >
                          <span>{HOUR_LABELS_SHORT[h]}</span>
                          {isChecked && <Check className="w-3 h-3 ml-1" />}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="mt-3 flex items-center justify-end space-x-2">
                  {editingStation && (
                    <button
                      type="button"
                      onClick={handleResetForm}
                      className="px-3 py-1 text-xs text-apple-gray-500 hover:text-apple-gray-800 dark:hover:text-white"
                    >
                      Cancel
                    </button>
                  )}
                  <button
                    type="submit"
                    disabled={isSubmitting || !formId || !formName}
                    className="px-4 py-1.5 bg-apple-blue hover:bg-apple-blue-dark active:scale-95 text-white text-xs font-semibold rounded-xl shadow-sm transition-all disabled:opacity-50"
                  >
                    {editingStation ? 'Update Station' : 'Add Station'}
                  </button>
                </div>
              </form>

              {/* Station List */}
              <div className="space-y-2">
                {stations.map((stn) => {
                  const sId = stn.id || stn.station_id;
                  const sName = stn.name || stn.station_name;
                  return (
                    <div 
                      key={sId}
                      className="flex items-center justify-between p-3 bg-white dark:bg-neutral-800 rounded-xl border border-apple-gray-200/80 dark:border-white/5 shadow-sm"
                    >
                      <div className="flex items-center space-x-3">
                        <span className="font-mono font-bold text-xs bg-apple-gray-100 dark:bg-neutral-700 px-2 py-1 rounded-lg text-apple-gray-900 dark:text-white">
                          {sId}
                        </span>
                        <div>
                          <div className="font-semibold text-xs text-apple-gray-900 dark:text-white">
                            {sName}
                          </div>
                          <div className="text-[11px] text-apple-gray-400">
                            {stn.state || stn.region} • {stn.required_hours?.length || 8} hours configured
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center space-x-1.5">
                        <button
                          onClick={() => handleStartEdit(stn)}
                          className="p-1.5 text-apple-gray-400 hover:text-apple-blue rounded-lg"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => onDeleteStation(sId)}
                          className="p-1.5 text-apple-gray-400 hover:text-apple-red rounded-lg"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>

            </div>
          )}

          {/* TAB 2: SMART POLLING CONFIGURATION */}
          {activeTab === 'polling' && (
            <div className="space-y-5">
              
              <div className="bg-apple-gray-50 dark:bg-neutral-800/60 p-4.5 rounded-2xl border border-apple-gray-200 dark:border-white/5">
                <div className="flex items-start justify-between">
                  <div className="space-y-1">
                    <h4 className="text-sm font-bold text-apple-gray-900 dark:text-white flex items-center gap-2">
                      <Zap className="w-4 h-4 text-amber-500" />
                      Dynamic Synoptic Window Polling
                    </h4>
                    <p className="text-xs text-apple-gray-500 dark:text-neutral-400 max-w-lg leading-relaxed">
                      Automatically shifts into high-gear (1-minute polling) from <strong>15 minutes before</strong> each observation cycle (e.g. 02:45 UTC) until <strong>30 minutes after</strong> (03:30 UTC). Outside this critical 45-minute window, it relaxes to 30-minute polling.
                    </p>
                  </div>

                  <button
                    onClick={onToggleDynamicPolling}
                    className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                      useDynamicPolling ? 'bg-apple-blue' : 'bg-apple-gray-300 dark:bg-neutral-700'
                    }`}
                  >
                    <span
                      className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                        useDynamicPolling ? 'translate-x-5' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>

                {/* Status card */}
                {dynamicWindow && (
                  <div className="mt-4 p-3 bg-white dark:bg-neutral-800 rounded-xl border border-apple-gray-200/80 dark:border-white/5 text-xs space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-apple-gray-500">Current Window State:</span>
                      <span className={`font-semibold px-2 py-0.5 rounded-md ${
                        dynamicWindow.is_active 
                          ? 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300' 
                          : 'bg-apple-gray-100 text-apple-gray-700 dark:bg-neutral-700 dark:text-neutral-300'
                      }`}>
                        {dynamicWindow.status_text}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-apple-gray-600 dark:text-neutral-400">
                      <span>Active Poll Frequency:</span>
                      <span className="font-mono font-bold text-apple-blue">
                        Every {dynamicWindow.target_poll_seconds / 60} min ({dynamicWindow.target_poll_seconds}s)
                      </span>
                    </div>
                    <p className="text-[11px] text-apple-gray-400 mt-1">
                      {dynamicWindow.description}
                    </p>
                  </div>
                )}
              </div>

            </div>
          )}

          {/* TAB 3: UPLOAD */}
          {activeTab === 'upload' && (
            <div className="space-y-4">
              <p className="text-xs text-apple-gray-500 dark:text-neutral-400">
                Load offline or archived AMSS Delhi GTS bulletins to evaluate them against your station watchlist:
              </p>

              <textarea
                rows={8}
                value={uploadText}
                onChange={(e) => setUploadText(e.target.value)}
                placeholder="Paste ZCZC ... AAXX ... NNNN text here..."
                className="w-full bg-apple-gray-50 dark:bg-neutral-800 border border-apple-gray-200 dark:border-white/10 rounded-xl p-3 text-xs font-mono text-apple-gray-800 dark:text-white placeholder-apple-gray-400 focus:outline-none focus:ring-2 focus:ring-apple-blue/20"
              />

              {uploadStatus && (
                <div className="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300 text-xs flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4" />
                  {uploadStatus}
                </div>
              )}

              <div className="flex justify-end">
                <button
                  onClick={handleProcessUpload}
                  disabled={isUploading || !uploadText.trim()}
                  className="px-5 py-2 bg-apple-blue hover:bg-apple-blue-dark active:scale-95 text-white text-xs font-semibold rounded-xl shadow-sm transition-all disabled:opacity-50"
                >
                  {isUploading ? 'Processing...' : 'Process Bulletin Data'}
                </button>
              </div>
            </div>
          )}

        </div>

      </div>
    </div>
  );
}
