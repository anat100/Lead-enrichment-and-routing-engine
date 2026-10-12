# Generates workflow/inbound-lead-engine-mvp.json (the n8n workflow export).
# Edit the JS or node layout here, then run: python3 scripts/build_workflow.py
import json, uuid

_NS = uuid.UUID("6f1c2a52-8d3e-4b7a-9c41-2e5d7f0a1b93")
_count = 0


def uid():
    # Deterministic IDs: re-running the generator gives byte-identical output, so diffs stay clean.
    global _count
    _count += 1
    return str(uuid.uuid5(_NS, str(_count)))

# ---------------------------------------------------------------- JS code

CONFIG_JS = r'''// ============================================================
// CONFIG: every tunable setting lives here.
// In the full engine this moves to a database table (scoring_config, routing_rules).
// ============================================================
return [{
  json: {
    llm_model: 'gpt-4o-mini',
    slack_webhook_url: 'https://hooks.slack.com/services/REPLACE/ME/PLEASE',
    hubspot_portal_id: '', // your HubSpot account ID, used to build record links in Slack

    // Set to true after creating the custom contact properties icp_score, icp_tier, icp_reason, lead_language
    write_custom_properties: false,

    tier_a_min: 70,
    tier_b_min: 40,

    // Routing: owner per region. Replace the names with your reps. hubspot_owner_id = numeric owner ID from HubSpot (Settings > Users), or '' to skip.
    owners: {
      DACH:  { name: 'DACH BDR',              slack: '', hubspot_owner_id: '' },
      EU:    { name: 'EU BDR',                slack: '', hubspot_owner_id: '' },
      OTHER: { name: 'Inbound queue',          slack: '', hubspot_owner_id: '' }
    },

    dach_countries: ['DE', 'AT', 'CH', 'LI'],
    eu_countries: ['BE','BG','CZ','DK','EE','IE','GR','ES','FR','HR','IT','CY','LV','LT','LU','HU','MT','NL','PL','PT','RO','SI','SK','FI','SE'],

    free_mail_domains: ['gmail.com','googlemail.com','yahoo.com','yahoo.de','hotmail.com','hotmail.de','outlook.com','outlook.de','live.com','icloud.com','me.com','gmx.de','gmx.net','gmx.at','gmx.ch','web.de','t-online.de','freenet.de','aol.com','proton.me','protonmail.com','posteo.de','mail.de'],

    // Practice areas with heavy document work score higher (matched as substrings, lowercase)
    doc_heavy_practice_areas: ['corporate','m&a','merger','litigation','dispute','employment','labour','labor','real estate','compliance','banking','finance','arbeitsrecht','gesellschaftsrecht','immobilien','prozess']
  }
}];
'''

NORMALIZE_JS = r'''// Normalize the raw form payload and run the guardrails:
// email validity, GDPR consent, free-mail filter, language and region detection.
const cfg = $('Config').first().json;
const body = $('Lead Form Webhook').first().json.body || {};

const clean = v => String(v ?? '').trim();
const email = clean(body.email).toLowerCase();
const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
const domain = emailValid ? email.split('@')[1] : '';
const country = clean(body.country).toUpperCase().slice(0, 2);
const message = clean(body.message);
const firstName = clean(body.first_name);
const lastName = clean(body.last_name);
const company = clean(body.company) || domain;

// GDPR: only an explicit opt-in counts as consent
const consent = [true, 'true', 'on', 'yes', 'ja', '1', 1].includes(body.consent);
const isFreeMail = cfg.free_mail_domains.includes(domain);

// Region: country field first, then the email domain's TLD
const tld = domain.split('.').pop();
let region = 'OTHER';
if (cfg.dach_countries.includes(country) || ['de', 'at', 'ch', 'li'].includes(tld)) region = 'DACH';
else if (cfg.eu_countries.includes(country)) region = 'EU';

// Language: simple keyword heuristic (good enough for an MVP; swap for a library or the LLM later)
const text = message.toLowerCase();
const deHits = (text.match(/\b(und|der|die|das|wir|ich|nicht|mit|eine|ist|sie|unsere|kanzlei|bitte|gerne|anfrage|interesse)\b/g) || []).length
  + (/[äöüß]/.test(text) ? 2 : 0);
const enHits = (text.match(/\b(the|and|we|our|with|for|is|are|you|firm|please|would|like|interested)\b/g) || []).length;
const language = deHits > enHits ? 'de' : enHits > deHits ? 'en' : (region === 'DACH' ? 'de' : 'en');

const skipReasons = [];
if (!emailValid) skipReasons.push('invalid_email');
if (!consent) skipReasons.push('no_consent');
if (isFreeMail) skipReasons.push('free_mail');

return [{
  json: {
    lead_id: 'lead_' + Date.now(),
    received_at: new Date().toISOString(),
    first_name: firstName,
    last_name: lastName,
    email,
    domain,
    company,
    country,
    message,
    consent,
    language,
    region,
    is_processable: skipReasons.length === 0,
    skip_reasons: skipReasons
  }
}];
'''

