// CLI walkthrough shown in the terminal. Commands are taken from veramynd/README.md.
export type TokenKind = 'tx' | 'fn' | 'str' | 'cm' | 'id' | 'pl' | 'kw'
export type Token = [TokenKind, string]
/** A code line (indent in px) or `null` for a blank spacer line. */
export type CodeLine = { indent: number; tokens: Token[] } | null

export type CommandTab = {
  id: 'verify' | 'normalize' | 'retrieve' | 'judge'
  tab: string
  title: string
  lines: CodeLine[]
}

const cmd = (sub: string): Token[] => [['fn', 'veramynd-parser'], ['id', ` ${sub}`]]
const comment = (text: string, indent = 0): CodeLine => ({ indent, tokens: [['cm', `# ${text}`]] })
const flag = (name: string, value?: string, indent = 24): CodeLine => ({
  indent,
  tokens: value ? [['kw', name], ['str', ` ${value}`], ['pl', ' \\']] : [['kw', name]],
})

export const COMMAND_TABS: CommandTab[] = [
  {
    id: 'verify',
    tab: 'Verify',
    title: 'Parse and verify the teacher guide',
    lines: [
      comment('Stage 1: split lessons, keep page provenance, issue GO or BLOCK'),
      { indent: 0, tokens: [...cmd('verify'), ['str', ' "ELA Grade 1 Module 2 Teacher Guide.pdf"'], ['kw', ' --expect'], ['pl', ' 40']] },
      null,
      comment('Full Stage-1 export with the standards workbook'),
      { indent: 0, tokens: [...cmd('export'), ['str', ' "ELA Grade 1 Module 2 Teacher Guide.pdf"'], ['pl', ' \\']] },
      flag('--out', 'output/stage1'),
      flag('--standards', '"Grade 1 GA ELA Standards.xlsx"'),
      { indent: 24, tokens: [['kw', '--framework'], ['str', ' "GA ELA"']] },
      null,
      comment('Standards only: Code | Standard Text | Notes, hierarchy from dotted codes'),
      { indent: 0, tokens: [...cmd('stds'), ['str', ' "Grade 1 GA ELA Standards.xlsx"'], ['kw', ' --framework'], ['str', ' "GA ELA"']] },
      null,
      comment('Only GO output is trusted downstream'),
    ],
  },
  {
    id: 'normalize',
    tab: 'Normalize',
    title: 'Normalize lessons and standards',
    lines: [
      comment('Distill every lesson into what the student actually does'),
      { indent: 0, tokens: [...cmd('normalize-lessons'), ['str', ' output/stage1/lessons'], ['kw', ' --out'], ['str', ' output/normalize']] },
      null,
      comment('Turn each standard leaf into retrieval-ready text'),
      { indent: 0, tokens: [...cmd('normalize-standards'), ['str', ' output/stage1/standards.json'], ['pl', ' \\']] },
      { indent: 24, tokens: [['kw', '--out'], ['str', ' output/normalize_standards']] },
      null,
      comment('Embed standards only; lesson vectors are never stored'),
      { indent: 0, tokens: [...cmd('embed-standards'), ['str', ' output/normalize_standards'], ['pl', ' \\']] },
      { indent: 24, tokens: [['kw', '--out'], ['str', ' output/embeddings'], ['kw', ' --recreate']] },
      null,
      comment('After normalize changes, re-apply sanitizers without a full LLM re-run'),
      { indent: 0, tokens: [...cmd('repair-normalized'), ['str', ' output/stage1/lessons'], ['kw', ' --normalize-dir'], ['str', ' output/normalize']] },
    ],
  },
  {
    id: 'retrieve',
    tab: 'Retrieve',
    title: 'Retrieve candidate standards',
    lines: [
      comment('Query arms from the normalized lesson: dense + BM25, RRF, cross-encoder'),
      { indent: 0, tokens: [...cmd('retrieve-standards'), ['pl', ' \\']] },
      flag('--normalize-file', 'output/normalize/G1M2U1L3.json'),
      { indent: 24, tokens: [['kw', '--out'], ['str', ' output/retrieve/G1M2U1L3.json']] },
      null,
      comment('Protected recall bar on the SME gold set (gold is eval-only)'),
      { indent: 0, tokens: [['fn', 'python'], ['kw', ' -m'], ['id', ' veramynd_parser.scripts.eval_r20']] },
      null,
      comment('Batch-1 gold, 20 positives across four lessons'),
      { indent: 0, tokens: [['tx', 'Recall@25'], ['pl', '  100% (20/20)'], ['cm', 'protected QA bar']] },
      { indent: 0, tokens: [['tx', 'Recall@20'], ['pl', '   90% (18/20)'], ['cm', 'product cut']] },
      { indent: 0, tokens: [['tx', 'Recall@50'], ['pl', '  100% (20/20)'], ['cm', 'SME shortlist']] },
    ],
  },
  {
    id: 'judge',
    tab: 'Judge',
    title: 'Judge and report alignments',
    lines: [
      comment('Score each lesson × standard full / partial / none, clause by clause'),
      { indent: 0, tokens: [...cmd('judge-standards'), ['pl', ' \\']] },
      flag('--retrieve-file', 'output/retrieve/G1M2U1L1.json'),
      flag('--lesson-file', 'output/stage1/lessons/G1M2U1L1.json'),
      flag('--standards-dir', 'output/normalize_standards'),
      { indent: 24, tokens: [['kw', '--out'], ['str', ' output/judge/G1M2U1L1.json'], ['kw', ' --limit'], ['pl', ' 25']] },
      null,
      comment('Evidence quotes are checked against the source; ungrounded quotes become none'),
      null,
      comment('Export the audit trail: CSV, HTML, client DOCX and XLSX'),
      { indent: 0, tokens: [...cmd('report-alignments'), ['kw', ' --judge-dir'], ['str', ' output/judge'], ['pl', ' \\']] },
      { indent: 24, tokens: [['kw', '--out'], ['str', ' output/result/alignments.csv']] },
    ],
  },
]
