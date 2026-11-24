// Web Audio API chime & alarm synthesizer for desktop and web notifications
class AudioAlertService {
  constructor() {
    this.audioCtx = null;
    this.enabled = true;
  }

  init() {
    if (!this.audioCtx && typeof window !== 'undefined') {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (AudioContext) {
        this.audioCtx = new AudioContext();
      }
    }
  }

  setEnabled(val) {
    this.enabled = val;
  }

  isEnabled() {
    return this.enabled;
  }

  // Critical Alarm: loud, distinct multi-pulse sound for late/missing stations
  playAlarm() {
    if (!this.enabled) return;
    try {
      this.init();
      if (!this.audioCtx) return;
      if (this.audioCtx.state === 'suspended') {
        this.audioCtx.resume();
      }

      const now = this.audioCtx.currentTime;

      // Pulse 1
      this._createBeep(now, 880, 0.15);
      // Pulse 2
      this._createBeep(now + 0.18, 1108.73, 0.15);
      // Pulse 3
      this._createBeep(now + 0.36, 880, 0.22);
    } catch (e) {
      console.warn("Audio alarm prevented or unsupported:", e);
    }
  }

  _createBeep(startTime, freq, duration) {
    const osc = this.audioCtx.createOscillator();
    const gain = this.audioCtx.createGain();
    osc.type = 'triangle'; // Crisp, penetrating wave
    osc.frequency.setValueAtTime(freq, startTime);

    gain.gain.setValueAtTime(0, startTime);
    gain.gain.linearRampToValueAtTime(0.4, startTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.001, startTime + duration);

    osc.connect(gain);
    gain.connect(this.audioCtx.destination);
    osc.start(startTime);
    osc.stop(startTime + duration + 0.01);
  }

  playChime(type = 'success') {
    if (!this.enabled) return;
    try {
      this.init();
      if (!this.audioCtx) return;
      if (this.audioCtx.state === 'suspended') {
        this.audioCtx.resume();
      }

      const now = this.audioCtx.currentTime;

      if (type === 'alert') {
        this.playAlarm();
      } else {
        // Soft single pleasant chime
        const osc = this.audioCtx.createOscillator();
        const gain = this.audioCtx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(587.33, now); // D5
        osc.frequency.exponentialRampToValueAtTime(880, now + 0.15); // A5

        gain.gain.setValueAtTime(0, now);
        gain.gain.linearRampToValueAtTime(0.2, now + 0.03);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);

        osc.connect(gain);
        gain.connect(this.audioCtx.destination);
        osc.start(now);
        osc.stop(now + 0.36);
      }
    } catch (e) {
      console.warn("Audio chime prevented or unsupported:", e);
    }
  }
}

export const audioAlert = new AudioAlertService();
