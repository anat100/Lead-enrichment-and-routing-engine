// Runs the workflow's Code nodes outside n8n. HTTP nodes (website, OpenAI, HubSpot)
// are replaced by the mocked responses passed in.
const path = require('path');
const wf = require(path.join(__dirname, '..', 'workflow', 'inbound-lead-engine-mvp.json'));

const code = name => wf.nodes.find(n => n.name === name).parameters.jsCode;

function runPipeline({ body, websiteHtml, llmResponse, upsertResult = { id: '101', new: true } }) {
  const out = {};
  const run = (name, $json = {}) => {
    const $ = node => ({ first: () => out[node][0] });
    out[name] = new Function('$', '$json', code(name))($, $json);
    return out[name][0].json;
  };
  out['Lead Form Webhook'] = [{ json: { body } }];
  run('Config');
  const lead = run('Normalize & Validate');
  if (!lead.is_processable) return { lead };
  const llmRequest = run('Prepare LLM Request', { data: websiteHtml });
  const scored = run('Score Lead', llmResponse);
  out['HubSpot: Upsert Contact'] = [{ json: { results: [upsertResult] } }];
  const routed = run('Route & Compose');
  return { lead, llmRequest, scored, routed };
}

const llm = obj => ({ choices: [{ message: { content: JSON.stringify(obj) } }] });

module.exports = { runPipeline, llm };
