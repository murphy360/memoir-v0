import type { AssetEntry, LifeEvent } from "../types";

export const UNASSIGNED_PERIOD_VALUE = "__unassigned__";

export type PeriodSortMode =
  | "timeline-asc"
  | "timeline-desc"
  | "updated-desc"
  | "events-desc"
  | "title-asc";

export function formatAssetCaptureDate(asset: AssetEntry): string | null {
  if (asset.captured_at_text) {
    return asset.captured_at_text;
  }
  if (asset.captured_at) {
    const parsed = new Date(asset.captured_at);
    if (!Number.isNaN(parsed.getTime())) {
      return parsed.toLocaleString();
    }
    return asset.captured_at;
  }
  return null;
}

export function formatAssetGps(asset: AssetEntry): string | null {
  if (asset.gps_latitude === null || asset.gps_longitude === null) {
    return null;
  }
  const coords = `${asset.gps_latitude.toFixed(5)}, ${asset.gps_longitude.toFixed(5)}`;
  if (asset.location_name) {
    return `${asset.location_name} (${coords})`;
  }
  return coords;
}

export function renderImageMetadataBadges(
  asset: AssetEntry,
): JSX.Element | null {
  const isImage =
    asset.kind === "photo" || (asset.content_type || "").startsWith("image/");
  if (!isImage) {
    return null;
  }

  const hasLocation =
    asset.gps_latitude !== null && asset.gps_longitude !== null;
  const hasCapture = Boolean(asset.captured_at_text || asset.captured_at);
  const hasCamera = Boolean(
    asset.camera_make || asset.camera_model || asset.lens_model,
  );
  const hasDimensions =
    asset.image_width !== null || asset.image_height !== null;
  const hasNonLocationMetadata = hasCapture || hasCamera || hasDimensions;

  let metadataLabel = "Metadata: none";
  let metadataClass = "assetMetaBadge isMissing";
  if (hasLocation && hasNonLocationMetadata) {
    metadataLabel = "Metadata: rich";
    metadataClass = "assetMetaBadge isPresent";
  } else if (hasLocation || hasNonLocationMetadata) {
    metadataLabel = "Metadata: partial";
    metadataClass = "assetMetaBadge isPartial";
  }

  return (
    <div className="assetMetaBadgeRow">
      <span className={metadataClass}>{metadataLabel}</span>
      <span
        className={`assetMetaBadge ${hasLocation ? "isPresent" : "isMissing"}`}
      >
        Location: {hasLocation ? "present" : "missing"}
      </span>
    </div>
  );
}

export function collectEventMemoryIds(
  event: LifeEvent,
  assets: AssetEntry[],
): number[] {
  const ids = new Set<number>();
  for (const memoryId of event.linked_memory_ids) {
    ids.add(memoryId);
  }
  for (const asset of assets) {
    if (asset.legacy_memory_id !== null) {
      ids.add(asset.legacy_memory_id);
    }
  }
  return Array.from(ids);
}

export function parsePeriodYearHint(value: string | null): number | null {
  if (!value) {
    return null;
  }

  const directYear = value.match(/\b(19\d{2}|20\d{2})\b/);
  if (directYear) {
    return Number.parseInt(directYear[1], 10);
  }

  const decadeYear = value.match(/\b(19\d0|20\d0)s\b/i);
  if (decadeYear) {
    return Number.parseInt(decadeYear[1], 10);
  }

  return null;
}

export function parseOptionalDateTimestamp(
  value: string | null,
): number | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  const time = parsed.getTime();
  return Number.isNaN(time) ? null : time;
}

export function compareDateStringsDesc(left: string, right: string): number {
  const leftTime = new Date(left).getTime();
  const rightTime = new Date(right).getTime();
  if (Number.isNaN(leftTime) && Number.isNaN(rightTime)) {
    return 0;
  }
  if (Number.isNaN(leftTime)) {
    return 1;
  }
  if (Number.isNaN(rightTime)) {
    return -1;
  }
  return rightTime - leftTime;
}
