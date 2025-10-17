// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import { resolveServiceURL } from "./resolve-service-url";

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  metadata?: Record<string, any>;
}

export interface ConversationMessage {
  id: string;
  conversation_id: string;
  role: string;
  content: string;
  agent?: string;
  metadata?: Record<string, any>;
  created_at: string;
}

export interface ConversationListResponse {
  conversations: Conversation[];
  total: number;
  limit: number;
  offset: number;
}

export interface MessageListResponse {
  messages: ConversationMessage[];
  total: number;
  limit: number;
  offset: number;
}

/**
 * Fetch all conversations
 */
export async function fetchConversations(
  limit: number = 50,
  offset: number = 0
): Promise<ConversationListResponse> {
  const baseUrl = resolveServiceURL("");
  const response = await fetch(
    `${baseUrl}conversations?limit=${limit}&offset=${offset}`
  );
  
  if (!response.ok) {
    throw new Error(`Failed to fetch conversations: ${response.statusText}`);
  }
  
  return response.json();
}

/**
 * Fetch a single conversation
 */
export async function fetchConversation(
  conversationId: string
): Promise<Conversation> {
  const baseUrl = resolveServiceURL("");
  const response = await fetch(
    `${baseUrl}conversations/${conversationId}`
  );
  
  if (!response.ok) {
    throw new Error(`Failed to fetch conversation: ${response.statusText}`);
  }
  
  return response.json();
}

/**
 * Create a new conversation
 */
export async function createConversation(
  title?: string,
  metadata?: Record<string, any>
): Promise<Conversation> {
  const baseUrl = resolveServiceURL("");
  const response = await fetch(`${baseUrl}conversations`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ title, metadata }),
  });
  
  if (!response.ok) {
    throw new Error(`Failed to create conversation: ${response.statusText}`);
  }
  
  return response.json();
}

/**
 * Update conversation title or metadata
 */
export async function updateConversation(
  conversationId: string,
  updates: { title?: string; metadata?: Record<string, any> }
): Promise<Conversation> {
  const baseUrl = resolveServiceURL("");
  const response = await fetch(
    `${baseUrl}conversations/${conversationId}`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(updates),
    }
  );
  
  if (!response.ok) {
    throw new Error(`Failed to update conversation: ${response.statusText}`);
  }
  
  return response.json();
}

/**
 * Delete a conversation
 */
export async function deleteConversation(
  conversationId: string
): Promise<void> {
  const baseUrl = resolveServiceURL("");
  const response = await fetch(
    `${baseUrl}conversations/${conversationId}`,
    {
      method: "DELETE",
    }
  );
  
  if (!response.ok) {
    throw new Error(`Failed to delete conversation: ${response.statusText}`);
  }
}

/**
 * Fetch messages for a conversation
 */
export async function fetchConversationMessages(
  conversationId: string,
  limit: number = 100,
  offset: number = 0
): Promise<MessageListResponse> {
  const baseUrl = resolveServiceURL("");
  const response = await fetch(
    `${baseUrl}conversations/${conversationId}/messages?limit=${limit}&offset=${offset}`
  );
  
  if (!response.ok) {
    throw new Error(
      `Failed to fetch conversation messages: ${response.statusText}`
    );
  }
  
  return response.json();
}

/**
 * Export conversation
 */
export async function exportConversation(
  conversationId: string,
  format: "markdown" | "json" = "markdown"
): Promise<Blob> {
  const baseUrl = resolveServiceURL("");
  const response = await fetch(
    `${baseUrl}conversations/${conversationId}/export?format=${format}`
  );
  
  if (!response.ok) {
    throw new Error(`Failed to export conversation: ${response.statusText}`);
  }
  
  return response.blob();
}

/**
 * Generate title for conversation
 */
export async function generateConversationTitle(
  firstMessage: string
): Promise<{ title: string }> {
  const baseUrl = resolveServiceURL("");
  const response = await fetch(`${baseUrl}conversations/generate-title`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ first_message: firstMessage }),
  });
  
  if (!response.ok) {
    throw new Error(`Failed to generate title: ${response.statusText}`);
  }
  
  return response.json();
}

