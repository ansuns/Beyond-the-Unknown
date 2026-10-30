import type { ApiError } from "../network/rest-client";
import type { RestClient } from "../network/rest-client";
import type {
  CharacterCatalogData,
  CharacterSelectionData,
  LawRuleId,
  LevelCatalogData,
  LevelEnterData,
  LevelRunData,
  MapEnterData,
  PersonalLevelState,
  PlayerProfile,
  RuleCatalogData,
  RulePoint
} from "../network/types";
import type { MapEventHandler } from "../network/map-socket";
import type { LawController } from "./law-controller";
import type { MapSession } from "./map-session";
import type { PersonalLevelSession } from "./personal-level-session";

export interface WorldEntryData {
  map: MapEnterData;
  profile: PlayerProfile;
  characters: CharacterCatalogData;
}

export interface RoomEntryData {
  entry: LevelEnterData;
  run: LevelRunData;
  rules: RuleCatalogData;
  state: PersonalLevelState;
}

/**
 * Coordinates the already-tested transport/session modules for a Cocos scene.
 * It deliberately contains no engine objects or client-side game authority.
 */
export class WorldPlaySession {
  constructor(
    private readonly map: MapSession,
    private readonly api: RestClient,
    private readonly level: PersonalLevelSession,
    private readonly laws: LawController,
    private readonly createIdempotencyKey: () => string
  ) {}

  async enterWorld(
    onMapEvent: MapEventHandler,
    reconnect = false
  ): Promise<WorldEntryData> {
    const map = await this.map.enter(onMapEvent, reconnect);
    try {
      const [profile, characters] = await Promise.all([
        this.api.getPlayerProfile(),
        this.api.listCharacters()
      ]);
      return { map, profile, characters };
    } catch (error) {
      this.map.leave();
      throw error;
    }
  }

  listLevels(): Promise<LevelCatalogData> {
    return this.api.listLevels();
  }

  selectCharacter(characterId: string): Promise<CharacterSelectionData> {
    return this.api.selectCharacter(characterId);
  }

  async enterRoom(levelId: string, entranceId: string): Promise<RoomEntryData> {
    const { entry, run } = await this.level.enterAndStart(
      levelId,
      entranceId,
      this.createIdempotencyKey()
    );
    const [rules, state] = await Promise.all([
      this.laws.refreshCatalog(),
      this.laws.refreshState()
    ]);
    return { entry, run, rules, state };
  }

  castLaw(
    ruleId: LawRuleId,
    target: { targetId?: string; targetPoint?: RulePoint }
  ) {
    return this.laws.cast(ruleId, target, this.createIdempotencyKey());
  }

  maintainGazeIfDue() {
    return this.laws.maintainGazeIfDue();
  }

  refreshRoomState(): Promise<PersonalLevelState> {
    return this.laws.refreshState();
  }

  async abandonRoom(): Promise<LevelRunData> {
    if (this.laws.hasActiveGaze()) await this.laws.stopGaze();
    return this.level.abandon();
  }

  move(x: number, y: number, direction: string, clientTick: number): void {
    this.map.move(x, y, direction, clientTick);
  }

  action(actionId: string): void {
    this.map.action(actionId);
  }

  ping(): void {
    this.map.ping();
  }

  leaveWorld(): void {
    this.map.leave();
  }

  dispose(): void {
    this.map.dispose();
  }
}
