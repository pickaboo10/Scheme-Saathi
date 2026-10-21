import React, { useEffect, useRef, useState } from 'react';
import { Icon } from './icons';
import {
  ActionButton, BusyNote, CategoryDisc, IconDisc, ListenButton, MatchBadge, SheetLayer, StatusBanner, cx,
} from './ui';
import { translateReason, useI18n } from '../lib/i18n';
import { CATEGORY_STYLE, docIcon, hostOf, sentences, whatsappUrl } from '../lib/schemes';

/* ------------------------------------------------------------------ SchemeCard */
export function SchemeCard({ view, onOpen, flipping }) {
  const { t, lang } = useI18n();
  const style = CATEGORY_STYLE[view.category];
  const catName = t.cat[view.category];
  const whyText = translateReason(view.why, lang);
  const label = `${view.title}. ${view.benefit}. ${t.cardHint}`;
  return (
    <div className="ss-flip-scene">
      <div className={cx('ss-flip-card relative', flipping && 'is-flipped')}>
        <article className="ss-face relative flex h-full flex-col gap-4 rounded-lg border-2 border-line bg-surface-raised p-5 shadow-card">
          <div className="flex items-center gap-4">
            <CategoryDisc category={view.category} />
            <div className="min-w-0">
              <p className="text-caption text-ink-muted">{catName}</p>
              <h3 lang={view.listenLang} className="break-words text-heading">{view.title}</h3>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-turmeric-400 text-ink"><Icon name="rupee" size={20} /></span>
            <p lang={view.listenLang} className="line-clamp-4 min-w-0 text-body font-semibold">{view.benefit}</p>
          </div>
          {whyText && <p lang={lang} className="text-caption text-ink-muted">{whyText}</p>}
          <div className="mt-auto flex items-center gap-3 pt-1">
            <MatchBadge strength={view.strength} />
            <span className="flex-1" />
            <span className="relative z-[2]">
              <ListenButton text={`${view.title}. ${view.benefit}`} lang={view.listenLang} />
            </span>
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-field-700 text-on-fill" aria-hidden="true">
              <Icon name="chevron-right" size={26} stroke={3} />
            </span>
          </div>
          <button type="button" onClick={() => onOpen(view.slug)} aria-label={label}
            className="absolute inset-0 z-[1] rounded-lg" />
        </article>
        <div aria-hidden="true" className={cx('ss-face ss-back absolute inset-0 flex flex-col items-center justify-center gap-4 rounded-lg p-5 text-center', style.disc)}>
          <CategoryDisc category={view.category} size={80} />
          <p className="text-heading">{view.title}</p>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ DocumentChecklist */
export function DocumentChecklist({ docs }) {
  const { t } = useI18n();
  const [have, setHave] = useState({});
  return (
    <ul className="flex flex-col gap-3">
      {docs.map((d) => {
        const on = !!have[d];
        return (
          <li key={d}>
            <button type="button" role="checkbox" aria-checked={on}
              onClick={() => setHave((h) => ({ ...h, [d]: !h[d] }))}
              className={cx('ss-press flex w-full items-center gap-3 rounded-sm border-2 p-3 text-left',
                on ? 'border-field-700 bg-field-100' : 'border-line-strong bg-surface-raised')}>
              <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-sm bg-surface-sunken"><Icon name={docIcon(d)} size={34} /></span>
              <span className="min-w-0 flex-1 break-words text-body font-semibold">{d}</span>
              <span className={cx('flex h-12 min-w-12 shrink-0 items-center justify-center gap-1 rounded-full border-2 px-2 text-caption font-bold',
                on ? 'border-field-700 bg-field-700 text-on-fill' : 'border-line-strong')}>
                {on && <><Icon name="check" size={22} stroke={3} />{t.haveIt}</>}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

/* ------------------------------------------------------------------ SchemeDetailSheet */
function Section({ icon, title, lang, children }) {
  return (
    <section className="border-t-2 border-line pt-6">
      <div className="mb-4 flex items-center gap-3">
        <IconDisc name={icon} />
        <h3 className="min-w-0 flex-1 text-heading">{title}</h3>
        <ListenButton text={title} />
      </div>
      <div lang={lang}>{children}</div>
    </section>
  );
}

function Bullets({ items }) {
  return (
    <ul className="flex flex-col gap-3">
      {items.map((s, i) => (
        <li key={i} className="flex items-start gap-3 text-body">
          <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-field-700 text-on-fill"><Icon name="check" size={18} stroke={3} /></span>
          <span className="min-w-0 break-words">{s}</span>
        </li>
      ))}
    </ul>
  );
}

function LoadingBody({ onRetry, state }) {
  const { t } = useI18n();
  if (state?.status === 'error') {
    const kind = state.error?.kind;
    const banner = kind === 'offline' ? 'offline' : kind === 'timeout' ? 'slow' : kind === 'busy' ? 'busy' : 'error';
    return <div className="mt-6"><StatusBanner kind={banner} onAction={kind === 'not-found' ? undefined : onRetry} /></div>;
  }
  return (
    <div className="mt-6 flex flex-col gap-4" aria-busy="true">
      <BusyNote text={`${t.loadingDetails} ${t.loadingNote}`} />
      {[70, 90, 55].map((w) => <div key={w} className="ss-pulse h-6 rounded-sm bg-surface-sunken" style={{ width: `${w}%` }} />)}
    </div>
  );
}

export function SchemeDetailSheet({ view, official, card, state, whyList, onClose, onRetry }) {
  const { t } = useI18n();
  const back = useRef(null);
  const brief = card?.brief;
  const lang = view.listenLang;
  const docs = brief?.documents || [];
  const applyUrl = card?.apply_url || card?.source_url;
  const sourceUrl = card?.source_url;
  const benefit = brief?.benefit || view.benefit;
  const share = whatsappUrl({ title: view.title, benefit, docs, url: sourceUrl || '' }, t);
  const backLabel = (
    <><Icon name="arrow-left" size={24} />{t.backAll}</>
  );
  const backCls = 'ss-press inline-flex h-touch items-center gap-2 rounded-md border-2 border-line-strong bg-surface-raised px-4 text-label';
  return (
    <SheetLayer onClose={onClose} labelledBy="scheme-title" initialFocus={back}
      panelClass="h-full w-full sm:h-[min(92vh,900px)] sm:max-w-column sm:rounded-lg">
      {(close) => (
        <>
          <div className="shrink-0 border-b-2 border-line bg-surface p-3 sm:rounded-t-lg">
            <button ref={back} type="button" onClick={close} className={backCls}>{backLabel}</button>
          </div>
          <div className="flex-1 overflow-y-auto px-4 pb-8 pt-6">
            <div className="flex items-center gap-4">
              <CategoryDisc category={view.category} size={72} />
              <div className="min-w-0">
                <h2 id="scheme-title" lang={lang} className="break-words text-title">{view.title}</h2>
                {official && official !== view.title && <p lang="en" className="text-caption text-ink-muted">{official}</p>}
              </div>
            </div>
            <div className="mt-4 flex items-center gap-3 rounded-lg bg-turmeric-100 p-4">
              <span className="hidden h-12 w-12 shrink-0 items-center justify-center rounded-full bg-turmeric-400 text-ink sm:flex"><Icon name="rupee" size={26} /></span>
              <p lang={lang} className="min-w-0 flex-1 break-words text-heading">{benefit}</p>
              <ListenButton size="lg" tone="warm" text={benefit} lang={lang} />
            </div>
            <div className="mt-4"><MatchBadge strength={view.strength} /></div>
            {((view.translationStatus === 'fallback_english' || card?.translation_status === 'fallback_english') && lang !== 'en') && (
              <div className="mt-3 flex items-center gap-2 rounded-md bg-turmeric-100/60 p-2 text-caption text-ink-muted">
                <Icon name="link" size={16} />
                <span>{t.englishSourceNotice}</span>
              </div>
            )}

            {!brief ? <LoadingBody state={state} onRetry={onRetry} /> : (
              <div className="mt-6 flex flex-col gap-6">
                <Section icon="help" title={t.whatIs} lang={lang}>
                  <p className="text-body">{brief.spoken || brief.one_line}</p>
                  <div className="mt-3"><ListenButton text={brief.spoken || brief.one_line} lang={lang} /></div>
                </Section>
                {brief.who_can_get && <Section icon="person" title={t.whoCan} lang={lang}><Bullets items={sentences(brief.who_can_get)} /></Section>}
                {brief.benefit && <Section icon="rupee" title={t.whatGet} lang={lang}><Bullets items={sentences(brief.benefit)} /></Section>}
                {docs.length > 0 && <Section icon="aadhaar" title={t.docs} lang={lang}><DocumentChecklist docs={docs} /></Section>}
                <Section icon="map-pin" title={t.howApply} lang={lang}>
                  <div className="flex flex-col gap-3">
                    {brief.how_to_apply && (
                      <div className="flex items-start gap-3 rounded-sm bg-surface-sunken p-3">
                        <Icon name="office" size={28} className="mt-0.5" />
                        <p className="min-w-0 flex-1 break-words text-body font-semibold">{brief.how_to_apply}</p>
                        <ListenButton text={brief.how_to_apply} lang={lang} />
                      </div>
                    )}
                    <div className="flex items-center gap-3 rounded-sm bg-surface-sunken p-3">
                      <Icon name="office" size={28} />
                      <p className="min-w-0 flex-1 text-body">{t.csc}</p>
                      <ListenButton text={t.csc} />
                    </div>
                    {sourceUrl && applyUrl !== sourceUrl && (
                      <a href={sourceUrl} target="_blank" rel="noopener noreferrer"
                        className="ss-press flex items-center gap-3 rounded-sm border-2 border-line-strong bg-surface-raised p-3">
                        <Icon name="link" size={28} />
                        <span className="min-w-0 flex-1"><span className="block text-caption text-ink-muted">{t.officialPage}</span><span className="block break-all text-body font-semibold">{hostOf(sourceUrl)}</span></span>
                        <Icon name="chevron-right" size={24} />
                      </a>
                    )}
                    {applyUrl && <ActionButton variant="primary" icon="link" href={applyUrl} newTab>{card?.apply_url ? t.applyOnline : t.openSite}</ActionButton>}
                  </div>
                </Section>
                {whyList.length > 0 && (
                  <Section icon="search" title={t.whyShown} lang={lang}>
                    <Bullets items={whyList.map((w) => translateReason(w, lang))} />
                  </Section>
                )}
              </div>
            )}

            <div className="mt-8 flex flex-col gap-3 border-t-2 border-line pt-6">
              <ActionButton icon="share" href={share} newTab>{t.share}</ActionButton>
              <p className="text-center text-caption text-ink-muted">{t.shareHint}</p>
              <button type="button" onClick={close} className={cx(backCls, 'h-touch-primary w-full justify-center')}>{backLabel}</button>
            </div>
          </div>
        </>
      )}
    </SheetLayer>
  );
}

/* ------------------------------------------------------------------ SearchingState */
function FieldSunrise({ progress }) {
  const p = Math.max(0, Math.min(1, progress));
  const rays = Array.from({ length: 8 }, (_, i) => i * 45);
  return (
    <svg viewBox="0 0 280 180" className="ss-sunrise w-full max-w-[280px]" role="img" aria-label="" aria-hidden="true">
      <rect width="280" height="180" rx="28" className="ss-fill-sunken" />
      <g className="ss-sun" style={{ transform: `translateY(${(1 - p) * 50}px)` }}>
        {rays.map((a) => (
          <line key={a} x1="140" y1="68" x2="140" y2="50" strokeWidth="5" strokeLinecap="round"
            style={{ stroke: 'var(--turmeric-400)' }} transform={`rotate(${a} 140 100)`} />
        ))}
        <circle cx="140" cy="100" r="28" style={{ fill: 'var(--turmeric-400)' }} />
      </g>
      <rect y="120" width="280" height="60" className="ss-fill-field100" />
      {[50, 95, 140, 185, 230].map((x) => {
        const h = 12 + p * 30;
        return (
          <g key={x}>
            <line x1={x} y1="165" x2={x} y2={165 - h} strokeWidth="4" strokeLinecap="round" style={{ stroke: 'var(--field-700)' }} />
            <ellipse cx={x - 7} cy={165 - h} rx="7" ry="4" style={{ fill: 'var(--field-500)', opacity: 0.4 + p * 0.6 }} />
            <ellipse cx={x + 7} cy={165 - h + 6} rx="7" ry="4" style={{ fill: 'var(--field-500)', opacity: 0.4 + p * 0.6 }} />
          </g>
        );
      })}
    </svg>
  );
}

export function SearchingState({ message, progress, slow }) {
  const { t } = useI18n();
  return (
    <div className="flex flex-col items-center gap-6 text-center">
      <FieldSunrise progress={progress} />
      <div className="flex items-center gap-3" aria-live="polite">
        <h1 className="text-title">{message}</h1>
        <ListenButton size="lg" text={message} />
      </div>
      <p className="text-body text-ink-muted">{t.searchNote}</p>
      <div className="h-4 w-full overflow-hidden rounded-full border-2 border-line-strong bg-surface-sunken" role="progressbar"
        aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)}>
        <div className="h-full rounded-full bg-field-500" style={{ width: `${Math.round(progress * 100)}%`, transition: 'width 700ms ease' }} />
      </div>
      {slow && <div className="w-full text-left"><StatusBanner kind="slow" /></div>}
    </div>
  );
}

/* ------------------------------------------------------------------ EmptyState */
export function EmptyState({ onTellMore }) {
  const { t } = useI18n();
  const rows = [['mic', t.noneTell], ['office', t.noneCsc], ['phone', t.noneCall]];
  return (
    <div className="flex flex-col gap-6">
      <svg viewBox="0 0 280 140" className="mx-auto w-full max-w-[280px]" aria-hidden="true">
        <rect width="280" height="140" rx="28" className="ss-fill-sunken" />
        <circle cx="205" cy="48" r="20" style={{ fill: 'var(--turmeric-400)' }} />
        <path d="M0 110 Q70 80 140 105 T280 100 V140 H0z" className="ss-fill-field100" />
        <line x1="90" y1="112" x2="90" y2="85" strokeWidth="4" strokeLinecap="round" style={{ stroke: 'var(--field-700)' }} />
        <ellipse cx="83" cy="85" rx="7" ry="4" style={{ fill: 'var(--field-500)' }} />
        <ellipse cx="97" cy="91" rx="7" ry="4" style={{ fill: 'var(--field-500)' }} />
      </svg>
      <div className="flex items-center gap-3">
        <h1 className="min-w-0 flex-1 text-title">{t.noneTitle}</h1>
        <ListenButton size="lg" text={t.noneTitle} />
      </div>
      <div className="flex items-center gap-3">
        <p className="min-w-0 flex-1 text-body">{t.noneIntro}</p>
        <ListenButton text={t.noneIntro} />
      </div>
      <ul className="flex flex-col gap-3">
        {rows.map(([icon, text]) => (
          <li key={icon} className="flex items-center gap-3 rounded-lg bg-surface-raised p-4 shadow-card">
            <IconDisc name={icon} />
            <p className="min-w-0 flex-1 text-body font-bold">{text}</p>
            <ListenButton text={text} />
          </li>
        ))}
      </ul>
      <ActionButton variant="primary" icon="mic" onClick={onTellMore}>{t.tellMore}</ActionButton>
    </div>
  );
}
