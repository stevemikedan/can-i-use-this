import { useCallback, useEffect, useRef, useState } from 'react'
import type { PipelineEvent, QueryParams, RightsResponse } from './types'
import { runQuery, streamQuery } from './lib/api'
import { splitQuery } from './lib/format'
import Entry from './screens/Entry'
import Progress from './screens/Progress'
import Result from './screens/Result'
import Disambiguation from './screens/Disambiguation'
import { Boundary, ErrorScreen, NotFound } from './screens/Status'

// Development fixtures: real RightsResponses captured from the pipeline
// (web/src/dev/*.json). ?fixture=<name> renders one without running a query.
const FIXTURES = import.meta.glob<RightsResponse>('./dev/*.json', { import: 'default' })
const fixtureNames = Object.keys(FIXTURES).map((p) => p.replace('./dev/', '').replace('.json', '')).sort()

type Screen = 'entry' | 'progress' | 'result' | 'disambiguation' | 'notfound' | 'boundary' | 'error'

const DEFAULT_PARAMS: QueryParams = { title: '', intent: 'film_tv', jurisdiction: 'US' }

function routeFor(resp: RightsResponse): Screen {
  if (resp.stop_for_disambiguation) return 'disambiguation'
  if (resp.boundary_note) return 'boundary'
  if (resp.entity.layers.length === 0) {
    // An unreachable source is a retry, not a "refine your query".
    return resp.unresolved[0]?.question_id === 'resolve:upstream_failure' ? 'error' : 'notfound'
  }
  return 'result'
}

export default function App() {
  const [screen, setScreen] = useState<Screen>('entry')
  const [params, setParams] = useState<QueryParams>(DEFAULT_PARAMS)
  const [resp, setResp] = useState<RightsResponse | null>(null)
  const [events, setEvents] = useState<PipelineEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)          // Result control toggles only
  const stopStream = useRef<(() => void) | null>(null)
  const abort = useRef<AbortController | null>(null)

  const fixtureParam = new URLSearchParams(window.location.search).get('fixture')
  useEffect(() => {
    if (!fixtureParam) return
    const loader = FIXTURES[`./dev/${fixtureParam}.json`]
    if (!loader) return
    loader().then((r) => {
      const { title, artist } = splitQuery(r.query.raw_input)
      setParams({ title, artist: artist ?? undefined, intent: r.query.intent, jurisdiction: r.query.jurisdiction })
      setResp(r)
      setScreen(routeFor(r))
    })
  }, [fixtureParam])

  /** Full run with the streamed progress screen. */
  const research = useCallback((p: QueryParams) => {
    stopStream.current?.()
    setParams(p)
    setEvents([])
    setError(null)
    setScreen('progress')
    stopStream.current = streamQuery(p, {
      onProgress: (ev) => setEvents((es) => [...es, ev]),
      onResponse: (r) => {
        setResp(r)
        const next = routeFor(r)
        if (next === 'error') setError(r.unresolved[0]?.why_it_matters ?? r.overall_headline)
        setScreen(next)
      },
      onError: (message) => { setError(message); setScreen('error') },
    })
  }, [])

  /** Re-run for a control toggle on Result — no progress screen, ~1 s warm. */
  const requery = useCallback(async (p: QueryParams) => {
    abort.current?.abort()
    const ac = new AbortController()
    abort.current = ac
    setBusy(true)
    setError(null)
    try {
      const r = await runQuery(p, ac.signal)
      if (ac.signal.aborted) return
      setParams(p)
      setResp(r)
      setScreen(routeFor(r))
    } catch (e) {
      if (!ac.signal.aborted) setError(e instanceof Error ? e.message : String(e))
    } finally {
      if (!ac.signal.aborted) setBusy(false)
    }
  }, [])

  const toEntry = useCallback(() => {
    stopStream.current?.()
    abort.current?.abort()
    setBusy(false)
    setError(null)
    setScreen('entry')
    if (fixtureParam) window.history.replaceState(null, '', window.location.pathname)
  }, [fixtureParam])

  const devBar = fixtureParam && (
    <div className="max-w-[920px] mx-auto px-6 pt-3 flex gap-x-3 gap-y-1 items-baseline flex-wrap text-meta">
      <span className="eyebrow text-ink-70">Dev — fixture</span>
      {fixtureNames.map((n) => (
        <a key={n} href={`?fixture=${n}`} className={`font-mono ${n === fixtureParam ? 'text-ink font-semibold no-underline' : ''}`}>{n}</a>
      ))}
    </div>
  )

  const body = (() => {
    switch (screen) {
      case 'progress':
        return <Progress params={params} events={events} />
      case 'result':
        return resp && (
          <>
            <Result resp={resp} intent={params.intent} jurisdiction={params.jurisdiction} busy={busy}
              onIntent={(intent) => requery({ ...params, intent })}
              onJurisdiction={(jurisdiction) => requery({ ...params, jurisdiction })}
              onNewInquiry={toEntry} />
            {error && <div className="max-w-[920px] mx-auto px-6 pb-8 text-body text-ink-70">Could not re-run the inquiry: {error}</div>}
          </>
        )
      case 'disambiguation':
        return resp && (
          <Disambiguation resp={resp} params={params}
            onPick={(artist) => research({ ...params, artist })}
            onComposition={(artist) => research({ ...params, artist, intent: 'rerecord' })}
            onRefine={toEntry} />
        )
      case 'notfound':
        return resp && <NotFound resp={resp} params={params} onRefine={toEntry} onRetry={() => research(params)}
          onPick={(title, artist) => research({ ...params, title, artist })} />
      case 'boundary':
        return resp?.boundary_note && <Boundary note={resp.boundary_note} params={params} onNew={toEntry} />
      case 'error':
        return <ErrorScreen message={error ?? 'Unknown failure.'} eventsSeen={events.length} params={params}
          onRetry={() => research(params)} onNew={toEntry} />
      default:
        return <Entry busy={false} error={null} initial={params.title ? params : undefined} onSubmit={research} />
    }
  })()

  return (
    <>
      {devBar}
      {body}
    </>
  )
}
