import { useNavigate } from 'react-router-dom'
import AudienceSection from '../components/landing/audience/AudienceSection'
import CtaSection from '../components/landing/cta/CtaSection'
import EngineSection from '../components/landing/engine/EngineSection'
import SiteFooter from '../components/landing/footer/SiteFooter'
import Hero from '../components/landing/hero/Hero'
import ResourcesSection from '../components/landing/resources/ResourcesSection'
import useDocumentTitle from '../components/landing/useDocumentTitle'
import useHashScroll from '../components/landing/useHashScroll'
import { SITE } from '../config/site'
import WorkflowSection from '../components/landing/workflow/WorkflowSection'

export function LandingPage() {
  const navigate = useNavigate()
  useHashScroll()
  useDocumentTitle(`${SITE.name} — ${SITE.tagline}`)

  return (
    <div className="landing-page">
      <Hero onAsk={(query) => navigate(`/docs?q=${encodeURIComponent(query)}`)} />
      <WorkflowSection />
      <EngineSection />
      <AudienceSection />
      <ResourcesSection />
      <CtaSection />
      <SiteFooter />
    </div>
  )
}

export default LandingPage
