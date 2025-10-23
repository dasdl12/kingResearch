// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import { nanoid } from "nanoid";

import type { Message } from "../messages";
import { restoreChatFromHistory } from "../store/store";

import type { CompleteResearch } from "./research";
import { getResearchForRestore } from "./research";

/**
 * Convert backend research data to frontend Message format
 */
function convertResearchToMessages(research: CompleteResearch): {
  messages: Message[];
  researchIds: string[];
  researchPlanIds: Map<string, string>;
  researchReportIds: Map<string, string>;
  researchActivityIds: Map<string, string[]>;
  openResearchId: string | null;
} {
  const messages: Message[] = [];
  const researchIds: string[] = [];
  const researchPlanIds = new Map<string, string>();
  const researchReportIds = new Map<string, string>();
  const researchActivityIds = new Map<string, string[]>();
  
  // 1. Add user's initial question
  const userMessageId = nanoid();
  messages.push({
    id: userMessageId,
    threadId: research.thread_id,
    role: "user",
    content: research.research_topic,
    contentChunks: [research.research_topic],
  });
  
  // 2. Add planner message with the plan
  const planMessageId = nanoid();
  const planContent = JSON.stringify(research.plan);
  messages.push({
    id: planMessageId,
    threadId: research.thread_id,
    agent: "planner",
    role: "assistant",
    content: planContent,
    contentChunks: [planContent],
    isStreaming: false,
  });
  
  // 3. Create research ID for this research
  const researchId = nanoid();
  researchIds.push(researchId);
  researchPlanIds.set(researchId, planMessageId);
  
  const activityIds: string[] = [planMessageId];
  
  // 4. Add observations as researcher/coder messages
  if (research.observations && research.observations.length > 0) {
    research.observations.forEach((observation, index) => {
      const obsMessageId = nanoid();
      // Determine agent based on content
      const agent = observation.includes("```") ? "coder" : "researcher";
      messages.push({
        id: obsMessageId,
        threadId: research.thread_id,
        agent,
        role: "assistant",
        content: observation,
        contentChunks: [observation],
        isStreaming: false,
      });
      activityIds.push(obsMessageId);
    });
  }
  
  // 5. Add final report as reporter message
  const reportMessageId = nanoid();
  messages.push({
    id: reportMessageId,
    threadId: research.thread_id,
    agent: "reporter",
    role: "assistant",
    content: research.final_report,
    contentChunks: [research.final_report],
    isStreaming: false,
  });
  activityIds.push(reportMessageId);
  
  researchReportIds.set(researchId, reportMessageId);
  researchActivityIds.set(researchId, activityIds);
  
  return {
    messages,
    researchIds,
    researchPlanIds,
    researchReportIds,
    researchActivityIds,
    openResearchId: researchId, // Open research panel by default
  };
}

/**
 * Load and restore a complete chat session from history
 */
export async function restoreChatFromThreadId(threadId: string): Promise<boolean> {
  try {
    const research = await getResearchForRestore(threadId);
    if (!research) {
      console.error("Failed to load research data");
      return false;
    }
    
    const chatData = convertResearchToMessages(research);
    restoreChatFromHistory({
      threadId: research.thread_id,
      ...chatData,
    });
    
    return true;
  } catch (error) {
    console.error("Error restoring chat from history:", error);
    return false;
  }
}

