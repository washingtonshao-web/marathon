# Phase 1: Charter and research

Research is the cheapest quality lever: most past rework came from building before studying the benchmark, the literature or real references. Raw material must not flood the lead's context: researchers read widely, a synthesizer distils, and the lead reads a short decision summary.

## Budget
15–20% of the work budget, front-loaded (research agents start in the background during the intake turn), plus targeted top-ups when a gate finds a knowledge gap. Code that doesn't depend on research results (scaffold, data pipeline skeleton, QA harness) may start in parallel. The run never waits for the user to read the brief.

## Who does it
- Researcher agents, one lens each, count by mode. Each writes `research/notes/<lens>.md` (≤1,500 words, every claim with a source link) and saves raw pages, data and images to `research/raw/<lens>/`.
- One **synthesizer** agent then writes `research/BRIEF.md` from the notes. It returns a ≤300-word decision summary with BRIEF.md section pointers. Builders/reviewers use the full brief; the lead opens specific sections only to resolve a disputed decision.
- Use the research skill if installed; otherwise the lead dispatches its own research workers using the lens, note limits and source requirements above. With that skill, these lens paths replace its folder layout. Asset hunts ("fetch assets from online") are a lens too, with licences recorded.
- Check `library.md` and your assets folder first: reuse proven basemaps, asset sources, scripts and datasets.

## Lenses (pick 3–6)
| Type | Lenses |
|---|---|
| Game | benchmark teardown (systems, loop, UI, onboarding, controls; screenshots); art direction and references (real photos of real places, the benchmark's art); asset sources with licences; tech (engine features, performance, UE tooling if relevant); what players praise and hate in the genre; the predecessor's gate gaps and compromises |
| Site / atlas | best-in-class sites (screenshots, interaction patterns, why they work); data sources (coverage, fields, licence, rate limits, robots); data model and accuracy traps; map and visual references; performance at the target data size; sampling lists (frozen now, see the site pack) |
| Research | literature map (key papers, reviews, guidelines); industry practice and terms; numbers with sources; tools and pipelines (versions, benchmarks); public datasets for verification (size, licence, truth sets); competitors and products; open controversies; the decision frame |

## `research/BRIEF.md` (≤5,000 words)
1. Benchmark: what "as good as <benchmark>" concretely means, as a list, with a `research/benchmark/` contact sheet. Gate agents compare against this.
2. Key facts and numbers, each with a source.
3. Sources, assets, tools and datasets chosen (and rejected, with the reason).
4. Risks and traps.
5. Implications: concrete decisions for the CHARTER and the build.

## Finalise the charter
- Turn the provisional targets into final G-rows, each with how it is measured.
- Adjust the `RUBRIC:` line (and `FLOOR:` with adjusted-bar rows when the benchmark is out of reach).
- Fill references (build on / reference only / tooling only) and the parameter ledger.
- Log every change from the intake draft under Decisions (`note <dir> decision`).
