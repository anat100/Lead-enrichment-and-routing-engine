// Runs the workflow's Code nodes outside n8n with mocked inputs.
// Usage: node tests/simulate_code_nodes.js
const assert = require('assert');
const path = require('path');
const { runPipeline, llm } = require('./harness');
const payload = file => require(path.join(__dirname, '..', 'test-payloads', file));
const website = '<html><title>Firm</title><body>' + 'Corporate M&A litigation '.repeat(20) + '</body></html>';
const pipeline = (body, llmResponse, upsertResult) => runPipeline({ body, websiteHtml: website, llmResponse, upsertResult });

const strongFirm = llm({ org_type: 'law_firm', lawyer_count: 60, practice_areas: ['Corporate/M&A', 'Employment'], legaltech_signals: ['innovation page', 'legal engineer job'], fit_score: 17, fit_reason: 'Mid-size firm with an innovation team.', summary: 'A German full-service firm.' });

let passed = 0;
const test = (name, fn) => { fn(); passed++; console.log('ok -', name); };

test('German law firm lands in Tier A, DACH, German, notifies Slack', () => {
  const { lead, scored, routed } = pipeline(payload('tier-a-law-firm.json'), strongFirm);
  assert.strictEqual(lead.region, 'DACH');
  assert.strictEqual(lead.language, 'de');
  assert.strictEqual(scored.tier, 'A');
  assert.strictEqual(routed.notify, true);
  assert.ok(routed.slack_body.text.includes('Tier A'));
});

test('Dutch English lead routes to EU in English', () => {
  const { lead, scored } = pipeline(payload('rest-of-eu-english.json'), strongFirm);
  assert.strictEqual(lead.region, 'EU');
  assert.strictEqual(lead.language, 'en');
  assert.strictEqual(scored.owner.name, 'EU BDR');
});

test('Free-mail without consent is blocked before enrichment', () => {
  const { lead, scored } = pipeline(payload('blocked-free-mail-no-consent.json'), strongFirm);
  assert.strictEqual(lead.is_processable, false);
  assert.deepStrictEqual(lead.skip_reasons, ['no_consent', 'free_mail']);
  assert.strictEqual(scored, undefined);
});

test('LLM failure falls back to rules only and flags manual review', () => {
  const { scored } = pipeline(payload('tier-a-law-firm.json'), { error: { message: 'timeout' } });
  assert.strictEqual(scored.llm_ok, false);
  assert.strictEqual(scored.needs_review, true);
  assert.strictEqual(scored.llm_score, 0);
});

test('Returning contact is marked in the Slack alert', () => {
  const { routed } = pipeline(payload('tier-a-law-firm.json'), strongFirm, { id: '101', new: false });
  assert.ok(routed.slack_body.text.includes('returning contact'));
});

test('Tier C does not notify Slack', () => {
  const weak = llm({ org_type: 'other', lawyer_count: null, practice_areas: [], legaltech_signals: [], fit_score: 2, fit_reason: 'Not a legal organisation.', summary: '' });
  const { scored, routed } = pipeline(payload('rest-of-eu-english.json'), weak);
  assert.strictEqual(scored.tier, 'C');
  assert.strictEqual(routed.notify, false);
});

console.log(`\n${passed} tests passed`);
