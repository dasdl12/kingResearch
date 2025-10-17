"use client";

import React, { useEffect, useState } from "react";
import { Plus, MessageSquare, Trash2, Edit2, Download, ChevronLeft, ChevronRight, X, Check } from "lucide-react";
import { toast } from "sonner";
import { useStore } from "~/core/store/store";
import { 
  fetchConversations, 
  createConversation, 
  deleteConversation as apiDeleteConversation,
  updateConversation,
  exportConversation,
  type Conversation 
} from "~/core/api/conversations";
import { cn } from "~/lib/utils";

export function ConversationSidebar() {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [conversationToDelete, setConversationToDelete] = useState<string | null>(null);

  const {
    conversations,
    conversationId,
    setConversations,
    setConversationId,
    addConversation,
    removeConversation,
    updateConversationInList,
  } = useStore();

  // Load conversations on mount
  useEffect(() => {
    const initSidebar = async () => {
      await loadConversations();
      
      // Verify current conversation ID is valid
      if (conversationId) {
        const result = await fetchConversations(50, 0);
        const conversationExists = result.conversations.some(c => c.id === conversationId);
        if (!conversationExists) {
          console.warn(`⚠️ Clearing invalid conversation ID from localStorage: ${conversationId}`);
          // Clear invalid ID from localStorage
          if (typeof window !== "undefined") {
            localStorage.removeItem("current_conversation_id");
          }
          setConversationId("");
        }
      }
    };
    
    initSidebar();
    
    // Don't auto-create conversation here - let the backend create it
    // when user sends their first message. This avoids duplicate conversations.
    
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run once on mount

  const loadConversations = async () => {
    try {
      setIsLoading(true);
      const result = await fetchConversations(50, 0);
      setConversations(result.conversations);
    } catch (error) {
      console.error("Failed to load conversations:", error);
      toast.error("Failed to load conversations");
    } finally {
      setIsLoading(false);
    }
  };

  const handleNewConversation = async () => {
    try {
      const newConv = await createConversation();
      addConversation(newConv);
      setConversationId(newConv.id);
      
      // Clear current messages
      useStore.setState({ 
        messageIds: [], 
        messages: new Map(),
        researchIds: [],
        researchPlanIds: new Map(),
        researchReportIds: new Map(),
        researchActivityIds: new Map(),
      });
      
      toast.success("New conversation created");
    } catch (error) {
      console.error("Failed to create conversation:", error);
      toast.error("Failed to create conversation");
    }
  };

  const handleSelectConversation = async (conv: Conversation) => {
    try {
      setConversationId(conv.id);
      
      // Clear current messages
      useStore.setState({ 
        messageIds: [], 
        messages: new Map(),
        researchIds: [],
        researchPlanIds: new Map(),
        researchReportIds: new Map(),
        researchActivityIds: new Map(),
      });
      
      // Load messages from this conversation
      const { fetchConversationMessages } = await import("~/core/api/conversations");
      const messagesData = await fetchConversationMessages(conv.id, 100, 0);
      
      // Convert messages to store format and add them
      if (messagesData.messages && messagesData.messages.length > 0) {
        const messageIds: string[] = [];
        const messagesMap = new Map();
        
        for (const msg of messagesData.messages) {
          messageIds.push(msg.id);
          messagesMap.set(msg.id, {
            id: msg.id,
            threadId: msg.conversation_id,
            role: msg.role,
            agent: msg.agent,
            content: msg.content,
            contentChunks: [msg.content],
            reasoningContent: "",
            reasoningContentChunks: [],
            isStreaming: false,
          });
        }
        
        useStore.setState({
          messageIds,
          messages: messagesMap,
        });
        
        console.log(`✅ Loaded ${messagesData.messages.length} messages for conversation ${conv.id}`);
      }
      
      toast.success(`Switched to: ${conv.title}`);
    } catch (error) {
      console.error("Failed to load conversation messages:", error);
      toast.error("Failed to load messages");
    }
  };

  const handleStartEdit = (conv: Conversation) => {
    setEditingId(conv.id);
    setEditTitle(conv.title);
  };

  const handleSaveEdit = async (convId: string) => {
    try {
      const updated = await updateConversation(convId, { title: editTitle });
      updateConversationInList(updated);
      setEditingId(null);
      toast.success("Title updated");
    } catch (error) {
      console.error("Failed to update conversation:", error);
      toast.error("Failed to update title");
    }
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setEditTitle("");
  };

  const handleDeleteClick = (convId: string) => {
    setConversationToDelete(convId);
    setDeleteDialogOpen(true);
  };

  const handleDeleteConfirm = async () => {
    if (!conversationToDelete) return;

    try {
      await apiDeleteConversation(conversationToDelete);
      removeConversation(conversationToDelete);
      
      // If deleting current conversation, clear it but don't auto-create
      // User can manually create when they want to start a new conversation
      if (conversationId === conversationToDelete) {
        setConversationId("");
        
        // Clear messages
        useStore.setState({
          messageIds: [],
          messages: new Map(),
          researchIds: [],
          researchPlanIds: new Map(),
          researchReportIds: new Map(),
          researchActivityIds: new Map(),
        });
        
        // Clear localStorage
        if (typeof window !== "undefined") {
          localStorage.removeItem("current_conversation_id");
        }
      }
      
      toast.success("Conversation deleted");
    } catch (error) {
      console.error("Failed to delete conversation:", error);
      toast.error("Failed to delete conversation");
    } finally {
      setDeleteDialogOpen(false);
      setConversationToDelete(null);
    }
  };

  const handleExport = async (convId: string, format: "markdown" | "json") => {
    try {
      const blob = await exportConversation(convId, format);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `conversation_${convId}.${format === "markdown" ? "md" : "json"}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      toast.success(`Exported as ${format.toUpperCase()}`);
    } catch (error) {
      console.error("Failed to export conversation:", error);
      toast.error("Failed to export conversation");
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) {
      return "Today";
    } else if (diffDays === 1) {
      return "Yesterday";
    } else if (diffDays < 7) {
      return `${diffDays} days ago`;
    } else {
      return date.toLocaleDateString();
    }
  };

  if (isCollapsed) {
    return (
      <div className="fixed left-0 top-0 z-40 h-screen w-12 border-r bg-background p-2">
        <button
          onClick={() => setIsCollapsed(false)}
          className="w-full h-10 flex items-center justify-center hover:bg-accent rounded-md transition-colors"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    );
  }

  return (
    <>
      <div className="fixed left-0 top-0 z-40 h-screen w-64 border-r bg-background flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="text-lg font-semibold">Conversations</h2>
          <div className="flex gap-1">
            <button 
              onClick={handleNewConversation}
              className="h-8 w-8 flex items-center justify-center hover:bg-accent rounded-md transition-colors"
            >
              <Plus className="h-4 w-4" />
            </button>
            <button
              onClick={() => setIsCollapsed(true)}
              className="h-8 w-8 flex items-center justify-center hover:bg-accent rounded-md transition-colors"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Conversation List */}
        <div className="flex-1 p-2 overflow-y-auto">
          {isLoading ? (
            <div className="text-center text-sm text-muted-foreground py-8">
              Loading...
            </div>
          ) : conversations.length === 0 ? (
            <div className="text-center text-sm text-muted-foreground py-8">
              No conversations yet
            </div>
          ) : (
            <div className="space-y-1">
              {conversations.map((conv) => (
                <div
                  key={conv.id}
                  className={cn(
                    "group relative rounded-lg border p-3 hover:bg-accent cursor-pointer transition-colors",
                    conversationId === conv.id && "bg-accent"
                  )}
                >
                  {editingId === conv.id ? (
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleSaveEdit(conv.id);
                          if (e.key === "Escape") handleCancelEdit();
                        }}
                        className="flex-1 h-8 text-sm px-2 border rounded bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                        autoFocus
                      />
                      <button
                        onClick={() => handleSaveEdit(conv.id)}
                        className="h-8 w-8 flex items-center justify-center hover:bg-accent rounded transition-colors"
                      >
                        <Check className="h-4 w-4" />
                      </button>
                      <button
                        onClick={handleCancelEdit}
                        className="h-8 w-8 flex items-center justify-center hover:bg-accent rounded transition-colors"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                  ) : (
                    <>
                      <div onClick={() => handleSelectConversation(conv)}>
                        <div className="flex items-start gap-2 pr-24">
                          <MessageSquare className="h-4 w-4 mt-0.5 flex-shrink-0" />
                          <div className="flex-1 min-w-0">
                            <div className="font-medium text-sm truncate">
                              {conv.title}
                            </div>
                            <div className="text-xs text-muted-foreground">
                              {formatDate(conv.updated_at)} · {conv.message_count} msgs
                            </div>
                          </div>
                        </div>
                      </div>
                      
                      {/* Action Buttons */}
                      <div className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1 bg-background/80 backdrop-blur-sm rounded p-0.5">
                        <button
                          className="h-6 w-6 flex items-center justify-center hover:bg-accent rounded transition-colors"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleStartEdit(conv);
                          }}
                        >
                          <Edit2 className="h-3 w-3" />
                        </button>
                        <button
                          className="h-6 w-6 flex items-center justify-center hover:bg-accent rounded transition-colors"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleExport(conv.id, "markdown");
                          }}
                        >
                          <Download className="h-3 w-3" />
                        </button>
                        <button
                          className="h-6 w-6 flex items-center justify-center hover:bg-accent rounded transition-colors text-destructive"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteClick(conv.id);
                          }}
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Delete Confirmation Dialog */}
      {deleteDialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
          <div className="bg-background border rounded-lg shadow-lg p-6 max-w-md mx-4">
            <h3 className="text-lg font-semibold mb-2">Delete Conversation?</h3>
            <p className="text-sm text-muted-foreground mb-4">
              This will permanently delete this conversation and all its messages.
              This action cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setDeleteDialogOpen(false)}
                className="px-4 py-2 text-sm border rounded-md hover:bg-accent transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleDeleteConfirm}
                className="px-4 py-2 text-sm bg-destructive text-destructive-foreground rounded-md hover:bg-destructive/90 transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

