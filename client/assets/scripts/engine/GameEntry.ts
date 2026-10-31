// @ts-nocheck
// Cocos Creator 3.8.8 runtime entry point.
// Engine typings are supplied by the Cocos editor; the repository's Node/Vitest
// typecheck intentionally covers the engine-independent network/session layer.
import {
  _decorator,
  Camera,
  Canvas,
  Color,
  Component,
  Graphics,
  Label,
  Layers,
  Node,
  NodeEventType,
  UITransform,
  view
} from "cc";

import { RestClient } from "../network/rest-client";
import type { LawRuleId, MapServerEvent, PersonalLevelState } from "../network/types";
import { createWeChatFetch, createWeChatWebSocketFactory } from "../platform/wechat-network";
import {
  BrowserPlatform,
  createBrowserFetch,
  createBrowserWebSocketFactory,
  hasWeChatApi
} from "../platform/browser-platform";
import { WeChatPlatform } from "../platform/wechat-platform";
import { SessionStore } from "../player/session-store";
import { CharacterSelectionSession } from "../player/character-selection-session";
import { MapSession } from "../world/map-session";
import { PersonalLevelSession } from "../world/personal-level-session";
import { deriveRoom01VisualState } from "../world/room01-presentation";
import { selectNextPlayableLevel } from "../world/level-progression";
import { buildPrototypeRuleOptions } from "../world/prototype-rule-options";
import {
  parsePrototypeComboDefinitions,
  type PrototypeComboDefinition
} from "../world/prototype-combos";
import {
  calculatePrototypeRoomScale,
  getPrototypeRoomDimensions,
  parsePrototypeLayoutConfig,
  prototypeLevelToLocal,
  prototypeLocalToLevel,
  screenDirectionToLogicalDirection,
  sortIsometricDepth,
  type PrototypeLayoutConfig
} from "../world/prototype-layout";
import {
  getPrototypeMechanismShape,
  getPrototypeMechanismVisualState,
  type PrototypeMechanismShape
} from "../world/prototype-mechanism-visual";
import { LatestPositionSyncQueue } from "../world/latest-position-sync-queue";
import { getGazeLeaseRenewalInterval } from "../world/gaze-lease-timing";
import { formatProgressSummary } from "../ui/progress-summary";
import {
  applyRoomBackground,
  applySprite,
  fitWithin,
  loadArtSet,
  playEchoPulse,
  type ArtSet
} from "./art-assets";
import { assetService } from "./asset-service";

const { ccclass, property } = _decorator;

type Avatar = {
  player_id: string;
  x: number;
  y: number;
  direction?: string;
  character_id?: string;
};

@ccclass("BeyondTheUnknownGameEntry")
export class BeyondTheUnknownGameEntry extends Component {
  @property
  apiBaseUrl = "http://127.0.0.1:8000/api/v1";

  @property
  websocketBaseUrl = "ws://127.0.0.1:8000";

  private root?: Node;
  private worldRoot?: Node;
  private statusLabel?: Label;
  private rulesLabel?: Label;
  private progressLabel?: Label;
  private art?: ArtSet;
  private artReady = false;
  private mapSession?: MapSession;
  private characterSession?: CharacterSelectionSession;
  private currentCharacterId?: string;
  private levelSession?: PersonalLevelSession;
  private api?: RestClient;
  private sessionStore?: SessionStore;
  private localPlayerId?: string;
  private readonly avatars = new Map<string, Node>();
  private clientTick = 0;
  private currentMode: "MENU" | "WORLD" | "PERSONAL_LEVEL" = "MENU";
  private pendingLevelName = "";
  private pendingLevelId = "";
  private moveTarget?: { x: number; y: number };
  private moveSendElapsed = 0;
  private levelMoveSendElapsed = 0;
  private levelPosition = { x: 1, y: 4 };
  private levelAvatar?: Node;
  private prototypeDepthNodes: Node[] = [];
  private joystickRoot?: Node;
  private joystickKnob?: Node;
  private joystickActive = false;
  private joystickMagnitude = 0;
  private joystickScreenDirection = { x: 0, y: 0 };
  private readonly joystickRadius = 48;
  private lastMoveDirection = "S";
  private levelPositionSync?: LatestPositionSyncQueue;
  private readonly roomControlNodes: Node[] = [];
  private roomMechanismStates = new Map<string, Record<string, unknown>>();
  private roomMechanismCatalog = new Map<string, {
    mechanism_type: string;
    position_x: number | null;
    position_y: number | null;
    target_type: string | null;
    config: Record<string, unknown>;
  }>();
  private prototypeComboDefinitions: PrototypeComboDefinition[] = [];
  private prototypeLayout: PrototypeLayoutConfig = {
    bounds: { minX: 0, maxX: 12, minY: 0, maxY: 8 },
    spawn: { x: 1, y: 4 },
    movementSpeed: 3,
    interactionRadius: 1.5,
    positionSyncIntervalMs: 120
  };
  private prototypeGazeTargetId: string | undefined;
  private prototypeGazeLeaseTimeoutMs = 0;
  private prototypeGazeRenewalIntervalMs = 0;
  private prototypeGazeMaintainAt = 0;
  private prototypeGazeNextMaintainAt = 0;
  private prototypeGazeMaintainInFlight = false;
  private readonly prototypeRuleCooldownUntil = new Map<string, number>();
  private prototypeActionInFlight = false;
  private levelRoomScale = 40;
  private readonly worldPixelsPerUnit = 40;
  private readonly moveSpeedPixelsPerSecond = 160;
  private readonly moveSyncIntervalSeconds = 0.12;

  onLoad(): void {
    this.buildShell();
    void this.prepareArt();
  }

  /** Load the delivered P0 art, then dress whatever the prototype has drawn. */
  private async prepareArt(): Promise<void> {
    try {
      // The bundle must be in memory before any frame is requested; the
      // service handles timeout, retry and de-duplication.
      await assetService.ensureBundle("resources", {
        onProgress: (percent, note) =>
          this.setStatus(`${note} ${Math.round(percent * 100)}%`)
      });
    } catch (error) {
      this.setStatus(`资源加载失败：${error instanceof Error ? error.message : "未知错误"}`);
      return;
    }
    this.art = await loadArtSet((loaded, total) =>
      this.setStatus(`美术资源 ${loaded}/${total}`)
    );
    this.artReady = true;
    this.decorateScene();
    const missing = this.art.missing;
    if (missing.length) {
      // Visible on purpose: a placeholder is not delivery, and the status line
      // is where a tester sees which sprite never arrived.
      console.warn(`[art] missing sprite frames: ${missing.join(", ")}`);
    }
  }

  /**
   * Attach sprites to the nodes the prototype already built.
   *
   * Called after loading and after every room redraw, because the redraw wipes
   * the room's children. Placeholder Graphics are switched off only when the
   * matching sprite really loaded, so a missing asset leaves a usable scene.
   */
  private decorateScene(): void {
    if (!this.artReady || !this.art || !this.worldRoot) return;
    const frames = this.art.frames;

    const room = this.worldRoot.children.find(
      (child) =>
        child.name.startsWith("RoomPrototype-") || child.name === "Room01Prototype"
    );
    // The room is drawn in an isometric projection, so its playable area is a
    // diamond and a rectangular backdrop fitted to it would be a narrow strip.
    // The art goes full-bleed behind the viewport instead, and the diamond
    // outline reads as the walkable area drawn on top of it.
    const worldTransform = this.worldRoot.getComponent(UITransform);
    if (worldTransform) {
      applyRoomBackground(this.worldRoot, frames.background, {
        width: worldTransform.width,
        height: worldTransform.height
      });
    }

    if (room) {
      for (const marker of room.children) {
        const isMechanism = marker.name.startsWith("Mechanism-");
        const isLightMarker = marker.name === "LightMarker";
        if (!isMechanism && !isLightMarker) continue;
        const label = isLightMarker
          ? undefined
          : marker.getChildByName(`Label-${marker.name.slice("Mechanism-".length)}`);
        const status = label?.getComponent(Label)?.string ?? "";
        const active = status.includes("ACTIVE") || status.includes("TRIGGERED");
        const frame = active ? frames.mechanismActive : frames.mechanismInactive;
        const markerGraphics = marker.getComponent(Graphics);
        if (applySprite(marker, "ArtMechanism", frame, { width: 30, height: 30, footAnchored: true })) {
          if (markerGraphics) markerGraphics.enabled = false;
        }
      }
    }

    if (this.levelAvatar && frames.character) {
      const avatarGraphics = this.levelAvatar.getComponent(Graphics);
      const box = fitWithin(frames.character, 38, 56);
      if (
        applySprite(this.levelAvatar, "ArtCharacter", frames.character, {
          width: box.width,
          height: box.height,
          footAnchored: true
        })
      ) {
        if (avatarGraphics) avatarGraphics.enabled = false;
      }
    }

    for (const node of this.avatars.values()) {
      this.decorateAvatar(node);
    }
  }

