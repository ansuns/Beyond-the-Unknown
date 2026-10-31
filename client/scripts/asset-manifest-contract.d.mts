export interface AssetManifestValidationResult {
  errors: string[];
  counts: Record<
    "MISSING" | "PROCESSING" | "IN_PROGRESS" | "GENERATED" | "REVIEW" | "READY" | "BLOCKED",
    number
  >;
  total: number;
  expectedCount: number;
}
export function validateAssetManifestStructure(
  manifest: Record<string, any>,
  levelConfig: Record<string, any>,
  strict?: boolean
): AssetManifestValidationResult;
