import { Link } from 'react-router-dom'
import { SITE } from '../../../config/site'

export function FooterLogo() {
  return (
    <Link to="/landing" className="cf-logo" aria-label={`${SITE.name} home`}>
      <svg className="cf-logo__mark" width="37" height="22" viewBox="0 0 37 22" aria-hidden="true">
        <circle cx="26.3" cy="11" r="9.75" fill="none" stroke="#000" strokeWidth="1.5" />
        <circle cx="10.5" cy="11" r="10.5" fill="#000" />
      </svg>
      <span>{SITE.name}</span>
    </Link>
  )
}

export default FooterLogo
