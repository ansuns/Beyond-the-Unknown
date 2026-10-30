import { describe, expect, it, vi } from "vitest";
import { CharacterSelectionSession } from "../assets/scripts/player/character-selection-session";

describe("CharacterSelectionSession", () => {
  it("cycles only unlocked characters and wraps around", async () => {
    const api = {
      listCharacters: vi.fn().mockResolvedValue({
        current_character_id: "CHAR_A",
        characters: [
          { character_id: "CHAR_A", display_name: "A", is_unlocked: true },
          { character_id: "CHAR_LOCKED", display_name: "Locked", is_unlocked: false },
          { character_id: "CHAR_B", display_name: "B", is_unlocked: true },
          { character_id: "CHAR_C", display_name: "C", is_unlocked: true }
        ]
      }),
      selectCharacter: vi.fn(async (characterId: string) => ({
        success: true,
        current_character_id: characterId
      }))
    };
    const session = new CharacterSelectionSession(api as never);

    expect((await session.selectNext()).character_id).toBe("CHAR_B");
    expect((await session.selectNext()).character_id).toBe("CHAR_C");
    expect((await session.selectNext()).character_id).toBe("CHAR_A");
    expect(api.selectCharacter.mock.calls.map(([id]) => id)).toEqual([
      "CHAR_B",
      "CHAR_C",
      "CHAR_A"
    ]);
    expect(api.listCharacters).toHaveBeenCalledOnce();
  });

  it("does not update local selection when the server rejects the change", async () => {
    const api = {
      listCharacters: vi.fn().mockResolvedValue({
        current_character_id: "CHAR_A",
        characters: [
          { character_id: "CHAR_A", display_name: "A", is_unlocked: true },
          { character_id: "CHAR_B", display_name: "B", is_unlocked: true }
        ]
      }),
      selectCharacter: vi.fn().mockResolvedValue({
        success: false,
        current_character_id: "CHAR_A"
      })
    };
    const session = new CharacterSelectionSession(api as never);
    await session.load();

    await expect(session.selectNext()).rejects.toThrow("角色选择未被服务端确认");
    expect(session.currentCharacter()?.character_id).toBe("CHAR_A");
  });

  it("reports an empty unlocked catalog", async () => {
    const api = {
      listCharacters: vi.fn().mockResolvedValue({
        current_character_id: null,
        characters: [{ character_id: "CHAR_LOCKED", display_name: "Locked", is_unlocked: false }]
      }),
      selectCharacter: vi.fn()
    };
    const session = new CharacterSelectionSession(api as never);

    await expect(session.selectNext()).rejects.toThrow("没有已解锁的角色");
    expect(api.selectCharacter).not.toHaveBeenCalled();
  });
});
