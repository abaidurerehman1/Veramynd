import { Link } from 'react-router-dom'
import DocLayout, { DocSection, type TocItem } from '../components/landing/doc/DocLayout'
import { SITE } from '../config/site'

const TOC: TocItem[] = [
  { id: 'scope', label: 'Scope' },
  { id: 'collect', label: 'Information we collect' },
  { id: 'use', label: 'How we use it' },
  { id: 'ai', label: 'AI processing' },
  { id: 'sharing', label: 'Service providers' },
  { id: 'cookies', label: 'Cookies' },
  { id: 'retention', label: 'Retention & deletion' },
  { id: 'security', label: 'Security' },
  { id: 'student-data', label: 'Student data & children' },
  { id: 'rights', label: 'Your choices & rights' },
  { id: 'changes', label: 'Changes' },
  { id: 'contact', label: 'Contact' },
]

export function PrivacyPage() {
  const email = SITE.contactEmail

  return (
    <DocLayout
      eyebrow="Legal"
      title="Privacy Policy"
      intro={
        <p>
          What information {SITE.name} collects, why, who processes it on our behalf, and the choices you have. We
          have written it to describe how the service actually works.
        </p>
      }
      meta={`Effective ${SITE.policyEffectiveDate}`}
      toc={TOC}
    >
      <DocSection id="scope" title="Scope">
        <p>
          This policy covers the {SITE.name} website, the operator web app and its API (the “Service”). “We”, “us”
          and “our” mean the operator of {SITE.name}. If your organisation gave you access, its agreement with us may
          add terms about how its data is handled.
        </p>
      </DocSection>

      <DocSection id="collect" title="Information we collect">
        <h3>Account information</h3>
        <ul>
          <li>
            Your name and email address, and whether your email has been verified. Your password is never stored as
            written; we keep only a salted bcrypt hash.
          </li>
          <li>
            If you sign in with Google: your Google account identifier, name, email address and, if provided, your
            profile picture URL.
          </li>
          <li>A profile photo, if you choose to upload one.</li>
        </ul>
        <h3>Content you upload</h3>
        <ul>
          <li>Curriculum files (teacher-guide PDFs) and standards workbooks (XLSX), with any labels you add.</li>
          <li>
            Everything the pipeline produces from them: parsed lessons, normalized text, alignment verdicts,
            evidence excerpts, reports and exports.
          </li>
        </ul>
        <h3>Operational information</h3>
        <ul>
          <li>
            Pipeline job logs: stage and lesson events, errors and estimated processing cost. Projects you open are
            linked to your account.
          </li>
          <li>
            Standard server request data (such as IP address and browser type) that our hosting infrastructure may
            record.
          </li>
        </ul>
        <p>
          We do not use advertising or analytics trackers, and we do not ask for payment details through the
          Service.
        </p>
      </DocSection>

      <DocSection id="use" title="How we use information">
        <ul>
          <li>To create and secure your account, verify your email and reset your password.</li>
          <li>To run the alignment pipeline on the files you upload and show you the results.</li>
          <li>To operate, troubleshoot and improve the reliability and cost of the Service.</li>
          <li>To send service emails such as verification and password-reset messages. We do not send marketing email.</li>
          <li>To comply with law and enforce our <Link to="/terms">Terms of Use</Link>.</li>
        </ul>
        <p>We do not sell your personal information or your uploaded content.</p>
      </DocSection>

      <DocSection id="ai" title="AI processing of your content">
        <p>
          The pipeline sends text extracted from your uploaded curriculum and standards to third-party AI providers
          to produce its results:
        </p>
        <ul>
          <li>
            <strong>OpenAI</strong>: lesson and standards normalization, and text embeddings for retrieval.
          </li>
          <li>
            <strong>Anthropic</strong>: alignment judging.
          </li>
        </ul>
        <p>
          These providers process the content under their API terms to return results to us. We do not use your
          content to train our own models. Some retrieval steps (keyword search, reranking and the vector index) run
          on our own infrastructure.
        </p>
        <p className="doc-note">
          Do not upload files that contain personal information about students or other individuals. Teacher guides
          and standards rarely need it, and the pipeline does not.
        </p>
      </DocSection>

      <DocSection id="sharing" title="Service providers">
        <p>We share information only with providers that help us run the Service:</p>
        <ul>
          <li>AI processing: OpenAI and Anthropic, as described above.</li>
          <li>Email delivery: an SMTP provider that sends account emails.</li>
          <li>Sign-in: Google, if you choose Google sign-in.</li>
          <li>Fonts: Google Fonts, which serves the typefaces used by our pages and therefore sees your IP address.</li>
          <li>Hosting: the infrastructure provider that runs our servers and stores your files.</li>
        </ul>
        <p>
          We may also disclose information if the law requires it, to protect the rights and safety of users or the
          public, or as part of a merger or acquisition, in which case this policy would continue to apply.
        </p>
      </DocSection>

      <DocSection id="cookies" title="Cookies">
        <ul>
          <li>
            <strong>Session cookie</strong> (<code>veramynd_token</code>): keeps you signed in. It is HTTP-only, so
            page scripts cannot read it, and it expires after 7 days by default.
          </li>
          <li>
            <strong>Sign-in flow cookie</strong>: a short-lived session cookie used only while you complete Google
            sign-in.
          </li>
        </ul>
        <p>We use no advertising or cross-site tracking cookies.</p>
      </DocSection>

      <DocSection id="retention" title="Retention & deletion">
        <ul>
          <li>Account information: kept while your account exists.</li>
          <li>
            Uploaded files and pipeline output: kept until the project is deleted. Job logs are kept until they are
            cleared, which is a separate action from deleting a project.
          </li>
          <li>Email verification links expire after 48 hours; password-reset links after 2 hours.</li>
          <li>
            To delete your account and its data, email <a href={`mailto:${email}`}>{email}</a>. Backups may take
            longer to expire.
          </li>
        </ul>
      </DocSection>

      <DocSection id="security" title="Security">
        <p>
          We hash passwords with bcrypt, sign session tokens and keep them in HTTP-only cookies, and limit upload
          types and sizes. No system is perfectly secure: use a strong, unique password and tell us promptly at{' '}
          <a href={`mailto:${email}`}>{email}</a> if you suspect unauthorised access.
        </p>
      </DocSection>

      <DocSection id="student-data" title="Student data & children">
        <p>
          {SITE.name} is a professional tool for curriculum publishers, reviewers and specialists. It is not
          directed to children and is not designed to process student education records. Do not create accounts for
          children or upload student personal information.
        </p>
      </DocSection>

      <DocSection id="rights" title="Your choices & rights">
        <p>
          You can update your name, photo and password in Settings and delete projects in the app. Depending on
          where you live, you may also have the right to access, correct, export or delete your personal
          information, or to object to some processing. To make a request, email{' '}
          <a href={`mailto:${email}`}>{email}</a>. We will respond within the time the law requires.
        </p>
      </DocSection>

      <DocSection id="changes" title="Changes to this policy">
        <p>
          We will update this page when our practices change and revise the effective date above. If a change is
          significant, we will give notice in the Service or by email before it takes effect.
        </p>
      </DocSection>

      <DocSection id="contact" title="Contact">
        <p>
          Privacy questions or requests: <a href={`mailto:${email}`}>{email}</a>.
        </p>
      </DocSection>
    </DocLayout>
  )
}

export default PrivacyPage
