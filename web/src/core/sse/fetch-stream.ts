// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import { type StreamEvent } from "./StreamEvent";

export async function* fetchStream(
  url: string,
  init: RequestInit,
): AsyncIterable<StreamEvent> {
  // Get auth token from localStorage
  const token = typeof window !== "undefined" ? localStorage.getItem("auth_token") : null;
  
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    "Cache-Control": "no-cache",
    ...(token && { "Authorization": `Bearer ${token}` }),
  };
  
  const response = await fetch(url, {
    method: "POST",
    headers,
    ...init,
  });
  if (response.status !== 200) {
    throw new Error(`Failed to fetch from ${url}: ${response.status}`);
  }
  // Read from response body, event by event. An event always ends with a '\n\n'.
  const reader = response.body
    ?.pipeThrough(new TextDecoderStream())
    .getReader();
  if (!reader) {
    throw new Error("Response body is not readable");
  }

  try {
    let buffer = "";
    // Increased buffer size for DeepResearch large responses
    // Research reports can be 5-10MB+
    const MAX_BUFFER_SIZE = 50 * 1024 * 1024; // 50MB buffer size limit
    const WARN_BUFFER_SIZE = 10 * 1024 * 1024; // 10MB warning threshold

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        // Handle remaining buffer data
        if (buffer.trim()) {
          const event = parseEvent(buffer.trim());
          if (event) {
            yield event;
          }
        }
        break;
      }

      buffer += value;

      // Process events as they arrive to keep buffer size down
      let newlineIndex;
      while ((newlineIndex = buffer.indexOf("\n\n")) !== -1) {
        const chunk = buffer.slice(0, newlineIndex);
        buffer = buffer.slice(newlineIndex + 2);

        if (chunk.trim()) {
          const event = parseEvent(chunk);
          if (event) {
            yield event;
          }
        }
      }

      // Intelligent buffer overflow prevention
      if (buffer.length > MAX_BUFFER_SIZE) {
        // If we've processed events but buffer is still too large,
        // it means we have one extremely large event without proper boundaries
        console.error(
          `Buffer overflow: ${Math.round(buffer.length / 1024 / 1024)}MB accumulated without event boundaries. ` +
          `This likely indicates a server-side SSE formatting issue.`
        );
        throw new Error(
          `Buffer overflow - received ${Math.round(buffer.length / 1024 / 1024)}MB without proper event boundaries (\\n\\n)`
        );
      }

      // Warning for large buffers (helps with debugging)
      if (buffer.length > WARN_BUFFER_SIZE) {
        console.warn(
          `Large SSE buffer: ${Math.round(buffer.length / 1024 / 1024)}MB accumulated. ` +
          `Ensure server sends proper event boundaries (\\n\\n).`
        );
      }
    }
  } finally {
    reader.releaseLock(); // Release the reader lock
  }

}

function parseEvent(chunk: string) {
  let resultEvent = "message";
  let resultData: string | null = null;
  for (const line of chunk.split("\n")) {
    const pos = line.indexOf(": ");
    if (pos === -1) {
      continue;
    }
    const key = line.slice(0, pos);
    const value = line.slice(pos + 2);
    if (key === "event") {
      resultEvent = value;
    } else if (key === "data") {
      resultData = value;
    }
  }
  if (resultEvent === "message" && resultData === null) {
    return undefined;
  }
  return {
    event: resultEvent,
    data: resultData,
  } as StreamEvent;
}
