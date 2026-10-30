-- Beyond the Unknown | PostgreSQL initial schema
-- Migration: 0001_initial_schema
-- PostgreSQL 15+ recommended. All timestamptz values are UTC instants.
BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE schema_migrations (
  version varchar(100) PRIMARY KEY,
  applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TYPE player_status AS ENUM ('NORMAL','BANNED');
CREATE TYPE level_run_status AS ENUM ('CREATED','RUNNING','COMPLETED','FAILED','ABANDONED');
CREATE TYPE board_type AS ENUM ('EXPLORE','CLEAR','COLLECT');
CREATE TYPE season_type AS ENUM ('WEEKLY','MONTHLY');
CREATE TYPE season_status AS ENUM ('SCHEDULED','ACTIVE','CLOSED','SETTLING','SETTLED');
CREATE TYPE reward_type AS ENUM ('RT_APPEARANCE','RT_TITLE','RT_PET','RT_BADGE','RT_ACHIEVE');
CREATE TYPE grant_mode AS ENUM ('AUTO','CLAIM');
CREATE TYPE player_reward_status AS ENUM ('OWNED','PENDING_CLAIM');
CREATE TYPE achievement_status AS ENUM ('IN_PROGRESS','COMPLETED');
CREATE TYPE discovery_type AS ENUM ('DIS_HIDDEN_OBJ','DIS_HIDDEN_AREA','DIS_RULE_EFFECT','DIS_COMBO','DIS_PUZZLE','DIS_ENDING');
CREATE TYPE codex_category AS ENUM ('CAT_AREA','CAT_RULE','CAT_CREATURE','CAT_RELIC','CAT_ENDING');
CREATE TYPE collection_source AS ENUM ('DISCOVERY','SETTLEMENT','REWARD');
CREATE TYPE ad_reward_type AS ENUM ('APPEARANCE','HINT');

CREATE TABLE characters (
  character_id varchar(64) PRIMARY KEY,
  display_name varchar(100) NOT NULL,
  is_enabled boolean NOT NULL DEFAULT true,
  config jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE players (
  player_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  wx_openid varchar(128) UNIQUE NOT NULL,
  current_character_id varchar(64) REFERENCES characters(character_id),
  progress_version bigint NOT NULL DEFAULT 0 CHECK (progress_version >= 0),
  status player_status NOT NULL DEFAULT 'NORMAL',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE player_characters (
  player_id uuid NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
  character_id varchar(64) NOT NULL REFERENCES characters(character_id),
  unlocked_at timestamptz NOT NULL DEFAULT now(),
  source varchar(16) NOT NULL DEFAULT 'DEFAULT' CHECK (source IN ('DEFAULT','REWARD','EVENT')),
  PRIMARY KEY (player_id, character_id)
);

CREATE TABLE maps (
  map_id varchar(64) PRIMARY KEY,
  display_name varchar(120) NOT NULL,
  config jsonb NOT NULL DEFAULT '{}'::jsonb,
  is_enabled boolean NOT NULL DEFAULT true
);

CREATE TABLE map_instances (
  instance_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  map_id varchar(64) NOT NULL REFERENCES maps(map_id),
  shard_key varchar(100) NOT NULL,
  max_players integer NOT NULL CHECK (max_players > 0),
  current_players integer NOT NULL DEFAULT 0 CHECK (current_players >= 0),
  status varchar(16) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','DRAINING','CLOSED')),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_map_instances_map_status ON map_instances(map_id,status);

CREATE TABLE level_runs (
  run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id uuid NOT NULL REFERENCES players(player_id),
  level_id varchar(64) NOT NULL,
  instance_id uuid REFERENCES map_instances(instance_id),
  status level_run_status NOT NULL DEFAULT 'CREATED',
  started_at timestamptz,
  ended_at timestamptz,
  completion_time_ms bigint CHECK (completion_time_ms IS NULL OR completion_time_ms >= 0),
  result_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (run_id, player_id),
  CHECK (ended_at IS NULL OR started_at IS NULL OR ended_at >= started_at)
);
CREATE INDEX idx_level_runs_player_status ON level_runs(player_id,status);
CREATE INDEX idx_level_runs_player_created ON level_runs(player_id,created_at DESC);

CREATE TABLE mechanism_states (
  mechanism_state_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id uuid NOT NULL,
  player_id uuid NOT NULL,
  mechanism_config_id varchar(100) NOT NULL,
  mechanism_type varchar(64) NOT NULL,
  state jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_mechanism_run_owner FOREIGN KEY (run_id,player_id)
    REFERENCES level_runs(run_id,player_id) ON DELETE CASCADE,
  UNIQUE (run_id,mechanism_config_id)
);
CREATE INDEX idx_mechanism_states_run ON mechanism_states(run_id);

CREATE TABLE discovery_catalog (
  discovery_id varchar(100) PRIMARY KEY,
  discovery_type discovery_type NOT NULL,
  level_id varchar(64),
  location jsonb NOT NULL DEFAULT '{}'::jsonb,
  related_rule varchar(64),
  display_name varchar(160) NOT NULL,
  is_enabled boolean NOT NULL DEFAULT true
);

CREATE TABLE collection_catalog (
  collection_id varchar(100) PRIMARY KEY,
  codex_category codex_category NOT NULL,
  source_discovery_id varchar(100) REFERENCES discovery_catalog(discovery_id),
  display_name varchar(160) NOT NULL,
  description text NOT NULL DEFAULT '',
  asset_id varchar(160),
  sort_order integer NOT NULL DEFAULT 0,
  is_enabled boolean NOT NULL DEFAULT true
);

CREATE TABLE player_discoveries (
  player_id uuid NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
  discovery_id varchar(100) NOT NULL REFERENCES discovery_catalog(discovery_id),
  discovery_type discovery_type NOT NULL,
  level_id varchar(64),
  run_id uuid REFERENCES level_runs(run_id),
  location jsonb NOT NULL DEFAULT '{}'::jsonb,
  related_rule varchar(64),
  first_discovered_at timestamptz NOT NULL DEFAULT now(),
  trigger_count integer NOT NULL DEFAULT 1 CHECK (trigger_count > 0),
  PRIMARY KEY (player_id,discovery_id)
);
CREATE INDEX idx_player_discoveries_player_time ON player_discoveries(player_id,first_discovered_at DESC);

CREATE TABLE player_collections (
  player_id uuid NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
  collection_id varchar(100) NOT NULL REFERENCES collection_catalog(collection_id),
  codex_category codex_category NOT NULL,
  source collection_source NOT NULL,
  source_id varchar(128) NOT NULL,
  obtained_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (player_id,collection_id)
);

CREATE TABLE world_archive (
  discovery_id varchar(100) PRIMARY KEY REFERENCES discovery_catalog(discovery_id),
  first_player_id uuid NOT NULL REFERENCES players(player_id),
  first_discovered_at timestamptz NOT NULL,
  location jsonb NOT NULL,
  related_rule varchar(64),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_world_archive_first_time ON world_archive(first_discovered_at);

CREATE TABLE seasons (
  season_id varchar(64) PRIMARY KEY,
  season_type season_type NOT NULL,
  start_at_utc timestamptz NOT NULL,
  end_at_utc timestamptz NOT NULL,
  status season_status NOT NULL DEFAULT 'SCHEDULED',
  settlement_status varchar(16) NOT NULL DEFAULT 'PENDING' CHECK (settlement_status IN ('PENDING','REVIEW','APPROVED','FAILED')),
  settled_at_utc timestamptz,
  CHECK (end_at_utc > start_at_utc)
);
CREATE INDEX idx_seasons_type_range ON seasons(season_type,start_at_utc,end_at_utc);

CREATE TABLE score_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id uuid NOT NULL REFERENCES players(player_id),
  board_type board_type NOT NULL,
  period_id varchar(64) NOT NULL,
  delta bigint NOT NULL,
  reason varchar(32) NOT NULL CHECK (reason IN ('EXP_DISCOVER','CLEAR_STAGE','COLLECT_NEW','CORRECTION')),
  source_event_id varchar(128) NOT NULL,
  run_id uuid REFERENCES level_runs(run_id),
  idempotency_key varchar(200) NOT NULL,
  created_at_utc timestamptz NOT NULL DEFAULT now(),
  UNIQUE (board_type,period_id,idempotency_key)
);
CREATE INDEX idx_score_events_player_board_period_time
  ON score_events(player_id,board_type,period_id,created_at_utc);
CREATE INDEX idx_score_events_period_board ON score_events(period_id,board_type);

CREATE TABLE leaderboard_snapshots (
  season_id varchar(64) NOT NULL REFERENCES seasons(season_id),
  board_type board_type NOT NULL,
  player_id uuid NOT NULL REFERENCES players(player_id),
  score bigint NOT NULL,
  rank integer NOT NULL CHECK (rank > 0),
  snapshot_at_utc timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (season_id,board_type,player_id)
);
CREATE INDEX idx_leaderboard_rank ON leaderboard_snapshots(season_id,board_type,rank);

CREATE TABLE rewards (
  reward_id varchar(100) PRIMARY KEY,
  reward_type reward_type NOT NULL,
  reward_name varchar(160) NOT NULL,
  condition_ref varchar(160),
  grant_mode grant_mode NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  is_paid boolean NOT NULL DEFAULT false,
  is_enabled boolean NOT NULL DEFAULT true
);

CREATE TABLE player_rewards (
  player_reward_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id uuid NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
  reward_id varchar(100) NOT NULL REFERENCES rewards(reward_id),
  grant_mode grant_mode NOT NULL,
  status player_reward_status NOT NULL,
  source varchar(32) NOT NULL,
  source_id varchar(128) NOT NULL,
  idempotency_key varchar(200) NOT NULL,
  granted_at timestamptz NOT NULL DEFAULT now(),
  claimed_at timestamptz,
  UNIQUE(player_id,reward_id,source_id),
  UNIQUE(player_id,idempotency_key),
  CHECK ((status='PENDING_CLAIM' AND grant_mode='CLAIM' AND claimed_at IS NULL)
      OR (status='OWNED' AND (grant_mode='AUTO' OR claimed_at IS NOT NULL)))
);
CREATE INDEX idx_player_rewards_inbox ON player_rewards(player_id,status,granted_at DESC);

CREATE TABLE achievements (
  achievement_id varchar(100) PRIMARY KEY,
  name varchar(160) NOT NULL,
  condition_ref varchar(160) NOT NULL,
  progress_rule jsonb NOT NULL DEFAULT '{}'::jsonb,
  reward_id varchar(100) REFERENCES rewards(reward_id),
  is_enabled boolean NOT NULL DEFAULT false
);

CREATE TABLE player_achievements (
  player_id uuid NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
  achievement_id varchar(100) NOT NULL REFERENCES achievements(achievement_id),
  progress jsonb NOT NULL DEFAULT '{}'::jsonb,
  status achievement_status NOT NULL DEFAULT 'IN_PROGRESS',
  completed_at timestamptz,
  PRIMARY KEY(player_id,achievement_id),
  CHECK ((status='IN_PROGRESS' AND completed_at IS NULL) OR (status='COMPLETED' AND completed_at IS NOT NULL))
);

CREATE TABLE player_tasks (
  player_id uuid NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
  task_id varchar(100) NOT NULL,
  status varchar(24) NOT NULL,
  progress jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(player_id,task_id)
);

CREATE TABLE progress_snapshots (
  snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id uuid NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
  progress_version bigint NOT NULL CHECK (progress_version >= 0),
  completed_level_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  permanent_progress jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(player_id,progress_version)
);

CREATE TABLE settlements (
  result_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id uuid NOT NULL UNIQUE REFERENCES level_runs(run_id),
  player_id uuid NOT NULL REFERENCES players(player_id),
  level_id varchar(64) NOT NULL,
  result_status varchar(24) NOT NULL CHECK (result_status IN ('COMPLETED','FAILED')),
  completion_time_ms bigint CHECK (completion_time_ms IS NULL OR completion_time_ms >= 0),
  score_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  idempotency_key varchar(200) NOT NULL UNIQUE
);

ALTER TABLE level_runs ADD CONSTRAINT fk_level_runs_result
  FOREIGN KEY (result_id) REFERENCES settlements(result_id) DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE ad_reward_grants (
  ad_grant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id uuid NOT NULL REFERENCES players(player_id),
  placement_id varchar(100) NOT NULL,
  reward_type ad_reward_type NOT NULL,
  reward_value varchar(160) NOT NULL,
  is_value_bearing boolean NOT NULL DEFAULT false CHECK (is_value_bearing=false),
  provider_transaction_id varchar(200),
  granted_at timestamptz NOT NULL DEFAULT now(),
  idempotency_key varchar(200) NOT NULL UNIQUE
);
CREATE UNIQUE INDEX uq_ad_provider_transaction ON ad_reward_grants(provider_transaction_id)
  WHERE provider_transaction_id IS NOT NULL;

CREATE TABLE actions_log (
  action_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id uuid REFERENCES players(player_id),
  action_type varchar(64) NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  request_id varchar(128),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_actions_log_player_time ON actions_log(player_id,created_at DESC);

INSERT INTO schema_migrations(version) VALUES ('0001_initial_schema');
COMMIT;
