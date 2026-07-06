import type { SimplifiedFormValues } from './simplifiedForm'

/** Build the retrieval question for grounded RAG estimation from form fields. */
export function buildRagQuestion(values: SimplifiedFormValues): string {
  const oneLine = values.oneLineSummary?.trim() ?? ''
  const transcript = values.transcript.trim()
  if (oneLine && transcript) {
    return `${oneLine}\n\n${transcript}`
  }
  return oneLine || transcript
}
