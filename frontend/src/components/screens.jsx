import React, { useEffect, useRef, useState } from 'react';
import { Icon } from './icons';
import {
  ActionButton, BusyNote, ChatBubble, LanguageTile, ListenButton, MicButton, QuickReplyChip, StatusBanner,
  SummaryCard, TextFallback, VoiceWave, useAutoSpeak,
} from './ui';
import { EmptyState, SchemeCard, SearchingState } from './scheme-ui';
import { LANGUAGES, useI18n } from '../lib/i18n';
import { TOPICS, chipLabel, chipSend, chipsFor, topicSend } from '../lib/chips';
import { api, bannerFor } from '../lib/api';
import { schemeView, splitResults } from '../lib/schemes';

const Screen = ({ children, className = '' }) => <div className={`ss-screen flex flex-col ${className}`}>{children}</div>;

/** Heading/prompt with its ListenButton beside it. */
function Spoken({ as: Tag = 'h2', text, size, className = '', lang }) {
  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <Tag lang={lang} className={`min-w-0 flex-1 ${size}`}>{text}</Tag>
      <ListenButton size={size === 'text-heading' ? 'md' : 'lg'} text={text} lang={lang} />
    </div>
  );
}

/* ------------------------------------------------------------------ Welcome */
export function WelcomeScreen({ lang, onPickLanguage, rec, busy, onMic, onSendText }) {
  const { t } = useI18n();
  useAutoSpeak(t.tellProblem, lang);
  return (
    <Screen>
      <Spoken text={t.chooseLanguage} size="text-heading" />
      <div className="mt-4 grid grid-cols-2 gap-3 sm:gap-4">
        {LANGUAGES.map((l) => (
          <LanguageTile key={l.code} language={l} selected={l.code === lang} onSelect={onPickLanguage} />
        ))}
      </div>
      <Spoken as="h1" text={t.tellProblem} size="text-display" className="mt-12" />
      <div className="mt-8 flex flex-col items-center gap-6">
        {busy ? <div className="w-full"><BusyNote text={busy === 'transcribing' ? t.writing : t.thinking} /></div> : rec.blocked ? (
          <>
            <MicButton state="disabled" label={t.tapToSpeak} size="lg" />
            <div className="w-full"><StatusBanner kind="mic-off" /></div>
            <div className="flex flex-wrap justify-center gap-3">
              {TOPICS.map((tp) => (
                <QuickReplyChip key={tp.id} icon={tp.icon} label={t[tp.key]} lang={lang} onClick={() => onSendText(topicSend(tp, lang))} />
              ))}
            </div>
            <TextFallback lang={lang} onSend={onSendText} />
          </>
        ) : (
          <MicButton state="idle" label={t.tapToSpeak} onClick={onMic} />
        )}
      </div>
    </Screen>
  );
}

/* ------------------------------------------------------------------ Listening */
export function ListeningScreen({ lang, rec, busy, heardText, sorry, prompt, onDone, onToggle, onAgain, onStart, onSendText }) {
  const { t } = useI18n();
  const recording = rec.status === 'recording';
  const paused = rec.status === 'paused';
  const active = recording || paused;
  const line = sorry ? t.sorryTitle : paused ? t.paused : active ? t.listening : prompt;
  useAutoSpeak(sorry ? `${t.sorryTitle} ${t.sorryBody}` : prompt, lang, !active);
  const micState = rec.blocked ? 'disabled' : recording ? 'listening' : paused ? 'paused' : 'idle';
  const working = !!busy;
  return (
    <Screen className="gap-8">
      {sorry ? (
        <ChatBubble tone="sorry" text={t.sorryTitle} lang={lang}><p className="mt-2 text-body">{t.sorryBody}</p></ChatBubble>
      ) : <ChatBubble icon="mic" text={line} lang={lang} />}
      {rec.blocked ? (
        <>
          <StatusBanner kind="mic-off" />
          <TextFallback lang={lang} onSend={onSendText} disabled={working} />
        </>
      ) : (
        <div className="flex flex-col items-center gap-6">
          <MicButton state={micState} size="lg"
            label={active ? (recording ? t.pause : t.continue) : t.tapToSpeak}
            onClick={active ? onToggle : onStart} />
          <VoiceWave active={recording} />
        </div>
      )}
      <section aria-live="polite" className="min-h-[148px] rounded-lg border-2 border-line bg-surface-sunken p-5">
        <p className="mb-2 flex items-center gap-2 text-caption text-ink-muted"><Icon name="mic" size={20} />{t.youSaid}</p>
        {heardText
          ? <p lang={lang} className="text-transcript">{heardText}</p>
          : <p className="text-transcript text-ink-muted">{busy === 'transcribing' ? t.writing : t.speakNow}{recording && <span className="ss-caret" />}</p>}
        {busy === 'thinking' && <p className="mt-3 text-body text-ink-muted">{t.thinking}</p>}
      </section>
      {!rec.blocked && (
        <div className="flex flex-col gap-3">
          <ActionButton variant="primary" icon="check" onClick={onDone} disabled={!active || !rec.heard || working}>{t.done}</ActionButton>
          <div className="grid grid-cols-2 gap-3">
            <ActionButton icon={recording ? 'pause' : 'play'} onClick={onToggle} disabled={!active || working}>{recording ? t.pause : t.continue}</ActionButton>
            <ActionButton icon="restart" onClick={onAgain} disabled={!active || working}>{t.startAgain}</ActionButton>
          </div>
        </div>
      )}
    </Screen>
  );
}