  private decorateAvatar(node: Node): void {
    if (!this.art || !this.art.frames.character) return;
    const box = fitWithin(this.art.frames.character, 38, 60);
    const sprite = applySprite(node, "ArtCharacter", this.art.frames.character, {
      width: box.width,
      height: box.height,
      footAnchored: true
    });
    if (!sprite) return;
    sprite.setPosition(0, -12, 0);
    const graphics = node.getComponent(Graphics);
    if (graphics) graphics.enabled = false;
  }

  onDestroy(): void {
    this.stopJoystickMovement();
    this.mapSession?.dispose();
    this.mapSession = undefined;
  }

  update(deltaTime: number): void {
    if (this.currentMode === "PERSONAL_LEVEL") {
      this.updateJoystickMoveTarget();
      this.updatePrototypeGazeMaintain();
      this.updatePersonalLevelMovement(deltaTime);
      return;
    }
    if (this.currentMode === "WORLD") this.updateJoystickMoveTarget();
    if (
      this.currentMode !== "WORLD" ||
      !this.moveTarget ||
      !this.mapSession ||
      !this.localPlayerId
    ) return;

    const avatar = this.avatars.get(this.localPlayerId);
    if (!avatar) return;
    const current = avatar.position;
    const currentX = current.x / this.worldPixelsPerUnit;
    const currentY = current.y / this.worldPixelsPerUnit;
    const dx = this.moveTarget.x - currentX;
    const dy = this.moveTarget.y - currentY;
    const distance = Math.hypot(dx, dy);
    const speedUnits = this.moveSpeedPixelsPerSecond / this.worldPixelsPerUnit;
    const step = speedUnits * Math.max(0, deltaTime) * (this.joystickActive ? this.joystickMagnitude : 1);
    const reached = distance <= step || distance < 0.001;
    const nextX = reached ? this.moveTarget.x : currentX + (dx / distance) * step;
    const nextY = reached ? this.moveTarget.y : currentY + (dy / distance) * step;
    const direction =
      Math.abs(dx) > Math.abs(dy)
        ? (dx >= 0 ? "E" : "W")
        : (dy >= 0 ? "N" : "S");
    this.lastMoveDirection = direction;

    avatar.setPosition(
      nextX * this.worldPixelsPerUnit,
      nextY * this.worldPixelsPerUnit,
      0
    );
    this.moveSendElapsed += deltaTime;
    if (this.moveSendElapsed >= this.moveSyncIntervalSeconds || reached) {
      this.clientTick += 1;
      try {
        this.mapSession.move(nextX, nextY, direction, this.clientTick);
      } catch (error) {
        this.setStatus(`移动同步失败：${error instanceof Error ? error.message : "连接已断开"}`);
      }
      this.moveSendElapsed = 0;
    }
    if (reached) this.moveTarget = undefined;
  }

  /**
   * Create a runtime node on the UI layer.
   *
   * Cocos only dispatches pointer events to UI_2D nodes. A node left on the
   * default 3D layer still draws through the canvas camera, so the failure is
   * invisible: buttons and the joystick render perfectly and simply never react.
   */
  private uiNode(name: string): Node {
    const node = new Node(name);
    node.layer = Layers.Enum.UI_2D;
    return node;
  }

  /**
   * A 2D camera for the canvas.
   *
   * The scene ships a perspective 3D camera, which draws a DEFAULT-layer node
   * but not a UI_2D one, and UI input only reaches UI_2D nodes. The project
   * needs one camera that both renders and hit-tests the interface, so the
   * canvas gets its own orthographic camera and renders last.
   */
  private createUICamera(canvasNode: Node, size: { width: number; height: number }): Camera {
    const cameraNode = this.uiNode("UICamera");
    canvasNode.addChild(cameraNode);
    cameraNode.setPosition(0, 0, 1000);
    const camera = cameraNode.addComponent(Camera);
    camera.projection = Camera.ProjectionType.ORTHO;
    camera.orthoHeight = size.height / 2;
    camera.near = 1;
    camera.far = 2000;
    camera.clearFlags = Camera.ClearFlag.SOLID_COLOR;
    camera.clearColor = new Color(10, 18, 32, 255);
    camera.visibility = Layers.Enum.UI_2D;
    // Renders after the scene's 3D camera so its clear does not erase the UI.
    camera.priority = 1073741824;
    return camera;
  }

  private buildShell(): void {
    const size = view.getVisibleSize();
    const canvasNode = this.uiNode("RuntimeCanvas");
    this.node.addChild(canvasNode);
    canvasNode.addComponent(UITransform).setContentSize(size.width, size.height);
    const canvas = canvasNode.addComponent(Canvas);
    canvas.cameraComponent = this.createUICamera(canvasNode, size);
    canvas.alignCanvasWithScreen = true;

    this.root = this.uiNode("BeyondTheUnknownRuntime");
    canvasNode.addChild(this.root);

    const background = this.uiNode("Background");
    this.root.addChild(background);
    background.addComponent(UITransform).setContentSize(size.width, size.height);
    const bg = background.addComponent(Graphics);
    bg.fillColor = new Color(10, 18, 32, 255);
    bg.rect(-size.width / 2, -size.height / 2, size.width, size.height);
    bg.fill();

    this.createLabel("Title", "无界之外 · Beyond the Unknown", 0, size.height / 2 - 48, 30);
    this.statusLabel = this.createLabel(
      "Status",
      "测试原型：点击「登录并进入世界」连接微信沙盒与共享地图",
      0,
      size.height / 2 - 92,
      16
    );

    this.worldRoot = this.uiNode("WorldViewport");
    this.root.addChild(this.worldRoot);
    this.worldRoot.setPosition(0, -40, 0);
    const worldTransform = this.worldRoot.addComponent(UITransform);
    worldTransform.setContentSize(Math.min(size.width - 48, 760), Math.min(size.height - 250, 420));
    const worldGraphics = this.worldRoot.addComponent(Graphics);
    worldGraphics.lineWidth = 3;
    worldGraphics.strokeColor = new Color(72, 112, 144, 255);
    worldGraphics.fillColor = new Color(17, 34, 50, 255);
    worldGraphics.rect(
      -worldTransform.width / 2,
      -worldTransform.height / 2,
      worldTransform.width,
      worldTransform.height
    );
    worldGraphics.fill();
    worldGraphics.stroke();
    this.worldRoot.on(Node.EventType.TOUCH_END, this.onWorldTouch, this);

    this.createButton(
      "LoginButton",
      "登录并进入世界",
      -size.width / 2 + 130,
      -size.height / 2 + 62,
      210,
      54,
      () => this.loginAndEnterWorld()
    );
    this.createButton(
      "EnterLevelButton",
      "进入探索房间",
      0,
      -size.height / 2 + 62,
      190,
      54,
      () => this.enterFirstRoom()
    );
    this.createButton(
      "ReturnButton",
      "放弃并返回世界",
      size.width / 2 - 130,
      -size.height / 2 + 62,
      210,
      54,
      () => this.returnToWorld()
    );
    this.createButton(
      "ProgressButton",
      "我的进度",
      -size.width / 2 + 72,
      size.height / 2 - 145,
      110,
      44,
      () => this.refreshProgress()
    );
    this.createButton(
      "CharacterButton",
      "切换角色",
      0,
      size.height / 2 - 145,
      110,
      44,
      () => this.cycleCharacter()
    );
    this.createButton(
      "EmoteButton",
      "招呼",
      size.width / 2 - 72,
      size.height / 2 - 145,
      110,
      44,
      () => this.mapSession?.action("ACT_001")
    );
    this.progressLabel = this.createLabel(
      "ProgressSummary",
      "进度：登录后可查看",
      0,
      size.height / 2 - 190,
      13
    );

    this.rulesLabel = this.createLabel(
      "RulesStatus",
      "法则：尚未读取",
      0,
      -size.height / 2 + 126,
      14
    );
    this.createLabel(
      "Hint",
      "共享地图：点击地图移动；房间机关与法则数值在完成内容/数值配置后启用",
      0,
      -size.height / 2 + 18,
      13
    );
    this.createVirtualJoystick(size);
  }

  private createLabel(name: string, value: string, x: number, y: number, fontSize: number): Label {
    const node = this.uiNode(name);
    this.root!.addChild(node);
    node.setPosition(x, y, 0);
    node.addComponent(UITransform).setContentSize(900, fontSize + 16);
    const label = node.addComponent(Label);
    label.string = value;
    label.fontSize = fontSize;
    label.lineHeight = fontSize + 8;
    label.color = new Color(226, 237, 246, 255);
    label.horizontalAlign = Label.HorizontalAlign.CENTER;
    label.verticalAlign = Label.VerticalAlign.CENTER;
    return label;
  }

