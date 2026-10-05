import AudienceIcon, { type AudienceIconName } from './AudienceIcon'

type Audience = {
  icon: AudienceIconName
  title: string
  lines: [string, string, string]
}

const AUDIENCES: Audience[] = [
  {
    icon: 'book',
    title: 'Curriculum Publishers',
    lines: ['Correlate every lesson in a guide', 'to state standards, with evidence', 'your clients can audit.'],
  },
  {
    icon: 'checklist',
    title: 'Alignment Reviewers',
    lines: ['Apply one rubric identically to', 'every lesson and standard instead', 'of coding pairs by hand.'],
  },
  {
    icon: 'magnifier',
    title: 'Curriculum Specialists',
    lines: ['Spend expert time on flagged', 'edge cases, with the source page', 'one click away.'],
  },
]

export function AudienceColumns() {
  return (
    <ul className="ro-columns">
      {AUDIENCES.map((a) => (
        <li key={a.title} className="ro-col">
          <AudienceIcon name={a.icon} />
          <div className="ro-col__text">
            <h3 className="ro-col__title">{a.title}</h3>
            <p className="ro-col__desc">
              {a.lines.map((line) => (
                <span key={line}>{line}</span>
              ))}
            </p>
          </div>
        </li>
      ))}
    </ul>
  )
}

export default AudienceColumns
