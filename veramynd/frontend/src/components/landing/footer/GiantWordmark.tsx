import { SITE } from '../../../config/site'

// Oversized wordmark; the section clips its lower half on purpose.
export function GiantWordmark() {
  return (
    <div className="cf-wordmark" aria-hidden="true">
      <span>{SITE.name}</span>
    </div>
  )
}

export default GiantWordmark
