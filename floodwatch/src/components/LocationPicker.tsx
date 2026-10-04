import { useEffect, useRef, useState } from 'react';
import { usePrefs } from '../lib/prefs';

// Example flood-prone sites inside the four RADARSAT-2 Tropical Forests regions.
// Interface only: they show where the same workflow can run; no data is loaded for them.
const REGIONS: { label: string; sites: string[] }[] = [
  { label: 'Africa', sites: ['Maiduguri, Nigeria', 'Beira, Mozambique', 'Kinshasa, DR Congo'] },
  { label: 'South-East Asia', sites: ['Jakarta, Indonesia', 'Mekong Delta, Viet Nam'] },
  { label: 'South America', sites: ['Belém, Brazil', 'Pucallpa, Peru'] },
  { label: 'Central America', sites: ['San Pedro Sula, Honduras'] },
];

/**
 * Compact site switcher. A custom popover rather than a native <select>, because
 * macOS draws native menus at the select's (large heading) font size.
 */
export function LocationPicker({ name, country }: { name: string; country: string }) {
  const { t } = usePrefs();
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    panel.current?.querySelector<HTMLElement>('[aria-current="true"]')?.focus({ preventScroll: true });
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

  return <div className="location-picker">
    <button ref={trigger} type="button" className="location-button" aria-expanded={open} aria-controls="location-panel"
      aria-label={t('Location') + ': ' + name} onClick={() => setOpen((v) => !v)}>
      <span className="location-name">{name}</span>
      <span className="location-chevron" aria-hidden="true" />
    </button>
    {open && <div ref={panel} id="location-panel" className="location-panel" role="group" aria-label={t('Choose a site')}>
      <p className="location-panel-note">{t('One radar workflow for any site in the RADARSAT-2 tropical archive.')}</p>
      {REGIONS.map((region, index) => <section key={region.label} aria-label={t(region.label)}>
        <h3>{t(region.label)}</h3>
        <ul>
          {index === 0 && <li>
            <button type="button" className="site current" aria-current="true" onClick={() => setOpen(false)}>
              <span>{name}, {t(country)}</span><small>{t('Active')}</small>
            </button>
          </li>}
          {region.sites.map((site) => <li key={site}>
            <span className="site pending" aria-disabled="true"><span>{t(site)}</span><small>{t('Not yet processed')}</small></span>
          </li>)}
        </ul>
      </section>)}
    </div>}
  </div>;
}
