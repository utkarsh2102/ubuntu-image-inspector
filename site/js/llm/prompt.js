/** System prompt and response shaping. */

export const SYSTEM_PROMPT = `You analyse Ubuntu image composition changes.

You are given an evidence pack of DETERMINISTIC facts computed from published
Ubuntu image manifests and HTTP metadata. Your job is interpretation only.

Hard rules:
1. Every number you cite must appear verbatim in the evidence pack. Never
   compute, estimate, or infer a number that is not there.
2. UNITS ARE NOT INTERCHANGEABLE. observed.imageBytesDelta is compressed
   image bytes. observed.installedKBDelta and every deltaInstalledKB are
   UNCOMPRESSED kilobytes. Never add them, never convert between them, and
   never describe an installed-size change as the image growing by that
   amount. Say "installed size" when you mean installed size.
3. Distinguish MEASURED values from things the pack says are unknown. If the
   pack says a package's size could not be resolved, do not guess it.
4. Never assert WHY a package entered the image unless dependencyEvidence is
   present. If it is null, say the data does not establish it.
5. If the evidence is insufficient to answer part of the question, say so
   plainly. "The data does not show this" is a correct and valuable answer.
6. Be concise and concrete. No generic advice such as "consider reviewing
   dependencies". Every claim must point at a specific named package or snap.

Respond with STRICT JSON only, no markdown fence:
{
  "summary": "one or two sentences stating what happened, with measured numbers",
  "findings": [
    {"claim": "specific, concrete statement", "evidenceRefs": ["c1"], "confidence": "high|medium|low"}
  ],
  "unknowns": ["what the data cannot establish"],
  "suggestedFollowUps": ["specific next investigation"]
}`;

export function buildUserMessage(pack) {
  return `Evidence pack:\n\n${JSON.stringify(pack, null, 2)}\n\nAnswer the question in "question".`;
}

/** Providers sometimes wrap JSON in prose or a fence; recover it. */
export function parseResponse(text) {
  const trimmed = (text || '').trim();
  const candidates = [trimmed];

  const fence = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (fence) candidates.push(fence[1].trim());

  const first = trimmed.indexOf('{');
  const last = trimmed.lastIndexOf('}');
  if (first !== -1 && last > first) candidates.push(trimmed.slice(first, last + 1));

  for (const c of candidates) {
    try {
      const parsed = JSON.parse(c);
      if (parsed && typeof parsed === 'object') return parsed;
    } catch {
      /* try next candidate */
    }
  }
  return { summary: trimmed, findings: [], unknowns: [], suggestedFollowUps: [], _raw: true };
}

/**
 * Flag numbers in generated prose that do not appear in the evidence pack.
 * A cheap, concrete hallucination guard -- it cannot catch everything, but it
 * catches invented magnitudes, which is the failure that matters here.
 */
export function verifyNumbers(text, packNums) {
  const bad = [];
  for (const m of String(text || '').matchAll(/\d[\d,.]*/g)) {
    const n = parseFloat(m[0].replace(/,/g, ''));
    if (!isFinite(n)) continue;
    // Small integers are ordinary prose ("the 3 largest"), not claims.
    if (Number.isInteger(n) && n <= 12) continue;
    if (!packNums.has(Math.abs(n))) bad.push(m[0]);
  }
  return bad;
}
