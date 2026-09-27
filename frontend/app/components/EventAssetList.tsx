import { useMemo, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import {
  formatAssetCaptureDate,
  formatAssetGps,
  parsePeriodYearHint,
  parseOptionalDateTimestamp,
  renderImageMetadataBadges,
} from "../lib/homePageHelpers";
import type {
  AssetEntry,
  EventFaceEntry,
  LifeEpic,
  LifeEvent,
  LifePeriod,
} from "../types";

type EventAssetListProps = {
  assets: AssetEntry[];
  highlightedElementId: string | null;
  expandedAssetRowIds: Set<number>;
  setExpandedAssetRowIds: Dispatch<SetStateAction<Set<number>>>;
  editingAssetTitleId: number | null;
  setEditingAssetTitleId: (id: number | null) => void;
  editingAssetTitleValue: string;
  setEditingAssetTitleValue: (value: string) => void;
  assetTitleSavingId: number | null;
  saveAssetTitle: (
    assetId: number,
    eventId?: number,
    nextTitle?: string,
  ) => Promise<void>;
  editingAssetNotesId: number | null;
  setEditingAssetNotesId: (id: number | null) => void;
  editingAssetNotesValue: string;
  setEditingAssetNotesValue: (value: string) => void;
  assetNotesSavingId: number | null;
  saveAssetNotes: (
    assetId: number,
    eventId?: number,
    nextNotes?: string,
  ) => Promise<void>;
  editingAssetCapturedDateId: number | null;
  setEditingAssetCapturedDateId: (id: number | null) => void;
  editingAssetCapturedDateValue: string;
  setEditingAssetCapturedDateValue: (value: string) => void;
  assetCapturedDateSavingId: number | null;
  saveAssetCapturedDate: (
    assetId: number,
    eventId?: number,
    nextCapturedDateText?: string,
  ) => Promise<void>;
  resolveApiUrl: (path: string) => string;
  formatBytes: (bytes: number) => string;
  deleteAsset: (assetId: number, eventId?: number) => Promise<void>;
  eventId?: number;
  eventFaces?: EventFaceEntry[];
  renameFaceSubject?: (
    faceId: number,
    newSubjectName: string,
    eventId: number,
  ) => Promise<void>;
  processPhotoAsset?: (assetId: number, eventId: number) => Promise<void>;
  processingPhotoAssetId?: number | null;
  recordingForAssetId?: number | null;
  startRecordingForAsset?: (assetId: number, eventId: number) => Promise<void>;
  stopRecording?: () => void;
  cancelRecording?: () => void;
  assetRecordingPending?: Record<
    number,
    {
      id: string;
      audioUrl: string;
      sizeBytes: number;
      status: "recorded" | "processing" | "saved" | "failed";
      error?: string;
    }
  >;
  isRecording?: boolean;
  isLoading?: boolean;
  audioDevices?: Array<{ deviceId: string; label: string }>;
  showLinkControls?: boolean;
  lifePeriods?: LifePeriod[];
  lifeEpics?: LifeEpic[];
  lifeEvents?: LifeEvent[];
  createEpicInPeriod?: (
    periodId: number,
    title: string,
  ) => Promise<LifeEpic | null>;
  createEventForLinking?: (payload: {
    title: string;
    periodId: number | null;
    epicId: number | null;
    eventDateText: string | null;
  }) => Promise<LifeEvent | null>;
  assetLinkTargets?: Record<number, string>;
  setAssetLinkTargets?: Dispatch<SetStateAction<Record<number, string>>>;
  linkUnlinkedAssetToEvent?: (
    assetId: number,
    eventId?: number,
  ) => Promise<void>;
  isSavingLifeStructure?: boolean;
};

function isImageAsset(asset: AssetEntry): boolean {
  const contentType = (asset.content_type || "").toLowerCase();
  return asset.kind === "photo" || contentType.startsWith("image/");
}

function isAudioAsset(asset: AssetEntry): boolean {
  const contentType = (asset.content_type || "").toLowerCase();
  return asset.kind === "recording" || contentType.startsWith("audio/");
}

function isDocumentAsset(asset: AssetEntry): boolean {
  return asset.kind === "document";
}

function isPdfAsset(asset: AssetEntry): boolean {
  return (asset.content_type || "").toLowerCase().includes("pdf");
}

function fileExtension(name: string | null): string {
  const raw = (name || "").trim();
  if (!raw || !raw.includes(".")) {
    return "FILE";
  }
  const ext = raw.split(".").pop() || "FILE";
  return ext.slice(0, 5).toUpperCase();
}

function formatSimilarityPercent(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "n/a";
  }
  return `${(value * 100).toFixed(2)}%`;
}

function stringifyComprefaceRaw(raw: Record<string, unknown> | null): string {
  if (!raw) {
    return "{}";
  }
  try {
    return JSON.stringify(raw, null, 2);
  } catch {
    return "{}";
  }
}

function parseDateFromAsset(asset: AssetEntry): Date | null {
  if (asset.captured_at) {
    const parsed = new Date(asset.captured_at);
    if (!Number.isNaN(parsed.getTime())) {
      return parsed;
    }
  }
  if (asset.captured_at_text) {
    const parsed = new Date(asset.captured_at_text);
    if (!Number.isNaN(parsed.getTime())) {
      return parsed;
    }
  }
  return null;
}

function assetYearHint(asset: AssetEntry): number | null {
  const parsedDate = parseDateFromAsset(asset);
  if (parsedDate) {
    return parsedDate.getFullYear();
  }
  return parsePeriodYearHint(asset.captured_at_text);
}

function dateRangeScore(
  year: number,
  startYear: number | null,
  endYear: number | null,
): number {
  if (startYear !== null && endYear !== null) {
    const normalizedStart = Math.min(startYear, endYear);
    const normalizedEnd = Math.max(startYear, endYear);
    if (year >= normalizedStart && year <= normalizedEnd) {
      return (normalizedEnd - normalizedStart) * 0.01;
    }
    return Math.min(
      Math.abs(year - normalizedStart),
      Math.abs(year - normalizedEnd),
    );
  }
  if (startYear !== null) {
    return Math.abs(year - startYear) + 1;
  }
  if (endYear !== null) {
    return Math.abs(year - endYear) + 1;
  }
  return Number.POSITIVE_INFINITY;
}

