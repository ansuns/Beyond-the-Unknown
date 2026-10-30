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
