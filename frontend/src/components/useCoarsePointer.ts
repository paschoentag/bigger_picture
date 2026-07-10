import { useEffect, useState } from 'react'

const QUERY = '(pointer: coarse)'

/**
 * True when the device's primary pointer is touch (no mouse/trackpad precision).
 * Used to gate interactions that need pixel-accurate clicking, like point annotation,
 * since touch's imprecision is inherent to the input and doesn't improve with more
 * screen space the way a layout reflow would.
 */
export function useCoarsePointer(): boolean {
  const [coarse, setCoarse] = useState(() => window.matchMedia(QUERY).matches)

  useEffect(() => {
    const mql = window.matchMedia(QUERY)
    const onChange = () => setCoarse(mql.matches)
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [])

  return coarse
}
