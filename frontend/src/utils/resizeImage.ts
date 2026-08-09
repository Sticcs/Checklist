// Downscales an uploaded image before it's stored, so a multi-megabyte
// phone photo doesn't blow past localStorage's per-origin quota (~5-10MB,
// browser-dependent) or bloat every page load with a huge data URI.
export async function resizeImageToDataUrl(file: File, maxDim = 1920, quality = 0.82): Promise<string> {
  const objectUrl = URL.createObjectURL(file)
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const el = new Image()
      el.onload = () => resolve(el)
      el.onerror = () => reject(new Error('Could not read image'))
      el.src = objectUrl
    })

    const scale = Math.min(1, maxDim / Math.max(img.width, img.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(img.width * scale)
    canvas.height = Math.round(img.height * scale)

    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('Canvas not supported')
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)

    return canvas.toDataURL('image/jpeg', quality)
  } finally {
    URL.revokeObjectURL(objectUrl)
  }
}
