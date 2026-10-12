# GDPR and data handling

Inbound leads in the EU are personal data. The workflow is built so that a sales team can process them without collecting more than it needs. This is a design summary, not legal advice.

## What is processed, and where

| Data | Source | Sent to | Stored in |
| --- | --- | --- | --- |
| Name, work email, company, country, message, consent | Form | n8n | HubSpot contact |
| Company domain | Email address | Fetch Website, HubSpot | HubSpot company |
| Public website text | The company's own homepage | OpenAI | Not stored (only the extracted facts are) |
| Company, domain, country, form message | Form | OpenAI | Not stored |
| Score, tier, reasoning | Workflow | Slack, HubSpot | HubSpot note, Slack message |

The LLM never receives the person's name or email address. It sees company-level information and the free-text message only.

## Safeguards in the workflow

- **Consent gate.** Nothing beyond normalization happens unless the consent field is an explicit opt-in. A pre-ticked or missing box does not count.
- **Business emails only.** Personal mailboxes (gmail.com, gmx.de, web.de, t-online.de …) are filtered out, which avoids enriching private individuals.
- **No scraping of people.** Enrichment reads the company's public homepage, not personal profiles.
- **One record per person.** Contacts are upserted by email, so a returning lead updates their existing record instead of creating copies. That also makes access and deletion requests easier to fulfil.

## What a production setup also needs

- **Data processing agreements** with every processor: n8n (if cloud-hosted), OpenAI, HubSpot and Slack. Choose EU data residency where offered.
- **A consent record.** Store the consent text version and a timestamp on the contact. On the roadmap as custom properties.
- **Execution log pruning in n8n.** n8n keeps execution data, including the form payload, by default. Set pruning (`EXECUTIONS_DATA_PRUNE`, `EXECUTIONS_DATA_MAX_AGE`) or turn off saving successful executions.
- **A home for blocked leads.** The MVP simply stops on leads without consent. The full engine stores a minimal record, without enrichment, so the decision is traceable.
- **Deletion.** Deleting a contact in HubSpot is the source of truth. Slack alerts should not be used as a long-term record.
