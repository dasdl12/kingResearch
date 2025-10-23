// Research history API functions

export interface Research {
  id: string;
  thread_id: string;
  research_topic: string;
  report_style: string;
  is_completed: boolean;
  created_at: string;
  completed_at: string;
  ts: string;
}

export interface CompleteResearch extends Research {
  final_report: string;
  observations: string[];
  plan: {
    title: string;
    thought: string;
    steps: Array<{
      title: string;
      description: string;
      step_type: string;
      execution_res?: string;
    }>;
    has_enough_context: boolean;
  };
}

function getAuthHeaders(): HeadersInit {
  const token = localStorage.getItem("auth_token");
  return {
    "Content-Type": "application/json",
    ...(token && { "Authorization": `Bearer ${token}` }),
  };
}

export async function getResearches(limit = 20, offset = 0): Promise<Research[]> {
  try {
    const response = await fetch(`/api/researches?limit=${limit}&offset=${offset}`, {
      headers: getAuthHeaders(),
    });
    
    if (!response.ok) {
      if (response.status === 401) {
        // Not authenticated
        return [];
      }
      throw new Error("Failed to fetch researches");
    }
    
    const data = await response.json();
    return data.data || [];
  } catch (error) {
    console.error("Error fetching researches:", error);
    return [];
  }
}

export async function getResearch(threadId: string): Promise<CompleteResearch | null> {
  try {
    const response = await fetch(`/api/research/${threadId}`, {
      headers: getAuthHeaders(),
    });
    
    if (!response.ok) {
      if (response.status === 404 || response.status === 401) {
        return null;
      }
      throw new Error("Failed to fetch research");
    }
    
    return await response.json();
  } catch (error) {
    console.error("Error fetching research:", error);
    return null;
  }
}

export async function deleteResearch(threadId: string): Promise<boolean> {
  try {
    const response = await fetch(`/api/research/${threadId}`, {
      method: "DELETE",
      headers: getAuthHeaders(),
    });
    
    return response.ok;
  } catch (error) {
    console.error("Error deleting research:", error);
    return false;
  }
}

export async function getResearchForRestore(threadId: string): Promise<CompleteResearch | null> {
  try {
    const response = await fetch(`/api/research/${threadId}`, {
      headers: getAuthHeaders(),
    });
    
    if (!response.ok) {
      return null;
    }
    
    return await response.json();
  } catch (error) {
    console.error("Error fetching research for restore:", error);
    return null;
  }
}