PREPARE_LLM_JS = r'''// Turn the fetched homepage into plain text and build the LLM request.
const lead = $('Normalize & Validate').first().json;
const cfg = $('Config').first().json;

const html = String($json.data || '');
const titleMatch = html.match(/<title[^>]*>([^<]*)<\/title>/i);
const title = titleMatch ? titleMatch[1].trim() : '';
const text = html
  .replace(/<script[\s\S]*?<\/script>/gi, ' ')
  .replace(/<style[\s\S]*?<\/style>/gi, ' ')
  .replace(/<[^>]+>/g, ' ')
  .replace(/&nbsp;/g, ' ')
  .replace(/&amp;/g, '&')
  .replace(/\s+/g, ' ')
  .trim()
  .slice(0, 6000);
const websiteOk = text.length > 200;

const system = `You are a B2B research assistant for a legal-AI company that sells to law firms, in-house legal departments and legal publishers in Europe.
Classify the organisation using the website text and the inbound form. Respond with JSON only, using exactly these keys:
{
  "org_type": "law_firm" | "in_house_legal" | "publisher" | "other",
  "lawyer_count": integer or null (only if stated or countable in the text),
  "practice_areas": array of short English strings,
  "legaltech_signals": array of short strings (e.g. "innovation page", "legal engineer job", "mentions AI tools"),
  "fit_score": integer from 0 to 20 (fit for a legal-AI workspace product),
  "fit_reason": one sentence in English,
  "summary": two sentences in English describing the organisation
}
If information is missing, use null or an empty array. Never invent numbers.`;

const user = `Company name: ${lead.company}
Domain: ${lead.domain}
Country: ${lead.country || 'unknown'}
Form message: ${lead.message || '(empty)'}
Website title: ${title || '(none)'}
Website text: ${websiteOk ? text : '(website could not be fetched)'}`;

return [{
  json: {
    website_ok: websiteOk,
    website_title: title,
    llm_request: {
      model: cfg.llm_model,
      temperature: 0,
      response_format: { type: 'json_object' },
      messages: [
        { role: 'system', content: system },
        { role: 'user', content: user }
      ]
    }
  }
}];
'''

