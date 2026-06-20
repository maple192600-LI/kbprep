import { existsSync, readFileSync } from "node:fs";

const htmlPath = "docs/kbprep-full-flowchart.html";
const flowPath = "docs/flowchart/kbprep-flow.json";
const allowedEdgeKinds = new Set(["next", "branch", "pass", "fail", "loop"]);
const requiredQualityGateProtection = new Map([
  ["conversion_quality_gate", ["G"]],
  ["patch_quality_gate", ["Q"]],
  ["document_cleaning_gate", ["T"]],
  ["publish_quality_gate", ["V"]],
]);

const failures = [];

if (!existsSync(flowPath)) {
  failures.push({ file: flowPath, reason: "flowchart contract file is missing" });
}
if (!existsSync(htmlPath)) {
  failures.push({ file: htmlPath, reason: "HTML flowchart is missing" });
}

if (!failures.length) {
  const flow = JSON.parse(readFileSync(flowPath, "utf8"));
  const html = readFileSync(htmlPath, "utf8");
  const htmlData = parseHtmlFlowchart(html);
  validateFlowSchema(flow);
  compareNodes(flow.nodes ?? [], htmlData.nodes);
  compareEdges(flow.edges ?? [], htmlData.edges);
  compareStages(flow.stages ?? [], htmlData.stages, htmlData.ranks);
  validateQualityGates(flow.qualityGates ?? [], flow.nodes ?? []);
  validateHtmlLoopMarker(html);
}

if (failures.length) {
  process.stderr.write(JSON.stringify({ ok: false, failures }, null, 2));
  process.stderr.write("\n");
  process.exit(1);
}

process.stdout.write(JSON.stringify({ ok: true, contract: flowPath, html: htmlPath }, null, 2));
process.stdout.write("\n");

function validateFlowSchema(flow) {
  if (!Array.isArray(flow.nodes)) failures.push({ file: flowPath, reason: "nodes must be an array" });
  if (!Array.isArray(flow.edges)) failures.push({ file: flowPath, reason: "edges must be an array" });
  if (!Array.isArray(flow.stages)) failures.push({ file: flowPath, reason: "stages must be an array" });
  if (!Array.isArray(flow.qualityGates)) failures.push({ file: flowPath, reason: "qualityGates must be an array" });
}

function compareNodes(flowNodes, htmlNodes) {
  const flowById = new Map(flowNodes.map((node) => [node.id, node]));
  for (const [id, label] of htmlNodes) {
    const node = flowById.get(id);
    if (!node) {
      failures.push({ file: flowPath, reason: `missing node from HTML: ${id}` });
      continue;
    }
    if (node.label !== label) {
      failures.push({ file: flowPath, node: id, reason: `label mismatch: JSON=${node.label} HTML=${label}` });
    }
  }
  for (const node of flowNodes) {
    if (!htmlNodes.has(node.id)) {
      failures.push({ file: flowPath, node: node.id, reason: "JSON node is not present in HTML" });
    }
    for (const key of ["id", "slug", "label", "type", "stage", "coreSection", "developmentDoc"]) {
      if (typeof node[key] !== "string" || !node[key].trim()) {
        failures.push({ file: flowPath, node: node.id, reason: `node.${key} must be a non-empty string` });
      }
    }
  }
}

function compareEdges(flowEdges, htmlEdges) {
  const htmlKeys = new Set(htmlEdges.map(edgeKey));
  const flowKeys = new Set();
  for (const edge of flowEdges) {
    const normalized = normalizeEdge(edge);
    const key = edgeKey(normalized);
    flowKeys.add(key);
    if (!allowedEdgeKinds.has(normalized.kind)) {
      failures.push({ file: flowPath, edge: `${normalized.from}->${normalized.to}`, reason: `invalid edge kind: ${normalized.kind}` });
    }
    if (!htmlKeys.has(key)) {
      failures.push({ file: flowPath, edge: key, reason: "JSON edge is not present in HTML" });
    }
  }
  for (const edge of htmlEdges) {
    const key = edgeKey(edge);
    if (!flowKeys.has(key)) {
      failures.push({ file: flowPath, edge: key, reason: "HTML edge is not present in JSON" });
    }
  }
  requireEdgeKind(flowEdges, "C", "D", "branch");
  requireEdgeKind(flowEdges, "H", "F", "loop");
  requireEdgeKind(flowEdges, "AA", "N", "loop");
}

