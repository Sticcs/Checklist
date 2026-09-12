// A task/list's title becomes a heading line, each subtask/item becomes its
// own "• " dot-point line below it - a plain-text outline meant for pasting
// into notes apps, chat, email, anywhere richer formatting doesn't survive.
export function formatAsOutline(heading: string, items: string[]): string {
  return [heading, ...items.map((item) => `• ${item}`)].join('\n')
}

export async function copyTextToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
