import { Link } from 'react-router-dom'
import { SITE } from '../../../config/site'

export function BrandLogo() {
  return (
    <Link to="/landing" className="fs-brand" aria-label={`${SITE.name} home`}>
      <svg className="fs-brand__mark" width="35" height="22" viewBox="0 0 35 22" aria-hidden="true">
        <circle cx="11" cy="11" r="11" fill="#000" />
        <circle cx="23.5" cy="11" r="10.5" fill="none" stroke="#000" strokeWidth="1" />
      </svg>
      <span className="fs-brand__name">{SITE.name}</span>
    </Link>
  )
}

export default BrandLogo
