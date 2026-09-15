# In action redesign — September 15, 2026

## Problem

The previous screen made the reader scan a slogan, subtitle, two sets of button groups, duplicate preview disclaimers, repeated model explanations, four unavailable metric fields and a completion paragraph before focusing on the answers. Three bordered panels split a single task into competing surfaces. Empty vertical blocks separated model identity from output.

## Research applied

- [NN/g: Progressive Disclosure](https://www.nngroup.com/articles/progressive-disclosure/) — defer secondary options and explanations while keeping the primary task discoverable. Applied with one “How this comparison works” disclosure; the global scripted-preview badge remains visible.
- [Google Material: Writing](https://m1.material.io/style/writing.html) — clear, accurate, concise interface text. Removed promotional headings and repeated narration; controls now directly name their actions.
- [GOV.UK: Question pages](https://design-system.service.gov.uk/patterns/question-pages/) — only request information needed for the task, and avoid long explanations as hints. The prompt has one visible label and a compact example selector; method details are separate.

These are general interaction principles adapted to this comparison tool, not a claim that those sources prescribe this exact layout.

## Final hierarchy

1. Compact title and comparison-mode switch.
2. Shared prompt and one primary action: Run preview → Stop while running → Replay after completion.
3. Equal answer columns in one surface. One model/configuration line per column; transient status occupies the same aligned header position.
4. A short illustrative route reason appears only in routing mode.
5. Method and preview limitations are available in a disclosure. No unavailable metric grid, duplicate back navigation, or permanent reset button.

The machine screen and its graphic are outside this edit. Actual token throughput, live model choice and answer grading remain unimplemented in this preview.

## Verification

- Syntax and whitespace checks pass.
- Browser verifies one-click completion in both lanes, mode switching, native example selector, clearing prior answers, stop/replay and accessible details.
- Equal answer animation pacing and null measurements remain unchanged from the tested provider.
- The responsive layout uses paired columns on wide screens and stacked answer sections on narrow screens; controls keep touch-sized targets.
