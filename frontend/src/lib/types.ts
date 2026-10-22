export type Role = "Admin" | "Department Head" | "Manager" | "Member" | "Guest";
export type AccessLevel = "public" | "department" | "private";
export type IndexStatus = "pending" | "processing" | "ready" | "failed";
export type Tier = "local" | "free" | "paid";

export type Profile = {
  id: number;
  email: string;
  full_name: string | null;
  department: string | null;
  role: Role | null;
  designation: string | null;
};

export type Meta = {
  app_name: string;
  version: string;
  auth_provider: "local" | "supabase";
  password_min_length: number;
};

export type TierStatus = {
  tier: Tier;
  tier_label: string;
  provider: string;
  model: string;
  enabled: boolean;
  position: number | null;
  healthy: boolean;
  circuit_open: boolean;
  requires_confirmation?: boolean | null;
  monthly_budget_usd?: number | null;
  month_spend_usd?: number | null;
};

export type SystemStatus = {
  tiers: TierStatus[];
  roles: Role[];
  departments: string[];
  access_levels: AccessLevel[];
  allowed_extensions: string[];
  max_file_size_mb: number;
  image_generation: boolean;
};

export type FileOut = {
  id: number;
  name: string;
  file_type: string | null;
  file_size_bytes: number | null;
  department: string | null;
  access_level: AccessLevel | null;
  index_status: IndexStatus;
  index_error: string | null;
  created_at: string;
  owner_id: number | null;
  chunk_count: number;
};

export type Source = {
  file_id: number;
  file_name: string;
  page: number | null;
  section: string | null;
  snippet: string;
};

export type ModelInfo = { tier: Tier; tier_label: string; provider: string; model: string };

export type Mode = "assistant" | "documents" | "file" | "clarify" | "video" | "general";

export type UserOut = Profile & {
  is_active: boolean;
  last_login: string | null;
  created_at: string;
};

export type AuditLogOut = {
  id: number;
  user_id: number | null;
  user_email: string | null;
  action: string | null;
  resource_type: string | null;
  resource_id: number | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
};

export type Stats = {
  users_total: number;
  users_active: number;
  files_total: number;
  files_ready: number;
  files_failed: number;
  files_in_progress: number;
  chunks_total: number;
  queries_24h: number;
  uploads_7d: number;
  users_by_department: { department: string; count: number }[];
};

export type ActivityPoint = { day: string; queries: number; uploads: number };

export type TierUsage = {
  tier: Tier;
  calls: number;
  failures: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  avg_latency_ms: number;
};

export type LLMUsageReport = {
  days: number;
  tiers: TierUsage[];
  daily: { day: string; local: number; free: number; paid: number }[];
  month_paid_spend_usd: number;
  monthly_budget_usd: number;
};

export type CatalogFile = {
  id: number;
  name: string;
  file_type: string | null;
  department: string | null;
  my_request_status: "pending" | "approved" | "denied" | null;
};

export type AccessRequestOut = {
  id: number;
  file_id: number;
  file_name: string | null;
  department: string | null;
  requester_id: number | null;
  requester_email: string | null;
  status: "pending" | "approved" | "denied" | null;
  is_recurring: boolean;
  requested_at: string;
  expires_at: string | null;
};

export type AccessRuleOut = {
  id: number;
  department: string | null;
  rule_name: string | null;
  source_role: string | null;
  target_file_type: string | null;
  grant_hours: number | null;
  is_active: boolean;
};

export type TeamStats = {
  department: string;
  members_total: number;
  members_active_7d: number;
  queries_7d: number;
  uploads_7d: number;
  members: {
    id: number;
    name: string;
    role: string | null;
    is_active: boolean;
    last_login: string | null;
    queries_7d: number;
    uploads_7d: number;
  }[];
};
