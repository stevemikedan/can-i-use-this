// Shared primitives — docs/design-system.md §5 "Shared".
import type { ReactNode } from 'react'
import type { Confidence, Intent, Jurisdiction, Verdict } from '../types'
import { INTENT_OPTIONS, JURISDICTIONS, TICKS, VERDICT_COLOR, VERDICT_UNDERLINE, VERDICT_WORD, confidenceLabel } from '../lib/format'
import { nav } from '../lib/nav'

export function Eyebrow({ children, className = '', tracking = 14 }: { children: ReactNode; className?: string; tracking?: 12 | 14 }) {
  return <div className={`${tracking === 12 ? 'eyebrow-12' : 'eyebrow'} ${className}`}>{children}</div>
}

/** Section head: eyebrow + one-sentence subtitle over a 1px INK rule. */
export function SectionHead({ title, sub, right }: { title: ReactNode; sub?: ReactNode; right?: ReactNode }) {
  return (
    <div className="border-b border-ink pb-[14px] flex gap-y-[6px] gap-x-5 items-baseline flex-wrap">
      <div className="flex flex-col gap-[6px] flex-[1_1_240px]">
        <Eyebrow>{title}</Eyebrow>
        {sub && <div className="text-body leading-[1.5] text-ink-70">{sub}</div>}
      </div>
      {right}
    </div>
  )
}

/** Verdict word in its stamp color. size: 38 blocking · 28 layer · 16 small · 21 record. */
export function Stamp({ verdict, size = 28, underline = false, muted = false, className = '' }:
  { verdict: Verdict; size?: 16 | 21 | 28 | 38; underline?: boolean; muted?: boolean; className?: string }) {
  const sizeCls = { 16: 'text-body tracking-[0.04em]', 21: 'text-title tracking-[0.02em]', 28: 'text-headline leading-[1.05] tracking-[0.01em]', 38: 'text-stat leading-[1.05] tracking-[0.01em]' }[size]
  return (
    <div className={`font-bold uppercase text-balance ${sizeCls} ${muted ? 'text-ink-70' : VERDICT_COLOR[verdict]} ${underline ? `${VERDICT_UNDERLINE[verdict]} pb-2 self-start` : ''} ${className}`}>
      {VERDICT_WORD[verdict]}
    </div>
  )
}

/** Four ticks and the label in words. size: overall 6×16 · layer 5×13 · evidence 4×11. */
export function Ticks({ level, size = 'layer', onInk = false, label = true }:
  { level: Confidence; size?: 'overall' | 'layer' | 'evidence'; onInk?: boolean; label?: boolean }) {
  const n = TICKS[level]
  const dims = { overall: 'w-[6px] h-4', layer: 'w-[5px] h-[13px]', evidence: 'w-1 h-[11px]' }[size]
  const gap = size === 'evidence' ? 'gap-[2px]' : 'gap-[3px]'
  const on = onInk ? 'bg-blue-on-ink' : 'bg-ink'
  const off = onInk ? 'bg-paper-25' : 'bg-ink-20'
  const labelCls = size === 'overall' ? 'text-body font-medium' : 'text-meta font-medium text-ink-70'
  return (
    <div className={`flex items-center ${size === 'evidence' ? 'gap-[6px]' : size === 'layer' ? 'gap-[7px]' : 'gap-2'}`} aria-label={confidenceLabel(level)}>
      <div className={`flex ${gap}`} aria-hidden="true">
        {[0, 1, 2, 3].map((i) => <div key={i} className={`${dims} ${i < n ? on : off}`} />)}
      </div>
      {label && <div className={`${labelCls} ${size === 'evidence' ? 'leading-none' : ''} ${onInk && size === 'overall' ? 'text-paper' : ''}`}>{confidenceLabel(level)}</div>}
    </div>
  )
}

export function Tag({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`tag ${className}`}>{children}</div>
}

export function TextToggle({ open, closed, opened, onClick, className = '' }:
  { open: boolean; closed: string; opened: string; onClick: () => void; className?: string }) {
  return (
    <button type="button" className={`text-toggle ${className}`} aria-expanded={open} onClick={onClick}>
      {open ? opened : closed}
    </button>
  )
}