function eventYearHint(event: LifeEvent): number | null {
  const sortableDate = event.event_date_sort
    ? new Date(event.event_date_sort)
    : null;
  if (sortableDate && !Number.isNaN(sortableDate.getTime())) {
    return sortableDate.getFullYear();
  }
  if (event.date_year !== null) {
    return event.date_year;
  }
  if (event.date_decade !== null) {
    return event.date_decade;
  }
  return parsePeriodYearHint(event.event_date_text);
}

function eventTimestampHint(event: LifeEvent): number | null {
  const sortableTime = parseOptionalDateTimestamp(event.event_date_sort);
  if (sortableTime !== null) {
    return sortableTime;
  }
  if (event.date_year === null) {
    return null;
  }
  const month = event.date_month ?? 1;
  const day = event.date_day ?? 1;
  const parsed = new Date(event.date_year, month - 1, day);
  const time = parsed.getTime();
  return Number.isNaN(time) ? null : time;
}

function pickDefaultPeriodId(
  asset: AssetEntry,
  lifePeriods: LifePeriod[],
): string {
  const year = assetYearHint(asset);
  if (year === null || lifePeriods.length === 0) {
    return "";
  }

  let bestPeriod: LifePeriod | null = null;
  let bestScore = Number.POSITIVE_INFINITY;
  for (const period of lifePeriods) {
    const normalizedStartYear = period.start_sort
      ? new Date(period.start_sort).getFullYear()
      : null;
    const normalizedEndYear = period.end_sort
      ? new Date(period.end_sort).getFullYear()
      : null;
    const score = dateRangeScore(
      year,
      normalizedStartYear ?? parsePeriodYearHint(period.start_date_text),
      normalizedEndYear ?? parsePeriodYearHint(period.end_date_text),
    );
    if (score < bestScore) {
      bestScore = score;
      bestPeriod = period;
    }
  }
  return bestPeriod ? `${bestPeriod.id}` : "";
}

function pickDefaultEpicId(
  asset: AssetEntry,
  epicsInScope: LifeEpic[],
): string {
  const year = assetYearHint(asset);
  if (year === null || epicsInScope.length === 0) {
    return "";
  }

  let bestEpic: LifeEpic | null = null;
  let bestScore = Number.POSITIVE_INFINITY;
  for (const epic of epicsInScope) {
    const normalizedStartYear = epic.start_sort
      ? new Date(epic.start_sort).getFullYear()
      : null;
    const normalizedEndYear = epic.end_sort
      ? new Date(epic.end_sort).getFullYear()
      : null;
    const score = dateRangeScore(
      year,
      normalizedStartYear ?? parsePeriodYearHint(epic.start_date_text),
      normalizedEndYear ?? parsePeriodYearHint(epic.end_date_text),
    );
    if (score < bestScore) {
      bestScore = score;
      bestEpic = epic;
    }
  }
  return bestEpic ? `${bestEpic.id}` : "";
}

function pickDefaultEventId(
  asset: AssetEntry,
  eventsInScope: LifeEvent[],
): string {
  if (eventsInScope.length === 0) {
    return "";
  }

  const assetDate = parseDateFromAsset(asset);
  const assetTime = assetDate?.getTime() ?? null;
  const assetYear = assetDate?.getFullYear() ?? assetYearHint(asset);
  let bestEvent: LifeEvent | null = null;
  let bestScore = Number.POSITIVE_INFINITY;

  for (const event of eventsInScope) {
    const eventTime = eventTimestampHint(event);
    let score = Number.POSITIVE_INFINITY;

    if (assetTime !== null && eventTime !== null) {
      score = Math.abs(assetTime - eventTime);
    } else if (assetYear !== null) {
      const yearHint = eventYearHint(event);
      if (yearHint !== null) {
        score = Math.abs(assetYear - yearHint) * 366;
      }
    }

    // Prefer the heavier event when dates tie or are missing.
    if (score === bestScore && bestEvent && event.weight > bestEvent.weight) {
      bestEvent = event;
      continue;
    }
    if (
      score < bestScore ||
      (bestEvent === null && Number.isFinite(score) === false)
    ) {
      bestScore = score;
      bestEvent = event;
    }
  }

  if (!bestEvent) {
    return "";
  }
  return `${bestEvent.id}`;
}