/* ------------------------------------------------------------------ Questions */
export function QuestionsScreen({ lang, conv, rec, busy, sorry, typing, onChip, onMic, onSendText }) {
  const { t } = useI18n();
  const { thread, last } = conv;
  const endRef = useRef(null);
  const lastBot = [...thread].reverse().find((m) => m.role === 'assistant');
  useAutoSpeak(lastBot?.text, last?.language || lang, !sorry);
  useAutoSpeak(sorry ? `${t.sorryTitle} ${t.sorryBody}` : '', lang, sorry);
  useEffect(() => { endRef.current?.scrollIntoView({ block: 'end' }); }, [thread.length, sorry, busy]);

  const chips = chipsFor(last?.asking_about);
  const recording = rec.status === 'recording' || rec.status === 'paused';
  const working = !!busy;
  const answered = conv.asked.length;
  return (
    <Screen className="gap-6">
      {answered > 0 && <p className="text-caption text-ink-muted">{t.question.replace('{n}', answered)}</p>}
      {thread.map((m, i) => (m.role === 'user'
        ? <ChatBubble key={i} from="user" icon="mic" text={m.text} lang={last?.language || lang} />
        : (
          <ChatBubble key={i} icon={m.icon} text={m.text} lang={m.lang || lang}>
            {i === thread.length - 1 && !sorry && chips.length > 0 && (
              <div className="mt-4 sm:pl-14">
                <p className="mb-2 text-caption text-ink-muted">{t.orTapAnswer}</p>
                <div className="flex flex-wrap gap-3">
                  {chips.map((c) => (
                    <QuickReplyChip key={c.id} icon={c.icon} tone={c.tone} lang={lang} disabled={working}
                      label={chipLabel(c, lang)} onClick={() => onChip(chipSend(c, lang))} />
                  ))}
                </div>
              </div>
            )}
          </ChatBubble>
        )))}
      {sorry && <ChatBubble tone="sorry" text={t.sorryTitle} lang={lang}><p className="mt-2 text-body">{t.sorryBody}</p></ChatBubble>}
      {working && <BusyNote text={busy === 'transcribing' ? t.writing : t.thinking} />}
      <div className="border-t-2 border-line pt-6">
        {rec.blocked ? (
          <div className="flex flex-col gap-4"><StatusBanner kind="mic-off" /></div>
        ) : (
          <div className="flex flex-col items-center gap-4">
            <MicButton size="sm" state={recording ? 'listening' : 'idle'} onClick={onMic}
              label={recording ? `${t.listening} ${t.tapWhenDone}` : t.speakAnswer} />
            {recording && <VoiceWave bars={13} active={rec.status === 'recording'} />}
          </div>
        )}
        {(rec.blocked || typing) && !recording && (
          <div className="mt-6"><TextFallback lang={lang} onSend={onSendText} disabled={working} /></div>
        )}
      </div>
      <div ref={endRef} />
    </Screen>
  );
}