  private createButton(
    name: string,
    title: string,
    x: number,
    y: number,
    width: number,
    height: number,
    action: () => void | Promise<void>
  ): Node {
    const node = this.uiNode(name);
    this.root!.addChild(node);
    node.setPosition(x, y, 0);
    node.addComponent(UITransform).setContentSize(width, height);
    const graphics = node.addComponent(Graphics);
    graphics.fillColor = new Color(35, 93, 123, 255);
    graphics.rect(-width / 2, -height / 2, width, height);
    graphics.fill();
    // A node can only carry one renderable, and this one already draws its
    // background with Graphics. Putting the Label on the button node silently
    // fails ("Can't add renderable component"), which is why every button used
    // to show up as an empty blue rectangle.
    const labelNode = this.uiNode(`${name}Label`);
    node.addChild(labelNode);
    labelNode.addComponent(UITransform).setContentSize(width, height);
    const label = labelNode.addComponent(Label);
    label.string = title;
    label.fontSize = 17;
    label.lineHeight = 23;
    label.color = Color.WHITE;
    label.horizontalAlign = Label.HorizontalAlign.CENTER;
    label.verticalAlign = Label.VerticalAlign.CENTER;
    node.on(NodeEventType.TOUCH_END, () => {
      void action();
    }, this);
    return node;
  }

  private createVirtualJoystick(size: { width: number; height: number }): void {
    const root = this.uiNode("VirtualJoystick");
    this.root!.addChild(root);
    root.setPosition(-size.width / 2 + 88, -size.height / 2 + 160, 0);
    root.addComponent(UITransform).setContentSize(144, 144);

    const ring = root.addComponent(Graphics);
    ring.lineWidth = 3;
    ring.strokeColor = new Color(150, 190, 210, 180);
    ring.circle(0, 0, 56);
    ring.stroke();

    const knob = this.uiNode("VirtualJoystickKnob");
    root.addChild(knob);
    knob.addComponent(UITransform).setContentSize(48, 48);
    const knobGraphics = knob.addComponent(Graphics);
    knobGraphics.fillColor = new Color(75, 145, 180, 230);
    knobGraphics.strokeColor = new Color(190, 225, 240, 255);
    knobGraphics.lineWidth = 2;
    knobGraphics.circle(0, 0, 22);
    knobGraphics.fill();
    knobGraphics.stroke();

    this.joystickRoot = root;
    this.joystickKnob = knob;
    root.active = false;
    root.on(NodeEventType.TOUCH_START, this.onJoystickStart, this);
    root.on(NodeEventType.TOUCH_MOVE, this.onJoystickMove, this);
    root.on(NodeEventType.TOUCH_END, this.onJoystickEnd, this);
    root.on(NodeEventType.TOUCH_CANCEL, this.onJoystickEnd, this);
  }

  private updateJoystickVisibility(): void {
    const visible = this.currentMode === "WORLD" || this.currentMode === "PERSONAL_LEVEL";
    if (this.joystickRoot) this.joystickRoot.active = visible;
    if (!visible) this.stopJoystickMovement();
  }

  private stopJoystickMovement(): void {
    this.joystickActive = false;
    this.joystickMagnitude = 0;
    this.joystickScreenDirection = { x: 0, y: 0 };
    this.moveTarget = undefined;
    this.joystickKnob?.setPosition(0, 0, 0);
  }

  private onJoystickStart(event: any): void {
    if (this.prototypeActionInFlight ||
        (this.currentMode !== "WORLD" && this.currentMode !== "PERSONAL_LEVEL")) return;
    this.joystickActive = true;
    this.moveTarget = undefined;
    this.updateJoystickFromEvent(event);
  }

  private onJoystickMove(event: any): void {
    if (!this.joystickActive) return;
    this.updateJoystickFromEvent(event);
  }

  private onJoystickEnd(): void {
    const wasActive = this.joystickActive;
    const mode = this.currentMode;
    this.stopJoystickMovement();
    if (!wasActive) return;

    if (mode === "PERSONAL_LEVEL" && this.levelPositionSync) {
      void this.levelPositionSync.flush({ ...this.levelPosition }).catch((error) => {
        this.setStatus(`摇杆位置同步失败：${error instanceof Error ? error.message : "网络错误"}`);
      });
      return;
    }

    if (mode === "WORLD" && this.mapSession && this.localPlayerId) {
      const avatar = this.avatars.get(this.localPlayerId);
      if (!avatar) return;
      this.clientTick += 1;
      this.moveSendElapsed = 0;
      try {
        this.mapSession.move(
          avatar.position.x / this.worldPixelsPerUnit,
          avatar.position.y / this.worldPixelsPerUnit,
          this.lastMoveDirection,
          this.clientTick
        );
      } catch (error) {
        this.setStatus(`摇杆位置同步失败：${error instanceof Error ? error.message : "连接已断开"}`);
      }
    }
  }

  private updateJoystickFromEvent(event: any): void {
    if (!this.joystickRoot) return;
    const location = event.getUILocation();
    const visible = view.getVisibleSize();
    const localX = location.x - visible.width / 2 - this.joystickRoot.position.x;
    const localY = location.y - visible.height / 2 - this.joystickRoot.position.y;
    const distance = Math.hypot(localX, localY);
    if (distance < 8) {
      this.joystickMagnitude = 0;
      this.joystickScreenDirection = { x: 0, y: 0 };
      this.joystickKnob?.setPosition(0, 0, 0);
      return;
    }

    const magnitude = Math.min(1, distance / this.joystickRadius);
    const direction = { x: localX / distance, y: localY / distance };
    const knobDistance = magnitude * this.joystickRadius;
    this.joystickMagnitude = magnitude;
    this.joystickScreenDirection = direction;
    this.joystickKnob?.setPosition(
      direction.x * knobDistance,
      direction.y * knobDistance,
      0
    );
  }

  private updateJoystickMoveTarget(): void {
    if (!this.joystickActive || this.prototypeActionInFlight) return;
    if (this.joystickMagnitude < 0.12) {
      this.moveTarget = undefined;
      return;
    }

    const direction = this.currentMode === "PERSONAL_LEVEL"
      ? screenDirectionToLogicalDirection(this.joystickScreenDirection)
      : this.joystickScreenDirection;
    const lookAhead = 10;

    if (this.currentMode === "PERSONAL_LEVEL") {
      const bounds = this.prototypeLayout.bounds;
      this.moveTarget = {
        x: Math.max(bounds.minX, Math.min(bounds.maxX, this.levelPosition.x + direction.x * lookAhead)),
        y: Math.max(bounds.minY, Math.min(bounds.maxY, this.levelPosition.y + direction.y * lookAhead))
      };
      return;
    }

    const avatar = this.localPlayerId ? this.avatars.get(this.localPlayerId) : undefined;
    const transform = this.worldRoot?.getComponent(UITransform);
    if (!avatar || !transform) return;
    const currentX = avatar.position.x / this.worldPixelsPerUnit;
    const currentY = avatar.position.y / this.worldPixelsPerUnit;
    const margin = 20;
    const minX = (-transform.width / 2 + margin) / this.worldPixelsPerUnit;
    const maxX = (transform.width / 2 - margin) / this.worldPixelsPerUnit;
    const minY = (-transform.height / 2 + margin) / this.worldPixelsPerUnit;
    const maxY = (transform.height / 2 - margin) / this.worldPixelsPerUnit;
    this.moveTarget = {
      x: Math.max(minX, Math.min(maxX, currentX + direction.x * lookAhead)),
      y: Math.max(minY, Math.min(maxY, currentY + direction.y * lookAhead))
    };
  }


  private setStatus(message: string): void {
    if (this.statusLabel) this.statusLabel.string = message;
  }

  private makeIdempotencyKey(prefix: string): string {
    return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  }

  private async createApi(): Promise<void> {
    const wxApi = (globalThis as any).wx;
    const wechatReady = Boolean(wxApi?.login && wxApi?.request && wxApi?.connectSocket);
    if (!wechatReady && !hasWeChatApi()) {
      // Browser preview: same code paths, fetch/WebSocket adapters instead of
      // wx.*. The mini game build always takes the branch above.
      this.sessionStore = new SessionStore();
      this.api = new RestClient({
        baseUrl: this.apiBaseUrl,
        token: () => this.sessionStore?.accessToken(),
        fetchImpl: createBrowserFetch()
      });
      return;
    }
    if (!wechatReady) {
      throw new Error("当前环境没有完整的微信小游戏 wx API，请在微信开发者工具中运行");
    }
    this.sessionStore = new SessionStore();
    this.api = new RestClient({
      baseUrl: this.apiBaseUrl,
      token: () => this.sessionStore?.accessToken(),
      fetchImpl: createWeChatFetch(wxApi)
    });
  }

