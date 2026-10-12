# Scoring model

The ICP score runs from 0 to 100: **rules give up to 80 points, the LLM's judgment up to 20.** The split is deliberate. Rules make the score explainable and stable from one run to the next; the LLM adds nuance that rules cannot express, but it can never decide a tier on its own.

![Score breakdown for the example lead](../assets/score-breakdown.png)

## Who the ICP is

The model assumes a legal-AI product sold in Europe, with DACH as the core market. The ideal customer:

- is a **law firm** or an **in-house legal department** (legal publishers are a secondary segment),
- has **enough lawyers** for a team-wide tool to matter,
- works in **document-heavy practice areas**, where AI review and drafting save the most time,
- shows **legal-tech maturity**: someone internally already owns innovation,
- sits in **DACH** (core market, German-speaking sales team), or elsewhere in the EU.

These criteria are an assumption made for the project, not a real company's ICP.

## Criteria

| Criterion | Points | Why it matters |
| --- | --- | --- |
| Org type: law firm / in-house legal / publisher / other | 20 / 20 / 10 / 0 | The product only fits legal organisations |
| Lawyers: 50+ / 10–49 / 3–9 / fewer or unknown | 20 / 15 / 5 / 0 | Deal size and the value of a shared workspace grow with headcount |
| Practice areas: document-heavy / any other / none found | 15 / 5 / 0 | Corporate, M&A, litigation, employment, real estate, compliance and banking work is document-heavy |
| Legal-tech signals: 2+ / 1 / none | 15 / 8 / 0 | An innovation team or a legal-engineer hire means a buyer and a faster sales cycle |
| Region: DACH / rest of EU / other | 10 / 5 / 0 | Core market first |
| LLM fit judgment | 0–20 | Catches what the rules miss, e.g. a firm that fits but describes itself unusually |

**Tiers:** A ≥ 70, B ≥ 40, C below 40. In the MVP, Tier A and B both trigger a Slack alert; Tier C stays in HubSpot only.

## The LLM's job: extract, then judge

The model is asked for one JSON object with fixed keys:

```json
{
  "org_type": "law_firm | in_house_legal | publisher | other",
  "lawyer_count": "integer or null",
  "practice_areas": ["short English strings"],
  "legaltech_signals": ["short strings"],
  "fit_score": "0-20",
  "fit_reason": "one sentence",
  "summary": "two sentences"
}
```

Guardrails:

- **`temperature: 0` and JSON mode**, so output is consistent and machine-readable.
- **"Never invent numbers."** A missing lawyer count must come back as `null`, which scores 0 rather than a guess.
- **The model extracts, the code decides.** Points for org type, size, practice areas and signals are assigned in JavaScript from the extracted facts. Only `fit_score` comes straight from the model, and it is clamped to 0–20.
- **Failure is safe.** Unparseable output or a failed call means the lead is scored on rules only and flagged `needs_review`.

The full prompt is in the *Prepare LLM Request* node, and the request for the example lead is saved in [`examples/03-llm-request.json`](../examples/03-llm-request.json).

## Tuning

All weights and thresholds live in the **Config** node, apart from the per-criterion point values in *Score Lead*. To tune:

1. Change a threshold or keyword list in Config.
2. Run `node tests/simulate_code_nodes.js` to confirm the test leads still land where expected.
3. Re-import the workflow, or edit the node directly in n8n.

Once outcomes are logged (on the roadmap: a Postgres table of every lead with its later deal stage), the weights can be checked against reality. For example, compare meeting-booked rates per tier, or check whether leads with legal-tech signals actually convert faster.
