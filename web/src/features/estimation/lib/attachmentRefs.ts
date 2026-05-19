/** Map browser files to session ``AttachmentRef`` payloads (inline base64). */

const MAX_BYTES_PER_FILE = 256 * 1024
const MAX_FILES = 3

const ALLOWED_MIME = new Set(['text/plain', 'text/markdown', 'application/pdf'])

function guessMimeType(filename: string): string {
  const lower = filename.toLowerCase()
  if (lower.endsWith('.pdf')) {
    return 'application/pdf'
  }
  if (lower.endsWith('.md')) {
    return 'text/markdown'
  }
  return 'text/plain'
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = ''
  for (let i = 0; i < bytes.byteLength; i += 1) {
    binary += String.fromCharCode(bytes[i]!)
  }
  return btoa(binary)
}

export type AttachmentRefPayload = {
  file_id: string
  name: string
  mime_type: string
  content_base64: string
}

export async function filesToAttachmentRefs(
  files: FileList | File[],
): Promise<AttachmentRefPayload[]> {
  const list = Array.from(files).slice(0, MAX_FILES)
  const out: AttachmentRefPayload[] = []
  for (const file of list) {
    const buf = new Uint8Array(await file.arrayBuffer())
    if (buf.byteLength > MAX_BYTES_PER_FILE) {
      throw new Error(`File "${file.name}" exceeds ${MAX_BYTES_PER_FILE} bytes.`)
    }
    const mime = guessMimeType(file.name)
    if (!ALLOWED_MIME.has(mime)) {
      throw new Error(`File "${file.name}" has unsupported type.`)
    }
    out.push({
      file_id: crypto.randomUUID(),
      name: file.name,
      mime_type: mime,
      content_base64: bytesToBase64(buf),
    })
  }
  return out
}
