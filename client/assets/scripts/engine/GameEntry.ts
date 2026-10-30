// @ts-nocheck
// Cocos Creator 3.8.8 runtime entry point.
// Engine typings are supplied by the Cocos editor; the repository's Node/Vitest
// typecheck intentionally covers the engine-independent network/session layer.
import {
  _decorator,
  Color,
  Component,
  Graphics,
  Label,
  Node,
  NodeEventType,
  UITransform,
  Vec3,
  view
} from "cc";

import { RestClient } from "../network/rest-client";
import type { MapServerEvent } from "../network/types";
import { createWeChatFetch, createWeChatWebSocketFactory } from "../platform/wechat-network";
import { WeChatPlatform } from "../platform/wechat-platform";
import { SessionStore } from "../player/session-store";
import { MapSession } from "../world/map-session";
import { PersonalLevelSession } from "../world/personal-level-session";

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
  private mapSession?: MapSession;
  private levelSession?: PersonalLevelSession;
  private api?: RestClient;
  private sessionStore?: SessionStore;
  private localPlayerId?: string;
  private readonly avatars = new Map<string, Node>();
  private clientTick = 0;
  private currentMode: "MENU" | "WORLD" | "PERSONAL_LEVEL" = "MENU";

  onLoad(): void {
    this.buildShell();
  }

  onDestroy(): void {
    this.mapSession?.dispose();
    this.mapSession = undefined;
  }

  private buildShell(): void {
    const size = view.getVisibleSize();
    this.root = new Node("BeyondTheUnknownRuntime");
    this.node.addChild(this.root);

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
    worldGraphics.roundRect(
      -worldTransform.width / 2,
      -worldTransform.height / 2,
      worldTransform.width,
      worldTransform.height,
      18
    );
    worldGraphics.fill();
    worldGraphics.stroke();
    this.worldRoot.on(NodeEventType.TOUCH_END, this.onWorldTouch, this);

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
      "EmoteButton",
      "招呼",
      size.width / 2 - 72,
      size.height / 2 - 145,
      110,
      44,
      () => this.mapSession?.action("ACT_001")
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
    graphics.roundRect(-width / 2, -height / 2, width, height, 10);
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
      this.currentMode = "WORLD";
      this.upsertAvatar({
        player_id: this.localPlayerId!,
        x: map.spawn_position.x,
        y: map.spawn_position.y,
        direction: map.spawn_position.direction
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
      const graphics = node.addComponent(Graphics);
      graphics.fillColor = local
        ? new Color(112, 220, 255, 255)
        : new Color(255, 190, 105, 255);
      graphics.circle(0, 0, 15);
      graphics.fill();
      const labelNode = new Node("PlayerLabel");
      node.addChild(labelNode);
      labelNode.setPosition(0, -27, 0);
      labelNode.addComponent(UITransform).setContentSize(110, 22);
      const label = labelNode.addComponent(Label);
      label.string = local ? "我" : avatar.player_id.slice(0, 6);
      label.fontSize = 11;
      label.lineHeight = 14;
      label.color = Color.WHITE;
      label.horizontalAlign = Label.HorizontalAlign.CENTER;
      this.avatars.set(avatar.player_id, node);
    }
    node.setPosition(avatar.x * 40, avatar.y * 40, 0);
  }

  private removeAvatar(playerId: string): void {
    const node = this.avatars.get(playerId);
    if (node) node.destroy();
    this.avatars.delete(playerId);
  }

  private onWorldTouch(event: any): void {
    if (this.currentMode !== "WORLD" || !this.mapSession || !this.worldRoot) return;
    const transform = this.worldRoot.getComponent(UITransform);
    const point = transform.convertToNodeSpaceAR(event.getUILocation());
    const x = point.x / 40;
    const y = point.y / 40;
    this.clientTick += 1;
    this.mapSession.move(x, y, "S", this.clientTick);
    if (this.localPlayerId) {
      this.upsertAvatar({ player_id: this.localPlayerId, x, y }, true);
    }
  }

  private async enterFirstRoom(): Promise<void> {
    if (this.currentMode !== "WORLD" || !this.api || !this.mapSession) {
      this.setStatus("请先登录并进入共享世界");
      return;
    }
    try {
      this.setStatus("正在读取房间目录…");
      const catalog = await this.api.listLevels();
      const level = catalog.levels.find((item) => !item.is_hidden && item.is_unlocked);
      if (!level) {
        this.setStatus("当前没有可进入的常规探索房间");
        return;
      }
      const personal = new PersonalLevelSession(this.api);
      const result = await personal.enterAndStart(
        level.level_id,
        level.entrance_id,
        this.makeIdempotencyKey("level-enter")
      );
      this.levelSession = personal;
      this.mapSession.leave();
      this.currentMode = "PERSONAL_LEVEL";
      this.clearAvatars();
      const rules = await personal.listRules();
      const configured = rules.rules.filter((rule) => rule.is_unlocked);
      const ready = configured.filter((rule) => rule.config_status === "READY").length;
      if (this.rulesLabel) {
        this.rulesLabel.string = configured
          .map((rule) => `${rule.display_name}：${rule.config_status}`)
          .join("  ·  ");
      }
      this.setStatus(
        `已进入个人关卡 ${result.entry.level.level_name} · ${result.run.run_id.slice(0, 8)} · 法则可用配置 ${ready}/${configured.length}`
      );
      this.drawPersonalRoom(result.entry.level.level_name);
    } catch (error) {
      this.setStatus(`进入关卡失败：${error instanceof Error ? error.message : "未知错误"}`);
    }
  }

  private drawPersonalRoom(levelName: string): void {
    if (!this.worldRoot) return;
    this.worldRoot.removeAllChildren();
    const size = this.worldRoot.getComponent(UITransform).contentSize;
    const room = new Node("PersonalRoomPlaceholder");
    this.worldRoot.addChild(room);
    room.addComponent(UITransform).setContentSize(size.width - 60, size.height - 60);
    const graphics = room.addComponent(Graphics);
    graphics.lineWidth = 4;
    graphics.strokeColor = new Color(111, 159, 184, 255);
    graphics.fillColor = new Color(26, 48, 62, 255);
    graphics.rect(-size.width / 2 + 30, -size.height / 2 + 30, size.width - 60, size.height - 60);
    graphics.fill();
    graphics.stroke();
    const labelNode = new Node("RoomStatus");
    room.addChild(labelNode);
    labelNode.addComponent(UITransform).setContentSize(size.width - 80, 90);
    const label = labelNode.addComponent(Label);
    label.string = `${levelName}\n场景与机关坐标待内容配置；法则数值未批准前保持关闭`;
    label.fontSize = 20;
    label.lineHeight = 32;
    label.color = new Color(218, 232, 240, 255);
    label.horizontalAlign = Label.HorizontalAlign.CENTER;
    label.verticalAlign = Label.VerticalAlign.CENTER;
  }

  private async returnToWorld(): Promise<void> {
    if (this.currentMode !== "PERSONAL_LEVEL" || !this.levelSession) {
      this.setStatus("当前不在个人关卡中");
      return;
    }
    try {
      this.setStatus("正在保存并放弃当前关卡…");
      await this.levelSession.abandon();
      this.levelSession = undefined;
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
