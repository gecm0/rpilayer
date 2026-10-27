# Visual view of an artifact

The Markdown is the source of truth. The HTML is a visual adaptation for reading, not a conversion: a reader should get the point from the view in under a minute, then dive into details. Rebuild it after every change to the Markdown; never edit the HTML by hand.

You write only the body. The template (`DIR/view-template.html`) owns styles and Mermaid rendering. Do not read the template or write CSS, `style=` attributes, or `<style>`/`<script>`.

```bash
python3 DIR/rpilayer.py view <task_dir>/<artifact>.md <<'HTML'
...body...
HTML
```

It writes `<artifact>.html` next to the Markdown and prints its path. It does not open it.

## Layout

The page is a stack of `.row`s separated by `<hr>`. Each row has a text column and an optional `.side` margin on the right for metadata: slug, phases, next step, file paths, counts, status. The text column reads like prose; everything that is a reference goes to the margin.

- Start with the header row. Then one row per section, each opening with an `<h2>`.
- Lists of similar things (questions, findings, phases) are one `.row` per item, the item in `.item` and its files in `.side .item`.
- Choices are `.opts`, flows are Mermaid, progress is `.checks`. Plain `<p>` is for connecting sentences.
- Keep code, paths, commands, and numbers exact. Drop nothing that affects a decision; long original text goes in `<details>`.
- Write the view in the language your task names ("written in Spanish" means every heading, sentence, and option title is in Spanish), even if the artifact and the task text are in another language. Keep code, paths, commands, identifiers, and numbers exactly as in the artifact. Only if the task names no language, write in the artifact's language.

## Components

```html
<!-- header row: always first. Phases before the current one get .done. -->
<div class="row">
  <div>
    <div class="kicker">research questions</div>
    <h1>Publish an APK on tag push</h1>
    <p class="lede">One or two sentences: what this document decides or finds, and what is still open.</p>
  </div>
  <div class="side">
    <b>ci-tag-apk-release</b>01-research-questions-ci-tag-apk-release.md<br><br>
    <ul class="phases"><li class="now">questions</li><li>research</li><li>design</li><li>outline</li><li>worktree</li><li>implement</li><li>pr</li></ul>
  </div>
</div>
<hr>

<!-- note (peach) with the next step in the margin -->
<div class="row">
  <div><p class="note">You do not need to answer these. They guide the research agent.</p></div>
  <div class="side">next<b>/rpilayer → create-research</b></div>
</div>
<hr>

<!-- section title, then one row per item -->
<div class="row"><div><h2>5 questions</h2></div></div>
<div class="row">
  <div class="item"><h3><span>01</span>Where the version lives</h3><p>How <code>versionCode</code> is defined…</p></div>
  <div class="side item">app/build.gradle.kts<br>AndroidManifest.xml<br><span class="risk">! unsigned apk</span></div>
</div>

<!-- open question: .row.ask makes its .opts clickable and adds a note box; a "Copy answers" button
     collects every .ask row for the reader to paste back. Warning, options (recommended first, .rec), margin status -->
<div class="row ask">
  <div>
    <h2>Signing strategy</h2>
    <div class="warn"><b>Unsigned APK.</b> Android refuses to install it.</div>
    <div class="opts">
      <div class="opt rec"><h4>A · Keystore in Secrets</h4><ul><li class="pro">Stable signature</li><li class="con">One-time setup</li></ul></div>
      <div class="opt"><h4>B · Debug key</h4><ul><li class="pro">Zero setup</li><li class="con">Reinstall needed</li></ul></div>
    </div>
  </div>
  <div class="side">status<b class="risk">open</b></div>
</div>

<!-- progress -->
<div class="row">
  <div><h2>Phases</h2><ul class="checks"><li class="done">Phase 1: version from tag</li><li>Phase 2: signed release build</li></ul></div>
  <div class="side">progress<b>1 / 2</b></div>
</div>

<!-- diagram; before/after is .opts with "Today" and "After" -->
<pre class="mermaid">flowchart LR
  tag[git push tag] --> ci[GitHub Actions] --> apk[assembleRelease] --> rel[Release .apk]</pre>

<!-- tables for real tabular data; <details> for full original text -->
<details><summary>Full text</summary>…</details>
```

In the margin, `<b>` holds a value under its label; `.risk` marks red and `.ok` marks green. Keep Mermaid flows to 6 nodes or fewer per row so the text stays legible.

## Recipes

- **research-questions**: margin with question count; one item per question with a 3-6 word title and a one-line summary, paths in its margin; context pointers as a final row.
- **research**: lede with the key finding; one item per finding with file paths in the margin; a Mermaid diagram of the main flow found in the code; open questions marked `.risk` in the margin.
- **design-discussion / prd / tdd**: before/after as `.opts`; each open question as a `.row.ask` with `.opts` and `status open` in the margin (only open questions get `.ask`; before/after `.opts` never do); resolved questions as items with `status resolved` (`.ok`); patterns to follow as items with code.
- **structure-outline / plan**: progress in the margin of the header; phases as `.checks`; each phase as an item with its files and verification commands in the margin; risks as `.warn`.

A diagram that is the heart of the document (a system architecture, a multi-service flow) can use the `archify` skill instead of Mermaid. Link its HTML from an item; do not embed it.
