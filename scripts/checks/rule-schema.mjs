import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const rulesRoot = path.join(repoRoot, "rules");

const allowedSchemas = new Set([
  "kbprep.cleaning_rules.v1",
  "kbprep.document_type_signals.v1",
  "kbprep.detail_signals.v1",
  "kbprep.obsidian_template.v1",
  "kbprep.ocr_normalization.v1",
  "kbprep.text_quality_signals.v1",
  "kbprep.text_profile_signals.v1",
  "kbprep.title_filters.v1",
]);

const allowedCleaningKeywordSets = new Set([
  "business_method_context_terms",
  "cta_keywords",
  "evidence_patterns",
  "feedback_discard_intent_terms",
  "feedback_protect_intent_terms",
  "footer_patterns",
  "image_educational_heading_indicators",
  "image_marketing_indicators",
  "image_operation_indicators",
  "image_proof_indicators",
  "image_qr_indicators",
  "knowledge_terms",
  "marketing_wrapper_back_matter_terms",
  "marketing_wrapper_heading_terms",
  "marketing_wrapper_line_patterns",
  "marketing_wrapper_passthrough_titles",
  "protected_patterns",
  "qr_image_markers",
  "refund_patterns",
  "transcript_filler_patterns",
  "tutorial_indicators",
]);

const objectKeywordSets = new Set(["evidence_patterns", "protected_patterns"]);
const allowedTextProfileNames = new Set([
  "ebook_or_long_report",
  "meeting_or_interview",
  "note",
  "tutorial",
]);

const failures = [];
for (const relative of collectJsonFiles(rulesRoot)) {
  const absolute = path.join(repoRoot, relative);
  let data;
  try {
    data = JSON.parse(readFileSync(absolute, "utf8"));
  } catch (error) {
    failures.push({ file: relative, reason: `invalid JSON: ${error.message}` });
    continue;
  }
  const schema = data?.schema;
  if (!allowedSchemas.has(schema)) {
    failures.push({ file: relative, reason: `unsupported or missing schema: ${schema || "<missing>"}` });
    continue;
  }
  if (schema === "kbprep.cleaning_rules.v1") {
    validateCleaningRuleFile(relative, data);
  } else if (schema === "kbprep.detail_signals.v1") {
    validateDetailSignals(relative, data);
  } else if (schema === "kbprep.text_quality_signals.v1") {
    validateTextQualitySignals(relative, data);
  } else if (schema === "kbprep.text_profile_signals.v1") {
    validateTextProfileSignals(relative, data);
  }
}

if (failures.length) {
  process.stderr.write(JSON.stringify({ ok: false, failures }, null, 2));
  process.stderr.write("\n");
  process.exit(1);
}

process.stdout.write(JSON.stringify({
  ok: true,
  checkedRuleFiles: collectJsonFiles(rulesRoot).length,
  allowedSchemas: [...allowedSchemas],
}, null, 2));
process.stdout.write("\n");

function validateCleaningRuleFile(file, data) {
  const rules = Array.isArray(data.rules) ? data.rules : [];
  const ruleIds = new Set(rules.map((rule) => rule?.id).filter((id) => typeof id === "string" && id));
  const keywordSets = data.keyword_sets && typeof data.keyword_sets === "object" && !Array.isArray(data.keyword_sets)
    ? new Set(Object.keys(data.keyword_sets))
    : new Set();

  validateCleaningKeywordSets(file, data.keyword_sets);

  const groups = data.rule_groups || {};
  if (groups && (typeof groups !== "object" || Array.isArray(groups))) {
    failures.push({ file, reason: "rule_groups must be an object when provided" });
    return;
  }
  for (const [groupName, group] of Object.entries(groups)) {
    if (!group || typeof group !== "object" || Array.isArray(group)) {
      failures.push({ file, reason: `rule_groups.${groupName} must be an object` });
      continue;
    }
    for (const ruleId of group.rules || []) {
      if (typeof ruleId !== "string" || !ruleIds.has(ruleId)) {
        failures.push({ file, reason: `rule_groups.${groupName}.rules references unknown rule: ${ruleId}` });
      }
    }
    for (const keywordSet of group.keyword_sets || []) {
      if (typeof keywordSet !== "string" || !keywordSets.has(keywordSet)) {
        failures.push({ file, reason: `rule_groups.${groupName}.keyword_sets references unknown keyword set: ${keywordSet}` });
      }
    }
  }
}

function validateCleaningKeywordSets(file, keywordSets) {
  if (keywordSets === undefined) return;
  if (!keywordSets || typeof keywordSets !== "object" || Array.isArray(keywordSets)) {
    failures.push({ file, reason: "keyword_sets must be an object when provided" });
    return;
  }
  for (const [name, values] of Object.entries(keywordSets)) {
    if (!allowedCleaningKeywordSets.has(name)) {
      failures.push({ file, reason: `keyword_sets.${name} is not a supported cleaning keyword set` });
    }
    if (!Array.isArray(values)) {
      failures.push({ file, reason: `keyword_sets.${name} must be an array` });
      continue;
    }
    if (objectKeywordSets.has(name)) {
      validatePatternKeywordSet(file, name, values);
    } else {
      validateStringKeywordSet(file, name, values);
    }
  }
}

