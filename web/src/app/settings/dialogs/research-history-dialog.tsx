"use client";

import { Trash2, Eye, MessageSquareText, Plus } from "lucide-react";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";

import { LoadingAnimation } from "~/components/deer-flow/loading-animation";
import { Tooltip } from "~/components/deer-flow/tooltip";
import { Button } from "~/components/ui/button";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "~/components/ui/dialog";
import { useAuth } from "~/core/auth";
import { getResearches, deleteResearch, type Research } from "~/core/api/research";
import { cn } from "~/lib/utils";

export function ResearchHistoryDialog() {
  const [open, setOpen] = useState(false);
  const [researches, setResearches] = useState<Research[]>([]);
  const [loading, setLoading] = useState(false);
  const { user, token } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (open && token) {
      loadResearches();
    }
  }, [open, token]);

  const loadResearches = async () => {
    setLoading(true);
    try {
      const data = await getResearches(50, 0);
      setResearches(data);
    } catch (error) {
      console.error("Failed to load researches:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleView = (threadId: string) => {
    setOpen(false);
    // Navigate to chat page with thread_id to restore the conversation
    router.push(`/chat?thread_id=${threadId}`);
  };

  const handleDelete = async (threadId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this research?")) {
      return;
    }

    const success = await deleteResearch(threadId);
    if (success) {
      setResearches(researches.filter((r) => r.thread_id !== threadId));
    } else {
      alert("Failed to delete research");
    }
  };

  const formatDate = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      return date.toLocaleString();
    } catch {
      return dateStr;
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Tooltip title="Research History" className="max-w-60">
        <DialogTrigger asChild>
          <Button variant="ghost" size="icon">
            <MessageSquareText />
          </Button>
        </DialogTrigger>
      </Tooltip>
      <DialogContent className="sm:max-w-[900px] max-h-[80vh]">
        <DialogHeader>
          <div className="flex items-center justify-between">
            <div>
              <DialogTitle>Your Research History</DialogTitle>
              <DialogDescription>
                {user
                  ? `Viewing completed researches for ${user.username}`
                  : "Please sign in to view your research history"}
              </DialogDescription>
            </div>
            {user && (
              <Tooltip title="New Research">
                <Button
                  size="sm"
                  onClick={() => {
                    setOpen(false);
                    // Navigate to chat with newChat flag to reset state
                    router.push("/chat?newChat=true");
                  }}
                >
                  <Plus className="w-4 h-4 mr-1" />
                  New
                </Button>
              </Tooltip>
            )}
          </div>
        </DialogHeader>

        <div className="flex flex-col h-[500px] overflow-auto border-y">
          {!token ? (
            <div className="flex flex-col items-center justify-center flex-1 space-y-4">
              <p className="text-muted-foreground">
                Sign in to save and view your research history
              </p>
              <Button
                onClick={() => {
                  setOpen(false);
                  router.push("/auth");
                }}
              >
                Sign In
              </Button>
            </div>
          ) : loading ? (
            <div className="flex items-center justify-center flex-1">
              <LoadingAnimation />
            </div>
          ) : researches.length === 0 ? (
            <div className="flex items-center justify-center flex-1">
              <p className="text-muted-foreground">
                No completed researches yet. Start a new research to see it here!
              </p>
            </div>
          ) : (
            <div className="space-y-3 p-4">
              {researches.map((research) => (
                <Card
                  key={research.thread_id}
                  className="cursor-pointer transition-all hover:shadow-md"
                  onClick={() => handleView(research.thread_id)}
                >
                  <div className="flex items-center justify-between p-4">
                    <div className="flex-1 min-w-0">
                      <CardHeader className="p-0">
                        <CardTitle className="text-lg truncate">
                          {research.research_topic}
                        </CardTitle>
                        <CardDescription className="flex items-center gap-2 text-sm">
                          <span>{formatDate(research.completed_at)}</span>
                          <span>•</span>
                          <span className="capitalize">{research.report_style}</span>
                        </CardDescription>
                      </CardHeader>
                    </div>
                    <div className="flex items-center gap-2 ml-4">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleView(research.thread_id)}
                      >
                        <Eye className="w-4 h-4 mr-1" />
                        View
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={(e) => handleDelete(research.thread_id, e)}
                      >
                        <Trash2 className="w-4 h-4 text-destructive" />
                      </Button>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}





