/**
 * Web Speech API Hazard Audio Alerts for MARSPath Astronaut Field HUD.
 *
 * Provides spoken terrain, life-support, and planetary-protection hazard announcements.
 * Handles unsupported browsers, deduplication cooldowns, user-gesture enablement,
 * and visual alert text event dispatching.
 */

class AudioAlertManager {
  constructor() {
    this.enabled = false;
    this.lastSpokenText = '';
    this.lastSpokenTime = 0;
    this.cooldownMs = 15000; // 15 seconds cooldown for identical alerts
    this.subscribers = new Set();
    this.currentAlert = null;
    this.speechSupported = typeof window !== 'undefined' && 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;
    
    // Read persisted preference if available
    if (typeof localStorage !== 'undefined') {
      try {
        const saved = localStorage.getItem('marspath_audio_alerts_enabled');
        if (saved !== null) {
          this.enabled = saved === 'true';
        }
      } catch {
        // ignore storage errors
      }
    }
  }

  isSupported() {
    return this.speechSupported;
  }

  isEnabled() {
    return this.enabled;
  }

  setEnabled(val) {
    this.enabled = Boolean(val);
    if (typeof localStorage !== 'undefined') {
      try {
        localStorage.setItem('marspath_audio_alerts_enabled', String(this.enabled));
      } catch {
        // ignore
      }
    }
    this.notifySubscribers();
  }

  subscribe(callback) {
    this.subscribers.add(callback);
    return () => this.subscribers.delete(callback);
  }

  notifySubscribers() {
    this.subscribers.forEach(cb => {
      try {
        cb({
          enabled: this.enabled,
          currentAlert: this.currentAlert,
          supported: this.speechSupported,
        });
      } catch (e) {
        console.error('Audio alert subscriber error:', e);
      }
    });
  }

  /**
   * Triggers a hazard alert.
   * @param {Object} options
   * @param {string} options.message - Spoken announcement and display text.
   * @param {'WARNING'|'CRITICAL'|'ADVISORY'} options.severity - Severity tier.
   * @param {string} [options.key] - Optional unique identifier to prevent duplicate spam.
   * @param {boolean} [options.force] - Force trigger even if within cooldown.
   */
  triggerAlert({ message, severity = 'WARNING', key = '', force = false }) {
    if (!message) return;

    const now = Date.now();
    const alertKey = key || message;

    // Check deduplication
    if (!force && this.lastSpokenText === alertKey && (now - this.lastSpokenTime) < this.cooldownMs) {
      return;
    }

    this.lastSpokenText = alertKey;
    this.lastSpokenTime = now;
    this.currentAlert = {
      message,
      severity,
      timestamp: new Date().toISOString(),
    };

    this.notifySubscribers();

    // Spoken audio alert using Web Speech API if enabled and supported
    if (this.enabled && this.speechSupported) {
      try {
        window.speechSynthesis.cancel(); // Cancel any lingering utterance

        const utterance = new SpeechSynthesisUtterance(message);
        utterance.rate = 1.05;
        utterance.pitch = 0.95; // Crisp military/flight controller cadence
        utterance.volume = 0.9;

        // Try to select an English female or neutral synthetic voice if available
        const voices = window.speechSynthesis.getVoices();
        const preferredVoice = voices.find(v => 
          v.lang.startsWith('en') && (v.name.includes('Samantha') || v.name.includes('Zira') || v.name.includes('Natural') || v.name.includes('Google'))
        ) || voices.find(v => v.lang.startsWith('en'));

        if (preferredVoice) {
          utterance.voice = preferredVoice;
        }

        utterance.onerror = (e) => {
          console.warn('Speech synthesis utterance error:', e);
        };

        window.speechSynthesis.speak(utterance);
      } catch (err) {
        console.warn('Speech synthesis failed:', err);
      }
    }
  }

  clearAlert() {
    this.currentAlert = null;
    this.notifySubscribers();
  }
}

export const audioAlerts = new AudioAlertManager();
