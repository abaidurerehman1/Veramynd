// Pipeline stages shown in the "How it works" section. Facts mirror veramynd/README.md.
export type StageStep = {
  title: string
  status: 'Complete' | 'Processing' | 'Waiting'
  description: string
}

export type Stage = {
  id: 'parse' | 'normalize' | 'retrieve' | 'judge' | 'report'
  tab: string
  title: [string, string, string]
  description: [string, string]
  linkLabel: string
  toolsLabel: string
  tools: string[]
  steps: [StageStep, StageStep, StageStep]
}

export const STAGES: Stage[] = [
  {
    id: 'parse',
    tab: 'Parse',
    title: ['Split the Teacher Guide', 'Into Lessons You', 'Can Trust.'],
    description: [
      'Docling and PyMuPDF split every lesson with page provenance,',
      'then a verifier issues GO or BLOCK before anything moves on.',
    ],
    linkLabel: 'How parsing works',
    toolsLabel: 'Inputs',
    tools: ['Teacher guide PDF', 'Standards XLSX', 'Auto OCR'],
    steps: [
      { title: 'Lesson Split', status: 'Complete', description: 'Bookmarks first, header fallback' },
      { title: 'Structure', status: 'Processing', description: 'Agenda, materials, vocab, steps' },
      { title: 'Verify', status: 'Waiting', description: 'GO or BLOCK before normalize' },
    ],
  },
  {
    id: 'normalize',
    tab: 'Normalize',
    title: ['Distill Each Lesson', 'Into What Students', 'Actually Do.'],
    description: [
      'An LLM rewrites every lesson as student acts and literacy signals,',
      'while each standard becomes a retrieval-ready leaf.',
    ],
    linkLabel: 'How normalizing works',
    toolsLabel: 'Built with',
    tools: ['gpt-4.1-mini', 'Content cache', 'Sanitizers'],
    steps: [
      { title: 'Lessons', status: 'Complete', description: 'Student acts, signals, texts' },
      { title: 'Standards', status: 'Processing', description: 'Leaf codes to retrieval text' },
      { title: 'Embed', status: 'Waiting', description: 'Standards only, into Qdrant' },
    ],
  },
  {
    id: 'retrieve',
    tab: 'Retrieve',
    title: ['Shortlist Standards', 'That Could Plausibly', 'Apply.'],
    description: [
      'Dense and BM25 search per query angle, fused with RRF, then',
      'reranked by a cross-encoder into a 50-standard shortlist.',
    ],
    linkLabel: 'How retrieval works',
    toolsLabel: 'Built with',
    tools: ['Qdrant', 'BM25', 'RRF', 'Reranker'],
    steps: [
      { title: 'Query Arms', status: 'Complete', description: 'Focused queries per lesson' },
      { title: 'Hybrid Search', status: 'Processing', description: 'Dense + keyword, fused by RRF' },
      { title: 'Shortlist', status: 'Waiting', description: 'Top 25 go to the judge' },
    ],
  },
  {
    id: 'judge',
    tab: 'Judge',
    title: ['Score Every Pair', 'Full, Partial, or None', 'With Evidence.'],
    description: [
      'Claude judges each lesson × standard clause by clause; quotes',
      'that cannot be found in the source are rejected as none.',
    ],
    linkLabel: 'How judging works',
    toolsLabel: 'Built with',
    tools: ['Claude Sonnet', 'Opus escalation', 'Grounding'],
    steps: [
      { title: 'Batch Judge', status: 'Complete', description: 'Whole shortlist in one call' },
      { title: 'Escalation', status: 'Processing', description: 'Borderline codes re-judged' },
      { title: 'Grounding', status: 'Waiting', description: 'Unfound quotes become none' },
    ],
  },
  {
    id: 'report',
    tab: 'Report',
    title: ['Export the Audit', 'Trail Your Clients', 'Expect.'],
    description: [
      'Alignment CSVs, an HTML report, and a client correlation',
      'DOCX and XLSX with parent roll-ups, ready to deliver.',
    ],
    linkLabel: 'See export formats',
    toolsLabel: 'Outputs',
    tools: ['CSV', 'HTML', 'DOCX', 'XLSX'],
    steps: [
      { title: 'Alignments', status: 'Complete', description: 'Per-lesson and combined CSV' },
      { title: 'Roll-ups', status: 'Processing', description: 'Parent standards summarized' },
      { title: 'Client Pack', status: 'Waiting', description: 'DOCX + XLSX correlation' },
    ],
  },
]
