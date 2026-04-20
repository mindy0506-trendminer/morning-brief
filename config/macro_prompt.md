# MacroTab SCTEEP Classification Prompt

> **Status:** placeholder for PR-2 (`macro_tagger.py`). PR-1 creates this file
> so the classification contract is reviewable ahead of the tagging pass
> (plan v2 §D2-D, OQ10).
>
> **Scholarly foundation (academic grounding only — no TrendLab506 editorial
> voice):**
> - Aguilar, F.J. (1967). *Scanning the Business Environment.* Macmillan. —
>   the original PEST macro-environment framework.
> - Yuksel, I. (2012). "Developing a Multi-Criteria Decision Making Model for
>   PESTEL Analysis." *International Journal of Business and Management* 7(24),
>   52-66. — formalizes PESTEL dimensions used here as SCTEEP.
> - Hofstede, G. (2011). "Dimensions of National Cultures." *Online Readings
>   in Psychology and Culture* 2(1). — grounds the **Culture** dimension as
>   distinct from **Social**.
> - Porter, M.E. (1980). *Competitive Strategy.* Free Press. — motivates
>   multi-dimensional coding (a single event may span multiple forces).

## Classification task

Given a news article cluster (canonical entity + article bundle), assign
**one or more** SCTEEP dimensions. Clusters without any macro signal receive
an empty list; they will not surface on the MacroTab.

### Dimension definitions

- **S — Social:** demographic shifts, generational cohorts (Gen Z, Alpha),
  labor-market dynamics, urbanization, income distribution, public-health
  structural trends. *Grounding: Aguilar "social".*
- **C — Culture:** Hofstede-style cultural value shifts, changes in
  media / entertainment consumption with broad societal reach, shifts in
  collective identity or norms. *Grounding: Hofstede 2011.*
- **T — Technology:** AI model capabilities, platform shifts, semiconductor
  supply, emerging hardware, protocol-level changes, software ecosystem
  realignment. *Grounding: Aguilar "technological".*
- **E — Economy:** interest rates, inflation, currency moves, M&A activity
  of macro significance, trade flows, recession / growth cycle indicators.
  *Grounding: Aguilar "economic".*
- **E — Environment:** ESG regulation, climate policy, supply-chain
  sustainability, resource scarcity, extreme-weather market impacts.
  *Grounding: Yuksel 2012 PESTEL "environmental".*
- **P — Politics:** elections, geopolitics, regulation, sanctions, tax
  policy, industrial policy, antitrust. *Grounding: Aguilar "political".*

Output format (strict):

```json
{
  "cluster_id": "<string>",
  "sceep_dimensions": ["Social", "Technology", ...]
}
```

`sceep_dimensions` must use the exact Literal values from
`morning_brief.models.SceepDimension`. Empty list = "no macro signal".

## Few-shot examples

Each example cites which scholarly dimension it exemplifies. These are
illustrative fixtures only — they do not reflect any proprietary editorial
line.

### Example 1 — Economy + Politics
Input cluster: *"Federal Reserve raises policy rate 25bp; US-EU trade talks
stall on digital-services tax."*
Output:
```json
{
  "cluster_id": "ex_001",
  "sceep_dimensions": ["Economy", "Politics"]
}
```
*Grounding: Economy (interest-rate policy, Aguilar); Politics (trade
regulation, Aguilar).*

### Example 2 — Technology + Social
Input cluster: *"AI coding assistants now used by 62% of junior developers;
entry-level engineering job postings drop 18% YoY."*
Output:
```json
{
  "cluster_id": "ex_002",
  "sceep_dimensions": ["Technology", "Social"]
}
```
*Grounding: Technology (AI platform shift, Aguilar); Social (labor-market
dynamics, Aguilar).*

### Example 3 — Culture only
Input cluster: *"Short-form video overtakes traditional TV as primary news
source for under-25s across 12 OECD markets."*
Output:
```json
{
  "cluster_id": "ex_003",
  "sceep_dimensions": ["Culture"]
}
```
*Grounding: Culture (media-consumption value shift, Hofstede 2011).*

### Example 4 — Environment + Economy
Input cluster: *"EU carbon border adjustment mechanism phase-in triggers
price hikes in steel-intensive supply chains."*
Output:
```json
{
  "cluster_id": "ex_004",
  "sceep_dimensions": ["Environment", "Economy"]
}
```
*Grounding: Environment (climate regulation, Yuksel 2012 PESTEL); Economy
(supply-chain cost pass-through, Aguilar).*

### Example 5 — No macro signal
Input cluster: *"Local coffee chain launches seasonal pumpkin latte."*
Output:
```json
{
  "cluster_id": "ex_005",
  "sceep_dimensions": []
}
```
*Grounding: isolated product launch with no population-level structural
signal; excluded from MacroTab.*

## Classification heuristics

1. Prefer **fewer** dimensions. A cluster that "touches" a dimension without
   structurally impacting it should NOT receive that label.
2. A single event may legitimately span 2–3 dimensions; 4+ is a red flag —
   re-read and verify each assignment against the definition.
3. Company-specific news without macro spillover → empty list.
4. If unsure between Social and Culture, use Hofstede's rule: **Culture** is
   about values / norms; **Social** is about demographic / structural
   composition.
