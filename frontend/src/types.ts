export type Inspiration = { name: string; doi: string; citation: string } | null;

export type Researcher = {
  researcher_id: string;
  display_name: string;
  theme: string;
  verified_researcher: boolean;
  published_topics: string[];
  is_simulated: boolean;
  public_scientific_inspiration: Inspiration;
};

export type TopicMatch = { metric: string; score: number; matched_topics: string[] };
export type DirectoryEntry = Researcher & { topic_match: TopicMatch };

export type Disclosure = "score_only" | "summary";
export type Visibility = "requester_only" | "both";

export type Channel = {
  id: string;
  owner_id: string;
  topics: string[];
  audience: string;
  visibility: string;
  approval_mode: string;
  max_disclosure: Disclosure;
  allowed_result_visibility: Visibility[];
  status: "DRAFT" | "ACTIVE" | "PAUSED" | "CLOSED" | "EXPIRED";
  activated_at: string | null;
  expires_at: string | null;
  policy_version: number;
  created_at: string;
};

export type DiscoveryChannel = {
  id: string;
  owner: { researcher_id: string; display_name: string };
  topics: string[];
  visibility: string;
  approval_mode: string;
  max_disclosure: Disclosure;
  allowed_result_visibility: Visibility[];
  expires_at: string;
  topic_match: TopicMatch;
};

export type Scope = {
  topics: string[];
  entity_classes: ("Protein" | "Interaction")[];
  metric: "jaccard" | "overlap_count";
  protocol: "psi_ca" | "plaintext_dev";
  disclosure: Disclosure | "evidence";
  normalization: string;
};

export type ComparisonRequest = {
  id: string;
  kind: "channel" | "targeted";
  channel_id: string | null;
  requester: { researcher_id: string; display_name: string };
  recipient: { researcher_id: string; display_name: string };
  requested_scope: Scope;
  result_visibility: Visibility;
  status: "PENDING" | "APPROVED" | "REJECTED" | "CANCELLED" | "EXPIRED" | "RUNNING" | "COMPLETED" | "FAILED";
  status_reason: string | null;
  created_at: string;
  decision_at: string | null;
  approved_policy_version: number | null;
  expires_at: string;
  execution_check?: { ok: boolean; reason: string | null };
};

export type ClassResult = { band: string; set_size_buckets?: { own: string; counterpart: string } };

export type MatchResult = {
  request_id: string;
  status: string;
  protocol: string;
  method: string;
  algorithm_version: string;
  disclosure: Disclosure;
  results: Record<string, ClassResult>;
  disclosed_to_counterpart: Record<string, string>;
  input_provenance: Record<string, string>;
  producer_id: string;
  policy_version: number | null;
  released_at: string;
  signature: { algorithm: string; signer: string; verified_at_release: boolean };
  caveat: string;
  matched_public_topics?: string[];
};

export type Notification = { id: string; kind: string; request_id: string | null; created_at: string; read: boolean };

export type AuditEvent = {
  id: string;
  actor_id: string | null;
  action: string;
  object_type: string;
  object_id: string | null;
  timestamp: string;
  policy_version: number | null;
  decision: "allow" | "deny";
  reason_code: string | null;
};

export type PolicyVersion = {
  version: number;
  topics: string[];
  max_disclosure: Disclosure;
  allowed_result_visibility: Visibility[];
  created_at: string;
};

export type OwnerGraph = {
  owner: string;
  nodes: { id: string; label: string; type: string; visibility: string; normalized_id?: string }[];
  edges: { source: string; target: string; type: string }[];
  hypotheses: { id: string; text: string }[];
  observations: {
    id: string; subject: string; object: string; effect: string;
    context: { cell_type: string; treatment: string; timepoint: string } | null; confidence: number;
  }[];
  local_contradictions: { pair: [string, string]; label: string }[];
  notice: string;
};

export type Persona = {
  researcher_id: string;
  display_name: string;
  theme: string;
  verified_researcher: boolean;
  is_simulated: boolean;
  public_scientific_inspiration: Inspiration;
  disclaimer: string;
};
