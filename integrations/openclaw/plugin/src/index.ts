/**
 * Engram — Local-first persistent memory for OpenClaw agents.
 *
 * Auto-Recall:  Injects relevant memories before the agent responds.
 * Auto-Capture: Extracts important facts after the agent responds.
 * Agent Tools:  memory_store, memory_search, memory_recall, memory_forget, memory_checkpoint.
 *
 * All data stays on your machine. No cloud. No API keys to third parties.
 *
 * @see https://github.com/engram-memory/engram
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PluginConfig {
  host: string;
  namespace: string;
  autoRecall: boolean;
  autoCapture: boolean;
  minImportance: number;
  maxRecallResults: number;
  apiKey?: string;
}

interface MemoryEntry {
  id: number;
  content: string;
  memory_type: string;
  importance: number;
  namespace: string;
  tags: string[];
  created_at: string;
  accessed_at: string;
  access_count: number;
}

interface SearchHit {
  memory: MemoryEntry;
  score: number;
  match_type: string;
}

interface StoreResponse {
  id: number | null;
  duplicate: boolean;
}

interface StatsResponse {
  total_memories: number;
  by_type: Record<string, number>;
  average_importance: number;
  db_size_mb: number;
  namespace: string | null;
}

// ---------------------------------------------------------------------------
// Engram Client — HTTP calls to local Engram server
// ---------------------------------------------------------------------------

class EngramClient {
  private host: string;
  private namespace: string;
  private headers: Record<string, string>;

  constructor(config: PluginConfig) {
    this.host = config.host.replace(/\/+$/, "");
    this.namespace = config.namespace;
    this.headers = { "Content-Type": "application/json" };
    if (config.apiKey) {
      this.headers["Authorization"] = `Bearer ${config.apiKey}`;
    }
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown
  ): Promise<T> {
    const url = `${this.host}${path}`;
    const opts: RequestInit = { method, headers: this.headers };
    if (body !== undefined) {
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(url, opts);
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`Engram API error ${res.status}: ${text}`);
    }
    return res.json() as Promise<T>;
  }

  async store(
    content: string,
    type: string = "fact",
    importance: number = 5,
    tags: string[] = []
  ): Promise<StoreResponse> {
    return this.request<StoreResponse>("POST", "/v1/memories", {
      content,
      type,
      importance,
      tags,
      namespace: this.namespace,
    });
  }

  async search(query: string, limit: number = 10): Promise<SearchHit[]> {
    return this.request<SearchHit[]>("POST", "/v1/search", {
      query,
      limit,
      namespace: this.namespace,
    });
  }

  async recall(
    limit: number = 10,
    minImportance: number = 5
  ): Promise<MemoryEntry[]> {
    return this.request<MemoryEntry[]>("POST", "/v1/recall", {
      limit,
      min_importance: minImportance,
      namespace: this.namespace,
    });
  }

  async delete(memoryId: number): Promise<{ deleted: boolean }> {
    return this.request<{ deleted: boolean }>(
      "DELETE",
      `/v1/memories/${memoryId}`
    );
  }

  async stats(): Promise<StatsResponse> {
    return this.request<StatsResponse>(
      "GET",
      `/v1/stats?namespace=${encodeURIComponent(this.namespace)}`
    );
  }

  async health(): Promise<boolean> {
    try {
      await this.request<{ status: string }>("GET", "/v1/health");
      return true;
    } catch {
      return false;
    }
  }
}

// ---------------------------------------------------------------------------
// Importance extraction — lightweight keyword-based scoring
// ---------------------------------------------------------------------------

const HIGH_IMPORTANCE_PATTERNS = [
  /\b(?:always|never|important|critical|remember|don't forget|key point)\b/i,
  /\b(?:password|secret|api.?key|credential|token)\b/i,
  /\b(?:rule|principle|convention|standard|requirement)\b/i,
  /\b(?:deadline|due date|by \w+ \d+)\b/i,
  /\b(?:decided|agreed|confirmed|approved|rejected)\b/i,
  /\b(?:bug|issue|error|fix|workaround|hack)\b/i,
  /\b(?:preference|prefer|like|hate|avoid)\b/i,
];

const LOW_IMPORTANCE_PATTERNS = [
  /\b(?:maybe|perhaps|might|could|not sure)\b/i,
  /\b(?:just testing|ignore|nevermind|scratch that)\b/i,
  /\b(?:hello|hi|hey|thanks|ok|sure|yeah)\b/i,
];

function estimateImportance(text: string): number {
  let score = 5;

  for (const pattern of HIGH_IMPORTANCE_PATTERNS) {
    if (pattern.test(text)) {
      score = Math.min(10, score + 1);
    }
  }

  for (const pattern of LOW_IMPORTANCE_PATTERNS) {
    if (pattern.test(text)) {
      score = Math.max(1, score - 1);
    }
  }

  // Longer content with substance is generally more important
  const wordCount = text.split(/\s+/).length;
  if (wordCount > 50) score = Math.min(10, score + 1);
  if (wordCount < 5) score = Math.max(1, score - 1);

  return score;
}

function classifyMemoryType(
  text: string
): string {
  const lower = text.toLowerCase();
  if (/\b(?:prefer|like|hate|always use|never use|favorite)\b/.test(lower))
    return "preference";
  if (/\b(?:decided|agreed|chose|pick|go with|confirmed)\b/.test(lower))
    return "decision";
  if (/\b(?:bug|error|fix|crash|issue|workaround|solved)\b/.test(lower))
    return "error_fix";
  if (/\b(?:pattern|convention|standard|rule|always do)\b/.test(lower))
    return "pattern";
  if (/\b(?:workflow|process|step|pipeline|deploy)\b/.test(lower))
    return "workflow";
  return "fact";
}

// ---------------------------------------------------------------------------
// Fact extraction — pull memorable statements from conversation
// ---------------------------------------------------------------------------

function extractFacts(userMessage: string, agentResponse: string): string[] {
  const facts: string[] = [];
  const combined = `${userMessage}\n${agentResponse}`;

  // Split into sentences
  const sentences = combined
    .split(/[.!?\n]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 15 && s.length < 500);

  for (const sentence of sentences) {
    const importance = estimateImportance(sentence);
    if (importance >= 6) {
      facts.push(sentence);
    }
  }

  // Deduplicate similar facts
  const unique: string[] = [];
  for (const fact of facts) {
    const isDuplicate = unique.some((existing) => {
      const overlap = existing
        .toLowerCase()
        .split(/\s+/)
        .filter((w) => fact.toLowerCase().includes(w));
      return overlap.length / existing.split(/\s+/).length > 0.7;
    });
    if (!isDuplicate) {
      unique.push(fact);
    }
  }

  return unique.slice(0, 5); // Max 5 facts per exchange
}

// ---------------------------------------------------------------------------
// Plugin export — OpenClaw plugin interface
// ---------------------------------------------------------------------------

const DEFAULT_CONFIG: PluginConfig = {
  host: "http://localhost:8100",
  namespace: "openclaw",
  autoRecall: true,
  autoCapture: true,
  minImportance: 5,
  maxRecallResults: 10,
};

export default function engramPlugin(userConfig: Partial<PluginConfig> = {}) {
  const config: PluginConfig = { ...DEFAULT_CONFIG, ...userConfig };
  const client = new EngramClient(config);
  let serverAvailable: boolean | null = null;

  // Check server on first use
  async function ensureServer(): Promise<boolean> {
    if (serverAvailable !== null) return serverAvailable;
    serverAvailable = await client.health();
    if (!serverAvailable) {
      console.error(
        `[engram] Server not reachable at ${config.host}. ` +
          `Start it with: engram-server\n` +
          `Install: pip install engram-core[server]`
      );
    }
    return serverAvailable;
  }

  return {
    name: "engram-memory",

    // -----------------------------------------------------------------------
    // Auto-Recall: inject memories before agent responds
    // -----------------------------------------------------------------------
    async onPreResponse(context: {
      userMessage: string;
      systemPrompt: string;
    }): Promise<{ systemPrompt?: string }> {
      if (!config.autoRecall) return {};
      if (!(await ensureServer())) return {};

      try {
        // Search for memories relevant to current message
        const hits = await client.search(
          context.userMessage,
          config.maxRecallResults
        );

        if (hits.length === 0) return {};

        // Build memory context block
        const memoryLines = hits
          .filter((h) => h.memory.importance >= config.minImportance)
          .map(
            (h) =>
              `- [${h.memory.memory_type}|imp:${h.memory.importance}] ${h.memory.content}`
          );

        if (memoryLines.length === 0) return {};

        const memoryBlock = [
          "",
          "## Engram Memory (auto-recalled)",
          "The following memories are relevant to this conversation:",
          ...memoryLines,
          "",
        ].join("\n");

        return {
          systemPrompt: context.systemPrompt + memoryBlock,
        };
      } catch (err) {
        console.error("[engram] Auto-recall failed:", err);
        return {};
      }
    },

    // -----------------------------------------------------------------------
    // Auto-Capture: extract facts after agent responds
    // -----------------------------------------------------------------------
    async onPostResponse(context: {
      userMessage: string;
      agentResponse: string;
    }): Promise<void> {
      if (!config.autoCapture) return;
      if (!(await ensureServer())) return;

      try {
        const facts = extractFacts(context.userMessage, context.agentResponse);

        for (const fact of facts) {
          const importance = estimateImportance(fact);
          const memType = classifyMemoryType(fact);
          await client.store(fact, memType, importance);
        }
      } catch (err) {
        console.error("[engram] Auto-capture failed:", err);
      }
    },

    // -----------------------------------------------------------------------
    // Agent Tools — explicit memory operations
    // -----------------------------------------------------------------------
    tools: {
      memory_store: {
        description:
          "Store a memory in Engram. Memories persist locally across sessions. " +
          "Use for important facts, decisions, preferences, or anything worth remembering.",
        parameters: {
          type: "object",
          properties: {
            content: {
              type: "string",
              description: "The memory content to store",
            },
            memory_type: {
              type: "string",
              enum: [
                "fact",
                "preference",
                "decision",
                "error_fix",
                "pattern",
                "workflow",
              ],
              default: "fact",
              description: "Type of memory",
            },
            importance: {
              type: "number",
              minimum: 1,
              maximum: 10,
              default: 5,
              description: "Importance 1-10 (10 = critical, never forget)",
            },
            tags: {
              type: "array",
              items: { type: "string" },
              default: [],
              description: "Searchable tags",
            },
          },
          required: ["content"],
        },
        async execute(args: {
          content: string;
          memory_type?: string;
          importance?: number;
          tags?: string[];
        }): Promise<string> {
          if (!(await ensureServer()))
            return "Engram server not running. Start with: engram-server";
          const result = await client.store(
            args.content,
            args.memory_type || "fact",
            args.importance || 5,
            args.tags || []
          );
          if (result.duplicate) {
            return `Memory already exists (deduplicated). Access count updated.`;
          }
          return `Stored memory #${result.id} (${args.memory_type || "fact"}, importance: ${args.importance || 5})`;
        },
      },

      memory_search: {
        description:
          "Search your memories using natural language. " +
          "Returns relevant memories ranked by relevance and importance.",
        parameters: {
          type: "object",
          properties: {
            query: {
              type: "string",
              description: "Natural language search query",
            },
            limit: {
              type: "number",
              default: 10,
              description: "Maximum results to return",
            },
          },
          required: ["query"],
        },
        async execute(args: {
          query: string;
          limit?: number;
        }): Promise<string> {
          if (!(await ensureServer()))
            return "Engram server not running. Start with: engram-server";
          const hits = await client.search(args.query, args.limit || 10);
          if (hits.length === 0) return "No matching memories found.";
          const lines = hits.map(
            (h) =>
              `[#${h.memory.id}|${h.memory.memory_type}|imp:${h.memory.importance}] ${h.memory.content}`
          );
          return `Found ${hits.length} memories:\n${lines.join("\n")}`;
        },
      },

      memory_recall: {
        description:
          "Recall your highest-priority memories. " +
          "Returns the most important memories you've stored, regardless of topic.",
        parameters: {
          type: "object",
          properties: {
            limit: {
              type: "number",
              default: 10,
              description: "Maximum memories to recall",
            },
            min_importance: {
              type: "number",
              default: 5,
              description: "Minimum importance threshold (1-10)",
            },
          },
        },
        async execute(args: {
          limit?: number;
          min_importance?: number;
        }): Promise<string> {
          if (!(await ensureServer()))
            return "Engram server not running. Start with: engram-server";
          const memories = await client.recall(
            args.limit || 10,
            args.min_importance || 5
          );
          if (memories.length === 0) return "No memories above threshold.";
          const lines = memories.map(
            (m) =>
              `[#${m.id}|${m.memory_type}|imp:${m.importance}] ${m.content}`
          );
          return `Recalled ${memories.length} memories:\n${lines.join("\n")}`;
        },
      },

      memory_forget: {
        description:
          "Delete a specific memory by its ID. Use when information is outdated or incorrect.",
        parameters: {
          type: "object",
          properties: {
            memory_id: {
              type: "number",
              description: "The ID of the memory to delete",
            },
          },
          required: ["memory_id"],
        },
        async execute(args: { memory_id: number }): Promise<string> {
          if (!(await ensureServer()))
            return "Engram server not running. Start with: engram-server";
          const result = await client.delete(args.memory_id);
          return result.deleted
            ? `Deleted memory #${args.memory_id}.`
            : `Memory #${args.memory_id} not found.`;
        },
      },

      memory_stats: {
        description:
          "Show memory statistics — total count, types, average importance.",
        parameters: {
          type: "object",
          properties: {},
        },
        async execute(): Promise<string> {
          if (!(await ensureServer()))
            return "Engram server not running. Start with: engram-server";
          const stats = await client.stats();
          const typeLines = Object.entries(stats.by_type)
            .map(([t, c]) => `  ${t}: ${c}`)
            .join("\n");
          return (
            `Engram Memory Stats (namespace: ${stats.namespace})\n` +
            `Total: ${stats.total_memories}\n` +
            `Avg importance: ${stats.average_importance.toFixed(1)}\n` +
            `By type:\n${typeLines}`
          );
        },
      },
    },
  };
}

export { EngramClient, PluginConfig, MemoryEntry, SearchHit };
