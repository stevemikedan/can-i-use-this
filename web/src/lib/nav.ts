// Masthead navigation without page reloads: the Band renders the links, the
// App owns the routing. A module-level handler keeps Band a dumb component
// and avoids losing in-memory state (a researched record, cue rows) to a
// full navigation.
export type NavTarget = 'entry' | 'cues' | 'about'

let handler: (t: NavTarget) => void = (t) => {
  // Before the App registers (or if it never does), fall back to real URLs —
  // the SPA fallback serves the app at every route.
  window.location.href = t === 'entry' ? '/' : `/${t}`
}

export function setNavHandler(h: (t: NavTarget) => void): void {
  handler = h
}

export function nav(t: NavTarget): void {
  handler(t)
}