SCORE_JS = r'''// ICP scoring = deterministic rules (0-80) + LLM fit judgment (0-20).
// If the LLM call failed, we score on rules only and flag the lead for manual review.
const lead = $('Normalize & Validate').first().json;
const prep = $('Prepare LLM Request').first().json;
const cfg = $('Config').first().json;

let ai = {};
let llmOk = false;
try {
  ai = JSON.parse($json.choices[0].message.content);
  llmOk = true;
} catch (e) {
  ai = {};
}

const breakdown = [];
const add = (label, pts) => { breakdown.push(`${label}: +${pts}`); return pts; };
let rule = 0;

const orgPts = { law_firm: 20, in_house_legal: 20, publisher: 10 }[ai.org_type] || 0;
rule += add(`Org type (${ai.org_type || 'unknown'})`, orgPts);

const n = Number.isFinite(ai.lawyer_count) ? ai.lawyer_count : null;
const sizePts = n === null ? 0 : n >= 50 ? 20 : n >= 10 ? 15 : n >= 3 ? 5 : 0;
rule += add(`Lawyers (${n ?? 'unknown'})`, sizePts);

const areas = Array.isArray(ai.practice_areas) ? ai.practice_areas : [];
const docHeavy = areas.some(a => cfg.doc_heavy_practice_areas.some(k => String(a).toLowerCase().includes(k)));
rule += add('Practice areas', docHeavy ? 15 : areas.length ? 5 : 0);

const signals = Array.isArray(ai.legaltech_signals) ? ai.legaltech_signals : [];
rule += add('Legal-tech signals', signals.length >= 2 ? 15 : signals.length === 1 ? 8 : 0);

rule += add(`Region (${lead.region})`, { DACH: 10, EU: 5 }[lead.region] || 0);

const fit = llmOk ? Math.max(0, Math.min(20, Math.round(Number(ai.fit_score) || 0))) : 0;
if (llmOk) breakdown.push(`LLM fit: +${fit}`);

const total = rule + fit;
const tier = total >= cfg.tier_a_min ? 'A' : total >= cfg.tier_b_min ? 'B' : 'C';
const needsReview = !llmOk || !prep.website_ok;
const owner = cfg.owners[lead.region] || cfg.owners.OTHER;

// HubSpot payloads (built here so the HTTP nodes stay simple)
const companyProps = { name: lead.company, domain: lead.domain };
if (lead.country) companyProps.country = lead.country;

const contactProps = { email: lead.email };
if (lead.first_name) contactProps.firstname = lead.first_name;
if (lead.last_name) contactProps.lastname = lead.last_name;
if (lead.company) contactProps.company = lead.company;
if (owner.hubspot_owner_id) contactProps.hubspot_owner_id = owner.hubspot_owner_id;
if (cfg.write_custom_properties) {
  contactProps.icp_score = total;
  contactProps.icp_tier = tier;
  contactProps.icp_reason = ai.fit_reason || '';
  contactProps.lead_language = lead.language;
}

return [{
  json: {
    ...lead,
    org_type: ai.org_type || 'unknown',
    lawyer_count: n,
    practice_areas: areas,
    legaltech_signals: signals,
    fit_reason: ai.fit_reason || '',
    summary: ai.summary || '',
    rule_score: rule,
    llm_score: fit,
    total_score: total,
    tier,
    breakdown,
    llm_ok: llmOk,
    website_ok: prep.website_ok,
    needs_review: needsReview,
    owner,
    hubspot_company_properties: companyProps,
    hubspot_contact_properties: contactProps
  }
}];
'''

RESOLVE_COMPANY_JS = r'''// Both branches (create or update) return the company object; keep only its ID.
return [{ json: { company_id: $json.id } }];
'''

