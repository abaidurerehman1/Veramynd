import { useLayoutEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import DocLayout, { DocSection, type TocItem } from '../components/landing/doc/DocLayout'
import { SITE, appRoute } from '../config/site'

const TOC: TocItem[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'quick-start', label: 'Quick start' },
  { id: 'inputs', label: 'Inputs' },
  { id: 'parse', label: '1. Parse & verify' },
  { id: 'normalize', label: '2. Normalize & embed' },
  { id: 'retrieve', label: '3. Retrieve' },
  { id: 'judge', label: '4. Judge' },
  { id: 'verdicts', label: 'Reading verdicts' },
  { id: 'review', label: 'Review queue' },
  { id: 'report', label: '5. Reports & exports' },
  { id: 'metrics', label: 'Gold-set metrics' },
  { id: 'cli', label: 'CLI reference' },
  { id: 'scope', label: 'Scope & limitations' },
  { id: 'support', label: 'Support' },
]

/** Hide sections that don't contain every search term; returns the visible count. */
function useSectionFilter(query: string) {
  const ref = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState<number | null>(null)

  useLayoutEffect(() => {
    const root = ref.current
    if (!root) return
    const terms = query.toLowerCase().split(/\s+/).filter(Boolean)
    const sections = root.querySelectorAll<HTMLElement>('[data-doc-section]')
    let count = 0
    sections.forEach((section) => {
      const text = section.textContent?.toLowerCase() ?? ''
      const match = terms.every((t) => text.includes(t))
      section.hidden = !match
      if (match) count += 1
    })
    setVisible(terms.length ? count : null)
  }, [query])

  return { ref, visible }
}

