// Single source for brand, contact and public-site navigation.
// TODO(owner): confirm CONTACT_EMAIL — the repo only has placeholder addresses.
export const SITE = {
  name: 'Veramynd',
  tagline: 'Curriculum–standards alignment with an audit trail.',
  contactEmail: 'hello@veramynd.com',
  demoProjectId: 'el-g1-m2-ga-ela',
  policyEffectiveDate: 'October 2, 2026',
} as const

/** Landing-page section anchors (used by the hero nav, footer and docs). */
export const ANCHORS = {
  howItWorks: 'how-it-works',
  pipeline: 'pipeline',
  audience: 'who-its-for',
  resources: 'resources',
} as const

/** Route into a page of the demo project inside the authenticated app. */
export function appRoute(page = '') {
  return `/projects/${SITE.demoProjectId}${page ? `/${page}` : ''}`
}
