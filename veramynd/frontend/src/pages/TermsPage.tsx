import { Link } from 'react-router-dom'
import DocLayout, { DocSection, type TocItem } from '../components/landing/doc/DocLayout'
import { SITE } from '../config/site'

const TOC: TocItem[] = [
  { id: 'agreement', label: 'Agreement' },
  { id: 'service', label: 'The Service' },
  { id: 'accounts', label: 'Accounts' },
  { id: 'content', label: 'Your content' },
  { id: 'acceptable-use', label: 'Acceptable use' },
  { id: 'ai-output', label: 'AI-generated output' },
  { id: 'ip', label: 'Intellectual property' },
  { id: 'third-parties', label: 'Third-party services' },
  { id: 'availability', label: 'Availability & changes' },
  { id: 'termination', label: 'Suspension & termination' },
  { id: 'disclaimers', label: 'Disclaimers' },
  { id: 'liability', label: 'Limitation of liability' },
  { id: 'general', label: 'General' },
  { id: 'contact', label: 'Contact' },
]

export function TermsPage() {
  const email = SITE.contactEmail

  return (
    <DocLayout
      eyebrow="Legal"
      title="Terms of Use"
      intro={
        <p>
          The rules for using {SITE.name}. Please read them together with our{' '}
          <Link to="/privacy">Privacy Policy</Link>.
        </p>
      }
      meta={`Effective ${SITE.policyEffectiveDate}`}
      toc={TOC}
    >
      <DocSection id="agreement" title="Agreement">
        <p>
          By creating an account or using the {SITE.name} website, operator web app or API (the “Service”), you
          agree to these Terms. If you use the Service for an organisation, you confirm you are authorised to accept
          them on its behalf. A separate written agreement with your organisation takes precedence where it
          conflicts with these Terms.
        </p>
      </DocSection>

      <DocSection id="service" title="The Service">
        <p>
          {SITE.name} analyses a teacher-guide PDF against a standards workbook and produces lesson × standard
          alignment verdicts, evidence excerpts and reports. Features, supported inputs and validated scope are
          described in the <Link to="/docs">documentation</Link>.
        </p>
      </DocSection>

      <DocSection id="accounts" title="Accounts">
        <ul>
          <li>Give accurate registration information and verify your email address.</li>
          <li>Keep your password confidential. You are responsible for activity under your account.</li>
          <li>
            Tell us promptly at <a href={`mailto:${email}`}>{email}</a> if you suspect unauthorised use.
          </li>
          <li>You must be old enough to form a binding contract where you live, and in any case at least 18.</li>
        </ul>
      </DocSection>

      <DocSection id="content" title="Your content">
        <p>
          You keep all rights in the files you upload and the results generated from them (“Your Content”). You
          grant us a limited licence to host, copy, process and transmit Your Content only as needed to provide and
          support the Service, including sending extracted text to the AI providers listed in the Privacy Policy.
        </p>
        <p>
          You are responsible for having the rights and permissions to upload Your Content, including any licence
          needed for publisher materials and standards documents.
        </p>
      </DocSection>

      <DocSection id="acceptable-use" title="Acceptable use">
        <p>You agree not to:</p>
        <ul>
          <li>upload content you have no right to use, or content that is unlawful or infringes others’ rights;</li>
          <li>upload personal information about students or other individuals;</li>
          <li>upload malware or attempt to disrupt, overload or gain unauthorised access to the Service or its data;</li>
          <li>access another user’s projects or data without permission;</li>
          <li>use the Service to build a competing dataset by systematically extracting output; or</li>
          <li>misrepresent machine-generated verdicts as the independent judgment of a human expert.</li>
        </ul>
      </DocSection>

      <DocSection id="ai-output" title="AI-generated output">
        <p>
          Verdicts, evidence and reports are produced by automated systems, including third-party AI models. They
          can be incomplete or wrong, even when they cite evidence. Published accuracy figures come from specific
          evaluation sets and do not guarantee results on other materials.
        </p>
        <p className="doc-note">
          Output is decision support, not a certification. Have a qualified reviewer confirm results before relying
          on them for adoption submissions, correlation claims, purchasing decisions or compliance purposes.
        </p>
      </DocSection>

      <DocSection id="ip" title="Intellectual property">
        <p>
          Apart from Your Content, the Service, including its software, prompts, design and branding, belongs to
          us or our licensors. Where parts of the {SITE.name} software are published under an open-source licence
          (such as MIT), that licence governs your use of that code. These Terms govern use of the hosted Service.
        </p>
        <p>
          If you send us feedback, we may use it without obligation to you.
        </p>
      </DocSection>

      <DocSection id="third-parties" title="Third-party services">
        <p>
          The Service relies on third parties, including AI, email, sign-in, font and hosting providers. Their
          services are governed by their own terms, and we are not responsible for their availability or conduct.
        </p>
      </DocSection>

      <DocSection id="availability" title="Availability & changes">
        <p>
          We work to keep the Service available but do not promise uninterrupted operation. We may change, add or
          remove features. We may update these Terms; if a change is material, we will give reasonable notice in the
          Service or by email. Continuing to use the Service after the effective date means you accept the update.
        </p>
      </DocSection>

      <DocSection id="termination" title="Suspension & termination">
        <p>
          You may stop using the Service at any time and ask us to delete your account. We may suspend or end
          access if you breach these Terms, if required by law, or to protect the Service or other users. Where
          practical, we will give notice and a chance to export Your Content first.
        </p>
      </DocSection>

      <DocSection id="disclaimers" title="Disclaimers">
        <p>
          To the fullest extent the law allows, the Service is provided “as is” and “as available”, without
          warranties of any kind, express or implied, including merchantability, fitness for a particular purpose,
          accuracy and non-infringement.
        </p>
      </DocSection>

      <DocSection id="liability" title="Limitation of liability">
        <p>
          To the fullest extent the law allows, we will not be liable for indirect, incidental, special,
          consequential or punitive damages, or for lost profits, revenue, data or goodwill. Our total liability for
          any claim relating to the Service is limited to the greater of the amount you paid us for the Service in
          the 12 months before the claim and USD 100. Some jurisdictions do not allow these limits, so they may not
          apply to you.
        </p>
      </DocSection>

      <DocSection id="general" title="General">
        <p>
          If any provision of these Terms is unenforceable, the rest stays in effect. Not enforcing a provision is
          not a waiver. You may not transfer these Terms without our consent; we may transfer them as part of a
          merger, acquisition or sale of assets.
        </p>
      </DocSection>

      <DocSection id="contact" title="Contact">
        <p>
          Questions about these Terms: <a href={`mailto:${email}`}>{email}</a>.
        </p>
      </DocSection>
    </DocLayout>
  )
}

export default TermsPage