  private async loginAndEnterWorld(): Promise<void> {
    this.stopJoystickMovement();
    try {
      this.clearRoomControls();
      this.worldRoot?.removeAllChildren();
      this.clearAvatars();
      this.moveTarget = undefined;
      this.rulesLabel && (this.rulesLabel.string = "法则：尚未读取");
      this.setStatus("正在请求微信登录码并连接共享地图…");
      await this.createApi();
      const wxApi = (globalThis as any).wx;
      const wechatReady = Boolean(wxApi?.login && wxApi?.request && wxApi?.connectSocket);
      const platform = wechatReady ? new WeChatPlatform(wxApi) : new BrowserPlatform();
      this.mapSession = new MapSession(platform, this.api!, this.sessionStore!, {
        websocketBaseUrl: this.websocketBaseUrl,
        socketFactory: wechatReady
          ? createWeChatWebSocketFactory(wxApi)
          : createBrowserWebSocketFactory()
      });
      const map = await this.mapSession.enter((event) => this.onMapEvent(event));
      this.localPlayerId = this.sessionStore!.playerId();
      this.characterSession = new CharacterSelectionSession(this.api!);
      try {
        const characterCatalog = await this.characterSession.load();
        this.currentCharacterId = characterCatalog.current_character_id ?? undefined;
      } catch {
        this.currentCharacterId = undefined;
      }
      this.currentMode = "WORLD";
      this.updateJoystickVisibility();
      this.decorateScene();
      this.upsertAvatar({
        player_id: this.localPlayerId!,
        x: map.spawn_position.x,
        y: map.spawn_position.y,
        direction: map.spawn_position.direction,
        character_id: this.currentCharacterId
      }, true);
      this.setStatus(
        `已进入共享世界 · 在线实例 ${map.current_players}/${map.max_players} · ${map.instance_id.slice(0, 8)}`
      );
    } catch (error) {
      this.setStatus(`连接失败：${error instanceof Error ? error.message : "未知错误"}`);
    }
  }

  private async refreshProgress(): Promise<void> {
    if (!this.api || !this.progressLabel) {
      this.setStatus("请先登录并进入共享世界");
      return;
    }

    this.setStatus("正在读取玩家进度…");
    try {
      const progress = await this.api.getPlayerProgress();
      const [discoveries, collections, rewards, archive, leaderboard] = await Promise.all([
        this.api.listPlayerDiscoveries().catch(() => undefined),
        this.api.listPlayerCollections().catch(() => undefined),
        this.api.listRewards().catch(() => undefined),
        this.api.listWorldArchive().catch(() => undefined),
        this.api.getLeaderboard("EXPLORE", "WEEKLY", "SELF").catch(() => undefined)
      ]);
      this.progressLabel.string = formatProgressSummary({
        completedLevels: progress.completed_level_ids.length,
        discoveries: discoveries?.discoveries.length,
        collections: collections?.collections.length,
        pendingRewards: rewards?.pending.length,
        worldArchiveRecords: archive?.records.length,
        weeklyExploreRank: leaderboard
          ? (leaderboard.my_rank?.rank ?? null)
          : undefined
      });
      this.setStatus(`进度已刷新 · 版本 ${progress.progress_version}`);
    } catch (error) {
      this.setStatus(`进度读取失败：${error instanceof Error ? error.message : "网络错误"}`);
    }
  }

  private async cycleCharacter(): Promise<void> {
    if (this.currentMode !== "WORLD" || !this.characterSession) {
      this.setStatus("请先进入共享世界，再切换角色");
      return;
    }

    try {
      const character = await this.characterSession.selectNext();
      this.currentCharacterId = character.character_id;
      if (this.localPlayerId) {
        const avatar = this.avatars.get(this.localPlayerId);
        if (avatar) {
          this.upsertAvatar({
            player_id: this.localPlayerId,
            x: avatar.position.x / this.worldPixelsPerUnit,
            y: avatar.position.y / this.worldPixelsPerUnit,
            character_id: character.character_id
          }, true);
        }
      }
      this.setStatus(`已切换角色：${character.display_name}`);
    } catch (error) {
      this.setStatus(`角色切换失败：${error instanceof Error ? error.message : "请稍后重试"}`);
    }
  }

  private onMapEvent(event: MapServerEvent): void {
    const payload = event.payload as Record<string, any>;
    if (event.cmd === "ENTER") {
      const players = Array.isArray(payload.players) ? payload.players : [];
      for (const player of players) this.upsertAvatar(player as Avatar);
    } else if (event.cmd === "MOVE_SYNC" && payload.player) {
      this.upsertAvatar(payload.player as Avatar);
    } else if (event.cmd === "LEAVE" && typeof payload.player_id === "string") {
      this.removeAvatar(payload.player_id);
    } else if (event.cmd === "ACTION_BROADCAST") {
      this.setStatus(`玩家 ${String(payload.player_id ?? "").slice(0, 8)} 向你打了个招呼`);
    } else if (event.cmd === "ERROR") {
      this.setStatus(`网络提示：${String(payload.code ?? "UNKNOWN")}`);
    }
  }

  private upsertAvatar(avatar: Avatar, local = false): void {
    if (!this.worldRoot || !avatar.player_id) return;
    let node = this.avatars.get(avatar.player_id);
    if (!node) {
      node = this.uiNode(local ? "LocalPlayer" : `RemotePlayer-${avatar.player_id.slice(0, 8)}`);
      this.worldRoot.addChild(node);
      node.addComponent(UITransform).setContentSize(34, 34);
      node.addComponent(Graphics);
      const labelNode = this.uiNode("PlayerLabel");
      node.addChild(labelNode);
      labelNode.setPosition(0, -27, 0);
      labelNode.addComponent(UITransform).setContentSize(110, 22);
      const label = labelNode.addComponent(Label);
      label.fontSize = 11;
      label.lineHeight = 14;
      label.color = Color.WHITE;
      label.horizontalAlign = Label.HorizontalAlign.CENTER;
      this.avatars.set(avatar.player_id, node);
    }
    const palette = [
      new Color(112, 220, 255, 255),
      new Color(255, 190, 105, 255),
      new Color(177, 150, 255, 255),
      new Color(122, 220, 174, 255),
      new Color(255, 130, 155, 255),
      new Color(235, 214, 116, 255),
      new Color(105, 185, 220, 255),
      new Color(216, 150, 110, 255),
      new Color(153, 196, 125, 255),
      new Color(205, 145, 220, 255),
      new Color(120, 205, 205, 255),
      new Color(230, 160, 190, 255)
    ];
    const seed = [...(avatar.character_id ?? avatar.player_id)].reduce(
      (sum, char) => sum + char.charCodeAt(0),
      0
    );
    const graphics = node.getComponent(Graphics);
    graphics.clear();
    graphics.fillColor = palette[seed % palette.length];
    graphics.circle(0, 0, 15);
    graphics.fill();
    const label = node.getChildByName("PlayerLabel")?.getComponent(Label);
    if (label) label.string = local ? "我" : (avatar.character_id ?? avatar.player_id).slice(0, 6);
    this.decorateAvatar(node);
    node.setPosition(avatar.x * this.worldPixelsPerUnit, avatar.y * this.worldPixelsPerUnit, 0);
  }

  private removeAvatar(playerId: string): void {
    const node = this.avatars.get(playerId);
    if (node) node.destroy();
    this.avatars.delete(playerId);
  }

  private onWorldTouch(event: any): void {
    if (!this.worldRoot) return;
    const transform = this.worldRoot.getComponent(UITransform);
    const uiPoint = event.getUILocation();
    const visible = view.getVisibleSize();
    const localX = uiPoint.x - visible.width / 2 - this.worldRoot.position.x;
    const localY = uiPoint.y - visible.height / 2 - this.worldRoot.position.y;
    if (this.currentMode === "PERSONAL_LEVEL") {
      this.moveTarget = this.prototypeLocalToLevel(localX, localY);
      return;
    }
    if (this.currentMode !== "WORLD" || !this.mapSession) return;
    const margin = 20;
    const x = Math.max(
      (-transform.width / 2 + margin) / this.worldPixelsPerUnit,
      Math.min((transform.width / 2 - margin) / this.worldPixelsPerUnit, localX / this.worldPixelsPerUnit)
    );
    const y = Math.max(
      (-transform.height / 2 + margin) / this.worldPixelsPerUnit,
      Math.min((transform.height / 2 - margin) / this.worldPixelsPerUnit, localY / this.worldPixelsPerUnit)
    );
    this.moveTarget = { x, y };
  }

