# Pack: website, atlas, encyclopedia, data site, tool

Craft: use your design workflow, or define typography, colors, spacing, references and responsive behavior before building. This pack owns data, coverage and process.

## Independent rebuilds
When the brief points at an existing site ("research this site and rebuild it"), study what it tries to do and what works. Then build with your own logic, data model and layout; copy nothing unless CHARTER says to build on it. Exception: an existing tool with real users keeps the layout habits they rely on.

## Data pipeline (encyclopedias, atlases, databases)
- **Sources** go in an inventory in BRIEF.md: coverage, fields, licence, rate limits, robots. Respect robots and use delays; worker briefs repeat this.
- **Stages**, each re-runnable: sources → raw (`sources/<src>/items.jsonl`) → normalize → geocode → translate / name → select (quotas) → build. Keep every stage inside the assigned project.
- **Provenance**: every record keeps its source URL and fetch date.
- **No placeholders** ("待补充", "TBD", "暂无"). A record missing required fields is either excluded or becomes a clearly labelled reference card.
- **Chinese names** are checked against official sources (e.g. 中国生物物种名录, brand sites), never guessed from transliteration.
- **Text** is written in our own words, with a source on each record. Never bulk-copy Wikipedia (CC BY-SA would bind the site), IUCN or a shop's text; short quotes carry attribution.
- **Images**: real, licensed photos for real species, places and products (Wikimedia Commons, iNaturalist research grade, CC0 / CC BY), with credit on each. GPT images only for decoration or concepts, and labelled. A generated picture of a real species or product is a factual error.
- **Media** over ~10 MB in total stays out of git (gitignored `media/` or similar), is published by your deploy command, and has its manifest with hashes in git.

## Targets to put in CHARTER (typical)
- Item count and per-category quotas.
- Required fields present: 100%.
- Map pins at the stated precision: ≥90%.
- **Sampling test**: 3 independent random samples of 50 well-known items, drawn from public lists (not our own), each with ≤1 missing. The lists are frozen in `research/sampling/` during phase 1, before selection runs.
- **Error audit**: 60 random records checked against primary sources; critical-field error rate ≤3%.
- Placeholders: 0.
- Initial payload ≤2.5 MB gzip; first content ≤1 s on desktop.
- Phone layout clean at 375 and 440 px wide.

## Maps
Plain or white basemaps were rejected every time. Start from a proven basemap (e.g. Esri National Geographic tiles or your own relief assets) and apply your map design rules, with China-standard borders for China. Compare against the user's best map sites before showing anything. Clusters open into lists rather than forcing a zoom to the last level.

## Hard checks
- Design `shoot.py` (desktop + iPhone, fonts, overflow, contrast) and the click test.
- Link checker.
- Data validators: counts, fields, placeholders, duplicates, licences present.
- Payload size and timing on the live URL.

## Human-only checklist
Is the first screen interesting? Does search find what a friend would type? Are the photos right for the items? Does it load fast on the user's phone over mobile data?