function validatePatternKeywordSet(file, name, values) {
  for (const [index, value] of values.entries()) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      failures.push({ file, reason: `keyword_sets.${name}[${index}] must be an object` });
      continue;
    }
    if (typeof value.label !== "string" || !value.label.trim()) {
      failures.push({ file, reason: `keyword_sets.${name}[${index}].label must be a non-empty string` });
    }
    if (typeof value.pattern !== "string" || !value.pattern.trim()) {
      failures.push({ file, reason: `keyword_sets.${name}[${index}].pattern must be a non-empty string` });
    }
  }
}

function validateStringKeywordSet(file, name, values) {
  for (const [index, value] of values.entries()) {
    if (typeof value !== "string" || !value.trim()) {
      failures.push({ file, reason: `keyword_sets.${name}[${index}] must be a non-empty string` });
    }
  }
}

function validateTextProfileSignals(file, data) {
  const profiles = data.profiles;
  if (!profiles || typeof profiles !== "object" || Array.isArray(profiles)) {
    failures.push({ file, reason: "profiles must be an object" });
    return;
  }
  for (const name of Object.keys(profiles)) {
    if (!allowedTextProfileNames.has(name)) {
      failures.push({ file, reason: `profiles.${name} is not a supported text profile` });
    }
  }
  for (const name of allowedTextProfileNames) {
    validateTextProfileTermList(file, name, profiles[name]);
  }
}

function validateTextProfileTermList(file, name, values) {
  if (!Array.isArray(values) || values.length === 0) {
    failures.push({ file, reason: `profiles.${name} must be a non-empty array` });
    return;
  }
  for (const [index, value] of values.entries()) {
    if (typeof value !== "string" || !value.trim()) {
      failures.push({ file, reason: `profiles.${name}[${index}] must be a non-empty string` });
    }
  }
}

function validateTextQualitySignals(file, data) {
  validateRegexString(file, "abnormal_unicode_sequence_pattern", data.abnormal_unicode_sequence_pattern);
  validateRegexString(file, "mojibake_sequence_pattern", data.mojibake_sequence_pattern);
  validateRegexString(file, "mojibake_character_pattern", data.mojibake_character_pattern);
  validateStringList(file, "mojibake_tokens", data.mojibake_tokens);
  validateRegexList(file, "ocr_ai_confusion_patterns", data.ocr_ai_confusion_patterns);
}

function validateDetailSignals(file, data) {
  validateRegexObject(file, "patterns", data.patterns);
  validateStringMap(file, "block_type_categories", data.block_type_categories);
  validateStringList(file, "strict_categories", data.strict_categories);
}

function validateRegexObject(file, name, values) {
  if (!values || typeof values !== "object" || Array.isArray(values)) {
    failures.push({ file, reason: `${name} must be an object` });
    return;
  }
  for (const [key, pattern] of Object.entries(values)) {
    validateRegexString(file, `${name}.${key}`, pattern);
  }
}

function validateRegexList(file, name, values) {
  if (!Array.isArray(values) || values.length === 0) {
    failures.push({ file, reason: `${name} must be a non-empty array` });
    return;
  }
  for (const [index, pattern] of values.entries()) {
    validateRegexString(file, `${name}[${index}]`, pattern);
  }
}

function validateRegexString(file, name, pattern) {
  if (typeof pattern !== "string" || !pattern.trim()) {
    failures.push({ file, reason: `${name} must be a non-empty regex string` });
    return;
  }
  try {
    new RegExp(pattern);
  } catch (error) {
    failures.push({ file, reason: `${name} must be a valid regex: ${error.message}` });
  }
}

function validateStringMap(file, name, values) {
  if (!values || typeof values !== "object" || Array.isArray(values)) {
    failures.push({ file, reason: `${name} must be an object` });
    return;
  }
  for (const [key, value] of Object.entries(values)) {
    if (typeof key !== "string" || !key.trim() || typeof value !== "string" || !value.trim()) {
      failures.push({ file, reason: `${name} must map non-empty strings to non-empty strings` });
    }
  }
}

function validateStringList(file, name, values) {
  if (!Array.isArray(values) || values.length === 0) {
    failures.push({ file, reason: `${name} must be a non-empty array` });
    return;
  }
  for (const [index, value] of values.entries()) {
    if (typeof value !== "string" || !value.trim()) {
      failures.push({ file, reason: `${name}[${index}] must be a non-empty string` });
    }
  }
}

function collectJsonFiles(root) {
  if (!existsSync(root)) return [];
  const files = [];
  function walk(absoluteDir) {
    for (const entry of readdirSync(absoluteDir)) {
      const absolutePath = path.join(absoluteDir, entry);
      const stat = statSync(absolutePath);
      if (stat.isDirectory()) {
        walk(absolutePath);
        continue;
      }
      if (entry.endsWith(".json")) {
        files.push(path.relative(repoRoot, absolutePath).replaceAll(path.sep, "/"));
      }
    }
  }
  walk(root);
  return files.sort();
}
