export interface LevelContentConfig {
  [key: string]: any;
  schema_version?: number;
  levels?: any[];
  hidden_routes?: any[];
}
export function validateLevelContentConfig(config: LevelContentConfig): string[];
