export interface WxLoginResult {
  code?: string;
  errMsg?: string;
}

export interface WxApi {
  login(options: { success: (result: WxLoginResult) => void; fail: (error: unknown) => void }): void;
}

export class WeChatPlatform {
  constructor(private readonly wx: WxApi) {}

  login(): Promise<string> {
    return new Promise((resolve, reject) => {
      this.wx.login({
        success: (result) => {
          if (result.code) resolve(result.code);
          else reject(new Error(result.errMsg || "wx.login returned no code"));
        },
        fail: (error) => reject(error instanceof Error ? error : new Error("wx.login failed"))
      });
    });
  }
}
