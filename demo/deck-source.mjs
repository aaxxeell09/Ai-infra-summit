import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const SKILL_DIR = "/Users/user/.codex/plugins/cache/openai-primary-runtime/presentations/26.909.12148/skills/presentations";
const TMP_DIR = "/tmp/demo-deck-build";
const DRAFT = path.join(TMP_DIR, "candidate.pptx");

const { resolvePresentationFont, applyPresentationChartFont } = await import(
  pathToFileURL(path.join(SKILL_DIR, "container_tools/artifact_tool_utils.mjs")).href
);
await fs.mkdir(TMP_DIR, { recursive: true });

const family = resolvePresentationFont();
const CHARCOAL = "#2B2E2A";
const WHITE = "#FFFFFF";
const LIME = "#A8D129";
const LIME_DARK = "#7FA312";
const MIST = "#F4F5F1";
const GREY = "#6E736B";
const LINEC = "#DDDFD8";

const SLIDES = [];
const p = Presentation.create({ slideSize: { width: 1280, height: 720 } });

function slideBase(bg = WHITE) {
  const s = p.slides.add();
  s.background.fill = bg;
  SLIDES.push(s);
  return s;
}

function titleBlock(s, kicker, title, onDark = false) {
  const k = s.shapes.add({
    geometry: "textbox",
    position: { left: 72, top: 44, width: 1136, height: 26 },
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  k.text = kicker;
  k.text.style = { typeface: family, fontSize: 13, bold: true, color: onDark ? LIME : LIME_DARK, autoFit: "none" };
  const t = s.shapes.add({
    geometry: "textbox",
    position: { left: 72, top: 70, width: 1136, height: 56 },
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  t.text = title;
  t.text.style = { typeface: family, fontSize: 32, bold: true, color: onDark ? WHITE : CHARCOAL, autoFit: "none" };
}

function sourceNote(s, txt, onDark = false) {
  const n = s.shapes.add({
    geometry: "textbox",
    position: { left: 72, top: 668, width: 1136, height: 26 },
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  n.text = txt;
  n.text.style = { typeface: family, fontSize: 11, color: onDark ? "#B9BDB3" : GREY, autoFit: "none" };
}

function bullets(s, items, pos, style = {}) {
  const b = s.shapes.add({
    geometry: "textbox",
    position: pos,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  b.text = items.join("\n");
  b.text.style = {
    typeface: family,
    fontSize: style.fontSize ?? 20,
    color: style.color ?? CHARCOAL,
    autoFit: "none",
    lineSpacingMultiple: 1.25,
    spaceAfterPoints: 10,
  };
  return b;
}

// slide 1 cover
{
  const s = slideBase(CHARCOAL);
  s.shapes.add({ geometry: "rect", position: { left: 0, top: 0, width: 12, height: 720 }, fill: LIME, line: { style: "solid", fill: LIME, width: 0 } });
  const kicker = s.shapes.add({ geometry: "textbox", position: { left: 84, top: 200, width: 900, height: 30 }, fill: "none", line: { style: "solid", fill: "none", width: 0 } });
  kicker.text = "LOCAL INFERENCE TUNER";
  kicker.text.style = { typeface: family, fontSize: 15, bold: true, color: LIME, autoFit: "none" };
  const t = s.shapes.add({ geometry: "textbox", position: { left: 84, top: 240, width: 1050, height: 170 }, fill: "none", line: { style: "solid", fill: "none", width: 0 } });
  t.text = "Getting a model onto Snapdragon is easy.\nGetting it fast is guesswork.";
  t.text.style = { typeface: family, fontSize: 48, bold: true, color: WHITE, autoFit: "none", lineSpacingMultiple: 1.05 };
  const sub = s.shapes.add({ geometry: "textbox", position: { left: 84, top: 430, width: 950, height: 60 }, fill: "none", line: { style: "solid", fill: "none", width: 0 } });
  sub.text = "A local tuner that measures real configurations on your device and recommends the one that fits your latency or battery objective.";
  sub.text.style = { typeface: family, fontSize: 20, color: "#CFD2C9", autoFit: "none", lineSpacingMultiple: 1.25 };
  const foot = s.shapes.add({ geometry: "textbox", position: { left: 84, top: 640, width: 1000, height: 26 }, fill: "none", line: { style: "solid", fill: "none", width: 0 } });
  foot.text = "Demo build - Dell Latitude 7455, Snapdragon X Elite X1E-80-100 - Qwen3-0.6B Q4_0 - September 2026";
  foot.text.style = { typeface: family, fontSize: 13, color: "#9AA096", autoFit: "none" };
  s.speakerNotes.textFrame.setText("All numbers in this deck come from paired, battery-powered confirmation runs on the actual Latitude 7455. Manifest: benchmarks/results/confirm-auto-01/sweep.json in the project repository.");
}

// slide 2 problem
{
  const s = slideBase();
  titleBlock(s, "PROBLEM", "Backend choice today is guesswork");
  bullets(s, [
    "The same model on the same laptop runs at very different speeds depending on runtime device and thread settings.",
    "Most teams pick a default, read one benchmark number, and never measure again on their own hardware.",
    "Intuition fails: on this Snapdragon X Elite laptop the NPU is the slowest decode backend for a small model, and CPU thread count changes throughput by double digits.",
    "The tuner replaces intuition with paired, repeatable measurements on the exact device, weights and workload you ship.",
  ], { left: 72, top: 180, width: 1136, height: 360 });
  const hl = s.shapes.add({ geometry: "rect", position: { left: 72, top: 560, width: 1136, height: 64 }, fill: MIST, line: { style: "solid", fill: LINEC, width: 1 }, borderRadius: 10 });
  hl.text = "Fastest decode is not the whole story: the NPU leg used 54% less energy for the same output. Speed and efficiency pull in opposite directions.";
  hl.text.style = { typeface: family, fontSize: 17, color: CHARCOAL, autoFit: "none", lineSpacingMultiple: 1.15 };
  sourceNote(s, "Sources: benchmarks/results/README.md; confirm-01 and confirm-auto-01 manifests (Qwen3-0.6B Q4_0, 512 prompt / 128 generated tokens, battery).");
  s.speakerNotes.textFrame.setText("Cite the README screening table: NPU decode 36.5 tok/s vs CPU 10-thread 97.9 tok/s, while NPU full-trial efficiency is 2.11 tokens/J vs 1.37. Emphasize that every claim in this deck is a measured observation, not a vendor spec.");
}

// slide 3 architecture
{
  const s = slideBase();
  titleBlock(s, "ARCHITECTURE", "Tuner, service, MCP tools, verified secretary");
  const boxes = [
    { x: 72, w: 250, head: "Sweep runner", body: "Native GenieX / llama.cpp benchmarks across device, threads, context and batch cells; per-cell JSON evidence." },
    { x: 346, w: 250, head: "Ranking + recommendation", body: "Ranks measured cells, builds the Pareto frontier, exports recommended modes with hashes and workload scope." },
    { x: 620, w: 250, head: "Local gateway", body: "Loopback HTTP service: status, modes, apply, tune and run endpoints; no cloud dependency." },
    { x: 894, w: 314, head: "MCP server + secretary", body: "Bounded MCP tools for coding agents; verified secretary fixture tasks check actions before any apply." },
  ];
  for (const b of boxes) {
    const sh = s.shapes.add({ geometry: "roundRect", position: { left: b.x, top: 190, width: b.w, height: 210 }, fill: MIST, line: { style: "solid", fill: LINEC, width: 1 }, borderRadius: 12 });
    sh.text = b.head + "\n\n" + b.body;
    sh.text.style = { typeface: family, fontSize: 15, color: CHARCOAL, autoFit: "none", lineSpacingMultiple: 1.2 };
  }
  for (const x of [322, 596, 870]) {
    s.shapes.add({ geometry: "rightArrow", position: { left: x, top: 280, width: 24, height: 28 }, fill: LIME_DARK, line: { style: "solid", fill: LIME_DARK, width: 0 } });
  }
  bullets(s, [
    "Modes: fast (CPU, 10 decode threads) and efficient (NPU) map measured profiles to objectives.",
    "UNO Q attach is optional future work; it is not part of the current measured pipeline.",
  ], { left: 72, top: 440, width: 1136, height: 140 }, { fontSize: 18 });
  const chip = s.shapes.add({ geometry: "rect", position: { left: 72, top: 596, width: 1136, height: 44 }, fill: CHARCOAL, line: { style: "solid", fill: CHARCOAL, width: 0 }, borderRadius: 8 });
  chip.text = "Live flow (tune, apply, verified secretary run, MCP tool calls) is under integration and is not yet a proven end-to-end pass.";
  chip.text.style = { typeface: family, fontSize: 15, bold: true, color: WHITE, autoFit: "none" };
  sourceNote(s, "Sources: docs/tuner-api.md, docs/agent-interface.md, docs/secretary-evaluation.md.");
  s.speakerNotes.textFrame.setText("Be explicit: the components exist and are tested individually; the demo flow that chains tune, apply, secretary verification and MCP calls is still being integrated. Do not present the flow as a completed end-to-end run.");
}

// slide 4 headline measured result
{
  const s = slideBase();
  titleBlock(s, "MEASURED RESULT", "CPU 10 threads decodes 2.67x faster than default NPU");
  const chart = s.charts.add("bar", {
    position: { left: 72, top: 170, width: 700, height: 420 },
    categories: ["NPU (default auto)", "CPU, 10 decode threads"],
    series: [{ name: "Aggregate decode tok/s", values: [36.36, 97.19], fill: CHARCOAL }],
    barOptions: { direction: "column", grouping: "clustered" },
    titleTextStyle: { typeface: family, fontSize: 15, bold: true, color: CHARCOAL },
    title: "Aggregate native decode tok/s, Qwen3-0.6B Q4_0, battery",
    titleTextStyle: { typeface: family, fontSize: 15, bold: true, color: CHARCOAL },
    hasLegend: false,
    dataLabels: { showValue: true, position: "outEnd" },
  });
  chart.title = "Aggregate native decode tok/s, Qwen3-0.6B Q4_0, battery";
    applyPresentationChartFont(chart, { fontFamily: family });
  const side = s.shapes.add({ geometry: "textbox", position: { left: 810, top: 180, width: 398, height: 400 }, fill: "none", line: { style: "solid", fill: "none", width: 0 } });
  side.text = "2.67x\ndecode advantage for the selected CPU configuration over default auto placement on the same weights, workload and power state.\n\nSame 512 prompt / 128 generated token workload, five alternating pairs, cold KV, all 25 repetitions per leg completed.\n\nThis is backend selection, not a new kernel: the win comes from choosing the right device and thread count, not from custom code.";
  side.text.style = { typeface: family, fontSize: 17, color: CHARCOAL, autoFit: "none", lineSpacingMultiple: 1.25 };
  sourceNote(s, "Source: benchmarks/results/confirm-auto-01/sweep.json via recommended.json (aggregate native decode: 36.36 vs 97.19 tok/s).");
  s.speakerNotes.textFrame.setText("Aggregate is total native tokens divided by summed native phase times, not an average of run rates. Workload: 512 prompt tokens, 128 generated tokens, context 4096, temperature 0, seed 42, battery powered, Qwen3-0.6B Q4_0 with a pinned SHA-256. Model hash: 33bcc57074ec7b6eada5a90651ee546ec0c2b271002c22baf9f1b2dd1e8f75cb.");
}

// slide 5 energy
{
  const s = slideBase();
  titleBlock(s, "ENERGY TRADE-OFF", "NPU delivers 1.54x the tokens per joule");
  const chart = s.charts.add("bar", {
    position: { left: 72, top: 170, width: 700, height: 420 },
    categories: ["NPU (default auto)", "CPU, 10 decode threads"],
    series: [{ name: "Full-trial SYS tokens/J", values: [2.1089, 1.3679], fill: LIME_DARK }],
    barOptions: { direction: "column", grouping: "clustered" },
    title: "Full-trial SYS tokens/J, battery-powered runs",
    titleTextStyle: { typeface: family, fontSize: 15, bold: true, color: CHARCOAL },
    hasLegend: false,
    dataLabels: { showValue: true, position: "outEnd" },
  });
  chart.title = "Full-trial SYS tokens/J, battery-powered runs";
    applyPresentationChartFont(chart, { fontFamily: family });
  const side = s.shapes.add({ geometry: "textbox", position: { left: 810, top: 180, width: 398, height: 420 }, fill: "none", line: { style: "solid", fill: "none", width: 0 } });
  side.text = "1.54x\nfull-trial efficiency for the NPU; the CPU leg used 54% more measured SYS energy for the same 3,200 generated tokens.\n\nThe energy interval includes model loading, prefill and decode. It does not establish decode-only power.\n\nObjective matters: pick fast with CPU, or efficient with NPU. The tuner exports both, with hashes and scope.";
  side.text.style = { typeface: family, fontSize: 17, color: CHARCOAL, autoFit: "none", lineSpacingMultiple: 1.25 };
  sourceNote(s, "Source: confirm-auto-01 pooled SYS energy deltas (Windows Energy Meter, pWh to J), reported in benchmarks/results/README.md and recommended.json.");
  s.speakerNotes.textFrame.setText("SYS is a Windows Energy Meter channel, not a wall-socket or NPU-only measurement. Conversions were independently checked (docs/energy-review.md). Screening tokens/J is deliberately null because the native JSON omits warmup token counts; only the confirmation runs with full token accounting produce this metric.");
}

// slide 6 CPU baseline caveat
{
  const s = slideBase();
  titleBlock(s, "HONEST BASELINE", "The stronger CPU comparison shows +16.9% aggregate, +3.2% median");
  const chart = s.charts.add("bar", {
    position: { left: 72, top: 170, width: 700, height: 420 },
    categories: ["Default CPU (12 threads)", "Selected CPU (10 threads)"],
    series: [{ name: "Aggregate decode tok/s", values: [75.86, 88.65], fill: CHARCOAL }],
    barOptions: { direction: "column", grouping: "clustered" },
    title: "CPU-only confirmation, same model, five alternating pairs",
    titleTextStyle: { typeface: family, fontSize: 15, bold: true, color: CHARCOAL },
    hasLegend: false,
    dataLabels: { showValue: true, position: "outEnd" },
  });
  chart.title = "CPU-only confirmation, same model, five alternating pairs";
    applyPresentationChartFont(chart, { fontFamily: family });
  const side = s.shapes.add({ geometry: "textbox", position: { left: 810, top: 180, width: 398, height: 430 }, fill: "none", line: { style: "solid", fill: "none", width: 0 } });
  side.text = "Aggregate decode: 75.86 to 88.65 tok/s, +16.9%.\n\nMedian individual run: +3.2%. Both legs show slowdown dips; their cause is unresolved and the next run records power state.\n\nWe show this note so tuning headlines are not misleading: the 2.67x number is backend selection, and CPU thread tuning alone is a smaller, variable gain.";
  side.text.style = { typeface: family, fontSize: 17, color: CHARCOAL, autoFit: "none", lineSpacingMultiple: 1.25 };
  sourceNote(s, "Source: benchmarks/results/confirm-01/sweep.json; 9,600 generated tokens per configuration, no in-process warmup.");
  s.speakerNotes.textFrame.setText("Disclose the variability: default trial medians ranged 59 to 95 tok/s. A median-of-trial-medians view gives +42.9% but is sensitive to how slowdown episodes fall within trials; we disclose it rather than headline it. Pooled full-trial tokens/J was 1.5043 vs 1.5089, no material efficiency gain.");
}

// slide 7 demo flow
{
  const s = slideBase();
  titleBlock(s, "DEMO", "Tune, apply, verify, then use it from an agent");
  const steps = [
    { head: "1 - Tune", body: "Sweep real configurations on the device; every cell writes JSON evidence." },
    { head: "2 - Apply", body: "Export and apply the recommended mode with hashes and workload scope." },
    { head: "3 - Verify", body: "Secretary fixtures check the exact tool action before the result is trusted." },
    { head: "4 - MCP", body: "Coding agents call bounded MCP tools: modes, run, tune, apply, verify." },
  ];
  steps.forEach((st, i) => {
    const sh = s.shapes.add({ geometry: "roundRect", position: { left: 72 + i * 292, top: 190, width: 260, height: 190 }, fill: i === 3 ? CHARCOAL : MIST, line: { style: "solid", fill: i === 3 ? CHARCOAL : LINEC, width: 1 }, borderRadius: 12 });
    sh.text = st.head + "\n\n" + st.body;
    sh.text.style = { typeface: family, fontSize: 15, color: i === 3 ? WHITE : CHARCOAL, autoFit: "none", lineSpacingMultiple: 1.2 };
    if (i < 3) {
      s.shapes.add({ geometry: "rightArrow", position: { left: 72 + i * 292 + 264, top: 270, width: 24, height: 28 }, fill: LIME_DARK, line: { style: "solid", fill: LIME_DARK, width: 0 } });
    }
  });
  const warn = s.shapes.add({ geometry: "rect", position: { left: 72, top: 430, width: 1136, height: 92 }, fill: WHITE, line: { style: "solid", fill: LIME, width: 2 }, borderRadius: 10 });
  warn.text = "Status: LIVE FLOW UNDER INTEGRATION. Components are individually tested; the chained tune-apply-verify-MCP demo has not yet passed end to end. We will say so on stage until it does.";
  warn.text.style = { typeface: family, fontSize: 17, bold: true, color: CHARCOAL, autoFit: "none", lineSpacingMultiple: 1.2 };
  sourceNote(s, "Sources: docs/agent-interface.md (MCP tool surface), docs/secretary-evaluation.md (action-level fixtures, held-out split).");
  s.speakerNotes.textFrame.setText("The MCP server is a bounded loopback client of the gateway with schema-validated tools; no shell and no arbitrary file execution. The secretary evaluation measures action choice on 50 synthetic prompts with deterministic checks; it is a workload-level quality check, not a broad generalization claim.");
}

// slide 8 roadmap
{
  const s = slideBase();
  titleBlock(s, "ROADMAP", "Next: larger models, calibrated routing, UNO Q worker");
  bullets(s, [
    "Larger-model routing: route between the small model and a larger local model, escalating only when a structured output fails validation. Quality comes from measured held-out task rates, never from model size alone.",
    "UNO Q worker: attach an optional UNO Q device as a benchmark target and remote worker. Available hardware, not required for the tuner core.",
    "Power-state and thermal recording on every confirmation run, to explain the slowdown dips seen in the CPU confirmation.",
    "QAIRT / QNN compiled bundles as first-class variants, one registered variant per compiled context.",
  ], { left: 72, top: 180, width: 1136, height: 330 }, { fontSize: 19 });
  const bounds = s.shapes.add({ geometry: "rect", position: { left: 72, top: 528, width: 1136, height: 108 }, fill: MIST, line: { style: "solid", fill: LINEC, width: 1 }, borderRadius: 10 });
  bounds.text = "Honest boundaries\nAll results are one device, one small model, one workload, battery power. No claim of superiority over all open-source stacks. No 100% support claim for any model. No invented quality scores: unmeasured quality means unavailable, never a number.";
  bounds.text.style = { typeface: family, fontSize: 16, color: CHARCOAL, autoFit: "none", lineSpacingMultiple: 1.2 };
  sourceNote(s, "Sources: docs/model-routing.md, AGENTS.md measurement rules, benchmarks/results/README.md scope statements.");
  s.speakerNotes.textFrame.setText("Close on credibility: the tuner's value is that its recommendations carry evidence, scope and hashes. The boundaries listed are deliberate disclosures, not disclaimers added for effect.");
}

const blob = await PresentationFile.exportPptx(p);
await blob.save(DRAFT);

for (let i = 0; i < SLIDES.length; i++) {
  const slide = SLIDES[i];
  const prev = await p.export({ slide, format: "png", scale: 1.5 });
  await fs.writeFile(path.join(TMP_DIR, "render", "slide-" + (i + 1) + ".png"), new Uint8Array(await prev.arrayBuffer()));
}
console.log("draft written:", DRAFT, "slides:", p.slides.count);
