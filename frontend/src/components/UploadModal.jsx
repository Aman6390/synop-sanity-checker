import React, { useState } from 'react';
import { X, UploadCloud, FileText, CheckCircle2 } from 'lucide-react';

export default function UploadModal({ isOpen, onClose, onUploadData }) {
  const [content, setContent] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [statusMsg, setStatusMsg] = useState(null);

  if (!isOpen) return null;

  const handleFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result;
      if (typeof text === 'string') {
        setContent(text);
      }
    };
    reader.readAsText(file);
  };

  const handleProcess = async () => {
    if (!content.trim()) return;
    setIsUploading(true);
    setStatusMsg(null);
    try {
      const res = await onUploadData(content);
      setStatusMsg(`Successfully processed ${res.total_bulletins} bulletins across ${res.stations_found} stations!`);
      setTimeout(() => {
        onClose();
        setStatusMsg(null);
        setContent('');
      }, 1500);
    } catch (err) {
      setStatusMsg(`Error: ${err.message || 'Failed to process bulletin data'}`);
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
      <div className="glass-card bg-white rounded-3xl border border-apple-gray-200/90 shadow-2xl w-full max-w-2xl flex flex-col overflow-hidden animate-in fade-in duration-200">
        
        {/* Header */}
        <div className="px-6 py-4 border-b border-apple-gray-100 flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-xl bg-apple-blue/10 text-apple-blue flex items-center justify-center">
              <UploadCloud className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-base font-bold text-apple-gray-900 tracking-tight">
                Upload or Paste Bulletin Data
              </h3>
              <p className="text-xs text-apple-gray-500">
                Load offline or archived AMSS Delhi GTS bulletins for immediate evaluation
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

        {/* Body */}
        <div className="p-6 space-y-4">
          
          {/* File input */}
          <div className="border-2 border-dashed border-apple-gray-200 rounded-2xl p-5 text-center hover:border-apple-blue/50 transition-all bg-apple-gray-50/50">
            <FileText className="w-7 h-7 text-apple-gray-400 mx-auto mb-2" />
            <label className="cursor-pointer">
              <span className="text-xs font-semibold text-apple-blue hover:underline">
                Choose a .txt bulletin file
              </span>
              <input
                type="file"
                accept=".txt,.dat,.raw"
                onChange={handleFileUpload}
                className="hidden"
              />
            </label>
            <p className="text-[11px] text-apple-gray-400 mt-1">
              or paste raw WMO GTS / AAXX text below
            </p>
          </div>

          {/* Text Area */}
          <div>
            <label className="block text-xs font-semibold text-apple-gray-700 mb-1.5">
              Raw Bulletin Stream Text:
            </label>
            <textarea
              rows={8}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Paste ZCZC ... AAXX ... NNNN text here..."
              className="w-full bg-apple-gray-50 border border-apple-gray-200 rounded-xl p-3 text-xs font-mono text-apple-gray-800 placeholder-apple-gray-400 focus:outline-none focus:ring-2 focus:ring-apple-blue/20"
            />
          </div>

          {statusMsg && (
            <div className={`p-3 rounded-xl text-xs font-medium flex items-center gap-2 ${
              statusMsg.startsWith('Error') 
                ? 'bg-red-50 text-apple-red border border-red-200' 
                : 'bg-emerald-50 text-emerald-800 border border-emerald-200'
            }`}>
              <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
              {statusMsg}
            </div>
          )}

          {/* Footer actions */}
          <div className="flex items-center justify-end space-x-2.5 pt-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-xs font-medium text-apple-gray-600 hover:text-apple-gray-800"
            >
              Cancel
            </button>
            <button
              onClick={handleProcess}
              disabled={isUploading || !content.trim()}
              className="px-5 py-2 bg-apple-blue hover:bg-apple-blue-dark active:scale-95 text-white text-xs font-semibold rounded-xl shadow-sm transition-all disabled:opacity-50"
            >
              {isUploading ? 'Processing Bulletins...' : 'Process & Evaluate'}
            </button>
          </div>

        </div>

      </div>
    </div>
  );
}