ROUTE_JS = r'''// Build the HubSpot note and the Slack alert, and decide whether to notify.
const s = $('Score Lead').first().json;
const cfg = $('Config').first().json;
const contact = $('HubSpot: Upsert Contact').first().json.results[0];
const contactId = contact.id;
const isReturning = contact.new === false;

const recordUrl = cfg.hubspot_portal_id
  ? `https://app.hubspot.com/contacts/${cfg.hubspot_portal_id}/record/0-1/${contactId}`
  : '';
const list = arr => (arr && arr.length ? arr.join(', ') : 'unknown');

const noteLines = [
  `<b>Inbound lead: Tier ${s.tier}, ICP score ${s.total_score}/100</b>`,
  `Owner: ${s.owner.name}`,
  `Region: ${s.region} | Language: ${s.language.toUpperCase()} | Returning contact: ${isReturning ? 'yes' : 'no'}`,
  `Org type: ${s.org_type} | Lawyers: ${s.lawyer_count ?? 'unknown'}`,
  `Practice areas: ${list(s.practice_areas)}`,
  `Legal-tech signals: ${list(s.legaltech_signals)}`,
  `Why: ${s.fit_reason || 'n/a'}`,
  `Summary: ${s.summary || 'n/a'}`,
  `Score breakdown: ${s.breakdown.join(' | ')}`,
  `Form message: ${s.message || '(empty)'}`
];
if (s.needs_review) noteLines.push('<b>Needs manual review: enrichment incomplete.</b>');

const icon = { A: ':large_green_circle:', B: ':large_yellow_circle:', C: ':white_circle:' }[s.tier];
const slackLines = [
  `${icon} *New inbound lead - Tier ${s.tier} (${s.total_score}/100)*${isReturning ? '  _returning contact_' : ''}`,
  `*${s.company}* (${s.domain}) | ${s.region} | ${s.language.toUpperCase()}`,
  `${[s.first_name, s.last_name].filter(Boolean).join(' ') || 'Unknown name'} - ${s.email}`,
  s.fit_reason ? `_${s.fit_reason}_` : '',
  `Practice areas: ${list(s.practice_areas)}`,
  `Owner: ${s.owner.slack || s.owner.name}`,
  recordUrl ? `<${recordUrl}|Open in HubSpot>` : '',
  s.needs_review ? ':warning: Enrichment incomplete, please check manually.' : ''
].filter(Boolean);

return [{
  json: {
    tier: s.tier,
    total_score: s.total_score,
    contact_id: contactId,
    notify: s.tier !== 'C',
    hubspot_note_body: {
      properties: {
        hs_timestamp: new Date().toISOString(),
        hs_note_body: noteLines.join('<br>')
      },
      associations: [{
        to: { id: contactId },
        types: [{ associationCategory: 'HUBSPOT_DEFINED', associationTypeId: 202 }]
      }]
    },
    slack_body: { text: slackLines.join('\n') }
  }
}];
'''

# ---------------------------------------------------------------- node builders

def code(name, js, pos):
    return {"parameters": {"jsCode": js}, "id": uid(), "name": name,
            "type": "n8n-nodes-base.code", "typeVersion": 2, "position": pos}

def http(name, pos, method, url, body=None, cred=None, on_error=False, extra_opts=None, headers=None):
    p = {"method": method, "url": url}
    if cred:
        p["authentication"] = "predefinedCredentialType"
        p["nodeCredentialType"] = cred
    if headers:
        p["sendHeaders"] = True
        p["headerParameters"] = {"parameters": [{"name": k, "value": v} for k, v in headers.items()]}
    if body is not None:
        p["sendBody"] = True
        p["specifyBody"] = "json"
        p["jsonBody"] = body
    p["options"] = extra_opts or {}
    n = {"parameters": p, "id": uid(), "name": name,
         "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": pos}
    if on_error:
        n["onError"] = "continueRegularOutput"
    return n

def if_node(name, left, pos):
    return {"parameters": {"conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                "conditions": [{"id": uid(), "leftValue": left, "rightValue": "",
                                "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                "combinator": "and"},
            "options": {}},
            "id": uid(), "name": name, "type": "n8n-nodes-base.if", "typeVersion": 2, "position": pos}

def sticky(content, pos, w, h, color=None):
    p = {"content": content, "width": w, "height": h}
    if color:
        p["color"] = color
    return {"parameters": p, "id": uid(), "name": "Note " + uid()[:6],
            "type": "n8n-nodes-base.stickyNote", "typeVersion": 1, "position": pos}

X = lambda i: 200 + i * 240
Y = 400

