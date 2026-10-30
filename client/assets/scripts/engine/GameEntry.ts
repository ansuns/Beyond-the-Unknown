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
  Node,
  NodeEventType,
  UITransform,
  view
} from "cc";

import { RestClient } from "../network/rest-client";
import type { LawRuleId, MapServerEvent, PersonalLevelState } from "../network/types";
import { createWeChatFetch, createWeChatWebSocketFactory } from "../platform/wechat-network";
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
  type PrototypeLayoutConfig
} from "../world/prototype-layout";
import { LatestPositionSyncQueue } from "../world/latest-position-sync-queue";
import { formatProgressSummary } from "../ui/progress-summary";

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
  }

  onDestroy(): void {
    this.mapSession?.dispose();
    this.mapSession = undefined;
  }

  update(deltaTime: number): void {
    if (this.currentMode === "PERSONAL_LEVEL") {
      this.updatePrototypeGazeMaintain();
      this.updatePersonalLevelMovement(deltaTime);
      return;
    }
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
    const step = speedUnits * Math.max(0, deltaTime);
    const reached = distance <= step || distance < 0.001;
    const nextX = reached ? this.moveTarget.x : currentX + (dx / distance) * step;
    const nextY = reached ? this.moveTarget.y : currentY + (dy / distance) * step;
    const direction =
      Math.abs(dx) > Math.abs(dy)
        ? (dx >= 0 ? "E" : "W")
        : (dy >= 0 ? "N" : "S");

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

  private buildShell(): void {
    const size = view.getVisibleSize();
    const canvasNode = new Node("RuntimeCanvas");
    this.node.addChild(canvasNode);
    canvasNode.addComponent(UITransform).setContentSize(size.width, size.height);
    const canvas = canvasNode.addComponent(Canvas);
    canvas.cameraComponent = this.node.getComponentInChildren(Camera);
    canvas.alignCanvasWithScreen = true;

    this.root = new Node("BeyondTheUnknownRuntime");
    canvasNode.addChild(this.root);

    const background = new Node("Background");
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

    this.worldRoot = new Node("WorldViewport");
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
  }

  private createLabel(name: string, value: string, x: number, y: number, fontSize: number): Label {
    const node = new Node(name);
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
    const node = new Node(name);
    this.root!.addChild(node);
    node.setPosition(x, y, 0);
    node.addComponent(UITransform).setContentSize(width, height);
    const graphics = node.addComponent(Graphics);
    graphics.fillColor = new Color(35, 93, 123, 255);
    graphics.rect(-width / 2, -height / 2, width, height);
    graphics.fill();
    const label = node.addComponent(Label);
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

  private setStatus(message: string): void {
    if (this.statusLabel) this.statusLabel.string = message;
  }

  private makeIdempotencyKey(prefix: string): string {
    return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  }

  private async createApi(): Promise<void> {
    const wxApi = (globalThis as any).wx;
    if (!wxApi?.login || !wxApi?.request || !wxApi?.connectSocket) {
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
    try {
      this.clearRoomControls();
      this.worldRoot?.removeAllChildren();
      this.clearAvatars();
      this.moveTarget = undefined;
      this.rulesLabel && (this.rulesLabel.string = "法则：尚未读取");
      this.setStatus("正在请求微信登录码并连接共享地图…");
      await this.createApi();
      const wxApi = (globalThis as any).wx;
      const platform = new WeChatPlatform(wxApi);
      this.mapSession = new MapSession(platform, this.api!, this.sessionStore!, {
        websocketBaseUrl: this.websocketBaseUrl,
        socketFactory: createWeChatWebSocketFactory(wxApi)
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
      node = new Node(local ? "LocalPlayer" : `RemotePlayer-${avatar.player_id.slice(0, 8)}`);
      this.worldRoot.addChild(node);
      node.addComponent(UITransform).setContentSize(34, 34);
      node.addComponent(Graphics);
      const labelNode = new Node("PlayerLabel");
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
    if (!session || !targetId || this.prototypeGazeMaintainInFlight) return;

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
    this.prototypeGazeNextMaintainAt = now + 1000;
    this.prototypeGazeMaintainInFlight = true;
    void session.maintainGaze(targetId)
      .then(() => {
        if (this.levelSession === session && this.prototypeGazeTargetId === targetId) {
          // RULE_GAZE has a 5-second server lease; renew well before it expires.
          this.prototypeGazeMaintainAt = Date.now() + 5000;
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
    const step = this.prototypeLayout.movementSpeed * Math.max(0, deltaTime);
    const reached = distance <= step || distance < 0.001;
    this.levelPosition = reached
      ? { ...this.moveTarget }
      : { x: this.levelPosition.x + dx / distance * step, y: this.levelPosition.y + dy / distance * step };
    const avatarPosition = this.prototypeLevelToLocal(this.levelPosition.x, this.levelPosition.y);
    this.levelAvatar.setPosition(avatarPosition.x, avatarPosition.y, 0);
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
    if (!this.levelSession) return;
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
      this.setStatus(result.effects.length ? "回声扩散：隐藏的符号显现了" : "回声没有回应");
    } catch (error) {
      this.setStatus(`回声失败：${error instanceof Error ? error.message : "请稍后重试"}`);
    }
  }

  private async castPrototypeCombo(
    definition: PrototypeComboDefinition
  ): Promise<void> {
    if (!this.levelSession || this.prototypeActionInFlight) return;
    const { comboId, targetId, ruleIds } = definition;
    this.prototypeActionInFlight = true;
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
          this.prototypeGazeMaintainAt = Date.now() + 5000;
          this.prototypeGazeNextMaintainAt = Date.now() + 1000;
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
    try {
      await this.flushLevelPosition();
      if (this.prototypeGazeTargetId) {
        await this.levelSession.stopGaze();
        this.prototypeGazeTargetId = undefined;
        this.prototypeGazeMaintainAt = 0;
        this.prototypeGazeNextMaintainAt = 0;
      }
      const result = await this.levelSession.settle(
        this.makeIdempotencyKey(`prototype-settle-${this.pendingLevelId}`)
      );
      this.levelSession = undefined;
      this.levelPositionSync = undefined;
      this.prototypeGazeTargetId = undefined;
      this.prototypeGazeMaintainAt = 0;
      this.prototypeGazeNextMaintainAt = 0;
      this.currentMode = "MENU";
      this.moveTarget = undefined;
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
    if (!this.levelSession) return;
    try {
      await this.flushLevelPosition();
      const result = await this.levelSession.interact(
        "H01-END",
        this.makeIdempotencyKey("hidden-ending-interact")
      );
      this.roomMechanismStates.set(result.mechanism_id, result.state);
      this.applyRoomMechanismStates(await this.levelSession.refreshState());
      if (result.state.status === "TRIGGERED") {
        await this.settlePrototypeRoom();
      } else {
        this.drawPersonalRoom(this.pendingLevelName);
        this.setStatus("结局核心尚未完成");
      }
    } catch (error) {
      this.setStatus(`结局核心交互失败：${error instanceof Error ? error.message : "请靠近机关后重试"}`);
    }
  }

  private async interactRoomExit(): Promise<void> {
    if (!this.levelSession) return;
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
        this.levelSession = undefined;
        this.levelPositionSync = undefined;
        this.drawPersonalRoom("探索完成", true);
        this.setStatus(`探索完成 · 用时 ${Math.round(settled.completion_time_ms / 1000)} 秒`);
      }
    } catch (error) {
      this.setStatus(`出口尚未开启或距离不足：${error instanceof Error ? error.message : "请继续探索"}`);
    }
  }

  private async enterFirstRoom(): Promise<void> {
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
      this.moveTarget = undefined;
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
  }

  private async finishPersonalLevel(levelName: string, runId: string): Promise<void> {
    if (!this.levelSession) return;
    const rules = await this.levelSession.listRules();
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

  private drawPersonalRoom(levelName: string, completed = false): void {
    if (!this.worldRoot) return;
    this.clearRoomControls();
    this.worldRoot.removeAllChildren();
    const size = this.worldRoot.getComponent(UITransform).contentSize;
    this.updatePrototypeRoomScale(size);
    const roomSize = this.prototypeRoomDimensions();
    if (this.pendingLevelId !== "LV-ROOM-01") {
      const room = new Node(`RoomPrototype-${this.pendingLevelId}`);
      this.worldRoot.addChild(room);
      room.addComponent(UITransform).setContentSize(roomSize.width, roomSize.height);
      const background = room.addComponent(Graphics);
      background.lineWidth = 3;
      background.strokeColor = new Color(105, 169, 190, 255);
      background.fillColor = new Color(18, 39, 55, 255);
      background.rect(-roomSize.width / 2, -roomSize.height / 2, roomSize.width, roomSize.height);
      background.fill();
      background.stroke();

      for (const [mechanismId, descriptor] of this.roomMechanismCatalog.entries()) {
        if (descriptor.position_x === null || descriptor.position_y === null) continue;
        const state = this.roomMechanismStates.get(mechanismId) ?? {};
        const status = String(state.status ?? "INACTIVE");
        const activated = status === "TRIGGERED" || state.visible === true;
        const locked = status === "LOCKED" || status === "SEALED";
        const color = activated
          ? new Color(122, 204, 151, 255)
          : locked
            ? new Color(220, 170, 104, 255)
            : new Color(117, 185, 220, 255);
        const markerNode = new Node(`Mechanism-${mechanismId}`);
        room.addChild(markerNode);
        const markerPosition = this.prototypeLevelToLocal(
          descriptor.position_x,
          descriptor.position_y
        );
        markerNode.setPosition(markerPosition.x, markerPosition.y, 0);
        markerNode.addComponent(UITransform).setContentSize(22, 22);
        const marker = markerNode.addComponent(Graphics);
        marker.fillColor = color;
        marker.strokeColor = color;
        marker.lineWidth = 2;
        marker.circle(0, 0, 10);
        if (activated) marker.fill();
        else marker.stroke();

        const labelNode = new Node(`Label-${mechanismId}`);
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
        this.levelAvatar = new Node("PersonalLevelAvatar");
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
      }

      const titleNode = new Node("RoomTitle");
      this.worldRoot.addChild(titleNode);
      titleNode.setPosition(0, size.height / 2 - 30, 0);
      titleNode.addComponent(UITransform).setContentSize(size.width - 40, 28);
      const title = titleNode.addComponent(Label);
      title.string = `${levelName} · ${this.pendingLevelId} 几何原型`;
      title.fontSize = 16;
      title.color = new Color(226, 237, 246, 255);
      title.horizontalAlign = Label.HorizontalAlign.CENTER;

      const hintNode = new Node("RoomPrototypeHint");
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

    const room = new Node("Room01Prototype");
    this.worldRoot.addChild(room);
    room.addComponent(UITransform).setContentSize(roomSize.width, roomSize.height);
    const graphics = room.addComponent(Graphics);
    graphics.lineWidth = 3;
    graphics.strokeColor = new Color(105, 169, 190, 255);
    graphics.fillColor = new Color(18, 39, 55, 255);
    graphics.rect(-roomSize.width / 2, -roomSize.height / 2, roomSize.width, roomSize.height);
    graphics.fill();
    graphics.stroke();

    const drawMarker = (name: string, x: number, y: number, color: Color, radius: number, visible: boolean) => {
      const node = new Node(name);
      room.addChild(node);
      const markerPosition = this.prototypeLevelToLocal(x, y);
      node.setPosition(markerPosition.x, markerPosition.y, 0);
      node.addComponent(UITransform).setContentSize(radius * 2, radius * 2);
      const marker = node.addComponent(Graphics);
      marker.fillColor = color;
      marker.circle(0, 0, radius);
      if (visible) marker.fill();
      else {
        marker.strokeColor = color;
        marker.lineWidth = 2;
        marker.stroke();
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
      drawMarker(nodeName, descriptor.position_x, descriptor.position_y, color, radius, visible);
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

    const labelNode = new Node("RoomTitle");
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
  }

  private async returnToWorld(): Promise<void> {
    if (this.currentMode !== "PERSONAL_LEVEL" || !this.levelSession) {
      this.setStatus("当前不在个人关卡中");
      return;
    }
    try {
      this.setStatus("正在保存并放弃当前关卡…");
      await this.levelPositionSync?.flush({ ...this.levelPosition });
      if (this.prototypeGazeTargetId) {
        await this.levelSession.stopGaze();
      }
      this.prototypeGazeTargetId = undefined;
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
      this.clearAvatars();
      await this.loginAndEnterWorld();
    } catch (error) {
      this.setStatus(`返回世界失败：${error instanceof Error ? error.message : "未知错误"}`);
    }
  }

  private clearAvatars(): void {
    for (const node of this.avatars.values()) node.destroy();
    this.avatars.clear();
  }
}