/** Purpose and territory selectors. Same component on paper and on the band (wrap the band in .on-ink). */
export function Controls({ intent, jurisdiction, onIntent, onJurisdiction, onInk = false, busy = false }:
  { intent: Intent; jurisdiction: Jurisdiction; onIntent: (i: Intent) => void; onJurisdiction: (j: Jurisdiction) => void; onInk?: boolean; busy?: boolean }) {
  const labelCls = onInk ? 'text-paper-72' : 'text-ink-70'
  return (
    <div className="flex flex-col gap-[22px]" aria-busy={busy}>
      <div className="flex flex-col gap-[10px]">
        <Eyebrow className={labelCls}>Purpose of use</Eyebrow>
        <div className="flex gap-2 flex-wrap" role="group" aria-label="Purpose of use">
          {INTENT_OPTIONS.map((o) => (
            <button key={o.value} type="button" className="control" aria-pressed={intent === o.value} onClick={() => onIntent(o.value)}>{o.label}</button>
          ))}
        </div>
      </div>
      <div className="flex flex-col gap-[10px]">
        <Eyebrow className={labelCls}>Territory</Eyebrow>
        <div className="flex gap-2" role="group" aria-label="Territory">
          {JURISDICTIONS.map((j) => (
            <button key={j} type="button" className="control" aria-pressed={jurisdiction === j} onClick={() => onJurisdiction(j)}>{j}</button>
          ))}
        </div>
      </div>
    </div>
  )
}

function MastLink({ to, children }: { to: 'cues' | 'about'; children: ReactNode }) {
  return (
    <a href={`/${to}`} onClick={(e) => { e.preventDefault(); nav(to) }}
      className="no-print font-mono font-medium text-meta tracking-[0.08em] uppercase text-blue-on-ink underline decoration-[1.5px] underline-offset-[3px] hover:text-paper">
      {children}
    </a>
  )
}

/** The INK band. Children supply the screen-specific content; the masthead
    carries the register's two standing links on every screen — a document
    header, not website chrome. */
export function Band({ label, context, children, padding = 'pt-7 pb-12' }:
  { label: string; context?: ReactNode; children: ReactNode; padding?: string }) {
  return (
    <div className="on-ink bg-ink text-paper">
      <div className={`max-w-[920px] mx-auto px-4 max-[560px]:pt-6 max-[560px]:pb-9 sm:px-6 ${padding} flex flex-col gap-9`}>
        <div className="flex items-baseline justify-between gap-4 flex-wrap">
          <Eyebrow tracking={12}>{label}</Eyebrow>
          <div className="flex gap-5 items-baseline flex-wrap">
            {context}
            <MastLink to="cues">Cue sheet</MastLink>
            <MastLink to="about">About</MastLink>
          </div>
        </div>
        {children}
      </div>
    </div>
  )
}

/** Site footer: sources named, repo linked, the disclaimer everywhere. META with a top rule. */
export function Footer() {
  const src = (name: string, href: string) => (
    <a key={name} href={href} target="_blank" rel="noopener" className="text-ink-70 hover:text-ink">{name}</a>
  )
  return (
    <footer className="no-print max-w-[920px] mx-auto px-4 sm:px-6 pb-10">
      <div className="border-t border-ink-20 pt-4 flex flex-col gap-2 text-meta font-medium leading-[1.7] text-ink-70">
        <div className="flex gap-x-4 gap-y-1 items-baseline flex-wrap">
          <span className="eyebrow-12 tracking-[0.1em]">Sources</span>
          {src('MusicBrainz', 'https://musicbrainz.org/')}
          {src('Wikidata', 'https://www.wikidata.org/')}
          {src('The MLC', 'https://portal.themlc.com/')}
          {src('US Copyright Office', 'https://www.copyright.gov/')}
          <span className="eyebrow-12 tracking-[0.1em] ml-2">Code</span>
          {src('github.com/stevemikedan/can-i-use-this', 'https://github.com/stevemikedan/can-i-use-this')}
        </div>
        <div className="max-w-[78ch]">This is research, not legal advice. Verify before relying on it for anything consequential.</div>
      </div>
    </footer>
  )
}

/** The document column under the band. */
export function Doc({ children }: { children: ReactNode }) {
  return <div className="max-w-[920px] mx-auto px-4 pb-16 sm:px-6 sm:pb-20">{children}</div>
}
