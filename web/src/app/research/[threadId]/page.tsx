"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { Button } from "~/components/ui/button";
import { LoadingAnimation } from "~/components/deer-flow/loading-animation";
import { getResearch, type CompleteResearch } from "~/core/api/research";

export default function ResearchViewPage() {
  const params = useParams();
  const router = useRouter();
  const threadId = params.threadId as string;
  
  const [research, setResearch] = useState<CompleteResearch | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadResearch();
  }, [threadId]);

  const loadResearch = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const data = await getResearch(threadId);
      if (data) {
        setResearch(data);
      } else {
        setError("Research not found or access denied");
      }
    } catch (err) {
      console.error("Failed to load research:", err);
      setError("Failed to load research");
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <LoadingAnimation />
      </div>
    );
  }

  if (error || !research) {
    return (
      <div className="flex flex-col h-screen items-center justify-center gap-4">
        <p className="text-destructive">{error || "Research not found"}</p>
        <Button onClick={() => router.push("/chat")}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Chat
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <header className="border-b px-6 py-4">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => router.push("/chat")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Button>
          <div className="flex-1">
            <h1 className="text-2xl font-bold">{research.research_topic}</h1>
            <p className="text-sm text-muted-foreground">
              Completed on {new Date(research.completed_at).toLocaleString()} • {research.report_style}
            </p>
          </div>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Research Activities Panel */}
        <aside className="w-80 border-r overflow-auto bg-muted/30">
          <div className="p-4 space-y-4">
            <h2 className="font-semibold text-lg">Research Process</h2>
            
            {/* Research Plan */}
            {research.plan && (
              <div className="space-y-2">
                <h3 className="font-medium">Plan:</h3>
                <p className="text-sm text-muted-foreground">{research.plan.thought}</p>
                <div className="space-y-2 mt-2">
                  {research.plan.steps.map((step, index) => (
                    <div key={index} className="p-3 bg-card rounded-lg border">
                      <div className="font-medium text-sm">{step.title}</div>
                      <div className="text-xs text-muted-foreground mt-1">
                        {step.description}
                      </div>
                      {step.execution_res && (
                        <div className="text-xs text-green-600 mt-1">✓ Completed</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Observations */}
            {research.observations && research.observations.length > 0 && (
              <div className="space-y-2">
                <h3 className="font-medium">Observations ({research.observations.length}):</h3>
                {research.observations.map((obs, index) => (
                  <div key={index} className="p-3 bg-card rounded-lg border text-sm">
                    <div className="font-medium text-xs text-muted-foreground mb-1">
                      Step {index + 1}
                    </div>
                    <div className="whitespace-pre-wrap line-clamp-3">{obs}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </aside>

        {/* Main Report Panel */}
        <main className="flex-1 overflow-auto">
          <div className="max-w-4xl mx-auto p-8">
            <div className="prose prose-neutral dark:prose-invert max-w-none">
              <div
                dangerouslySetInnerHTML={{
                  __html: convertMarkdownToHtml(research.final_report),
                }}
              />
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

// Simple markdown to HTML converter (you can use a library like marked or react-markdown)
function convertMarkdownToHtml(markdown: string): string {
  // Basic markdown conversion (you may want to use a proper library)
  let html = markdown
    // Headers
    .replace(/^### (.*$)/gim, '<h3>$1</h3>')
    .replace(/^## (.*$)/gim, '<h2>$1</h2>')
    .replace(/^# (.*$)/gim, '<h1>$1</h1>')
    // Bold
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    // Italic
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    // Links
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    // Line breaks
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br/>');

  return `<p>${html}</p>`;
}