  private updatePrototypeGazeMaintain(): void {
    const session = this.levelSession;
    const targetId = this.prototypeGazeTargetId;
    if (!session || !targetId || this.prototypeGazeMaintainInFlight || this.prototypeActionInFlight) return;

    if (this.prototypeGazeLeaseTimeoutMs <= 0 || this.prototypeGazeRenewalIntervalMs <= 0) {
      this.prototypeGazeTargetId = undefined;
      this.prototypeGazeMaintainAt = 0;
      this.prototypeGazeNextMaintainAt = 0;
      void session.stopGaze().catch(() => undefined);
      this.setStatus("注视租约配置无效，已停止持续注视");
      return;
    }

    const now = Date.now();
    if (now >= this.prototypeGazeMaintainAt) {
      this.prototypeGazeTargetId = undefined;
      this.prototypeGazeMaintainAt = 0;
      this.prototypeGazeNextMaintainAt = 0;
      void session.stopGaze().catch((error) => {
        this.setStatus(`注视效果结束同步失败：${error instanceof Error ? error.message : "网络错误"}`);
      });
      return;
    }

    if (now < this.prototypeGazeNextMaintainAt) return;
    this.prototypeGazeNextMaintainAt = now + this.prototypeGazeRenewalIntervalMs;
    this.prototypeGazeMaintainInFlight = true;
    void session.maintainGaze(targetId)
      .then(() => {
        if (this.levelSession === session && this.prototypeGazeTargetId === targetId) {
          this.prototypeGazeMaintainAt = Date.now() + this.prototypeGazeLeaseTimeoutMs;
        }
      })
      .catch((error) => {
        this.setStatus(`注视维持失败：${error instanceof Error ? error.message : "网络错误"}`);
        this.prototypeGazeTargetId = undefined;
        this.prototypeGazeMaintainAt = 0;
        this.prototypeGazeNextMaintainAt = 0;
        void session.stopGaze().catch(() => undefined);
      })
      .finally(() => {
        this.prototypeGazeMaintainInFlight = false;
      });
  }

  private updatePersonalLevelMovement(deltaTime: number): void {
    if (!this.moveTarget || !this.levelAvatar || !this.levelSession) return;
    const dx = this.moveTarget.x - this.levelPosition.x;
    const dy = this.moveTarget.y - this.levelPosition.y;
    const distance = Math.hypot(dx, dy);
    const step = this.prototypeLayout.movementSpeed * Math.max(0, deltaTime) * (this.joystickActive ? this.joystickMagnitude : 1);
    const reached = distance <= step || distance < 0.001;
    this.levelPosition = reached
      ? { ...this.moveTarget }
      : { x: this.levelPosition.x + dx / distance * step, y: this.levelPosition.y + dy / distance * step };
    const avatarPosition = this.prototypeLevelToLocal(this.levelPosition.x, this.levelPosition.y);
    this.levelAvatar.setPosition(avatarPosition.x, avatarPosition.y, 0);
    this.sortPrototypeDepth();
    this.levelMoveSendElapsed += deltaTime;
    if (
      this.levelMoveSendElapsed >= this.prototypeLayout.positionSyncIntervalMs / 1000 ||
      reached
    ) {
      this.sendLevelPosition({ ...this.levelPosition });
      this.levelMoveSendElapsed = 0;
    }
    if (reached) this.moveTarget = undefined;
  }

  private async castRoomEcho(): Promise<void> {
    if (!this.levelSession || this.prototypeActionInFlight) return;
    this.prototypeActionInFlight = true;
    this.stopJoystickMovement();
    try {
      await this.flushLevelPosition();
      const hiddenTarget = this.roomMechanismCatalog.get("M01-HIDEABLE-01");
      if (hiddenTarget?.position_x === null || hiddenTarget?.position_y === null || !hiddenTarget) {
        throw new Error("服务端未提供隐藏目标的有效坐标");
      }
      const result = await this.levelSession.castRule(
        "RULE_ECHO",
        buildPrototypeRuleOptions("RULE_ECHO", "M01-HIDEABLE-01", hiddenTarget),
        this.makeIdempotencyKey("room01-echo")
      );
      const state = await this.levelSession.refreshState();
      this.applyRoomMechanismStates(state);
      this.drawPersonalRoom(this.pendingLevelName);
      if (result.effects.length && this.worldRoot) {
        const room = this.worldRoot.children.find(
          (child) => child.name.startsWith("RoomPrototype-") || child.name === "Room01Prototype"
        );
        const target = this.prototypeLevelToLocal(
          hiddenTarget.position_x,
          hiddenTarget.position_y
        );
        if (room) playEchoPulse(room, this.art?.frames.echoPulse, target, 52);
      }
      this.setStatus(result.effects.length ? "回声扩散：隐藏的符号显现了" : "回声没有回应");
    } catch (error) {
      this.setStatus(`回声失败：${error instanceof Error ? error.message : "请稍后重试"}`);
    } finally {
      this.prototypeActionInFlight = false;
    }
  }

  private async castPrototypeCombo(
    definition: PrototypeComboDefinition
  ): Promise<void> {
    if (!this.levelSession || this.prototypeActionInFlight) return;
    const { comboId, targetId, ruleIds } = definition;
    if (definition.maintainGaze && this.prototypeGazeRenewalIntervalMs <= 0) {
      this.setStatus("服务端未提供有效的注视租约配置，已阻止施放持续注视组合");
      return;
    }
    this.prototypeActionInFlight = true;
    this.stopJoystickMovement();
    try {
      await this.flushLevelPosition();
      let matched = false;
      for (const ruleId of ruleIds) {
        const waitMs = (this.prototypeRuleCooldownUntil.get(ruleId) ?? 0) - Date.now();
        if (waitMs > 0) {
          await new Promise<void>((resolve) => setTimeout(resolve, waitMs));
        }
        const result = await this.levelSession.castRule(
          ruleId,
          buildPrototypeRuleOptions(
            ruleId,
            targetId,
            this.roomMechanismCatalog.get(targetId)
          ),
          this.makeIdempotencyKey(`prototype-${comboId}-${ruleId}`)
        );
        const cooldownUntil = Date.parse(result.cooldown_until);
        this.prototypeRuleCooldownUntil.set(
          ruleId,
          Number.isFinite(cooldownUntil) ? cooldownUntil : Date.now() + 1200
        );
        if (result.combo?.combo_id === comboId) matched = true;
      }
      if (ruleIds.includes("RULE_GAZE")) {
        if (matched && definition.maintainGaze) {
          this.prototypeGazeTargetId = targetId;
          this.prototypeGazeMaintainAt = Date.now() + this.prototypeGazeLeaseTimeoutMs;
          this.prototypeGazeNextMaintainAt = Date.now() + this.prototypeGazeRenewalIntervalMs;
        } else {
          await this.levelSession.stopGaze();
          this.prototypeGazeTargetId = undefined;
          this.prototypeGazeMaintainAt = 0;
          this.prototypeGazeNextMaintainAt = 0;
        }
      }
      const state = await this.levelSession.refreshState();
      this.applyRoomMechanismStates(state);
      this.drawPersonalRoom(this.pendingLevelName);
      this.setStatus(
        matched
          ? `${comboId} 已触发，目标机关状态已同步`
          : `${comboId} 的法则已施放；组合未匹配，请检查顺序、冷却和目标`
      );
    } catch (error) {
      this.setStatus(`组合施放失败：${error instanceof Error ? error.message : "请稍后重试"}`);
    } finally {
      this.prototypeActionInFlight = false;
    }
  }

  private async settlePrototypeRoom(): Promise<void> {
    if (!this.levelSession || this.prototypeActionInFlight) return;
    this.prototypeActionInFlight = true;
    this.stopJoystickMovement();
    try {
      await this.flushLevelPosition();
      // Do not stop GAZE before settlement: stop_gaze intentionally resets
      // gaze-only mechanism state. Completing the run ends the effect safely.
      const result = await this.levelSession.settle(
        this.makeIdempotencyKey(`prototype-settle-${this.pendingLevelId}`)
      );
      this.levelSession = undefined;
      this.levelPositionSync = undefined;
      this.prototypeGazeTargetId = undefined;
      this.prototypeGazeLeaseTimeoutMs = 0;
      this.prototypeGazeRenewalIntervalMs = 0;
      this.prototypeGazeMaintainAt = 0;
      this.prototypeGazeNextMaintainAt = 0;
      this.currentMode = "MENU";
      this.updateJoystickVisibility();
      this.stopJoystickMovement();
      this.drawPersonalRoom("探索完成", true);
      const unlockMessage = result.unlocked_hidden_level_id
        ? ` · 隐藏结局已解锁（${result.unlocked_hidden_level_id}），返回后可进入`
        : "";
      this.setStatus(
        result.result_status === "COMPLETED"
          ? `${this.pendingLevelId} 完成 · 用时 ${Math.round(result.completion_time_ms / 1000)} 秒${unlockMessage}`
          : `${this.pendingLevelId} 未完成 · ${result.result_status}`
      );
    } catch (error) {
      this.setStatus(`暂不能结算：${error instanceof Error ? error.message : "必要目标尚未完成"}`);
    } finally {
      this.prototypeActionInFlight = false;
    }
  }

  private async interactHiddenEnding(): Promise<void> {
    if (!this.levelSession || this.prototypeActionInFlight) return;
    this.prototypeActionInFlight = true;
    this.stopJoystickMovement();
    try {
      await this.flushLevelPosition();
      const result = await this.levelSession.interact(
        "H01-END",
        this.makeIdempotencyKey("hidden-ending-interact")
      );
      this.roomMechanismStates.set(result.mechanism_id, result.state);
      this.applyRoomMechanismStates(await this.levelSession.refreshState());
      if (result.state.status === "TRIGGERED") {
        this.prototypeActionInFlight = false;
        await this.settlePrototypeRoom();
      } else {
        this.drawPersonalRoom(this.pendingLevelName);
        this.setStatus("结局核心尚未完成");
      }
    } catch (error) {
      this.setStatus(`结局核心交互失败：${error instanceof Error ? error.message : "请靠近机关后重试"}`);
    } finally {
      this.prototypeActionInFlight = false;
    }
  }

