import React, { useState, useEffect, useCallback } from 'react';

/**
 * PWAInstallBanner - Shows "Add to Home Screen" prompt for installable PWAs.
 * Listens for the beforeinstallprompt event and provides a dismissible banner.
 */
export default function PWAInstallBanner() {
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [visible, setVisible] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    // Check if user previously dismissed
    try {
      const lastDismissed = localStorage.getItem('pwa_install_dismissed');
      if (lastDismissed) {
        const daysSince = (Date.now() - parseInt(lastDismissed)) / (1000 * 60 * 60 * 24);
        if (daysSince < 30) return; // Don't show for 30 days after dismissal
      }
    } catch { /* noop */ }

    const handler = (e) => {
      e.preventDefault();
      setDeferredPrompt(e);
      setVisible(true);
    };

    window.addEventListener('beforeinstallprompt', handler);

    // Check if already installed
    if (window.matchMedia('(display-mode: standalone)').matches) {
      return; // Already installed
    }

    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, []);

  const handleInstall = useCallback(async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    if (outcome === 'accepted') {
      setVisible(false);
    }
    setDeferredPrompt(null);
  }, [deferredPrompt]);

  const handleDismiss = useCallback(() => {
    setVisible(false);
    setDismissed(true);
    try {
      localStorage.setItem('pwa_install_dismissed', Date.now().toString());
    } catch { /* noop */ }
  }, []);

  if (!visible || dismissed) return null;

  return (
    <div className="pwa-install-banner">
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 2 }}>
          Install FLOWW
        </div>
        <div style={{ fontSize: 10, color: '#64748b', lineHeight: 1.4 }}>
          Add to home screen for instant access during market hours.
        </div>
      </div>
      <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
        <button
          onClick={handleInstall}
          style={{
            background: '#5eead4',
            color: '#07080a',
            border: 'none',
            borderRadius: 4,
            padding: '6px 12px',
            fontSize: 10,
            fontWeight: 600,
            cursor: 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          Install
        </button>
        <button
          onClick={handleDismiss}
          style={{
            background: 'none',
            border: 'none',
            color: '#64748b',
            cursor: 'pointer',
            fontSize: 14,
            padding: '4px 8px',
          }}
          aria-label="Dismiss install prompt"
        >
          ✕
        </button>
      </div>
    </div>
  );
}

export { PWAInstallBanner };
