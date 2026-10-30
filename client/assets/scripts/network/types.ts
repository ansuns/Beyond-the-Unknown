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
