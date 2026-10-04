import { useEffect, useRef, useState } from 'react';
import { usePrefs, type TextSize } from '../lib/prefs';

/**
 * Header controls: a one-click language switch (the Canada.ca pattern: the link
 * names the other language, in that language) and a small "Display" menu for
 * text size, high contrast and reduced motion.
 */
export function DisplaySettings() {
  const { lang, textSize, contrast, reduceMotion, set, reset, t } = usePrefs();
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    panel.current?.querySelector<HTMLElement>('button, input')?.focus({ preventScroll: true });
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); setOpen(false); trigger.current?.focus({ preventScroll: true }); }
    };
    const onDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!panel.current?.contains(target) && !trigger.current?.contains(target)) setOpen(false);
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onDown);
    return () => { document.removeEventListener('keydown', onKey); document.removeEventListener('pointerdown', onDown); };
  }, [open]);

  const sizes: { value: TextSize; label: string }[] = [
    { value: 1, label: t('Standard') }, { value: 2, label: t('Large') }, { value: 3, label: t('Larger') },
  ];
  const other = lang === 'en' ? 'fr' : 'en';
  return <div className="top-actions">
    <button type="button" className="lang-switch" lang={other} onClick={() => set({ lang: other })}
      aria-label={other === 'fr' ? 'Français — afficher l’interface en français' : 'English — show the interface in English'}>
      {other === 'fr' ? 'Français' : 'English'}
    </button>
    <div className="display-menu">
      <button ref={trigger} type="button" className="display-trigger" aria-expanded={open} aria-controls="display-panel" onClick={() => setOpen((v) => !v)}>
        <span aria-hidden="true" className="display-icon">Aa</span>{t('Display')}
      </button>
      {open && <div ref={panel} id="display-panel" className="display-panel" role="group" aria-label={t('Display and accessibility')}>
        <h2>{t('Display and accessibility')}</h2>
        <div className="display-row" role="group" aria-label={t('Text size')}>
          <span className="display-label" aria-hidden="true">{t('Text size')}</span>
          <div className="segmented">
            {sizes.map((s) => <button key={s.value} type="button" aria-pressed={textSize === s.value} onClick={() => set({ textSize: s.value })}
              style={{ fontSize: 11 + s.value }}>{s.label}</button>)}
          </div>
        </div>
        <label className="display-check">
          <input type="checkbox" checked={contrast} onChange={(e) => set({ contrast: e.target.checked })} aria-labelledby="pref-contrast" aria-describedby="pref-contrast-help" />
          <span><strong id="pref-contrast">{t('High contrast')}</strong><small id="pref-contrast-help">{t('Darker text and stronger outlines, for bright sunlight or low-quality screens.')}</small></span>
        </label>
        <label className="display-check">
          <input type="checkbox" checked={reduceMotion} onChange={(e) => set({ reduceMotion: e.target.checked })} aria-labelledby="pref-motion" aria-describedby="pref-motion-help" />
          <span><strong id="pref-motion">{t('Reduce motion')}</strong><small id="pref-motion-help">{t('Turns off animations and transitions.')}</small></span>
        </label>
        <p className="display-note">{t('Keyboard: Tab moves between controls; arrow keys move the comparison divider; Esc closes panels.')}</p>
        <button type="button" className="link-button" onClick={reset}>{t('Reset display settings')}</button>
      </div>}
    </div>
  </div>;
}
