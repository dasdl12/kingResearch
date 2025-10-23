import { parse } from "best-effort-json-parser";

export function parseJSON<T>(json: string | null | undefined, fallback: T) {
  if (!json) {
    return fallback;
  }
  try {
    const raw = json
      .trim()
      .replace(/^```json\s*/, "")
      .replace(/^```js\s*/, "")
      .replace(/^```ts\s*/, "")
      .replace(/^```plaintext\s*/, "")
      .replace(/^```\s*/, "")
      .replace(/\s*```$/, "");
    
    // First try standard JSON.parse for valid JSON
    try {
      return JSON.parse(raw) as T;
    } catch {
      // If standard parsing fails, use best-effort parser with suppressed errors
      // This prevents console pollution from partial/malformed JSON
      const originalConsoleError = console.error;
      try {
        console.error = () => {}; // Suppress best-effort-json-parser error output
        return parse(raw) as T;
      } finally {
        console.error = originalConsoleError; // Restore original console.error
      }
    }
  } catch {
    return fallback;
  }
}