  private async interactRoomExit(): Promise<void> {
    if (!this.levelSession || this.prototypeActionInFlight) return;
    this.prototypeActionInFlight = true;
    this.stopJoystickMovement();
    try {
      await this.flushLevelPosition();
      const result = await this.levelSession.interact(
        "M01-EXIT-01",
        this.makeIdempotencyKey("room01-exit")
      );
      this.roomMechanismStates.set(result.mechanism_id, result.state);
      if (result.state.status === "TRIGGERED") {
        const settled = await this.levelSession.settle(this.makeIdempotencyKey("room01-settle"));
        this.currentMode = "MENU";
        this.updateJoystickVisibility();
        this.levelSession = undefined;
        this.levelPositionSync = undefined;
        this.drawPersonalRoom("探索完成", true);
        this.setStatus(`探索完成 · 用时 ${Math.round(settled.completion_time_ms / 1000)} 秒`);
      }
    } catch (error) {
      this.setStatus(`出口尚未开启或距离不足：${error instanceof Error ? error.message : "请继续探索"}`);
    } finally {
      this.prototypeActionInFlight = false;
    }
  }

  private async enterFirstRoom(): Promise<void> {
    if (this.prototypeActionInFlight) return;
    this.prototypeActionInFlight = true;
    this.stopJoystickMovement();
    try {
        if (this.currentMode === "PERSONAL_LEVEL" && this.levelSession?.activeRun()) {
          try {
            const run = await this.levelSession.start();
            await this.finishPersonalLevel(this.pendingLevelName, run.run_id);
          } catch (error) {
            this.setStatus(`关卡启动重试失败：${error instanceof Error ? error.message : "未知错误"}`);
          }
          return;
        }
        if (this.currentMode !== "WORLD" || !this.api || !this.mapSession) {
          this.setStatus("请先登录并进入共享世界");
          return;
        }
        try {
          this.setStatus("正在读取房间目录与个人进度…");
          const [catalog, progress] = await Promise.all([
            this.api.listLevels(),
            this.api.getPlayerProgress()
          ]);
          const level = selectNextPlayableLevel(catalog.levels, progress.completed_level_ids);
          if (!level) {
            this.setStatus("当前没有已解锁的可进入关卡");
            return;
          }
          const personal = new PersonalLevelSession(this.api);
          const entry = await personal.enter(
            level.level_id,
            level.entrance_id,
            this.makeIdempotencyKey("level-enter")
          );
          this.levelSession = personal;
          this.pendingLevelName = entry.level.level_name;
          this.pendingLevelId = entry.level.level_id;
          this.prototypeComboDefinitions = parsePrototypeComboDefinitions(level.config);
          this.prototypeLayout = parsePrototypeLayoutConfig(level.config);
          this.prototypeGazeTargetId = undefined;
          this.prototypeGazeMaintainAt = 0;
          this.prototypeGazeNextMaintainAt = 0;
          this.currentMode = "PERSONAL_LEVEL";
          this.updateJoystickVisibility();
          this.stopJoystickMovement();
          this.mapSession.leave();
          this.clearAvatars();
          const run = await personal.start();
          await this.finishPersonalLevel(this.pendingLevelName, run.run_id);
        } catch (error) {
          this.setStatus(
            this.levelSession?.activeRun()
              ? `个人关卡已创建，启动失败；可再次点击「进入探索房间」重试：${error instanceof Error ? error.message : "未知错误"}`
              : `进入关卡失败：${error instanceof Error ? error.message : "未知错误"}`
          );
        }
    } finally {
      this.prototypeActionInFlight = false;
    }
  }

  private async finishPersonalLevel(levelName: string, runId: string): Promise<void> {
    if (!this.levelSession) return;
    const rules = await this.levelSession.listRules();
    const gazeRule = rules.rules.find((rule) => rule.rule_id === "RULE_GAZE");
    this.prototypeGazeLeaseTimeoutMs = gazeRule?.lease_timeout_ms ?? 0;
    this.prototypeGazeRenewalIntervalMs = getGazeLeaseRenewalInterval(gazeRule?.lease_timeout_ms) ?? 0;
    const configured = rules.rules.filter((rule) => rule.is_unlocked);
    const ready = configured.filter((rule) => rule.config_status === "READY").length;
    if (this.rulesLabel) {
      this.rulesLabel.string = configured
        .map((rule) => `${rule.display_name}：${rule.config_status}`)
        .join("  ·  ");
    }
    this.levelPosition = { ...this.prototypeLayout.spawn };
    this.levelMoveSendElapsed = 0;
    const session = this.levelSession;
    this.levelPositionSync = new LatestPositionSyncQueue(
      (position) => session.updatePosition(position.x, position.y),
      (error) => {
        this.setStatus(`位置同步失败：${error instanceof Error ? error.message : "网络错误"}`);
      }
    );
    this.roomMechanismStates.clear();
    this.roomMechanismCatalog.clear();
    this.prototypeRuleCooldownUntil.clear();
    const state = await this.levelSession.refreshState();
    this.applyRoomMechanismStates(state);
    this.setStatus(
      `已进入个人关卡 ${levelName} · 原型坐标/数值待实测 · 法则可用配置 ${ready}/${configured.length}`
    );
    this.drawPersonalRoom(levelName);
  }

  private applyRoomMechanismStates(state: PersonalLevelState): void {
    this.roomMechanismStates = new Map(
      state.mechanisms.map((item) => [item.mechanism_id, item.state])
    );
    this.roomMechanismCatalog = new Map(
      state.mechanisms.map((item) => [
        item.mechanism_id,
        {
          mechanism_type: item.mechanism_type,
          position_x: item.position_x,
          position_y: item.position_y,
          target_type: item.target_type,
          config: item.config ?? {}
        }
      ])
    );
  }

  private prototypeRoomDimensions(): { width: number; height: number } {
    return getPrototypeRoomDimensions(this.prototypeLayout.bounds, this.levelRoomScale);
  }

  private prototypeLevelToLocal(x: number, y: number): { x: number; y: number } {
    return prototypeLevelToLocal({ x, y }, this.prototypeLayout.bounds, this.levelRoomScale);
  }

  private prototypeLocalToLevel(x: number, y: number): { x: number; y: number } {
    return prototypeLocalToLevel({ x, y }, this.prototypeLayout.bounds, this.levelRoomScale);
  }
  /**
   * Draws a temporary, data-aligned isometric floor for playtesting.
   * This is deliberately procedural prototype presentation, not a READY art asset.
   */
  private drawPrototypeMechanismSymbol(
    graphics: Graphics,
    shape: PrototypeMechanismShape,
    active: boolean
  ): void {
    graphics.lineWidth = 2;
    const drawDiamond = (halfWidth: number, halfHeight: number) => {
      graphics.moveTo(0, halfHeight);
      graphics.lineTo(halfWidth, 0);
      graphics.lineTo(0, -halfHeight);
      graphics.lineTo(-halfWidth, 0);
      graphics.close();
    };
    const fillOrStroke = () => {
      if (active) graphics.fill();
      else graphics.stroke();
    };

    switch (shape) {
      case "BRIDGE":
        graphics.rect(-12, -5, 24, 10);
        fillOrStroke();
        graphics.moveTo(-7, -5);
        graphics.lineTo(-7, 5);
        graphics.moveTo(0, -5);
        graphics.lineTo(0, 5);
        graphics.moveTo(7, -5);
        graphics.lineTo(7, 5);
        graphics.stroke();
        break;
      case "DOOR":
        graphics.rect(-7, -12, 14, 24);
        fillOrStroke();
        graphics.circle(3, 0, 1.5);
        graphics.fill();
        break;
      case "ENERGY":
        graphics.circle(0, 0, 10);
        graphics.stroke();
        graphics.circle(0, 0, active ? 6 : 3);
        fillOrStroke();
        break;
      case "GATE":
        drawDiamond(12, 13);
        graphics.stroke();
        drawDiamond(6, 7);
        fillOrStroke();
        break;
      case "HIDEABLE":
        graphics.circle(0, 0, 10);
        fillOrStroke();
        graphics.moveTo(-6, 0);
        graphics.lineTo(6, 0);
        graphics.moveTo(0, -6);
        graphics.lineTo(0, 6);
        graphics.stroke();
        break;
      case "PLATFORM":
        drawDiamond(13, 8);
        fillOrStroke();
        graphics.moveTo(-7, -2);
        graphics.lineTo(7, -2);
        graphics.stroke();
        break;
      case "CORE":
        graphics.circle(0, 0, 10);
        graphics.stroke();
        graphics.circle(0, 0, 4);
        fillOrStroke();
        graphics.moveTo(-13, 0);
        graphics.lineTo(13, 0);
        graphics.moveTo(0, -13);
        graphics.lineTo(0, 13);
        graphics.stroke();
        break;
      default:
        graphics.circle(0, 0, 10);
        fillOrStroke();
        break;
    }
  }

