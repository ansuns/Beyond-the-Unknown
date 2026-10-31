// @ts-nocheck
// Loads the delivered P0 artwork and dresses the runtime prototype in it.
//
// The prototype draws everything with Graphics so it can run before any art
// exists. This module adds the real sprites on top without changing that
// drawing code: every helper takes a node the prototype already created and
// attaches a child, so a missing or malformed asset degrades to the placeholder
// instead of breaking the scene.
import {
  Color,
  ImageAsset,
  Layers,
  Node,
  Sprite,
  SpriteFrame,
  Texture2D,
  tween,
  UIOpacity,
  UITransform,
  Vec3,
  resources
} from "cc";

// Paths are relative to assets/resources and end in /spriteFrame, which is how
// Cocos addresses the sub-asset that a .png produces after import.
export const ART_PATHS = {
  background: "maps/MAP_MAIN_001/scene/MAP_MAIN_001_SCENE_01/spriteFrame",
  character: "characters/CHR_001/model/CHR_001_MODEL_IDLE_S_01/spriteFrame",
  portrait: "characters/CHR_001/portrait/CHR_001_PORTRAIT_FRONT_01/spriteFrame",
  mechanismInactive: "mechanisms/M01-LIGHT-01/M01-LIGHT-01_INACTIVE_01/spriteFrame",
  mechanismActive: "mechanisms/M01-LIGHT-01/M01-LIGHT-01_ACTIVE_01/spriteFrame",
  echoPulse: "effects/FX_ECHO_PULSE_01/spriteFrame"
} as const;

export type ArtKey = keyof typeof ART_PATHS;

export type ArtSet = {
  frames: Partial<Record<ArtKey, SpriteFrame>>;
  loaded: ArtKey[];
  missing: ArtKey[];
};

/** Sprites must live on the UI layer too, or they draw but never hit-test. */
function createUINode(name: string): Node {
  const node = new Node(name);
  node.layer = Layers.Enum.UI_2D;
  return node;
}

function loadFrame(path: string): Promise<SpriteFrame | null> {
  // The PNGs arrive as cc.ImageAsset because they were added to the project
  // outside the editor, so the importer never produced a spriteFrame sub-asset.
  // Building the frame from the image at runtime keeps the pipeline independent
  // of per-file import settings and produces the same result on web and in the
  // mini game.
  const imagePath = path.endsWith("/spriteFrame")
    ? path.slice(0, -"/spriteFrame".length)
    : path;
  return new Promise((resolve) => {
    resources.load(imagePath, ImageAsset, (error, image) => {
      if (error || !image) {
        // A missing image is not fatal: the prototype keeps its Graphics
        // placeholder, and the caller reports which keys never arrived.
        resolve(null);
        return;
      }
      try {
        const texture = new Texture2D();
        texture.image = image;
        // Artwork is not a multiple of four in every case, so it must not be
        // packed into the dynamic atlas.
        texture.setFilters(Texture2D.Filter.LINEAR, Texture2D.Filter.LINEAR);
        const frame = new SpriteFrame();
        frame.texture = texture;
        frame.packable = false;
        resolve(frame);
      } catch {
        resolve(null);
      }
    });
  });
}

export async function loadArtSet(): Promise<ArtSet> {
  const keys = Object.keys(ART_PATHS) as ArtKey[];
  const results = await Promise.all(keys.map((key) => loadFrame(ART_PATHS[key])));
  const frames: Partial<Record<ArtKey, SpriteFrame>> = {};
  const loaded: ArtKey[] = [];
  const missing: ArtKey[] = [];
  keys.forEach((key, index) => {
    const frame = results[index];
    if (frame) {
      frames[key] = frame;
      loaded.push(key);
    } else {
      missing.push(key);
    }
  });
  return { frames, loaded, missing };
}

export type SpriteOptions = {
  width: number;
  height?: number;
  /** Put the sprite's origin at the node's feet instead of its centre. */
  footAnchored?: boolean;
  opacity?: number;
};

