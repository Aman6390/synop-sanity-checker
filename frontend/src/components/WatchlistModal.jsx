import React, { useState } from 'react';
import { X, Plus, Trash2, Edit2, Check, SlidersHorizontal } from 'lucide-react';

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

export default function WatchlistModal({ 
  isOpen, 
  onClose, 
  stations, 
  onAddOrUpdateStation, 
  onDeleteStation 
}) {
  const [editingStation, setEditingStation] = useState(null);
  const [formId, setFormId] = useState('');
  const [formName, setFormName] = useState('');
  const [formState, setFormState] = useState('');
  const [formRegion, setFormRegion] = useState('North');
  const [formHours, setFormHours] = useState(ALL_HOURS);
  const [isSubmitting, setIsSubmitting] = useState(false);

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

  const handleSave = async (e) => {
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
      <div className="glass-card bg-white rounded-3xl border border-apple-gray-200/90 shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in duration-200">
        
        {/* Modal Header */}
        <div className="px-6 py-4.5 border-b border-apple-gray-100 flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-xl bg-apple-blue/10 text-apple-blue flex items-center justify-center">
              <SlidersHorizontal className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-base font-bold text-apple-gray-900 tracking-tight">
                Manage Station Watchlist & Schedules
              </h3>
              <p className="text-xs text-apple-gray-500">
                Configure monitored stations, names, and customized observation timings
              </p>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="p-1.5 text-apple-gray-400 hover:text-apple-gray-700 hover:bg-apple-gray-100 rounded-lg transition-all"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          
          {/* Add / Edit Form */}
          <form onSubmit={handleSave} className="bg-apple-gray-50/80 p-4.5 rounded-2xl border border-apple-gray-200/70">
            <h4 className="text-xs font-bold uppercase tracking-wider text-apple-gray-600 mb-3 flex items-center gap-1.5">
              {editingStation ? <Edit2 className="w-3.5 h-3.5 text-apple-blue" /> : <Plus className="w-3.5 h-3.5 text-apple-blue" />}
              {editingStation ? `Edit Station ${formId}` : 'Add New Station to Watchlist'}
            </h4>

            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
              <div>
                <label className="block text-[11px] font-semibold text-apple-gray-700 mb-1">
                  5-Digit Station ID
                </label>
                <input
                  type="text"
                  maxLength={5}
                  value={formId}
                  disabled={!!editingStation}
                  onChange={(e) => setFormId(e.target.value.replace(/\D/g, ''))}
                  placeholder="e.g. 42027"
                  className="w-full bg-white border border-apple-gray-200 rounded-xl px-3 py-1.5 text-xs font-mono font-bold text-apple-gray-900 focus:outline-none focus:ring-2 focus:ring-apple-blue/20 disabled:opacity-50"
                  required
                />
              </div>

              <div className="sm:col-span-2">
                <label className="block text-[11px] font-semibold text-apple-gray-700 mb-1">
                  Station Name
                </label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="e.g. Srinagar"
                  className="w-full bg-white border border-apple-gray-200 rounded-xl px-3 py-1.5 text-xs text-apple-gray-900 focus:outline-none focus:ring-2 focus:ring-apple-blue/20"
                  required
                />
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-apple-gray-700 mb-1">
                  State / Region
                </label>
                <input
                  type="text"
                  value={formState}
                  onChange={(e) => setFormState(e.target.value)}
                  placeholder="e.g. Jammu & Kashmir"
                  className="w-full bg-white border border-apple-gray-200 rounded-xl px-3 py-1.5 text-xs text-apple-gray-900 focus:outline-none focus:ring-2 focus:ring-apple-blue/20"
                />
              </div>
            </div>

            {/* Custom Hours Schedule Selection */}
            <div className="mt-4">
              <div className="flex items-center justify-between mb-2">
                <label className="text-[11px] font-semibold text-apple-gray-700">
                  Required Synoptic Observation Hours ({formHours.length}/8 selected):
                </label>
                <div className="space-x-2 text-[10px]">
                  <button 
                    type="button" 
                    onClick={() => setFormHours(ALL_HOURS)}
                    className="text-apple-blue hover:underline font-medium"
                  >
                    Select All 8
                  </button>
                  <span>•</span>
                  <button 
                    type="button" 
                    onClick={() => setFormHours(["0300", "0600", "0900", "1200"])}
                    className="text-apple-blue hover:underline font-medium"
                  >
                    Daylight Only (03–12Z)
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
                      className={`px-2.5 py-1.5 rounded-xl border text-xs font-mono transition-all flex items-center justify-between ${
                        isChecked 
                          ? 'bg-apple-blue text-white border-apple-blue shadow-sm font-semibold' 
                          : 'bg-white text-apple-gray-500 border-apple-gray-200 hover:border-apple-gray-300'
                      }`}
                    >
                      <span>{HOUR_LABELS_SHORT[h]}</span>
                      {isChecked && <Check className="w-3.5 h-3.5 ml-1" />}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Action buttons */}
            <div className="mt-4 flex items-center justify-end space-x-2">
              {editingStation && (
                <button
                  type="button"
                  onClick={handleResetForm}
                  className="px-3.5 py-1.5 text-xs font-medium text-apple-gray-600 hover:text-apple-gray-800"
                >
                  Cancel Edit
                </button>
              )}
              <button
                type="submit"
                disabled={isSubmitting || !formId || !formName || formHours.length === 0}
                className="px-4 py-1.5 bg-apple-blue hover:bg-apple-blue-dark active:scale-95 text-white text-xs font-medium rounded-xl shadow-sm transition-all disabled:opacity-50"
              >
                {editingStation ? 'Update Station' : 'Add Station'}
              </button>
            </div>
          </form>

          {/* Current Monitored Stations List */}
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-apple-gray-500 mb-3">
              Currently Monitored Stations ({stations.length})
            </h4>

            <div className="space-y-2">
              {stations.map((stn) => {
                const sId = stn.id || stn.station_id;
                const sName = stn.name || stn.station_name;
                const reqCount = stn.required_hours?.length || 8;

                return (
                  <div 
                    key={sId}
                    className="flex items-center justify-between p-3 bg-white rounded-xl border border-apple-gray-200/80 shadow-sm hover:border-apple-gray-300 transition-all"
                  >
                    <div className="flex items-center space-x-3">
                      <span className="font-mono font-bold text-xs bg-apple-gray-100 px-2.5 py-1 rounded-lg text-apple-gray-900 border border-apple-gray-200">
                        {sId}
                      </span>
                      <div>
                        <div className="font-semibold text-xs text-apple-gray-900">
                          {sName}
                        </div>
                        <div className="text-[11px] text-apple-gray-500">
                          {stn.state || stn.region} • {reqCount} hours configured
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => handleStartEdit(stn)}
                        className="p-1.5 text-apple-gray-500 hover:text-apple-blue hover:bg-apple-blue/10 rounded-lg transition-all"
                        title="Edit station schedule"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => onDeleteStation(sId)}
                        className="p-1.5 text-apple-gray-500 hover:text-apple-red hover:bg-apple-red/10 rounded-lg transition-all"
                        title="Remove from watchlist"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

        </div>

      </div>
    </div>
  );
}