nodes = [
    {"parameters": {"httpMethod": "POST", "path": "lead-intake", "responseMode": "onReceived", "options": {}},
     "id": uid(), "name": "Lead Form Webhook", "type": "n8n-nodes-base.webhook",
     "typeVersion": 2, "position": [X(0), Y], "webhookId": uid()},
    code("Config", CONFIG_JS, [X(1), Y]),
    code("Normalize & Validate", NORMALIZE_JS, [X(2), Y]),
    if_node("Processable?", "={{ $json.is_processable }}", [X(3), Y]),
    {"parameters": {}, "id": uid(), "name": "Stop: Not Processed", "type": "n8n-nodes-base.noOp",
     "typeVersion": 1, "position": [X(4), Y + 220]},
    http("Fetch Website", [X(4), Y], "GET", "=https://{{ $json.domain }}", on_error=True,
         headers={"User-Agent": "Mozilla/5.0 (compatible; LeadEnrichmentBot/0.1)"},
         extra_opts={"response": {"response": {"responseFormat": "text"}}, "timeout": 10000}),
    code("Prepare LLM Request", PREPARE_LLM_JS, [X(5), Y]),
    http("LLM Extract & Judge", [X(6), Y], "POST", "https://api.openai.com/v1/chat/completions",
         body="={{ JSON.stringify($json.llm_request) }}", cred="openAiApi", on_error=True,
         extra_opts={"timeout": 60000}),
    code("Score Lead", SCORE_JS, [X(7), Y]),
    http("HubSpot: Find Company", [X(8), Y], "POST", "https://api.hubapi.com/crm/v3/objects/companies/search",
         body="={{ JSON.stringify({ filterGroups: [{ filters: [{ propertyName: 'domain', operator: 'EQ', value: $json.domain }] }], properties: ['name', 'domain'], limit: 1 }) }}",
         cred="hubspotAppToken"),
    if_node("Company Exists?", "={{ $json.total > 0 }}", [X(9), Y]),
    http("HubSpot: Update Company", [X(10), Y - 120], "PATCH",
         "=https://api.hubapi.com/crm/v3/objects/companies/{{ $json.results[0].id }}",
         body="={{ JSON.stringify({ properties: $('Score Lead').first().json.hubspot_company_properties }) }}",
         cred="hubspotAppToken"),
    http("HubSpot: Create Company", [X(10), Y + 120], "POST",
         "https://api.hubapi.com/crm/v3/objects/companies",
         body="={{ JSON.stringify({ properties: $('Score Lead').first().json.hubspot_company_properties }) }}",
         cred="hubspotAppToken"),
    code("Resolve Company ID", RESOLVE_COMPANY_JS, [X(11), Y]),
    http("HubSpot: Upsert Contact", [X(12), Y], "POST",
         "https://api.hubapi.com/crm/v3/objects/contacts/batch/upsert",
         body="={{ JSON.stringify({ inputs: [{ idProperty: 'email', id: $('Score Lead').first().json.email, properties: $('Score Lead').first().json.hubspot_contact_properties }] }) }}",
         cred="hubspotAppToken"),
    http("HubSpot: Associate Contact", [X(13), Y], "PUT",
         "=https://api.hubapi.com/crm/v4/objects/contact/{{ $json.results[0].id }}/associations/default/company/{{ $('Resolve Company ID').first().json.company_id }}",
         cred="hubspotAppToken"),
    code("Route & Compose", ROUTE_JS, [X(14), Y]),
    http("HubSpot: Add Note", [X(15), Y], "POST", "https://api.hubapi.com/crm/v3/objects/notes",
         body="={{ JSON.stringify($json.hubspot_note_body) }}", cred="hubspotAppToken"),
    if_node("Tier A or B?", "={{ $('Route & Compose').first().json.notify }}", [X(16), Y]),
    http("Slack Alert", [X(17), Y], "POST", "={{ $('Config').first().json.slack_webhook_url }}",
         body="={{ JSON.stringify($('Route & Compose').first().json.slack_body) }}"),
    {"parameters": {}, "id": uid(), "name": "Tier C: CRM Only", "type": "n8n-nodes-base.noOp",
     "typeVersion": 1, "position": [X(17), Y + 220]},
]