/**
 * Create a child sprite of `parent` named `name`, or refresh the existing one.
 *
 * Idempotent so it can be called again when the room is redrawn: the prototype
 * destroys and rebuilds its children, and re-running this must not stack
 * duplicates.
 */
export function applySprite(
  parent: Node,
  name: string,
  frame: SpriteFrame | undefined,
  options: SpriteOptions
): Node | null {
  if (!frame || parent.getChildByName(name)) {
    const existing = parent.getChildByName(name);
    if (existing && frame) {
      const sprite = existing.getComponent(Sprite);
      if (sprite) sprite.spriteFrame = frame;
    }
    return existing;
  }
  const node = createUINode(name);
  parent.addChild(node);
  const height = options.height ?? options.width;
  const transform = node.addComponent(UITransform);
  transform.setAnchorPoint(0.5, options.footAnchored ? 0 : 0.5);
  const sprite = node.addComponent(Sprite);
  // Frame first, size second: assigning a frame re-applies the asset's own
  // dimensions, so a size written before it is silently overwritten.
  sprite.spriteFrame = frame;
  sprite.sizeMode = Sprite.SizeMode.CUSTOM;
  transform.setContentSize(options.width, height);
  // Graphics nodes have no alpha, so the sprite has to carry its own; without
  // this a faded effect would come back at full opacity on redraw.
  const opacity = node.addComponent(UIOpacity);
  opacity.opacity = options.opacity ?? 255;
  return node;
}

/** Background sprite spanning the room's playable area, behind everything. */
export function applyRoomBackground(
  room: Node,
  frame: SpriteFrame | undefined,
  size: { width: number; height: number; x?: number; y?: number }
): void {
  if (!frame) return;
  const existing = room.getChildByName("ArtBackground");
  if (existing) existing.destroy();
  const node = createUINode("ArtBackground");
  room.insertChild(node, 0);
  const transform = node.addComponent(UITransform);
  const sprite = node.addComponent(Sprite);
  sprite.spriteFrame = frame;
  sprite.sizeMode = Sprite.SizeMode.CUSTOM;
  transform.setContentSize(size.width, size.height);
  // The generated backdrop is roughly 3:2 and the room is wider than tall;
  // fill the room and let the edges crop rather than letterboxing a game map.
  sprite.type = Sprite.Type.SIMPLE;
  node.setPosition(size.x ?? 0, size.y ?? 0, 0);
}

/** Scale a sprite so it keeps the source aspect ratio inside a max box. */
export function fitWithin(
  frame: SpriteFrame,
  maxWidth: number,
  maxHeight: number
): { width: number; height: number } {
  const size = frame.originalSize ?? frame.getRect().size;
  const width = Math.max(1, size.width);
  const height = Math.max(1, size.height);
  const scale = Math.min(maxWidth / width, maxHeight / height);
  return { width: width * scale, height: height * scale };
}

/**
 * One-shot echo ring at a room-local position.
 *
 * Returns immediately; the node destroys itself when the tween ends so repeated
 * casts cannot accumulate invisible nodes.
 */
export function playEchoPulse(
  room: Node,
  frame: SpriteFrame | undefined,
  position: { x: number; y: number },
  size = 48
): void {
  if (!frame || !room.isValid) return;
  const node = createUINode("EchoPulse");
  room.addChild(node);
  node.setPosition(position.x, position.y, 0);
  node.addComponent(UITransform).setContentSize(size, size);
  const sprite = node.addComponent(Sprite);
  sprite.sizeMode = Sprite.SizeMode.CUSTOM;
  sprite.spriteFrame = frame;
  const opacity = node.addComponent(UIOpacity);
  opacity.opacity = 230;
  const target = new Vec3(1.9, 1.9, 1);
  node.setScale(new Vec3(0.45, 0.45, 1));
  tween(node)
    .to(0.45, { scale: target }, { easing: "quadOut" })
    .call(() => {
      if (node.isValid) node.destroy();
    })
    .start();
  tween(opacity).to(0.45, { opacity: 0 }).start();
}

export function tint(node: Node, color: Color): void {
  const sprite = node.getComponent(Sprite) ?? node.getComponentInChildren(Sprite);
  if (sprite) sprite.color = color;
}
