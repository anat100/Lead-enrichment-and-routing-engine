// Runs one fictional lead through the workflow's Code nodes and saves every stage
// to examples/. HTTP calls are mocked: the website HTML and LLM response below are
// illustrative, everything else is computed by the workflow's own code.
// Usage: node scripts/generate_examples.js
const fs = require('fs');
const path = require('path');
const { runPipeline, llm } = require('../tests/harness');

const dir = path.join(__dirname, '..', 'examples');
const save = (file, data) =>
  fs.writeFileSync(path.join(dir, file), typeof data === 'string' ? data : JSON.stringify(data, null, 2) + '\n');

const body = require('../test-payloads/tier-a-law-firm.json');

const websiteHtml = `<html><head><title>Muster Rechtsanwälte | Wirtschaftskanzlei München</title></head><body>
<h1>Muster Rechtsanwälte</h1>
<p>Wirtschaftskanzlei mit 35 Berufsträgerinnen und Berufsträgern in München und Frankfurt.</p>
<h2>Rechtsgebiete</h2>
<ul><li>Gesellschaftsrecht und M&amp;A</li><li>Arbeitsrecht</li><li>Prozessführung und Schiedsverfahren</li><li>Immobilienrecht</li></ul>
<h2>Karriere</h2><p>Wir suchen eine:n Legal Engineer (m/w/d) zur Digitalisierung unserer Arbeitsabläufe.</p>
</body></html>`;

const llmJson = {
  org_type: 'law_firm',
  lawyer_count: 35,
  practice_areas: ['Corporate/M&A', 'Employment', 'Litigation & Arbitration', 'Real Estate'],
  legaltech_signals: ['Hiring a Legal Engineer'],
  fit_score: 15,
  fit_reason: 'Mid-size commercial firm with document-heavy practices that is starting to invest in legal tech.',
  summary: 'Muster Rechtsanwälte is a commercial law firm with 35 lawyers in Munich and Frankfurt. It is hiring a Legal Engineer to digitise its workflows.'
};

const r = runPipeline({ body, websiteHtml, llmResponse: llm(llmJson), upsertResult: { id: '48213907', new: true } });

save('01-form-submission.json', body);
save('02-normalized-lead.json', r.lead);
save('03-llm-request.json', r.llmRequest.llm_request);
save('04-llm-response.json', llmJson);
const { hubspot_company_properties, hubspot_contact_properties, ...scored } = r.scored;
save('05-scored-lead.json', scored);
save('06-hubspot-payloads.json', { company: { properties: hubspot_company_properties }, contact: { properties: hubspot_contact_properties }, note: r.routed.hubspot_note_body });
save('07-slack-message.json', r.routed.slack_body);
console.log(`Tier ${scored.tier}, score ${scored.total_score}/100 -> examples/`);
