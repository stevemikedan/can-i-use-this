import { useCallback, useEffect, useRef, useState } from 'react'
import type { PipelineEvent, QueryParams, RightsResponse } from './types'
import { checkCached, runQuery, streamQuery } from './lib/api'
import Entry from './screens/Entry'
import Progress from './screens/Progress'
import Resume from './screens/Resume'
import Result from './screens/Result'
import Disambiguation from './screens/Disambiguation'
import About from './screens/About'
import Cues, { type CueRow } from './screens/Cues'
import { Boundary, ErrorScreen, NotFound } from './screens/Status'
import { paramsFromUrl, permalinkFor } from './lib/export'
import { setNavHandler } from './lib/nav'
import { Footer } from './components/ui'

type Screen = 'entry' | 'progress' | 'result' | 'disambiguation' | 'notfound' | 'boundary' | 'error' | 'about' | 'cues' | 'resume'

const DEFAULT_PARAMS: QueryParams = { title: '', intent: 'documentary', jurisdiction: 'US' }

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
  const [screen, setScreen] = useState<Screen>(
    window.location.pathname === '/about' ? 'about' : window.location.pathname === '/cues' ? 'cues' : 'entry')
  const [cueRows, setCueRows] = useState<CueRow[]>([])
  const [fromCues, setFromCues] = useState(false)
  const [params, setParams] = useState<QueryParams>(DEFAULT_PARAMS)
  const [resp, setResp] = useState<RightsResponse | null>(null)
  const [events, setEvents] = useState<PipelineEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)          // Result control toggles only
  const [resumeAt, setResumeAt] = useState<string | null>(null)   // permalink: when the record was researched
  const stopStream = useRef<(() => void) | null>(null)
  const abort = useRef<AbortController | null>(null)

  /** Full run with the streamed progress screen. */
  const research = useCallback((p: QueryParams) => {
    stopStream.current?.()
    setParams(p)
    setFromCues(false)
    setEvents([])
    setError(null)
    setScreen('progress')
    try { window.history.replaceState(null, '', permalinkFor(p).slice(window.location.origin.length)) } catch { /* permalink is best-effort */ }
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
    window.history.replaceState(null, '', '/')
  }, [])

  const toAbout = useCallback(() => {
    setScreen('about')
    window.history.replaceState(null, '', '/about')
  }, [])

  const toCues = useCallback(() => {
    setScreen('cues')
    window.history.replaceState(null, '', '/cues')
  }, [])

  useEffect(() => {
    setNavHandler((t) => {
      if (t === 'entry') toEntry()
      else if (t === 'cues') toCues()
      else toAbout()
    })
  }, [toEntry, toCues, toAbout])

  // A shared permalink (/?q=...) re-opens the record. It auto-runs only when
  // the record was researched recently enough that the re-run is effectively
  // instant; otherwise the reader chooses whether to spend a research run.
  useEffect(() => {
    const p = paramsFromUrl(window.location.search)
    if (!p) return
    setParams(p)
    checkCached(p)
      .then((c) => {
        if (c.researched && c.fresh) research(p)
        else { setResumeAt(c.researched_at); setScreen('resume') }
      })
      .catch(() => { setResumeAt(null); setScreen('resume') })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const body = (() => {
    switch (screen) {
      case 'resume':
        return <Resume params={params} researchedAt={resumeAt}
          onResearch={() => research(params)} onNewInquiry={toEntry} />
      case 'progress':
        return <Progress params={params} events={events} onCancel={toEntry} />
      case 'result':
        return resp && (
          <>
            <Result resp={resp} params={params} busy={busy}
              onIntent={(intent) => requery({ ...params, intent })}
              onJurisdiction={(jurisdiction) => requery({ ...params, jurisdiction })}
              onDuration={(duration) => requery({ ...params, duration })}
              onAnswer={(questionId, answer, attestation) =>
                requery({ ...params, answers: { ...(params.answers ?? {}), [questionId]: { answer, attestation: attestation || null } } })}
              onNewInquiry={toEntry}
              onBack={fromCues ? toCues : undefined} />
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
      case 'about':
        return <About onNewInquiry={toEntry} />
      case 'cues':
        return <Cues params={params} rows={cueRows} setRows={setCueRows} onNewInquiry={toEntry}
          onOpen={(r, p) => { setResp(r); setParams(p); setFromCues(true); setScreen('result') }} />
      default:
        return <Entry busy={false} error={null} initial={params.title ? params : undefined} onSubmit={research} onAbout={toAbout} onCues={toCues} />
    }
  })()

  return (
    <>
      {body}
      <Footer />
    </>
  )
}
