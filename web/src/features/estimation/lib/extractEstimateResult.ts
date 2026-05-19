/** Normalize session estimate payload to the structured result object for the UI. */
export function extractEstimateResult(
  estimate: Record<string, unknown> | null | undefined,
): Record<string, unknown> | null {
  if (!estimate || typeof estimate !== 'object') {
    return null
  }

  const nested = estimate.result
  if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
    return nested as Record<string, unknown>
  }

  if (
    typeof estimate.title === 'string' ||
    estimate.totals != null ||
    Array.isArray(estimate.phases)
  ) {
    return estimate
  }

  return null
}
