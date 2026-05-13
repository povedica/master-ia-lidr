/** Convert uploaded files to API attachment objects (base64). */

const MAX_BYTES = 256 * 1024

function guessContentType(filename: string): 'text/plain' | 'text/markdown' | 'application/pdf' {
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

export async function filesToAttachments(
  files: FileList | File[],
): Promise<
  Array<{
    filename: string
    content_type: 'text/plain' | 'text/markdown' | 'application/pdf'
    content_base64: string
  }>
> {
  const list = Array.from(files).slice(0, 3)
  const out: Array<{
    filename: string
    content_type: 'text/plain' | 'text/markdown' | 'application/pdf'
    content_base64: string
  }> = []
  for (const file of list) {
    const buf = new Uint8Array(await file.arrayBuffer())
    if (buf.byteLength > MAX_BYTES) {
      throw new Error(`File "${file.name}" exceeds ${MAX_BYTES} bytes.`)
    }
    out.push({
      filename: file.name,
      content_type: guessContentType(file.name),
      content_base64: bytesToBase64(buf),
    })
  }
  return out
}