export function EventAssetList({
  assets,
  highlightedElementId,
  expandedAssetRowIds,
  setExpandedAssetRowIds,
  editingAssetTitleId,
  setEditingAssetTitleId,
  editingAssetTitleValue,
  setEditingAssetTitleValue,
  assetTitleSavingId,
  saveAssetTitle,
  editingAssetNotesId,
  setEditingAssetNotesId,
  editingAssetNotesValue,
  setEditingAssetNotesValue,
  assetNotesSavingId,
  saveAssetNotes,
  editingAssetCapturedDateId,
  setEditingAssetCapturedDateId,
  editingAssetCapturedDateValue,
  setEditingAssetCapturedDateValue,
  assetCapturedDateSavingId,
  saveAssetCapturedDate,
  resolveApiUrl,
  formatBytes,
  deleteAsset,
  eventId,
  eventFaces = [],
  renameFaceSubject,
  processPhotoAsset,
  processingPhotoAssetId = null,
  recordingForAssetId = null,
  startRecordingForAsset,
  stopRecording,
  cancelRecording,
  assetRecordingPending = {},
  isRecording = false,
  isLoading = false,
  audioDevices = [],
  showLinkControls = false,
  lifePeriods = [],
  lifeEpics = [],
  lifeEvents = [],
  createEpicInPeriod,
  createEventForLinking,
  assetLinkTargets = {},
  setAssetLinkTargets,
  linkUnlinkedAssetToEvent,
  isSavingLifeStructure = false,
}: EventAssetListProps) {
  const [previewAssetId, setPreviewAssetId] = useState<number | null>(null);
  const [modalEditingTitleId, setModalEditingTitleId] = useState<number | null>(
    null,
  );
  const [modalEditingTitleValue, setModalEditingTitleValue] = useState("");
  const [modalEditingNotesId, setModalEditingNotesId] = useState<number | null>(
    null,
  );
  const [modalEditingNotesValue, setModalEditingNotesValue] = useState("");
  const [showFaceBoxesByAssetId, setShowFaceBoxesByAssetId] = useState<
    Record<number, boolean>
  >({});
  const [assetPeriodTargets, setAssetPeriodTargets] = useState<
    Record<number, string>
  >({});
  const [assetEpicTargets, setAssetEpicTargets] = useState<
    Record<number, string>
  >({});
  const [newEpicTitleByAssetId, setNewEpicTitleByAssetId] = useState<
    Record<number, string>
  >({});
  const [newEventTitleByAssetId, setNewEventTitleByAssetId] = useState<
    Record<number, string>
  >({});
  const [editingFaceSubjectId, setEditingFaceSubjectId] = useState<
    number | null
  >(null);
  const [editingFaceSubjectValue, setEditingFaceSubjectValue] = useState("");
  const [renamingFaceSubjectId, setRenamingFaceSubjectId] = useState<
    number | null
  >(null);

  const galleryAssets = useMemo(
    () =>
      assets.filter(
        (asset) =>
          isImageAsset(asset) || isAudioAsset(asset) || isDocumentAsset(asset),
      ),
    [assets],
  );

  const previewAsset = useMemo(
    () => assets.find((asset) => asset.id === previewAssetId) || null,
    [assets, previewAssetId],
  );

  const previewAssetFaces = useMemo(() => {
    if (!previewAsset) {
      return [];
    }
    return eventFaces.filter((face) => face.asset_id === previewAsset.id);
  }, [eventFaces, previewAsset]);

  const showFaceBoxes = previewAsset
    ? Boolean(showFaceBoxesByAssetId[previewAsset.id])
    : false;
  const hasPreviewGps = Boolean(
    previewAsset &&
    previewAsset.gps_latitude !== null &&
    previewAsset.gps_longitude !== null,
  );
  const previewPositionText =
    hasPreviewGps && previewAsset
      ? `${previewAsset.gps_latitude!.toFixed(6)}, ${previewAsset.gps_longitude!.toFixed(6)}`
      : "Unavailable";
  const previewMapUrl =
    hasPreviewGps && previewAsset
      ? `https://www.google.com/maps?q=${previewAsset.gps_latitude},${previewAsset.gps_longitude}`
      : null;

  const handleCloseModal = () => {
    setPreviewAssetId(null);
    setModalEditingTitleId(null);
    setModalEditingTitleValue("");
    setModalEditingNotesId(null);
    setModalEditingNotesValue("");
    setEditingFaceSubjectId(null);
    setEditingFaceSubjectValue("");
    setRenamingFaceSubjectId(null);
  };

  const beginFaceSubjectEdit = (face: EventFaceEntry) => {
    setEditingFaceSubjectId(face.id);
    setEditingFaceSubjectValue(face.compreface_subject || "");
  };

  const cancelFaceSubjectEdit = () => {
    setEditingFaceSubjectId(null);
    setEditingFaceSubjectValue("");
  };

  const saveFaceSubjectEdit = async (faceId: number) => {
    if (!renameFaceSubject || eventId === undefined) {
      return;
    }
    const normalized = editingFaceSubjectValue.trim();
    if (!normalized) {
      return;
    }
    setRenamingFaceSubjectId(faceId);
    try {
      await renameFaceSubject(faceId, normalized, eventId);
      setEditingFaceSubjectId(null);
      setEditingFaceSubjectValue("");
    } finally {
      setRenamingFaceSubjectId(null);
    }
  };

  const canProcessPreviewPhoto = Boolean(
    previewAsset &&
    isImageAsset(previewAsset) &&
    processPhotoAsset &&
    eventId !== undefined,
  );
  const canRecordPreviewPhoto = Boolean(
    previewAsset &&
    isImageAsset(previewAsset) &&
    startRecordingForAsset &&
    eventId !== undefined,
  );
  const isRecordingThisAsset = Boolean(
    previewAsset && recordingForAssetId === previewAsset.id,
  );
  const previewPendingRecording = previewAsset
    ? assetRecordingPending[previewAsset.id]
    : undefined;
  const selectedPeriodId = previewAsset
    ? assetPeriodTargets[previewAsset.id] ||
      pickDefaultPeriodId(previewAsset, lifePeriods)
    : "";
  const eventsInPeriod = useMemo(() => {
    if (!selectedPeriodId) {
      return lifeEvents;
    }
    const periodId = Number(selectedPeriodId);
    return lifeEvents.filter((event) => event.period_id === periodId);
  }, [lifeEvents, selectedPeriodId]);
  const epicsInPeriod = useMemo(() => {
    if (!selectedPeriodId) {
      return lifeEpics;
    }
    const periodId = Number(selectedPeriodId);
    return lifeEpics.filter((epic) => epic.period_id === periodId);
  }, [lifeEpics, selectedPeriodId]);
  const selectedEpicId = previewAsset
    ? assetEpicTargets[previewAsset.id] ||
      pickDefaultEpicId(previewAsset, epicsInPeriod)
    : "";
  const eventsInScope = useMemo(() => {
    if (!selectedEpicId) {
      return eventsInPeriod;
    }
    const epicId = Number(selectedEpicId);
    return eventsInPeriod.filter((event) => event.epic_id === epicId);
  }, [eventsInPeriod, selectedEpicId]);
  const selectedEventTarget = previewAsset
    ? assetLinkTargets[previewAsset.id] ||
      pickDefaultEventId(previewAsset, eventsInScope)
    : "";
  const draftEpicTitle = previewAsset
    ? newEpicTitleByAssetId[previewAsset.id] || ""
    : "";
  const draftEventTitle = previewAsset
    ? newEventTitleByAssetId[previewAsset.id] || ""
    : "";

  return (
    <>
      {galleryAssets.length > 0 && (
        <div className="assetGridGallery">
          {galleryAssets.map((asset) => (
            <button
              key={asset.id}
              className="assetGridTile"
              type="button"
              onClick={() => setPreviewAssetId(asset.id)}
              title={
                asset.title || asset.original_filename || `Asset ${asset.id}`
              }
            >
              {isImageAsset(asset) && (
                <img
                  src={resolveApiUrl(`${asset.download_url}?download=false`)}
                  alt={
                    asset.title ||
                    asset.original_filename ||
                    `Asset ${asset.id}`
                  }
                />
              )}
              {isAudioAsset(asset) && <div className="assetAudioTile">🎵</div>}
              {isDocumentAsset(asset) && (
                <div className="assetDocTile">
                  {fileExtension(asset.original_filename)}
                </div>
              )}
            </button>
          ))}
        </div>
      )}
      {previewAsset && (
        <div
          className="assetPreviewOverlay"
          role="dialog"
          aria-modal="true"
          onClick={handleCloseModal}
        >
          <div
            className="assetPreviewModal"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="assetPreviewHeader">
              {modalEditingTitleId === previewAsset.id ? (
                <div
                  className="controls"
                  style={{ display: "flex", gap: "0.5rem", flex: 1 }}
                >
                  <input
                    className="directoryInput"
                    type="text"
                    value={modalEditingTitleValue}
                    autoFocus
                    onChange={(e) => setModalEditingTitleValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        void saveAssetTitle(
                          previewAsset.id,
                          eventId,
                          modalEditingTitleValue,
                        );
                        setModalEditingTitleId(null);
                      }
                      if (e.key === "Escape") {
                        setModalEditingTitleId(null);
                        setModalEditingTitleValue("");
                      }
                    }}
                  />
                  <button
                    className="primary"
                    type="button"
                    onClick={() => {
                      void saveAssetTitle(
                        previewAsset.id,
                        eventId,
                        modalEditingTitleValue,
                      );
                      setModalEditingTitleId(null);
                    }}
                    disabled={assetTitleSavingId === previewAsset.id}
                  >
                    Save
                  </button>
                  <button
                    className="secondary"
                    type="button"
                    onClick={() => {
                      setModalEditingTitleId(null);
                      setModalEditingTitleValue("");
                    }}
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    flex: 1,
                  }}
                >
                  <h3>
                    {previewAsset.title ||
                      previewAsset.original_filename ||
                      `Asset ${previewAsset.id}`}
                  </h3>
                  <button
                    className="secondary"
                    type="button"
                    style={{ whiteSpace: "nowrap" }}
                    onClick={() => {
                      setModalEditingTitleId(previewAsset.id);
                      setModalEditingTitleValue(
                        previewAsset.title ||
                          previewAsset.original_filename ||
                          "",
                      );
                    }}
                  >
                    Edit Title
                  </button>
                </div>
              )}
              <button
                className="secondary"
                type="button"
                onClick={handleCloseModal}
                style={{ marginLeft: "0.5rem" }}
              >
                Close
              </button>
            </div>

            <p className="meta">
              {previewAsset.kind}
              {previewAsset.size_bytes
                ? ` · ${formatBytes(previewAsset.size_bytes)}`
                : ""}
            </p>

            {isImageAsset(previewAsset) && (
              <>
                {canProcessPreviewPhoto && (
                  <div className="assetPreviewImageControls">
                    <button
                      className="secondary"
                      type="button"
                      onClick={() => {
                        if (!processPhotoAsset || eventId === undefined) {
                          return;
                        }
                        void processPhotoAsset(previewAsset.id, eventId);
                      }}
                      disabled={processingPhotoAssetId === previewAsset.id}
                    >
                      {processingPhotoAssetId === previewAsset.id
                        ? "Analyzing..."
                        : "Analyze Photo"}
                    </button>
                    {previewAssetFaces.length > 0 && (
                      <h4
                        style={{
                          cursor: "pointer",
                          userSelect: "none",
                          display: "flex",
                          alignItems: "center",
                          gap: "0.4rem",
                          margin: 0,
                          padding: "0.2rem 0",
                        }}
                        onClick={() =>
                          setShowFaceBoxesByAssetId((current) => ({
                            ...current,
                            [previewAsset.id]: !current[previewAsset.id],
                          }))
                        }
                      >
                        <span>{showFaceBoxes ? "▾" : "▸"}</span>
                        Face Boxes ({previewAssetFaces.length})
                      </h4>
                    )}
                    {canRecordPreviewPhoto && !isRecordingThisAsset && (
                      <button
                        className="secondary"
                        type="button"
                        onClick={() => {
                          if (
                            !previewAsset ||
                            !startRecordingForAsset ||
                            eventId === undefined
                          ) {
                            return;
                          }
                          void startRecordingForAsset(previewAsset.id, eventId);
                        }}
                        disabled={
                          isRecording || isLoading || audioDevices.length === 0
                        }
                      >
                        Record Voice Memory
                      </button>
                    )}
                    {canRecordPreviewPhoto && isRecordingThisAsset && (
                      <>
                        <button
                          className="secondary"
                          type="button"
                          onClick={stopRecording}
                          disabled={!isRecording || isLoading}
                        >
                          Stop &amp; Save
                        </button>
                        <button
                          className="ghost"
                          type="button"
                          onClick={cancelRecording}
                          disabled={!isRecording || isLoading}
                        >
                          Cancel
                        </button>
                      </>
                    )}
                  </div>
                )}
                {previewPendingRecording && (
                  <div
                    className="pendingRecordingInline"
                    style={{ marginTop: "0.6rem" }}
                  >
                    <audio
                      controls
                      preload="metadata"
                      src={previewPendingRecording.audioUrl}
                      style={{ flex: 1 }}
                    />
                    <span className="meta">
                      {previewPendingRecording.status === "processing" &&
                        "Processing..."}
                      {previewPendingRecording.status === "saved" &&
                        "Saved to photo ✓"}
                      {previewPendingRecording.status === "failed" &&
                        (previewPendingRecording.error ?? "Failed")}
                    </span>
                  </div>
                )}
                <div className="assetPreviewImageWrap">
                  <img
                    src={resolveApiUrl(
                      `${previewAsset.download_url}?download=false`,
                    )}
                    alt={
                      previewAsset.title ||
                      previewAsset.original_filename ||
                      `Asset ${previewAsset.id}`
                    }
                    className="assetPreviewImage"
                  />
                  {showFaceBoxes &&
                    previewAssetFaces.map((face) => {
                      const left = Math.max(
                        0,
                        Math.min(100, face.bbox_x * 100),
                      );
                      const top = Math.max(0, Math.min(100, face.bbox_y * 100));
                      const width = Math.max(
                        1,
                        Math.min(100, face.bbox_w * 100),
                      );
                      const height = Math.max(
                        1,
                        Math.min(100, face.bbox_h * 100),
                      );
                      const similarityText =
                        face.compreface_similarity !== null
                          ? formatSimilarityPercent(face.compreface_similarity)
                          : null;
                      const ageText =
                        face.compreface_age_low !== null &&
                        face.compreface_age_high !== null
                          ? `${face.compreface_age_low}-${face.compreface_age_high}`
                          : null;
                      const labelText =
                        face.person_name ||
                        face.compreface_subject ||
                        "Unknown";
                      const badgeText = similarityText
                        ? `${labelText} ${similarityText}`
                        : labelText;
                      const tooltipParts = [
                        face.person_name ? `Tagged: ${face.person_name}` : null,
                        face.compreface_subject
                          ? `CompreFace: ${face.compreface_subject}`
                          : null,
                        similarityText ? `Similarity: ${similarityText}` : null,
                        face.compreface_gender
                          ? `Gender: ${face.compreface_gender}`
                          : null,
                        ageText ? `Age: ${ageText}` : null,
                      ].filter(Boolean);
                      return (
                        <div
                          key={face.id}
                          className="assetPreviewFaceBox"
                          style={{
                            left: `${left}%`,
                            top: `${top}%`,
                            width: `${width}%`,
                            height: `${height}%`,
                          }}
                          title={tooltipParts.join(" | ") || "Detected face"}
                        >
                          <span className="assetPreviewFaceLabel">
                            {badgeText}
                          </span>
                        </div>
                      );
                    })}
                </div>
                {showFaceBoxes && previewAssetFaces.length > 0 && (
                  <div className="assetPreviewFaceMetaPanel">
                    {previewAssetFaces.map((face, index) => {
                      const ageText =
                        face.compreface_age_low !== null &&
                        face.compreface_age_high !== null
                          ? `${face.compreface_age_low}-${face.compreface_age_high}`
                          : "n/a";
                      const canEditSubject = Boolean(
                        renameFaceSubject &&
                        eventId !== undefined &&
                        face.compreface_subject,
                      );
                      const isEditingSubject = editingFaceSubjectId === face.id;
                      const isSavingSubject = renamingFaceSubjectId === face.id;
                      const faceThumbnailUrl = resolveApiUrl(
                        `/api/faces/${face.id}/thumbnail?size=96`,
                      );
                      return (
                        <article
                          key={`meta-${face.id}`}
                          className="assetPreviewFaceMetaCard"
                        >
                          <div
                            style={{
                              display: "flex",
                              gap: "0.75rem",
                              alignItems: "center",
                              marginBottom: "0.45rem",
                            }}
                          >
                            <img
                              src={faceThumbnailUrl}
                              alt={`Face ${index + 1} thumbnail`}
                              width={72}
                              height={72}
                              loading="lazy"
                              style={{
                                width: "72px",
                                height: "72px",
                                borderRadius: "8px",
                                border: "1px solid var(--border)",
                                objectFit: "cover",
                                background: "#f2f2f2",
                                flexShrink: 0,
                              }}
                            />
                            <h4 style={{ margin: 0 }}>Face {index + 1}</h4>
                          </div>
                          <p className="meta">
                            <strong>Assigned Person:</strong>{" "}
                            {face.person_name || "n/a"}
                          </p>
                          {isEditingSubject ? (
                            <div
                              className="controls"
                              style={{ marginBottom: "0.45rem" }}
                            >
                              <label
                                className="meta"
                                style={{
                                  display: "block",
                                  marginBottom: "0.25rem",
                                }}
                              >
                                <strong>CompreFace Subject</strong>
                              </label>
                              <input
                                className="directoryInput"
                                type="text"
                                value={editingFaceSubjectValue}
                                autoFocus
                                onChange={(e) =>
                                  setEditingFaceSubjectValue(e.target.value)
                                }
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") {
                                    void saveFaceSubjectEdit(face.id);
                                  }
                                  if (e.key === "Escape") {
                                    cancelFaceSubjectEdit();
                                  }
                                }}
                                disabled={isSavingSubject}
                              />
                              <div
                                style={{
                                  display: "flex",
                                  gap: "0.5rem",
                                  marginTop: "0.35rem",
                                }}
                              >
                                <button
                                  className="primary"
                                  type="button"
                                  onClick={() =>
                                    void saveFaceSubjectEdit(face.id)
                                  }
                                  disabled={
                                    isSavingSubject ||
                                    !editingFaceSubjectValue.trim()
                                  }
                                >
                                  Save
                                </button>
                                <button
                                  className="secondary"
                                  type="button"
                                  onClick={cancelFaceSubjectEdit}
                                  disabled={isSavingSubject}
                                >
                                  Cancel
                                </button>
                              </div>
                            </div>
                          ) : (
                            <div style={{ marginBottom: "0.35rem" }}>
                              <div
                                style={{
                                  display: "flex",
                                  justifyContent: "space-between",
                                  gap: "0.5rem",
                                  alignItems: "center",
                                }}
                              >
                                <p className="meta" style={{ margin: 0 }}>
                                  <strong>CompreFace Subject:</strong>{" "}
                                  {face.compreface_subject || "n/a"}
                                </p>
                                {canEditSubject && (
                                  <button
                                    className="secondary"
                                    type="button"
                                    style={{
                                      padding: "0.1rem 0.55rem",
                                      fontSize: "0.8rem",
                                    }}
                                    onClick={() => beginFaceSubjectEdit(face)}
                                  >
                                    Edit
                                  </button>
                                )}
                              </div>
                            </div>
                          )}
                          <p className="meta">
                            <strong>Similarity:</strong>{" "}
                            {formatSimilarityPercent(
                              face.compreface_similarity,
                            )}
                          </p>
                          <p className="meta">
                            <strong>Gender:</strong>{" "}
                            {face.compreface_gender || "n/a"}
                          </p>
                          <p className="meta">
                            <strong>Age Range:</strong> {ageText}
                          </p>
                          <p className="meta">
                            <strong>Detection Confidence:</strong>{" "}
                            {formatSimilarityPercent(face.confidence)}
                          </p>
                          <p className="meta">
                            <strong>BBox (normalized):</strong> x=
                            {face.bbox_x.toFixed(4)}, y={face.bbox_y.toFixed(4)}
                            , w={face.bbox_w.toFixed(4)}, h=
                            {face.bbox_h.toFixed(4)}
                          </p>
                          <details>
                            <summary>Raw CompreFace Metadata</summary>
                            <pre className="assetPreviewFaceRaw">
                              {stringifyComprefaceRaw(face.compreface_raw)}
                            </pre>
                          </details>
                        </article>
                      );
                    })}
                  </div>
                )}
              </>
            )}

            {isAudioAsset(previewAsset) && previewAsset.playback_url && (
              <audio
                controls
                preload="metadata"
                src={resolveApiUrl(previewAsset.playback_url)}
                style={{ width: "100%", marginTop: "0.6rem" }}
              />
            )}

            {isPdfAsset(previewAsset) && (
              <iframe
                title={
                  previewAsset.title ||
                  previewAsset.original_filename ||
                  `Asset ${previewAsset.id}`
                }
                src={resolveApiUrl(
                  `${previewAsset.download_url}?download=false`,
                )}
                className="assetPreviewFrame"
              />
            )}

            {!isImageAsset(previewAsset) &&
              !isAudioAsset(previewAsset) &&
              !isPdfAsset(previewAsset) && (
                <div className="assetPreviewFallback">
                  <p className="meta">
                    Preview not available for this file type. Use View or
                    Download for full details.
                  </p>
                </div>
              )}

            <div className="assetPreviewMeta">
              <p className="meta">
                <strong>Filename:</strong>{" "}
                {previewAsset.original_filename || "none"}
              </p>
              {previewAsset.gemini_suggested_title && (
                <p className="meta">
                  <strong>Gemini Suggested Title:</strong>{" "}
                  {previewAsset.gemini_suggested_title}
                </p>
              )}
              {editingAssetCapturedDateId === previewAsset.id ? (
                <div className="controls" style={{ marginTop: "0.35rem" }}>
                  <label style={{ display: "block", marginBottom: "0.25rem" }}>
                    <strong>Captured Date</strong>
                  </label>
                  <input
                    className="directoryInput"
                    type="text"
                    value={editingAssetCapturedDateValue}
                    autoFocus
                    onChange={(e) =>
                      setEditingAssetCapturedDateValue(e.target.value)
                    }
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        void saveAssetCapturedDate(
                          previewAsset.id,
                          eventId,
                          editingAssetCapturedDateValue,
                        );
                        setEditingAssetCapturedDateId(null);
                      }
                      if (e.key === "Escape") {
                        setEditingAssetCapturedDateId(null);
                        setEditingAssetCapturedDateValue("");
                      }
                    }}
                    style={{ flex: 1, width: "100%" }}
                    placeholder="e.g. April 10-12, 2026 or 2026-04-10"
                  />
                  <div
                    style={{
                      display: "flex",
                      gap: "0.5rem",
                      marginTop: "0.35rem",
                    }}
                  >
                    <button
                      className="primary"
                      type="button"
                      onClick={() => {
                        void saveAssetCapturedDate(
                          previewAsset.id,
                          eventId,
                          editingAssetCapturedDateValue,
                        );
                        setEditingAssetCapturedDateId(null);
                      }}
                      disabled={assetCapturedDateSavingId === previewAsset.id}
                    >
                      Save
                    </button>
                    <button
                      className="secondary"
                      type="button"
                      onClick={() => {
                        setEditingAssetCapturedDateId(null);
                        setEditingAssetCapturedDateValue("");
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div style={{ marginTop: "0.15rem" }}>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <p className="meta" style={{ margin: 0 }}>
                      <strong>Captured:</strong>{" "}
                      {formatAssetCaptureDate(previewAsset) || "unknown"}
                    </p>
                    <button
                      className="secondary"
                      type="button"
                      style={{ padding: "0.1rem 0.55rem", fontSize: "0.8rem" }}
                      onClick={() => {
                        setEditingAssetCapturedDateId(previewAsset.id);
                        setEditingAssetCapturedDateValue(
                          previewAsset.captured_at_text || "",
                        );
                      }}
                    >
                      Edit
                    </button>
                  </div>
                </div>
              )}
              {previewAsset.exif_place_name && (
                <p className="meta">
                  <strong>EXIF Place:</strong> {previewAsset.exif_place_name}
                </p>
              )}
              {previewAsset.reverse_geocode_location_name && (
                <p className="meta">
                  <strong>Reverse Geocode:</strong>{" "}
                  {previewAsset.reverse_geocode_location_name}
                </p>
              )}
              {previewAsset.analyzed_place_name && (
                <p className="meta">
                  <strong>Gemini Assessed Place:</strong>{" "}
                  {previewAsset.analyzed_place_name}
                </p>
              )}
              {!previewAsset.reverse_geocode_location_name &&
                previewAsset.location_name && (
                  <p className="meta">
                    <strong>Place:</strong> {previewAsset.location_name}
                  </p>
                )}
              <p className="meta">
                <strong>Position:</strong> {previewPositionText}
                {previewMapUrl && (
                  <>
                    {" "}
                    <a href={previewMapUrl} target="_blank" rel="noreferrer">
                      Map
                    </a>
                  </>
                )}
              </p>
              {!previewAsset.reverse_geocode_location_name &&
                formatAssetGps(previewAsset) && (
                  <p className="meta">
                    <strong>Location:</strong> {formatAssetGps(previewAsset)}
                  </p>
                )}
              {renderImageMetadataBadges(previewAsset)}
              {(previewAsset.image_width !== null ||
                previewAsset.image_height !== null) && (
                <p className="meta">
                  <strong>Dimensions:</strong> {previewAsset.image_width || "?"}{" "}
                  x {previewAsset.image_height || "?"}
                </p>
              )}
              {(previewAsset.camera_make || previewAsset.camera_model) && (
                <p className="meta">
                  <strong>Camera:</strong>{" "}
                  {[previewAsset.camera_make, previewAsset.camera_model]
                    .filter(Boolean)
                    .join(" ")}
                </p>
              )}
              {modalEditingNotesId === previewAsset.id ? (
                <div className="controls" style={{ marginTop: "0.35rem" }}>
                  <label style={{ display: "block", marginBottom: "0.25rem" }}>
                    <strong>Notes</strong>
                  </label>
                  <input
                    className="directoryInput"
                    type="text"
                    value={modalEditingNotesValue}
                    autoFocus
                    onChange={(e) => setModalEditingNotesValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        void saveAssetNotes(
                          previewAsset.id,
                          eventId,
                          modalEditingNotesValue,
                        );
                        setModalEditingNotesId(null);
                      }
                      if (e.key === "Escape") {
                        setModalEditingNotesId(null);
                        setModalEditingNotesValue("");
                      }
                    }}
                    style={{ flex: 1, width: "100%" }}
                  />
                  <div
                    style={{
                      display: "flex",
                      gap: "0.5rem",
                      marginTop: "0.35rem",
                    }}
                  >
                    <button
                      className="primary"
                      type="button"
                      onClick={() => {
                        void saveAssetNotes(
                          previewAsset.id,
                          eventId,
                          modalEditingNotesValue,
                        );
                        setModalEditingNotesId(null);
                      }}
                      disabled={assetNotesSavingId === previewAsset.id}
                    >
                      Save
                    </button>
                    <button
                      className="secondary"
                      type="button"
                      onClick={() => {
                        setModalEditingNotesId(null);
                        setModalEditingNotesValue("");
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div style={{ marginTop: "0.5rem" }}>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <strong>Notes</strong>
                    <button
                      className="secondary"
                      type="button"
                      style={{ padding: "0.1rem 0.55rem", fontSize: "0.8rem" }}
                      onClick={() => {
                        setModalEditingNotesId(previewAsset.id);
                        setModalEditingNotesValue(previewAsset.notes || "");
                      }}
                    >
                      Edit
                    </button>
                  </div>
                  <p className="meta">{previewAsset.notes || "none"}</p>
                </div>
              )}
              {previewAsset.text_excerpt && (
                <p className="meta assetTranscript">
                  <strong>Transcript:</strong> {previewAsset.text_excerpt}
                </p>
              )}
            </div>

            <div className="assetPreviewActions">
              <a
                className="secondary linkButton"
                href={resolveApiUrl(
                  `${previewAsset.download_url}?download=false`,
                )}
                target="_blank"
                rel="noreferrer"
              >
                View
              </a>
              <a
                className="secondary linkButton"
                href={resolveApiUrl(
                  `${previewAsset.download_url}?download=true`,
                )}
              >
                Download
              </a>
              <button
                className="ghost"
                type="button"
                onClick={() => {
                  void deleteAsset(previewAsset.id, eventId);
                  handleCloseModal();
                }}
              >
                Delete
              </button>
            </div>

            {showLinkControls &&
              setAssetLinkTargets &&
              linkUnlinkedAssetToEvent && (
                <div
                  className="lifeAssetLinkControls"
                  style={{
                    marginTop: "1rem",
                    borderTop: "1px solid var(--border)",
                    paddingTop: "0.75rem",
                  }}
                >
                  <select
                    className="directoryInput"
                    value={selectedPeriodId}
                    onChange={(e) => {
                      const nextPeriodId = e.target.value;
                      setAssetPeriodTargets((current) => ({
                        ...current,
                        [previewAsset.id]: nextPeriodId,
                      }));
                      setAssetEpicTargets((current) => {
                        const next = { ...current };
                        delete next[previewAsset.id];
                        return next;
                      });
                      setAssetLinkTargets((current) => {
                        const next = { ...current };
                        delete next[previewAsset.id];
                        return next;
                      });
                    }}
                    disabled={
                      isSavingLifeStructure ||
                      lifeEvents.length === 0 ||
                      lifePeriods.length === 0
                    }
                  >
                    <option value="">All periods</option>
                    {lifePeriods.map((period) => (
                      <option key={period.id} value={period.id}>
                        {period.title}
                      </option>
                    ))}
                  </select>
                  <select
                    className="directoryInput"
                    value={selectedEpicId}
                    onChange={(e) => {
                      const nextEpicId = e.target.value;
                      setAssetEpicTargets((current) => ({
                        ...current,
                        [previewAsset.id]: nextEpicId,
                      }));
                      setAssetLinkTargets((current) => {
                        const next = { ...current };
                        delete next[previewAsset.id];
                        return next;
                      });
                    }}
                    disabled={isSavingLifeStructure || lifeEvents.length === 0}
                    style={{ marginTop: "0.5rem" }}
                  >
                    <option value="">All epics</option>
                    {epicsInPeriod.map((epic) => (
                      <option key={epic.id} value={epic.id}>
                        {epic.title}
                      </option>
                    ))}
                  </select>
                  {createEpicInPeriod && (
                    <div
                      className="controls"
                      style={{ marginTop: "0.5rem", gap: "0.45rem" }}
                    >
                      <input
                        className="directoryInput"
                        type="text"
                        placeholder="Create new epic in selected period"
                        value={draftEpicTitle}
                        onChange={(e) =>
                          setNewEpicTitleByAssetId((current) => ({
                            ...current,
                            [previewAsset.id]: e.target.value,
                          }))
                        }
                        onKeyDown={(e) => {
                          if (e.key !== "Enter") {
                            return;
                          }
                          const title = (
                            newEpicTitleByAssetId[previewAsset.id] || ""
                          ).trim();
                          if (
                            !selectedPeriodId ||
                            !title ||
                            !createEpicInPeriod
                          ) {
                            return;
                          }
                          void createEpicInPeriod(
                            Number(selectedPeriodId),
                            title,
                          ).then((createdEpic) => {
                            if (!createdEpic) {
                              return;
                            }
                            setAssetEpicTargets((current) => ({
                              ...current,
                              [previewAsset.id]: `${createdEpic.id}`,
                            }));
                            setNewEpicTitleByAssetId((current) => ({
                              ...current,
                              [previewAsset.id]: "",
                            }));
                            setAssetLinkTargets((current) => {
                              const next = { ...current };
                              delete next[previewAsset.id];
                              return next;
                            });
                          });
                        }}
                        disabled={isSavingLifeStructure || !selectedPeriodId}
                        style={{ flex: 1 }}
                      />
                      <button
                        className="secondary"
                        type="button"
                        onClick={() => {
                          const title = (
                            newEpicTitleByAssetId[previewAsset.id] || ""
                          ).trim();
                          if (
                            !selectedPeriodId ||
                            !title ||
                            !createEpicInPeriod
                          ) {
                            return;
                          }
                          void createEpicInPeriod(
                            Number(selectedPeriodId),
                            title,
                          ).then((createdEpic) => {
                            if (!createdEpic) {
                              return;
                            }
                            setAssetEpicTargets((current) => ({
                              ...current,
                              [previewAsset.id]: `${createdEpic.id}`,
                            }));
                            setNewEpicTitleByAssetId((current) => ({
                              ...current,
                              [previewAsset.id]: "",
                            }));
                            setAssetLinkTargets((current) => {
                              const next = { ...current };
                              delete next[previewAsset.id];
                              return next;
                            });
                          });
                        }}
                        disabled={
                          isSavingLifeStructure ||
                          !selectedPeriodId ||
                          !draftEpicTitle.trim()
                        }
                        style={{ whiteSpace: "nowrap" }}
                      >
                        + Create Epic
                      </button>
                    </div>
                  )}
                  <select
                    className="directoryInput"
                    value={selectedEventTarget}
                    onChange={(e) =>
                      setAssetLinkTargets((current) => ({
                        ...current,
                        [previewAsset.id]: e.target.value,
                      }))
                    }
                    disabled={
                      isSavingLifeStructure || eventsInScope.length === 0
                    }
                    style={{ marginTop: "0.5rem" }}
                  >
                    <option value="">Select event to link to</option>
                    {eventsInScope.map((event) => (
                      <option key={event.id} value={event.id}>
                        {event.title}
                      </option>
                    ))}
                  </select>
                  {createEventForLinking && (
                    <div
                      className="controls"
                      style={{ marginTop: "0.5rem", gap: "0.45rem" }}
                    >
                      <input
                        className="directoryInput"
                        type="text"
                        placeholder="Create new event for linking"
                        value={draftEventTitle}
                        onChange={(e) =>
                          setNewEventTitleByAssetId((current) => ({
                            ...current,
                            [previewAsset.id]: e.target.value,
                          }))
                        }
                        onKeyDown={(e) => {
                          if (e.key !== "Enter") {
                            return;
                          }
                          const title = (
                            newEventTitleByAssetId[previewAsset.id] || ""
                          ).trim();
                          if (!title || !createEventForLinking) {
                            return;
                          }
                          const periodId = selectedPeriodId
                            ? Number(selectedPeriodId)
                            : null;
                          const epicId = selectedEpicId
                            ? Number(selectedEpicId)
                            : null;
                          const eventDateText =
                            previewAsset.captured_at_text || null;
                          void createEventForLinking({
                            title,
                            periodId,
                            epicId,
                            eventDateText,
                          }).then((createdEvent) => {
                            if (!createdEvent) {
                              return;
                            }
                            setNewEventTitleByAssetId((current) => ({
                              ...current,
                              [previewAsset.id]: "",
                            }));
                            setAssetLinkTargets((current) => ({
                              ...current,
                              [previewAsset.id]: `${createdEvent.id}`,
                            }));
                            if (createdEvent.period_id !== null) {
                              setAssetPeriodTargets((current) => ({
                                ...current,
                                [previewAsset.id]: `${createdEvent.period_id}`,
                              }));
                            }
                            if (createdEvent.epic_id !== null) {
                              setAssetEpicTargets((current) => ({
                                ...current,
                                [previewAsset.id]: `${createdEvent.epic_id}`,
                              }));
                            }
                          });
                        }}
                        disabled={isSavingLifeStructure}
                        style={{ flex: 1 }}
                      />
                      <button
                        className="secondary"
                        type="button"
                        onClick={() => {
                          const title = (
                            newEventTitleByAssetId[previewAsset.id] || ""
                          ).trim();
                          if (!title || !createEventForLinking) {
                            return;
                          }
                          const periodId = selectedPeriodId
                            ? Number(selectedPeriodId)
                            : null;
                          const epicId = selectedEpicId
                            ? Number(selectedEpicId)
                            : null;
                          const eventDateText =
                            previewAsset.captured_at_text || null;
                          void createEventForLinking({
                            title,
                            periodId,
                            epicId,
                            eventDateText,
                          }).then((createdEvent) => {
                            if (!createdEvent) {
                              return;
                            }
                            setNewEventTitleByAssetId((current) => ({
                              ...current,
                              [previewAsset.id]: "",
                            }));
                            setAssetLinkTargets((current) => ({
                              ...current,
                              [previewAsset.id]: `${createdEvent.id}`,
                            }));
                            if (createdEvent.period_id !== null) {
                              setAssetPeriodTargets((current) => ({
                                ...current,
                                [previewAsset.id]: `${createdEvent.period_id}`,
                              }));
                            }
                            if (createdEvent.epic_id !== null) {
                              setAssetEpicTargets((current) => ({
                                ...current,
                                [previewAsset.id]: `${createdEvent.epic_id}`,
                              }));
                            }
                          });
                        }}
                        disabled={
                          isSavingLifeStructure || !draftEventTitle.trim()
                        }
                        style={{ whiteSpace: "nowrap" }}
                      >
                        + Create Event
                      </button>
                    </div>
                  )}
                  <button
                    className="secondary"
                    type="button"
                    onClick={() => {
                      void linkUnlinkedAssetToEvent(
                        previewAsset.id,
                        selectedEventTarget
                          ? Number(selectedEventTarget)
                          : undefined,
                      );
                      handleCloseModal();
                    }}
                    disabled={!selectedEventTarget || isSavingLifeStructure}
                    style={{ marginTop: "0.5rem" }}
                  >
                    Link
                  </button>
                </div>
              )}
          </div>
        </div>
      )}
    </>
  );
}