export function DocsPage() {
  const [params, setParams] = useSearchParams()
  const query = params.get('q') ?? ''
  const [draft, setDraft] = useState(query)
  const { ref, visible } = useSectionFilter(query)

  const onSearch = (e: FormEvent) => {
    e.preventDefault()
    const q = draft.trim()
    setParams(q ? { q } : {}, { replace: true })
  }

  const clear = () => {
    setDraft('')
    setParams({}, { replace: true })
  }

  const search = (
    <>
      <form className="doc-search" role="search" onSubmit={onSearch}>
        <input
          type="search"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Search the docs: verdicts, XLSX format, exports..."
          aria-label="Search the documentation"
        />
        <button type="submit">Search</button>
        {query && (
          <button type="button" onClick={clear}>
            Clear
          </button>
        )}
      </form>
      {visible !== null && (
        <p className="doc-search-status" role="status">
          {visible === 0
            ? `No sections match “${query}”.`
            : `${visible} section${visible === 1 ? '' : 's'} match “${query}”.`}
        </p>
      )}
    </>
  )

  return (
    <DocLayout
      eyebrow="Documentation"
      title="Veramynd documentation"
      intro={
        <p>
          How to run Veramynd, what each pipeline stage does, and how to read the verdicts it produces, from the
          operator web app or the <code>veramynd-parser</code> command line.
        </p>
      }
      toc={TOC}
      tools={search}
    >
      <div ref={ref}>
        <DocSection id="overview" title="Overview">
          <p>
            Veramynd is a curriculum–standards alignment engine. Given a teacher-guide PDF and a standards workbook,
            it determines which academic standards each lesson actually teaches, rated <strong>full</strong>,{' '}
            <strong>partial</strong> or <strong>none</strong>, with page-referenced evidence pulled straight from
            the source document.
          </p>
          <p>
            Alignment is normally coded by hand by a curriculum specialist: slow, expensive and inconsistent between
            raters. Veramynd applies one rubric identically to every lesson × standard pair and keeps a paper trail
            for each decision.
          </p>
          <p>There are two ways to use it:</p>
          <ul>
            <li>
              <strong>Operator web app</strong>: upload files, run the pipeline, then review and export results.
            </li>
            <li>
              <strong>Command line</strong>: the <code>veramynd-parser</code> package runs each stage directly. See{' '}
              <a href="#cli">CLI reference</a>.
            </li>
          </ul>
        </DocSection>

        <DocSection id="quick-start" title="Quick start">
          <ol className="doc-steps">
            <li>
              <strong>Create an account.</strong> <Link to="/signup">Sign up</Link> with your email and a password,
              then open the verification link we email you (valid for 48 hours). Google sign-in is available where
              it has been enabled.
            </li>
            <li>
              <strong>Ingest your files.</strong> On <Link to={appRoute('ingestion')}>Ingestion</Link>, upload one
              teacher-guide PDF and one standards XLSX, with optional program, grade and module labels. Saving an
              upload does not run anything.
            </li>
            <li>
              <strong>Run the pipeline.</strong> On <Link to={appRoute('pipeline')}>Pipeline</Link>, choose{' '}
              <em>Complete auto</em> or run stage by stage, confirming each start. If a run is interrupted, it
              resumes from the output already saved.
            </li>
            <li>
              <strong>Review the results.</strong> <Link to={appRoute()}>Overview</Link> shows status, key figures,
              the alignment mix and coverage. Curriculum and Lesson pages show the parsed structure; Standards shows
              the framework tree; Alignments lets you filter verdicts and open the evidence; Review lists items
              flagged for a human check.
            </li>
            <li>
              <strong>Export.</strong> On <Link to={appRoute('exports')}>Exports</Link>, download the client
              correlation DOCX/XLSX and the CSV packages.
            </li>
          </ol>
          <p className="doc-note">
            The Logging page lists jobs, stage and lesson events, typed errors and per-stage cost. Deleting a
            project does not clear its logs; use <em>Clear logs</em> for that.
          </p>
        </DocSection>

        <DocSection id="inputs" title="Inputs">
          <p>Each project takes exactly one PDF and one XLSX. Uploads can be up to 200 MB.</p>
          <h3>Teacher guide (PDF)</h3>
          <ul>
            <li>Born-digital or scanned; OCR turns on automatically when it is needed.</li>
            <li>Lessons are located from PDF bookmarks, with a font and heading fallback when bookmarks are missing.</li>
          </ul>
          <h3>Standards workbook (XLSX)</h3>
          <ul>
            <li>
              Columns: <code>Code</code> | <code>Standard Text</code> | <code>Notes</code>.
            </li>
            <li>
              The hierarchy comes from dotted, grade-prefixed codes, e.g. <code>1.F</code> (domain) →{' '}
              <code>1.F.PA</code> → <code>1.F.PA.4</code> → <code>1.F.PA.4.d</code> (leaf). The grade is the leading
              segment (<code>K</code>, <code>1</code>, …). Notes are not used to infer levels.
            </li>
            <li>
              The framework label (for example <code>GA ELA</code>) is supplied with the upload or on the command
              line.
            </li>
          </ul>
        </DocSection>

        <DocSection id="parse" title="1. Parse & verify">
          <p>
            Docling, with TableFormer for tables, is the primary parser. PyMuPDF reads bookmarks, provides the
            fallback and independently cross-checks the structure. Each lesson is divided into agenda, materials,
            vocabulary and instructional blocks and steps, with page provenance mapped to the printed page numbers.
          </p>
          <p>
            Standards the publisher declares in the guide are kept apart from the target framework, so they never
            leak into the verdicts.
          </p>
          <p>
            A verifier then issues <strong>GO</strong> or <strong>BLOCK</strong>; a soft warning still allows GO.
            Only GO output is trusted downstream unless an operator explicitly overrides it. Structural problems stop
            the pipeline rather than failing silently.
          </p>
        </DocSection>

        <DocSection id="normalize" title="2. Normalize & embed">
          <p>
            Each lesson is distilled into a standards-agnostic description of what the student actually does
            (prompt <code>normalize_ela.v2.3</code>). Sanitizers then re-apply literacy signals from the parsed
            source text. Each standard becomes retrieval-ready leaf text. Normalization uses OpenAI{' '}
            <code>gpt-4.1-mini</code>, escalating to <code>o4-mini</code>.
          </p>
          <p>
            Only standards are embedded (<code>text-embedding-3-large</code>, stored in Qdrant); lesson vectors are
            never stored. Results are content-addressed and cached, so the same input is not normalized twice.
          </p>
        </DocSection>

        <DocSection id="retrieve" title="3. Retrieve">
          <p>
            Several focused queries are built from each normalized lesson. Each one runs dense vector search and
            BM25 keyword search, fused with reciprocal rank fusion. The merged results are reranked by a local
            cross-encoder into a 50-standard shortlist, and the top 25 go to the judge. Recall at 25 is the
            protected quality bar.
          </p>
        </DocSection>

        <DocSection id="judge" title="4. Judge">
          <p>
            Anthropic Claude Sonnet judges the whole shortlist for a lesson in one batch. Borderline codes are
            re-judged together by Claude Opus. Every standard is broken into clauses, and a clause only counts when
            the <em>student</em> performs the act, not just the teacher. A coverage pass can add feedback and
            presentation standards that fell outside the top 25.
          </p>
          <p>
            <strong>Grounding:</strong> every evidence quote must be found in the lesson&apos;s source text. Short
            quotes are expanded to a grounded window; quotes that cannot be found are rejected and the verdict
            becomes <strong>none</strong>.
          </p>
          <p>
            The judge combines a framework-neutral engine with a per-framework overlay. The Georgia Grade 1 ELA
            overlay encodes rulings from subject-matter experts.
          </p>
        </DocSection>

        <DocSection id="verdicts" title="Reading verdicts">
          <div className="doc-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Field</th>
                  <th>Values</th>
                  <th>Meaning</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Alignment</td>
                  <td>
                    <code>full</code> · <code>partial</code> · <code>none</code>
                  </td>
                  <td>
                    All clauses met · some clauses met · no clause met, or gated out. Partial is not a confidence
                    level.
                  </td>
                </tr>
                <tr>
                  <td>Confidence</td>
                  <td>
                    <code>high</code> · <code>medium</code> · <code>low</code>
                  </td>
                  <td>How certain the judge is about the alignment it gave.</td>
                </tr>
                <tr>
                  <td>Clauses</td>
                  <td>
                    <code>met</code> · <code>partially_met</code> · <code>not_met</code>
                  </td>
                  <td>The judgment for each part of the standard, with the actor (student or teacher).</td>
                </tr>
                <tr>
                  <td>Evidence</td>
                  <td>Quote + page</td>
                  <td>A verbatim excerpt from the lesson, checked against the source.</td>
                </tr>
                <tr>
                  <td>Flags</td>
                  <td>
                    <code>needs_review</code> · <code>input_scope_caveat</code>
                  </td>
                  <td>
                    Marked for a human check · the verdict may be understated because part of the material (for
                    example a separate read-aloud guide) was not in the input.
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </DocSection>

        <DocSection id="review" title="Review queue">
          <p>
            The <Link to={appRoute('review')}>Review</Link> page lists verdicts that deserve a human look (low
            confidence, escalated, or flagged <code>needs_review</code>) together with the reason. It is read-only:
            use it to direct expert attention. Verdicts are not edited in the app.
          </p>
        </DocSection>

        <DocSection id="report" title="5. Reports & exports">
          <ul>
            <li>Alignment CSVs, per lesson and combined.</li>
            <li>An HTML report.</li>
            <li>
              A client correlation <strong>DOCX</strong> in a standard Table-1 layout, plus an <strong>XLSX</strong>{' '}
              mirror with a parent roll-up sheet that summarises substandards as “Fully met” or “Partially met”.
            </li>
            <li>JSON artifacts at every stage, for audit and reprocessing.</li>
          </ul>
        </DocSection>

        <DocSection id="metrics" title="Gold-set metrics">
          <p>
            Measured on Batch 1: the EL Education Grade 1 Module 2 teacher guide (40 lessons) against the Georgia
            Grade 1 ELA standards (188 standards). Four lessons have expert-confirmed (SME) labels, giving 20 positive
            (full or partial) pairs.
          </p>
          <div className="doc-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Metric</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Retrieval Recall@25 (protected bar)</td>
                  <td>100% (20/20)</td>
                </tr>
                <tr>
                  <td>Retrieval Recall@20 / @50 / @10</td>
                  <td>90% (18/20) / 100% (20/20) / 35% (7/20)</td>
                </tr>
                <tr>
                  <td>Judge 3-class exact match vs SME</td>
                  <td>20/20 (100%)</td>
                </tr>
                <tr>
                  <td>Judge vs SME-corrected master, same four lessons</td>
                  <td>95/102 (93.1%)</td>
                </tr>
                <tr>
                  <td>Binary precision / recall (full or partial)</td>
                  <td>100% / 100%</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="doc-note">
            These are small samples from one curriculum and one framework. All 40 lessons have been judged, but
            exact agreement with experts has only been measured on the four gold lessons. Gold labels are used for
            evaluation only and never feed retrieval or judging.
          </p>
        </DocSection>

        <DocSection id="cli" title="CLI reference">
          <p>
            Requires Python 3.11 or later. Normalize and embed need an OpenAI API key; the live judge needs an
            Anthropic API key (<code>OPENAI_API_KEY</code>, <code>ANTHROPIC_API_KEY</code>, <code>JUDGE_MODEL</code>{' '}
            in <code>.env</code>).
          </p>
          <pre>
            <code>{`pip install -e '.[normalize,embed,retrieve,judge]'

# Stage 1: parse + verify, then export with the standards workbook
veramynd-parser verify "Teacher Guide.pdf" --expect 40
veramynd-parser export "Teacher Guide.pdf" --out output/stage1 --expect 40 \\
  --standards "Standards.xlsx" --framework "GA ELA"

# Normalize and embed
veramynd-parser normalize-lessons output/stage1/lessons --out output/normalize
veramynd-parser normalize-standards output/stage1/standards.json --out output/normalize_standards
veramynd-parser embed-standards output/normalize_standards --out output/embeddings --recreate

# Retrieve, judge, report
veramynd-parser retrieve-standards --normalize-file output/normalize/LESSON.json \\
  --out output/retrieve/LESSON.json
veramynd-parser judge-standards --retrieve-file output/retrieve/LESSON.json \\
  --lesson-file output/stage1/lessons/LESSON.json \\
  --standards-dir output/normalize_standards --out output/judge/LESSON.json --limit 25
veramynd-parser report-alignments --judge-dir output/judge --out output/result/alignments.csv`}</code>
          </pre>
        </DocSection>

        <DocSection id="scope" title="Scope & limitations">
          <ul>
            <li>
              Validated today on English Language Arts: one publisher curriculum (EL Education Grade 1 Module 2) and
              one framework (Georgia Grade 1 ELA).
            </li>
            <li>
              The design relies on shared structural patterns rather than per-publisher rules, but other publishers,
              grades and subjects may need additional pattern work and are not claimed to work out of the box.
            </li>
            <li>Inputs are limited to one teacher-guide PDF and one standards XLSX per project.</li>
            <li>
              Verdicts are machine-generated decision support. Have a qualified reviewer confirm them before relying
              on them for adoption, correlation or compliance claims.
            </li>
          </ul>
        </DocSection>

        <DocSection id="support" title="Support">
          <p>
            Questions, bugs or access requests: <a href={`mailto:${SITE.contactEmail}`}>{SITE.contactEmail}</a>. See
            also the <Link to="/privacy">Privacy Policy</Link> and <Link to="/terms">Terms of Use</Link>.
          </p>
        </DocSection>
      </div>
    </DocLayout>
  )
}

export default DocsPage