notes = [
    sticky("## 1. Intake & guardrails\nWebhook receives the form POST and answers 200 immediately.\n\n**Config** holds every setting (owners, thresholds, model, Slack URL).\n\n**Normalize & Validate** cleans fields, checks GDPR consent, filters free-mail, detects DE/EN and region.\n\nMVP: unprocessable leads stop here. Full engine: store a minimal record and nurture.",
           [X(0) - 40, Y - 380], 940, 840, 7),
    sticky("## 2. Enrichment & scoring\n**Fetch Website** pulls the homepage (failures continue).\n\n**LLM Extract & Judge** returns strict JSON: org type, lawyer count, practice areas, legal-tech signals, fit score + reason.\n\n**Score Lead** = rules 0-80 + LLM 0-20 → Tier A/B/C. LLM failure = rules only + manual-review flag.",
           [X(4) - 40, Y - 380], 940, 840, 4),
    sticky("## 3. HubSpot (CRM)\nCompany: find by domain → update or create.\nContact: batch upsert by email (HubSpot's native dedup; returning contacts are detected).\nThen associate contact ↔ company.\n\nScore lives in a note. Flip `write_custom_properties` in Config once the custom properties exist.",
           [X(8) - 40, Y - 380], 1420, 840, 6),
    sticky("## 4. Route & notify\nOwner by region from Config. Note with score breakdown on the contact.\nTier A/B → Slack alert. Tier C → CRM only.\n\nFull engine: segment routing, round-robin, AI first-touch draft, Postgres funnel log.",
           [X(14) - 40, Y - 380], 940, 840, 5),
]

def link(*targets):
    return [[{"node": t, "type": "main", "index": 0} for t in targets]]

connections = {
    "Lead Form Webhook": {"main": link("Config")},
    "Config": {"main": link("Normalize & Validate")},
    "Normalize & Validate": {"main": link("Processable?")},
    "Processable?": {"main": [[{"node": "Fetch Website", "type": "main", "index": 0}],
                              [{"node": "Stop: Not Processed", "type": "main", "index": 0}]]},
    "Fetch Website": {"main": link("Prepare LLM Request")},
    "Prepare LLM Request": {"main": link("LLM Extract & Judge")},
    "LLM Extract & Judge": {"main": link("Score Lead")},
    "Score Lead": {"main": link("HubSpot: Find Company")},
    "HubSpot: Find Company": {"main": link("Company Exists?")},
    "Company Exists?": {"main": [[{"node": "HubSpot: Update Company", "type": "main", "index": 0}],
                                 [{"node": "HubSpot: Create Company", "type": "main", "index": 0}]]},
    "HubSpot: Update Company": {"main": link("Resolve Company ID")},
    "HubSpot: Create Company": {"main": link("Resolve Company ID")},
    "Resolve Company ID": {"main": link("HubSpot: Upsert Contact")},
    "HubSpot: Upsert Contact": {"main": link("HubSpot: Associate Contact")},
    "HubSpot: Associate Contact": {"main": link("Route & Compose")},
    "Route & Compose": {"main": link("HubSpot: Add Note")},
    "HubSpot: Add Note": {"main": link("Tier A or B?")},
    "Tier A or B?": {"main": [[{"node": "Slack Alert", "type": "main", "index": 0}],
                              [{"node": "Tier C: CRM Only", "type": "main", "index": 0}]]},
}

workflow = {
    "name": "Inbound Lead Engine - MVP (HubSpot)",
    "nodes": notes + nodes,
    "connections": connections,
    "pinData": {},
    "active": False,
    "settings": {"executionOrder": "v1"},
    "tags": [],
}

import os
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "workflow", "inbound-lead-engine-mvp.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(workflow, f, indent=2, ensure_ascii=False)
print("ok", len(nodes), "nodes")