  private drawPrototypeFloorTiles(graphics: Graphics): void {
    const bounds = this.prototypeLayout.bounds;
    const palette: Record<string, [Color, Color, Color]> = {
      "LV-ROOM-01": [new Color(22, 54, 72, 255), new Color(27, 65, 83, 255), new Color(91, 159, 181, 190)],
      "LV-ROOM-02": [new Color(20, 58, 61, 255), new Color(25, 70, 70, 255), new Color(93, 183, 166, 190)],
      "LV-ROOM-03": [new Color(67, 43, 34, 255), new Color(78, 49, 37, 255), new Color(205, 137, 92, 190)],
      "LV-ROOM-04": [new Color(43, 39, 72, 255), new Color(51, 46, 82, 255), new Color(145, 132, 207, 190)],
      "LV-ROOM-05": [new Color(64, 55, 32, 255), new Color(76, 64, 36, 255), new Color(207, 177, 103, 190)],
      "LV-HIDDEN-01": [new Color(38, 35, 65, 255), new Color(47, 40, 79, 255), new Color(169, 145, 221, 210)]
    };
    const [tileA, tileB, edge] = palette[this.pendingLevelId ?? ""] ??
      [new Color(22, 54, 72, 255), new Color(27, 65, 83, 255), new Color(91, 159, 181, 190)];

    graphics.lineWidth = 1;
    for (let x = Math.floor(bounds.minX); x < bounds.maxX; x += 1) {
      for (let y = Math.floor(bounds.minY); y < bounds.maxY; y += 1) {
        const corners = [
          this.prototypeLevelToLocal(x, y),
          this.prototypeLevelToLocal(x + 1, y),
          this.prototypeLevelToLocal(x + 1, y + 1),
          this.prototypeLevelToLocal(x, y + 1)
        ];
        graphics.fillColor = (x + y) % 2 === 0 ? tileA : tileB;
        graphics.strokeColor = edge;
        graphics.moveTo(corners[0].x, corners[0].y);
        for (let index = 1; index < corners.length; index += 1) {
          graphics.lineTo(corners[index].x, corners[index].y);
        }
        graphics.close();
        graphics.fill();
        graphics.stroke();
      }
    }

    const topLeft = this.prototypeLevelToLocal(bounds.minX, bounds.minY);
    const topRight = this.prototypeLevelToLocal(bounds.maxX, bounds.minY);
    const bottomRight = this.prototypeLevelToLocal(bounds.maxX, bounds.maxY);
    const bottomLeft = this.prototypeLevelToLocal(bounds.minX, bounds.maxY);
    graphics.lineWidth = 3;
    graphics.strokeColor = edge;
    graphics.moveTo(topLeft.x, topLeft.y);
    graphics.lineTo(topRight.x, topRight.y);
    graphics.lineTo(bottomRight.x, bottomRight.y);
    graphics.lineTo(bottomLeft.x, bottomLeft.y);
    graphics.close();
    graphics.stroke();
  }


  private updatePrototypeRoomScale(size: { width: number; height: number }): void {
    this.levelRoomScale = calculatePrototypeRoomScale(this.prototypeLayout.bounds, size);
  }

  private sendLevelPosition(position: { x: number; y: number }): void {
    this.levelPositionSync?.enqueue(position);
  }

  private async flushLevelPosition(): Promise<void> {
    if (!this.levelSession || !this.levelPositionSync) return;
    await this.levelPositionSync.flush({ ...this.levelPosition });
  }

  private clearRoomControls(): void {
    for (const control of this.roomControlNodes) control.destroy();
    this.roomControlNodes.length = 0;
  }

  private sortPrototypeDepth(): void {
    const ordered = sortIsometricDepth(
      this.prototypeDepthNodes.map((node) => ({
        id: node.name,
        screenY: node.position.y,
        node
      }))
    );
    ordered.forEach((item, index) => item.node.setSiblingIndex(index));
  }

