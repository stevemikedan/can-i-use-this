import { useCallback, useEffect, useRef, useState } from 'react'
import type { Intent, Jurisdiction, QueryParams, RightsResponse } from './types'
import { runQuery } from './lib/api'
import { splitQuery } from './lib/format'
import Result from './screens/Result'

// Development fixtures: real RightsResponses captured from the pipeline
// (web/src/dev/*.json). ?fixture=<name> renders one without the API.
const FIXTURES = import.meta.glob<RightsResponse>('./dev/*.json', { import: 'default' })
const fixtureNames = Object.keys(FIXTURES).map((p) => p.replace('./dev/', '').replace('.json', '')).sort()

type Screen =
  | { kind: 'entry' }
  | { kind: 'result'; resp: RightsResponse; params: QueryParams }

export default function App() {
  const [screen, setScreen] = useState<Screen>({ kind: 'entry' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abort = useRef<AbortController | null>(null)

  const fixtureParam = new URLSearchParams(window.location.search).get('fixture')

  useEffect(() => {
    if (!fixtureParam) return
    const loader = FIXTURES[`./dev/${fixtureParam}.json`]
    if (!loader) return
    loader().then((resp) => {
      const { title, artist } = splitQuery(resp.query.raw_input)
      setScreen({ kind: 'result', resp, params: { title, artist: artist ?? undefined, intent: resp.query.intent, jurisdiction: resp.query.jurisdiction } })
    })
  }, [fixtureParam])

  const run = useCallback(async (params: QueryParams) => {
    abort.current?.abort()
    const ac = new AbortController()
    abort.current = ac
    setBusy(true)
    setError(null)
    try {
      const resp = await runQuery(params, ac.signal)
      if (!ac.signal.aborted) setScreen({ kind: 'result', resp, params })
    } catch (e) {
      if (!ac.signal.aborted) setError(e instanceof Error ? e.message : String(e))
    } finally {
      if (!ac.signal.aborted) setBusy(false)
    }
  }, [])

  const devBar = fixtureParam && (
    <div className="max-w-[920px] mx-auto px-6 pt-3 flex gap-x-3 gap-y-1 items-baseline flex-wrap text-meta">
      <span className="eyebrow text-ink-70">Dev — fixture</span>
      {fixtureNames.map((n) => (
        <a key={n} href={`?fixture=${n}`} className={`font-mono ${n === fixtureParam ? 'text-ink font-semibold no-underline' : ''}`}>{n}</a>
      ))}
      {error && <span className="text-ink-70">— {error}</span>}
    </div>
  )

  if (screen.kind === 'result') {
    const p = screen.params
    return (
      <>
        {devBar}
        <Result
          resp={screen.resp}
          intent={busy ? pendingIntent.current ?? p.intent : p.intent}
          jurisdiction={busy ? pendingJur.current ?? p.jurisdiction : p.jurisdiction}
          busy={busy}
          onIntent={(intent: Intent) => { pendingIntent.current = intent; pendingJur.current = p.jurisdiction; run({ ...p, intent }) }}
          onJurisdiction={(jurisdiction: Jurisdiction) => { pendingJur.current = jurisdiction; pendingIntent.current = p.intent; run({ ...p, jurisdiction }) }}
          onNewInquiry={() => { abort.current?.abort(); setBusy(false); setScreen({ kind: 'entry' }); window.history.replaceState(null, '', '/') }}
        />
        {error && <div className="max-w-[920px] mx-auto px-6 pb-8 text-body text-ink-70">Could not re-run the inquiry: {error}</div>}
      </>
    )
  }

  // Temporary entry form until the Entry screen is built.
  return (
    <>
      {devBar}
      <TempEntry busy={busy} error={error} onSubmit={run} />
    </>
  )
}

const pendingIntent = { current: null as Intent | null }
const pendingJur = { current: null as Jurisdiction | null }

function TempEntry({ busy, error, onSubmit }: { busy: boolean; error: string | null; onSubmit: (p: QueryParams) => void }) {
  const [title, setTitle] = useState('West End Blues')
  const [artist, setArtist] = useState('Louis Armstrong')
  return (
    <div className="max-w-[920px] mx-auto px-6 py-14 flex flex-col gap-4">
      <div className="eyebrow">Subject of inquiry (temporary form)</div>
      <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title" aria-label="Title"
        className="bg-transparent border-0 border-b-[3px] border-ink py-2 text-headline font-bold outline-none focus:border-blue" />
      <input value={artist} onChange={(e) => setArtist(e.target.value)} placeholder="Artist" aria-label="Artist"
        className="bg-transparent border-0 border-b-[3px] border-ink py-2 text-title font-bold outline-none focus:border-blue" />
      <div className="flex gap-4 items-baseline">
        <button type="button" className="btn-primary" disabled={busy} onClick={() => onSubmit({ title, artist: artist || undefined, intent: 'film_tv', jurisdiction: 'US' })}>
          {busy ? 'Researching…' : 'Begin research'}
        </button>
        {fixtureNames.length > 0 && <a href={`?fixture=${fixtureNames[0]}`} className="text-body">or open a fixture</a>}
      </div>
      {error && <div className="text-body text-ink-70">{error}</div>}
    </div>
  )
}
