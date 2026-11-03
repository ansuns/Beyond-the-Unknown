// The Cocos Creator editor generates real engine types into temp/declarations
// at build time, but CI only runs `tsc --noEmit` and never generates them, so
// any file importing "cc" fails with TS2307. Declaring the symbols used by
// type-checked files here lets them resolve (as `any`) while still checking
// their own logic - unlike `// @ts-nocheck`, which disables checking entirely.
//
// Files that are still `@ts-nocheck` (GameEntry, art-assets, asset-service) do
// not need entries here; add a symbol when a checked file starts using it.
declare module "cc" {
  export const Color: any;
  export type Color = any;
  export const Graphics: any;
  export type Graphics = any;
}
