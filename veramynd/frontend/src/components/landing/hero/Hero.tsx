import BrandLogo from './BrandLogo'
import CircleMark from './CircleMark'
import HeroNavigation from './HeroNavigation'
import HeroSearch from './HeroSearch'
import MetricsTicker from './MetricsTicker'
import './hero.css'

type Props = {
  onAsk?: (query: string) => void
}

export function Hero({ onAsk }: Props) {
  return (
    <section className="fs-hero" aria-label="Hero">
      <MetricsTicker />

      <div className="fs-hero__stage">
        <div className="fs-hero__bg" aria-hidden="true" />
        <div className="fs-hero__grain" aria-hidden="true" />

        <header className="fs-hero__top">
          <BrandLogo />
          <HeroNavigation />
        </header>

        <div className="fs-hero__center">
          <CircleMark />
          <p className="fs-hero__eyebrow">Auditable alignment of teacher guides to state academic standards.</p>
          <h1 className="fs-hero__title">
            <span>Evidence-Backed</span>
            <span>Standards Alignment.</span>
          </h1>
          <HeroSearch onAsk={onAsk} />
        </div>
      </div>
    </section>
  )
}

export default Hero
