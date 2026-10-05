// Two curved blades meeting at the centre: deep notches upper-left and lower-right,
// shallow concave edges between the other tips.
const PATH = 'M21.4,1.5 Q26.5,13.5 39.5,16.2 L20.5,20.5 L19.6,38.5 Q13.5,26.5 0.5,23.8 L19.5,19.5 Z'

export function SparkleMark() {
  return (
    <svg className="ro-sparkle" width="47" height="47" viewBox="0 0 40 40" aria-hidden="true">
      <path d={PATH} fill="#000" />
    </svg>
  )
}

export default SparkleMark
