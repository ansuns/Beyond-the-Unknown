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
export type LawActionKind = "APPLY" | "RELEASE";

export interface LevelCatalogItem {
  level_id: string;
  level_name: string;
  entrance_id: string;
  room_index: number | null;
  target_duration_min: number;
  target_duration_max: number;
  required_laws: string[];
  necessary_objectives: string[];
  is_hidden: boolean;
  is_unlocked: boolean;
  config: Record<string, unknown>;
}

export interface LevelCatalogData {
  levels: LevelCatalogItem[];
}

export interface LevelRunData {
  run_id: string;
  level_id: string;
  status: "CREATED" | "RUNNING" | "COMPLETED" | "FAILED" | "ABANDONED";
  started_at?: string | null;
}

export interface PersonalMechanismState {
  mechanism_id: string;
  mechanism_type: string;
  state: Record<string, unknown>;
  updated_at: string;
}

export interface PersonalMechanismList {
  run_id: string;
  level_id: string;
  status: string;
  mechanisms: PersonalMechanismState[];
}

export interface LawActionData {
  run_id: string;
  mechanism_id: string;
  rule_id: LawRuleId;
  action: LawActionKind;
  state: Record<string, unknown>;
  combo_id: string | null;
  idempotent_replay: boolean;
}