  private drawPersonalRoom(levelName: string, completed = false): void {
    if (!this.worldRoot) return;
    this.clearRoomControls();
    this.worldRoot.removeAllChildren();
    this.prototypeDepthNodes = [];
    const size = this.worldRoot.getComponent(UITransform).contentSize;
    this.updatePrototypeRoomScale(size);
    const roomSize = this.prototypeRoomDimensions();
    if (this.pendingLevelId !== "LV-ROOM-01") {
      const room = this.uiNode(`RoomPrototype-${this.pendingLevelId}`);
      this.worldRoot.addChild(room);
      room.addComponent(UITransform).setContentSize(roomSize.width, roomSize.height);
      const background = room.addComponent(Graphics);
      background.lineWidth = 3;
      background.strokeColor = new Color(105, 169, 190, 255);
      background.fillColor = new Color(18, 39, 55, 255);
      const bounds = this.prototypeLayout.bounds;
      const topLeft = this.prototypeLevelToLocal(bounds.minX, bounds.minY);
      const topRight = this.prototypeLevelToLocal(bounds.maxX, bounds.minY);
      const bottomRight = this.prototypeLevelToLocal(bounds.maxX, bounds.maxY);
      const bottomLeft = this.prototypeLevelToLocal(bounds.minX, bounds.maxY);
      background.moveTo(topLeft.x, topLeft.y);
      background.lineTo(topRight.x, topRight.y);
      background.lineTo(bottomRight.x, bottomRight.y);
      background.lineTo(bottomLeft.x, bottomLeft.y);
      background.close();
      background.fill();
      background.stroke();
      this.drawPrototypeFloorTiles(background);

      for (const [mechanismId, descriptor] of this.roomMechanismCatalog.entries()) {
        if (descriptor.position_x === null || descriptor.position_y === null) continue;
        const state = this.roomMechanismStates.get(mechanismId) ?? {};
        const status = String(state.status ?? "INACTIVE");
        const visualState = getPrototypeMechanismVisualState(status, state.visible === true);
        const activated = visualState === "ACTIVE";
        const color = activated
          ? new Color(122, 204, 151, 255)
          : visualState === "LOCKED"
            ? new Color(220, 170, 104, 255)
            : new Color(117, 185, 220, 255);
        const markerNode = this.uiNode(`Mechanism-${mechanismId}`);
        room.addChild(markerNode);
        this.prototypeDepthNodes.push(markerNode);
        const markerPosition = this.prototypeLevelToLocal(
          descriptor.position_x,
          descriptor.position_y
        );
        markerNode.setPosition(markerPosition.x, markerPosition.y, 0);
        markerNode.addComponent(UITransform).setContentSize(22, 22);
        const marker = markerNode.addComponent(Graphics);
        marker.fillColor = color;
        marker.strokeColor = color;
        this.drawPrototypeMechanismSymbol(
          marker,
          getPrototypeMechanismShape(descriptor.mechanism_type),
          activated
        );

        const labelNode = this.uiNode(`Label-${mechanismId}`);
        markerNode.addChild(labelNode);
        labelNode.setPosition(0, 20, 0);
        labelNode.addComponent(UITransform).setContentSize(170, 20);
        const label = labelNode.addComponent(Label);
        label.string = `${mechanismId} · ${status}`;
        label.fontSize = 10;
        label.color = new Color(226, 237, 246, 255);
        label.horizontalAlign = Label.HorizontalAlign.CENTER;
      }

      if (!completed) {
        this.levelAvatar = this.uiNode("PersonalLevelAvatar");
        room.addChild(this.levelAvatar);
        this.levelAvatar.addComponent(UITransform).setContentSize(30, 30);
        const avatarGraphics = this.levelAvatar.addComponent(Graphics);
        avatarGraphics.fillColor = new Color(247, 220, 137, 255);
        avatarGraphics.circle(0, 0, 13);
        avatarGraphics.fill();
        const avatarPosition = this.prototypeLevelToLocal(
          this.levelPosition.x,
          this.levelPosition.y
        );
        this.levelAvatar.setPosition(avatarPosition.x, avatarPosition.y, 0);
        this.prototypeDepthNodes.push(this.levelAvatar);
      }
      this.sortPrototypeDepth();

      const titleNode = this.uiNode("RoomTitle");
      this.worldRoot.addChild(titleNode);
      titleNode.setPosition(0, size.height / 2 - 30, 0);
      titleNode.addComponent(UITransform).setContentSize(size.width - 40, 28);
      const title = titleNode.addComponent(Label);
      title.string = `${levelName} · ${this.pendingLevelId} 几何原型`;
      title.fontSize = 16;
      title.color = new Color(226, 237, 246, 255);
      title.horizontalAlign = Label.HorizontalAlign.CENTER;

      const hintNode = this.uiNode("RoomPrototypeHint");
      this.worldRoot.addChild(hintNode);
      hintNode.setPosition(0, -size.height / 2 + 178, 0);
      hintNode.addComponent(UITransform).setContentSize(size.width - 40, 34);
      const hint = hintNode.addComponent(Label);
      hint.string = completed
        ? "本次探索已结算"
        : "服务器权威原型坐标 · 正式美术、数值平衡与真机验收仍待完成";
      hint.fontSize = 11;
      hint.color = new Color(230, 190, 135, 255);
      hint.horizontalAlign = Label.HorizontalAlign.CENTER;

      if (!completed) {
        const comboDefinitions = this.prototypeComboDefinitions;

        const buttonWidth = Math.min(170, (size.width - 48) / Math.max(1, comboDefinitions.length));
        const totalWidth = comboDefinitions.length * buttonWidth + Math.max(0, comboDefinitions.length - 1) * 8;
        comboDefinitions.forEach((definition, index) => {
          const x = -totalWidth / 2 + buttonWidth / 2 + index * (buttonWidth + 8);
          this.roomControlNodes.push(this.createButton(
            `Cast-${definition.comboId}-${index}`,
            definition.displayName,
            x,
            -size.height / 2 + 112,
            buttonWidth,
            42,
            () => this.castPrototypeCombo(definition)
          ));
        });

        if (this.pendingLevelId === "LV-HIDDEN-01") {
          this.roomControlNodes.push(this.createButton(
            "InteractEndingCore",
            "交互结局核心",
            0,
            -size.height / 2 + 112,
            180,
            42,
            () => this.interactHiddenEnding()
          ));
        } else {
          this.roomControlNodes.push(this.createButton(
            "SettlePrototypeRoom",
            "完成并结算",
            0,
            -size.height / 2 + 60,
            150,
            40,
            () => this.settlePrototypeRoom()
          ));
        }
        this.roomControlNodes.push(this.createButton(
          "RoomAbandonButton",
          "放弃并返回",
          size.width / 2 - 88,
          size.height / 2 - 145,
          150,
          40,
          () => this.returnToWorld()
        ));
      } else {
        this.roomControlNodes.push(this.createButton(
          "BackToWorldButton",
          "返回共享世界",
          0,
          -size.height / 2 + 70,
          170,
          42,
          () => this.loginAndEnterWorld()
        ));
      }
      return;
    }

    const room = this.uiNode("Room01Prototype");
    this.worldRoot.addChild(room);
    room.addComponent(UITransform).setContentSize(roomSize.width, roomSize.height);
    const graphics = room.addComponent(Graphics);
    graphics.lineWidth = 3;
    graphics.strokeColor = new Color(105, 169, 190, 255);
    graphics.fillColor = new Color(18, 39, 55, 255);
    const bounds = this.prototypeLayout.bounds;
    const topLeft = this.prototypeLevelToLocal(bounds.minX, bounds.minY);
    const topRight = this.prototypeLevelToLocal(bounds.maxX, bounds.minY);
    const bottomRight = this.prototypeLevelToLocal(bounds.maxX, bounds.maxY);
    const bottomLeft = this.prototypeLevelToLocal(bounds.minX, bounds.maxY);
    graphics.moveTo(topLeft.x, topLeft.y);
    graphics.lineTo(topRight.x, topRight.y);
    graphics.lineTo(bottomRight.x, bottomRight.y);
    graphics.lineTo(bottomLeft.x, bottomLeft.y);
    graphics.close();
    graphics.fill();
    graphics.stroke();
    this.drawPrototypeFloorTiles(graphics);

    const drawMarker = (
      name: string,
      x: number,
      y: number,
      color: Color,
      radius: number,
      visible: boolean,
      mechanismType?: string
    ) => {
      const node = this.uiNode(name);
      room.addChild(node);
      this.prototypeDepthNodes.push(node);
      const markerPosition = this.prototypeLevelToLocal(x, y);
      node.setPosition(markerPosition.x, markerPosition.y, 0);
      node.addComponent(UITransform).setContentSize(radius * 2, radius * 2);
      const marker = node.addComponent(Graphics);
      marker.fillColor = color;
      marker.strokeColor = color;
      if (mechanismType) {
        this.drawPrototypeMechanismSymbol(
          marker,
          getPrototypeMechanismShape(mechanismType),
          visible
        );
      } else {
        marker.circle(0, 0, radius);
        if (visible) marker.fill();
        else {
          marker.lineWidth = 2;
          marker.stroke();
        }
      }
      return node;
    };
    const roomVisualState = deriveRoom01VisualState(this.roomMechanismStates);
    const hiddenVisible = roomVisualState.hiddenTargetVisible;
    const exitOpen = roomVisualState.exitOpen;
    const drawCatalogMarker = (
      nodeName: string,
      mechanismId: string,
      color: Color,
      radius: number,
      visible: boolean
    ) => {
      const descriptor = this.roomMechanismCatalog.get(mechanismId);
      if (descriptor?.position_x === null || descriptor?.position_y === null || !descriptor) return;
      drawMarker(
        nodeName,
        descriptor.position_x,
        descriptor.position_y,
        color,
        radius,
        visible,
        descriptor.mechanism_type
      );
    };
    drawCatalogMarker(
      "HiddenObject",
      "M01-HIDEABLE-01",
      new Color(125, 207, 236, 255),
      14,
      hiddenVisible
    );
    drawCatalogMarker(
      "LightMarker",
      "M01-LIGHT-01",
      new Color(236, 211, 132, 255),
      11,
      hiddenVisible
    );
    drawCatalogMarker(
      "ExitGate",
      "M01-EXIT-01",
      exitOpen ? new Color(155, 214, 174, 255) : new Color(180, 105, 105, 255),
      17,
      exitOpen
    );
    this.levelAvatar = drawMarker("Player", this.levelPosition.x, this.levelPosition.y, new Color(115, 220, 255, 255), 12, true);
    this.sortPrototypeDepth();

    const labelNode = this.uiNode("RoomTitle");
    this.worldRoot.addChild(labelNode);
    labelNode.setPosition(0, size.height / 2 - 30, 0);
    labelNode.addComponent(UITransform).setContentSize(size.width - 40, 28);
    const label = labelNode.addComponent(Label);
    label.string = `${levelName} · ROOM-01 原型`;
    label.fontSize = 16;
    label.color = new Color(226, 237, 246, 255);
    label.horizontalAlign = Label.HorizontalAlign.CENTER;

    if (completed) {
      this.roomControlNodes.push(
        this.createButton(
          "BackToWorldButton",
          "返回共享世界",
          0,
          -size.height / 2 + 105,
          170,
          42,
          () => this.loginAndEnterWorld()
        )
      );
    } else {
      this.roomControlNodes.push(
        this.createButton("RoomEchoButton", "回声 · 显形", -95, -size.height / 2 + 155, 150, 42, () => this.castRoomEcho()),
        this.createButton("RoomExitButton", "靠近出口并交互", 95, -size.height / 2 + 155, 170, 42, () => this.interactRoomExit()),
        this.createButton("RoomAbandonButton", "放弃返回", size.width / 2 - 82, -size.height / 2 + 105, 130, 38, () => this.returnToWorld())
      );
    }
    this.decorateScene();
  }

  private async returnToWorld(): Promise<void> {
    if (
      this.currentMode !== "PERSONAL_LEVEL" ||
      !this.levelSession ||
      this.prototypeActionInFlight
    ) {
      this.setStatus("当前不在个人关卡中，或关卡操作尚未完成");
      return;
    }
    this.prototypeActionInFlight = true;
    this.stopJoystickMovement();
    try {
      this.setStatus("正在保存并放弃当前关卡…");
      // Abandon is allowed to proceed even if a best-effort position sync fails.
      await this.levelPositionSync?.waitForIdle();
      if (this.prototypeGazeTargetId) {
        try {
          await this.levelSession.stopGaze();
        } catch (error) {
          this.setStatus(`注视效果将在租约到期后结束：${error instanceof Error ? error.message : "网络错误"}`);
        }
      }
      this.prototypeGazeTargetId = undefined;
      this.prototypeGazeLeaseTimeoutMs = 0;
      this.prototypeGazeRenewalIntervalMs = 0;
      this.prototypeGazeMaintainAt = 0;
      this.prototypeGazeNextMaintainAt = 0;
      await this.levelSession.abandon();
      this.levelSession = undefined;
      this.levelPositionSync = undefined;
      this.pendingLevelName = "";
      this.pendingLevelId = "";
      this.roomMechanismCatalog.clear();
      this.prototypeRuleCooldownUntil.clear();
      this.moveTarget = undefined;
      this.mapSession = undefined;
      this.currentMode = "MENU";
      this.updateJoystickVisibility();
      this.clearAvatars();
      await this.loginAndEnterWorld();
    } catch (error) {
      this.setStatus(`返回世界失败：${error instanceof Error ? error.message : "未知错误"}`);
    } finally {
      this.prototypeActionInFlight = false;
    }
  }

  private clearAvatars(): void {
    for (const node of this.avatars.values()) node.destroy();
    this.avatars.clear();
  }
}
