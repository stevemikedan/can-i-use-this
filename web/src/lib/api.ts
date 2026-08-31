import type { PipelineEvent, QueryParams, RightsResponse } from '../types'

/** One query, waiting for the result. Used for control toggles on Result (warm: ~1 s). */
export async function runQuery(p: QueryParams, signal?: AbortSignal): Promise<RightsResponse> {
  const r = await fetch('/api/query', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      title: p.title, artist: p.artist || null, intent: p.intent, jurisdiction: p.jurisdiction,
      answers: p.answers && Object.keys(p.answers).length ? p.answers : undefined,
    }),
    signal,
  })
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return (await r.json()) as RightsResponse
}

export interface StreamHandlers {
  onProgress: (ev: PipelineEvent) => void
  onResponse: (resp: RightsResponse) => void
  onError: (message: string) => void
}

/** The same query as SSE: every PipelineEvent as it happens, then the response. Returns a stop function. */
export function streamQuery(p: QueryParams, h: StreamHandlers): () => void {
  const qs = new URLSearchParams({ title: p.title, intent: p.intent, jurisdiction: p.jurisdiction })
  if (p.artist) qs.set('artist', p.artist)
  const es = new EventSource(`/api/query/stream?${qs}`)
  let done = false
  es.addEventListener('progress', (e) => h.onProgress(JSON.parse((e as MessageEvent).data) as PipelineEvent))
  es.addEventListener('response', (e) => {
    done = true
    es.close()
    h.onResponse(JSON.parse((e as MessageEvent).data) as RightsResponse)
  })
  es.addEventListener('error', (e) => {
    if (done) return
    done = true
    es.close()
    const data = (e as MessageEvent).data
    let message = 'The connection to the research service was lost.'
    if (typeof data === 'string') {
      try { message = (JSON.parse(data) as { error: string }).error } catch { /* keep default */ }
    }
    h.onError(message)
  })
  es.onerror = () => {
    if (done) return
    done = true
    es.close()
    h.onError('The connection to the research service was lost.')
  }
  return () => { done = true; es.close() }
}