function compareStages(flowStages, htmlStages, ranks) {
  const htmlLabels = htmlStages.map(([label]) => label);
  const flowLabels = flowStages.map((stage) => stage.label);
  if (htmlLabels.join("|") !== flowLabels.join("|")) {
    failures.push({ file: flowPath, reason: `stage labels differ: JSON=${flowLabels.join(" > ")} HTML=${htmlLabels.join(" > ")}` });
  }
  const rankedNodes = new Set(ranks.flat());
  const stageNodes = new Set();
  for (const stage of flowStages) {
    if (!Array.isArray(stage.nodeIds) || !stage.nodeIds.length) {
      failures.push({ file: flowPath, stage: stage.id, reason: "stage.nodeIds must be a non-empty array" });
      continue;
    }
    for (const id of stage.nodeIds) stageNodes.add(id);
  }
  for (const id of rankedNodes) {
    if (!stageNodes.has(id)) {
      failures.push({ file: flowPath, node: id, reason: "ranked node is not assigned to a JSON stage" });
    }
  }
}

function validateQualityGates(qualityGates, nodes) {
  const nodeIds = new Set(nodes.map((node) => node.id));
  const gateById = new Map(qualityGates.map((gate) => [gate.id, gate]));
  for (const gate of qualityGates) {
    if (!Array.isArray(gate.protectsNodeIds) || !gate.protectsNodeIds.length) {
      failures.push({ file: flowPath, gate: gate.id, reason: "quality gate must protect at least one node" });
      continue;
    }
    for (const id of gate.protectsNodeIds) {
      if (!nodeIds.has(id)) {
        failures.push({ file: flowPath, gate: gate.id, reason: `quality gate references unknown node: ${id}` });
      }
    }
  }
  for (const [gateId, protectedNodes] of requiredQualityGateProtection) {
    const gate = gateById.get(gateId);
    if (!gate) {
      failures.push({ file: flowPath, gate: gateId, reason: "required quality gate is missing" });
      continue;
    }
    for (const id of protectedNodes) {
      if (!gate.protectsNodeIds.includes(id)) {
        failures.push({ file: flowPath, gate: gateId, reason: `required gate does not protect node ${id}` });
      }
    }
  }
}

function validateHtmlLoopMarker(html) {
  if (!html.includes('id="arrowLoop"')) {
    failures.push({ file: htmlPath, reason: "loop marker arrowLoop is missing" });
  }
}

function requireEdgeKind(edges, from, to, kind) {
  const edge = edges.map(normalizeEdge).find((item) => item.from === from && item.to === to);
  if (!edge) {
    failures.push({ file: flowPath, edge: `${from}->${to}`, reason: "required semantic edge is missing" });
  } else if (edge.kind !== kind) {
    failures.push({ file: flowPath, edge: `${from}->${to}`, reason: `edge must be ${kind}, got ${edge.kind}` });
  }
}

function parseHtmlFlowchart(html) {
  return {
    nodes: new Map(Object.entries(readConst(html, "NODE_LABELS"))),
    ranks: readConst(html, "RANKS"),
    edges: readConst(html, "EDGES").map(([from, to, label = "", kind = "next"]) => ({ from, to, label, kind })),
    stages: readConst(html, "STAGES"),
  };
}

function readConst(html, name) {
  const match = html.match(new RegExp(`const\\s+${name}\\s*=\\s*([\\s\\S]*?);\\n`));
  if (!match) {
    failures.push({ file: htmlPath, reason: `missing const ${name}` });
    return [];
  }
  return Function(`"use strict"; return (${match[1]});`)();
}

function normalizeEdge(edge) {
  return {
    from: edge.from,
    to: edge.to,
    label: edge.label ?? "",
    kind: edge.kind ?? "next",
  };
}

function edgeKey(edge) {
  const normalized = normalizeEdge(edge);
  return `${normalized.from}->${normalized.to}|${normalized.label}|${normalized.kind}`;
}
