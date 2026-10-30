export interface ApiEnvelope<T> {
  code: number;
  message: string;
  data: T;
  request_id: string;
}

export interface LoginData {
  access_token: string;
  token_type: "Bearer";
  expires_in: number;
  player_id: string;
  is_new_player: boolean;
  progress_version: number;
  server_time: number;
}

export interface MapEnterData {
  map_id: string;
  instance_id: string;
  session_id: string;
  spawn_position: { x: number; y: number; direction: string };
  current_players: number;
  max_players: number;
  reconnect_grace_seconds: number;
  websocket_path: string;
}

export interface WsEnvelope<T = Record<string, unknown>> {
  v: 1;
  cmd: string;
  seq: number;
  ts: number;
  payload: T;
}

export type MapServerEvent = WsEnvelope<Record<string, unknown>>;


export type LawRuleId = "RULE_ECHO" | "RULE_GAZE" | "RULE_REVERSE";

export interface RuleCatalogItem {
  rule_id: LawRuleId;
  display_name: string;
  duration_type: "INSTANT" | "WHILE_CASTING" | "TIMED";
  priority: number;
  scope_type: string;
  cooldown_ms: number | null;
  radius: number | null;
  duration_ms: number | null;
  lease_timeout_ms: number | null;
  allowed_target_types: string[];
  config_status: "READY" | "TUNING_REQUIRED" | string;
  is_unlocked: boolean;
}

export interface RuleCatalogData {
  rules: RuleCatalogItem[];
}

export interface RulePoint {
  x: number;
  y: number;
}

export interface RuleCastEffect {
  mechanism_id: string;
  state: Record<string, unknown>;
}

export interface RuleComboResult {
  combo_id: string;
  mechanism_id: string;
  status: string;
  already_applied?: boolean;
}

export interface RuleCastData {
  run_id: string;
  rule_id: LawRuleId;
  target_id: string | null;
  effects: RuleCastEffect[];
  combo: RuleComboResult | null;
  cooldown_until: string;
  idempotent_replay: boolean;
}

export interface GazeMaintainData {
  run_id: string;
  target_id: string;
  maintained_at: string;
}

export interface GazeStopData {
  run_id: string;
  stopped: boolean;
  target_id?: string;
}

export interface LevelCatalogItem {
  level_id: string;
  level_name: string;
  entrance_id: string;
  room_index: number | null;
  target_duration_min: number;
  target_duration_max: number;
  hard_time_limit: boolean;
  time_limit_seconds: number | null;
  repeatable: boolean;
  repeat_reward_mode: "NONE" | "REDUCED" | "FULL";
  required_laws: string[];
  necessary_objectives: string[];
  is_hidden: boolean;
  is_unlocked: boolean;
  config: Record<string, unknown>;
}

export type LevelEntrySummary = Omit<LevelCatalogItem, "is_unlocked">;

export interface LevelCatalogData {
  levels: LevelCatalogItem[];
}

export interface LevelPositionData {
  run_id: string;
  x: number;
  y: number;
}

export interface MechanismInteractData {
  run_id: string;
  mechanism_id: string;
  state: Record<string, unknown>;
  already_interacted: boolean;
  idempotent_replay: boolean;
}

export interface LevelRunData {
  run_id: string;
  level_id: string;
  status: "CREATED" | "RUNNING" | "COMPLETED" | "FAILED" | "ABANDONED";
  started_at?: string | null;
  ended_at?: string | null;
  idempotent_replay?: boolean;
}

export interface LevelEnterData {
  run_id: string;
  map_instance_id: string | null;
  status: "CREATED" | "RUNNING" | "COMPLETED" | "FAILED" | "ABANDONED";
  level: LevelEntrySummary;
  idempotent_replay: boolean;
}

export interface PersonalMechanismState {
  mechanism_id: string;
  mechanism_type: string;
  state: Record<string, unknown>;
  position_x: number | null;
  position_y: number | null;
  target_type: string | null;
  config: Record<string, unknown>;
  updated_at: string;
}

export interface PersonalLevelState {
  run_id: string;
  level_id: string;
  mechanisms: PersonalMechanismState[];
}


export interface PlayerProfile {
  player_id: string;
  current_character_id: string | null;
  progress_version: number;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface CharacterItem {
  character_id: string;
  display_name: string;
  config: Record<string, unknown>;
  unlocked_at: string;
  is_unlocked: boolean;
}

export interface CharacterCatalogData {
  current_character_id: string | null;
  characters: CharacterItem[];
}

export interface CharacterSelectionData {
  success: boolean;
  current_character_id: string;
}


export interface PlayerProgressData {
  progress_version: number;
  current_character_id: string | null;
  completed_level_ids: string[];
  permanent_progress: Record<string, unknown>;
  snapshot_at?: string;
}

export interface DiscoveryItem {
  discovery_id: string;
  discovery_type: string;
  display_name: string;
  level_id: string | null;
  related_rule: string | null;
  first_discovered_at: string;
  trigger_count: number;
}

export interface CollectionItem {
  collection_id: string;
  codex_category: string;
  display_name: string;
  description: string;
  asset_id: string | null;
  sort_order: number;
  source: string;
  source_id: string;
  obtained_at: string;
}

export interface WorldArchiveItem {
  discovery_id: string;
  display_name: string;
  first_player_id: string;
  first_discovered_at: string;
  location: Record<string, unknown>;
  related_rule: string | null;
}

export interface PlayerRewardItem {
  player_reward_id: string;
  reward_id: string;
  reward_type: string;
  reward_name: string;
  payload: Record<string, unknown>;
  grant_mode: "AUTO" | "CLAIM";
  status: "PENDING_CLAIM" | "OWNED";
  source: string;
  source_id: string;
  granted_at: string;
  claimed_at: string | null;
}

export interface RewardInboxData {
  pending: PlayerRewardItem[];
  owned: PlayerRewardItem[];
}

export interface RewardClaimData {
  player_reward_id: string;
  reward_id: string;
  status: "OWNED";
  already_claimed: boolean;
}

export type LeaderboardType = "EXPLORE" | "CLEAR" | "COLLECT";
export type LeaderboardPeriod = "WEEKLY" | "MONTHLY";
export type LeaderboardScope = "TOP" | "AROUND" | "SELF";

export interface LeaderboardEntry {
  player_id: string;
  score: number;
  rank: number;
  snapshot_at: string;
  is_self: boolean;
}

export interface LeaderboardData {
  season_id: string;
  period_type: LeaderboardPeriod;
  start_at_utc: string;
  end_at_utc: string;
  board_type: LeaderboardType;
  scope: LeaderboardScope;
  entries: LeaderboardEntry[];
  my_rank: { rank: number; score: number } | null;
  is_snapshot: boolean;
}

export interface SettlementData {
  result_id: string;
  run_id?: string;
  level_id: string;
  result_status: "COMPLETED" | "FAILED";
  completion_time_ms: number;
  score_payload: Record<string, unknown>;
  unlocked_hidden_level_id?: string | null;
  idempotent_replay: boolean;
}