/* ------------------------------------------------------------------ Summary */
export function SummaryScreen({ lang, conv, onConfirm, onCorrect }) {
  const { t } = useI18n();
  const last = conv.last;
  const speakLang = last?.language || lang;
  useAutoSpeak(last?.reply, speakLang);
  return (
    <Screen className="gap-6">
      <SummaryCard title={t.summaryTitle} reply={last?.reply} facts={last?.facts || []} lang={speakLang} />
      <ActionButton variant="confirm" onClick={onConfirm}>{t.yesRight}</ActionButton>
      <ActionButton variant="correct" onClick={onCorrect}>{t.noCorrect}</ActionButton>
    </Screen>
  );
}

/* ------------------------------------------------------------------ Searching */
export function SearchingScreen({ profile, lang, offline, onDone }) {
  const { t } = useI18n();
  const [progress, setProgress] = useState(0.05);
  const [step, setStep] = useState(0);
  const [slow, setSlow] = useState(false);
  const [error, setError] = useState(null);
  const [attempt, setAttempt] = useState(0);
  const started = useRef(null);
  const messages = [t.searching1, t.searching2, t.searching3];
  useAutoSpeak(messages[0], lang);

  // Wait for the internet to come back instead of failing; hold at the first step meanwhile.
  useEffect(() => {
    if (offline) return undefined;
    let cancelled = false;
    setError(null);
    setSlow(false);
    started.current = Date.now();
    const tick = setInterval(() => {
      const s = (Date.now() - started.current) / 1000;
      setStep(Math.min(2, Math.floor(s / 3)));
      setProgress((p) => Math.min(0.9, p + (0.9 - p) * 0.06));
      if (s > 8) setSlow(true);
    }, 700);
    api.match(profile, 12, lang)
      .then((res) => {
        if (cancelled) return;
        if (res.count === 0 && res.searched > 0 && res.failed_searches >= res.searched) {
          throw Object.assign(new Error('portal'), { kind: 'error' });   // every search failed: not "no schemes"
        }
        setProgress(1);
        setTimeout(() => { if (!cancelled) onDone(res); }, 750);
      })
      .catch((err) => { if (!cancelled) setError(err); })
      .finally(() => clearInterval(tick));
    return () => { cancelled = true; clearInterval(tick); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offline, attempt, lang]);

  const banner = error ? bannerFor(error) : null;
  return (
    <Screen className="gap-6">
      <SearchingState message={offline ? messages[0] : messages[step]} progress={offline ? 0.05 : progress} slow={slow && !error && !offline} />
      {banner && <StatusBanner kind={banner.kind} onAction={banner.retry ? () => { setProgress(0.05); setAttempt((a) => a + 1); } : undefined} />}
    </Screen>
  );
}

/* ------------------------------------------------------------------ Results */
export function ResultsScreen({ lang, results, cards, cardKey, flippingSlug, onOpen, onTellMore, onRetrySearch }) {
  const { t } = useI18n();
  const schemes = results.schemes || [];
  useAutoSpeak(t.resultsTitle, lang);
  if (!schemes.length) return <Screen><EmptyState onTellMore={onTellMore} /></Screen>;
  const { main, related } = splitResults(schemes);
  const view = (s) => schemeView(s, cards[cardKey(s.slug)]?.data, lang);
  const grid = 'grid grid-cols-1 gap-6 lg:grid-cols-2';
  const renderCard = (s) => <SchemeCard key={s.slug} view={view(s)} flipping={flippingSlug === s.slug} onOpen={onOpen} />;
  return (
    <Screen className="gap-6">
      {results.failed_searches > 0 && <StatusBanner kind="partial" onAction={onRetrySearch} />}
      <Spoken as="h1" text={t.resultsTitle} size="text-title" />
      <p className="flex items-center gap-2 text-body text-ink-muted"><Icon name="chevron-right" size={22} />{t.tapCard}</p>
      <div className={grid}>{main.map(renderCard)}</div>
      {related.length > 0 && (
        <>
          <div className="mt-6 border-t-2 border-line pt-12">
            <Spoken text={t.related} size="text-heading" />
          </div>
          <div className={grid}>{related.map(renderCard)}</div>
        </>
      )}
    </Screen>
  );
}
