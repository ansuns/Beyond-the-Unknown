import type { CharacterCatalogData, CharacterItem } from "../network/types";
import type { RestClient } from "../network/rest-client";

export class CharacterSelectionSession {
  private catalog?: CharacterCatalogData;

  constructor(private readonly api: RestClient) {}

  async load(): Promise<CharacterCatalogData> {
    this.catalog = await this.api.listCharacters();
    return this.catalog;
  }

  currentCharacter(): CharacterItem | undefined {
    return this.catalog?.characters.find(
      (character) => character.character_id === this.catalog?.current_character_id
    );
  }

  async selectNext(): Promise<CharacterItem> {
    const catalog = this.catalog ?? (await this.load());
    const unlocked = catalog.characters.filter((character) => character.is_unlocked);
    if (unlocked.length === 0) {
      throw new Error("没有已解锁的角色");
    }

    const currentIndex = unlocked.findIndex(
      (character) => character.character_id === catalog.current_character_id
    );
    const next = unlocked[(currentIndex + 1) % unlocked.length];
    const selection = await this.api.selectCharacter(next.character_id);
    if (!selection.success || selection.current_character_id !== next.character_id) {
      throw new Error("角色选择未被服务端确认");
    }

    this.catalog = {
      ...catalog,
      current_character_id: selection.current_character_id
    };
    return next;
  }
}
