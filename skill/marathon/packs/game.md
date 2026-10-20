# Pack: game

Craft: browser games use threejs-game-director, which routes to its gameplay, graphics, UI, asset, debug and QA siblings. Where the two skills overlap, marathon governs the process:
- worker caps come from the marathon mode;
- `STATE.md` replaces the director's `game-progress.md` (don't keep both);
- the director's visual scorecard is evidence for the `visual_art` key, and its premium bar becomes a hard target (G-row).

## Art pipeline (decided in phases 1–2, before art-dependent work)
Weak first-pass art was the most common complaint across game projects. Code-drawn or procedural-only visuals never met the bar.
1. Research: benchmark screenshots plus real photos of real places → `research/benchmark/`.
2. **Style board** (phase 2): 8–12 GPT images (your available image generator) in 3–4 distinct directions, on one contact sheet published as a link. A fresh configured Claude reviewer scores them on `visual_art` against the benchmark (`gate.md`). The best direction proceeds; the user may override at any time.
3. Asset sources, in order:
   - proven reusable assets (`library.md`, your assets folder);
   - verified CC0 / CC-BY 4.0 / MIT sources (Poly Haven, ambientCG, Kenney, Quaternius, Sketchfab CC-BY), with the licence checked today;
   - GPT images for key art, textures, UI art and concepts;
   - local generation when your hardware and resource limits permit;
   - 3D models from any generator the user has rights to use.

   Use real photos for real places. Record every third-party asset in a credits file.

4. Image batches run unattended (your image-batch runner): resumable, STATUS.md, STOP file, ledger.csv, contact sheets.

Code that doesn't depend on art (physics, AI, missions, save, QA bots, perf harness) starts in phase 1 with greybox assets.

## Predecessor of the same brief
Copy its tooling (QA bots, audit scripts, image runner) and read its COMPROMISE.md and last gate reports as a list of known gaps. Its code and art are reference only, unless the user said build on it at intake.

## Targets to put in CHARTER (typical)
- Core loop completable end to end, bot-verified (e.g. 12/12 missions).
- Content counts: levels, enemies, bosses, items.
- Desktop ≥60 fps and phone ≥30 fps in busy scenes.
- Draw-call and triangle budgets (e.g. desktop ≤300 calls / ≤800k triangles; phone ≤150 / ≤300k).
- First playable screen ≤5 s.
- 0 console errors.
- The director's visual scorecard at its premium bar.

## Hard checks
- Mission / completability bots.
- Performance capture per game state, on desktop and on phone (390×844, touch).
- Console errors.
- A contact sheet of the key views.
- Save and restart: no state leaking between runs.

## Human-only checklist (AI gates missed all of these in past projects)
- **Controls**: sprint, jump and interact keys exist and are shown; the cursor is styled and captured only while playing; touch controls don't overlap.
- **Onboarding**: what to do next is always clear (quest marker, objective text); skill and enemy guides (图鉴) exist.
- **Readability**: ranges, health, damage numbers, HUD hierarchy; text legible on a phone.
- **Feel**: camera at speed, the weight of driving or movement, hit feedback, audio mix, water and foliage pop-in.
- **Difficulty**: the first 10 minutes are neither trivial nor frustrating; difficulty modes exist.

Find what you can yourself with a scripted playthrough and screenshots; list the rest for the user.

## Playable link
Publish a playable build at the end of wave 1 only after exact-artifact release checks pass; keep the latest playable link in STATE `link`.

## UE / desktop builds
- **Smoke test**: run `UnrealEditor-Cmd.exe <project> -nullrhi -unattended -nosplash` from the found install (preflight prints it), plus a packaged build that launches, windowed and unfocused.
- **MCP**: UE's bundled MCP plugin is a client. Driving the editor needs a server: research current community UE MCP servers or the Remote Control API (a phase-1 lens), and use one only if it saves real time. The game must not depend on it.
- **Hands off**: never capture the user's cursor or focus (UE's ClipCursor once trapped the mouse). Test windowed, unfocused or offscreen, with no audio.
- **Builds**: package into the project; large binaries go to GitHub Releases or your artifact host, not git.
