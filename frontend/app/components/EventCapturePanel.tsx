import { useRef, useState } from "react";
import type { DragEventHandler, RefObject } from "react";

const EVENT_AUDIO_STORAGE_KEY = "memoir.audioInputDeviceId";

type PendingRecording = {
  id: string;
  audioUrl: string;
  sizeBytes: number;
  status: "recorded" | "processing" | "saved" | "failed";
  error?: string;
};

type AudioInputDevice = {
  deviceId: string;
  label: string;
};

type EventDocumentUploadProgressItem = {
  fileName: string;
  assetId?: number;
  isPhoto?: boolean;
  status: "uploading" | "saved" | "failed";
  error?: string;
  stages?: Partial<
    Record<
      "geocoding" | "faces" | "gemini",
      "pending" | "running" | "done" | "skipped"
    >
  >;
  stageDetails?: Partial<Record<"geocoding" | "faces" | "gemini", string>>;
};

type EventCapturePanelProps = {
  eventId: number;
  isRecording: boolean;
  isLoading: boolean;
  recordingForEventId: number | null;
  audioDevices: AudioInputDevice[];
  selectedDeviceId: string;
  setSelectedDeviceId: (value: string) => void;
  audioLevel: number;
  startRecording: (eventId: number) => void;
  stopRecording: () => void;
  cancelRecording: () => void;
  eventRecordingPending: Record<number, PendingRecording>;
  eventDocumentUploadingId: number | null;
  eventDocumentErrors: Record<number, string | null>;
  eventDocumentUploadProgress: EventDocumentUploadProgressItem[];
  uploadDocumentsToEvent: (
    files: File[],
    eventId: number,
    capturedDateText: string | null,
  ) => void;
  eventAssetInputRef: RefObject<HTMLInputElement>;
  isUploadingAsset: boolean;
  isSavingLifeStructure: boolean;
  uploadAssetToActiveEvent: (
    file: File,
    capturedDateText: string | null,
  ) => void;
};

export function EventCapturePanel({
  eventId,
  isRecording,
  isLoading,
  recordingForEventId,
  audioDevices,
  selectedDeviceId,
  setSelectedDeviceId,
  audioLevel,
  startRecording,
  stopRecording,
  cancelRecording,
  eventRecordingPending,
  eventDocumentUploadingId,
  eventDocumentErrors,
  eventDocumentUploadProgress,
  uploadDocumentsToEvent,
  eventAssetInputRef,
  isUploadingAsset,
  isSavingLifeStructure,
  uploadAssetToActiveEvent,
}: EventCapturePanelProps) {
  const [isDragOverDocumentTarget, setIsDragOverDocumentTarget] =
    useState(false);
  const [capturedDateOverride, setCapturedDateOverride] = useState("");
  const documentDragDepthRef = useRef(0);

  const onDocumentDragEnter: DragEventHandler<HTMLDivElement> = (event) => {
    event.preventDefault();
    if (eventDocumentUploadingId === eventId || isRecording || isLoading) {
      return;
    }
    documentDragDepthRef.current += 1;
    setIsDragOverDocumentTarget(true);
  };

  const onDocumentDragOver: DragEventHandler<HTMLDivElement> = (event) => {
    event.preventDefault();
    if (eventDocumentUploadingId === eventId || isRecording || isLoading) {
      return;
    }
    event.dataTransfer.dropEffect = "copy";
    setIsDragOverDocumentTarget(true);
  };

  const onDocumentDragLeave: DragEventHandler<HTMLDivElement> = (event) => {
    event.preventDefault();
    documentDragDepthRef.current = Math.max(
      0,
      documentDragDepthRef.current - 1,
    );
    if (documentDragDepthRef.current === 0) {
      setIsDragOverDocumentTarget(false);
    }
  };

  const onDocumentDrop: DragEventHandler<HTMLDivElement> = (event) => {
    event.preventDefault();
    documentDragDepthRef.current = 0;
    setIsDragOverDocumentTarget(false);

    if (eventDocumentUploadingId === eventId || isRecording || isLoading) {
      return;
    }

    const droppedFiles = Array.from(event.dataTransfer.files ?? []);
    if (droppedFiles.length === 0) {
      return;
    }

    uploadDocumentsToEvent(
      droppedFiles,
      eventId,
      capturedDateOverride.trim() || null,
    );
  };

  return (
    <div className="eventCapturePanel">
      <div className="captureBlock">
        <h4 className="captureBlockTitle">Record Audio</h4>
        <div className="inputSection">
          <label className="meta" htmlFor={`event-mic-${eventId}`}>
            Input device
          </label>
          <select
            id={`event-mic-${eventId}`}
            className="micSelect"
            value={selectedDeviceId}
            onChange={(e) => {
              const nextDeviceId = e.target.value;
              setSelectedDeviceId(nextDeviceId);
              if (nextDeviceId)
                localStorage.setItem(EVENT_AUDIO_STORAGE_KEY, nextDeviceId);
              else localStorage.removeItem(EVENT_AUDIO_STORAGE_KEY);
            }}
            disabled={isRecording || isLoading || audioDevices.length === 0}
          >
            {audioDevices.length === 0 && (
              <option value="">No microphones found</option>
            )}
            {audioDevices.map((device) => (
              <option key={device.deviceId} value={device.deviceId}>
                {device.label}
              </option>
            ))}
          </select>
          <div className="levelWrap" aria-label="audio input level">
            <div className="levelTrack">
              <div
                className="levelFill"
                style={{ width: `${Math.round(audioLevel * 100)}%` }}
              />
            </div>
            <span className="meta levelText">
              Input level: {Math.round(audioLevel * 100)}%
            </span>
          </div>
        </div>
        {recordingForEventId === eventId ? (
          <>
            <p className="meta" style={{ marginBottom: "0.35rem" }}>
              Recording... <span className="badge">live</span>
            </p>
            <div className="controls">
              <button
                className="secondary"
                type="button"
                onClick={stopRecording}
                disabled={!isRecording || isLoading}
              >
                Stop &amp; Process
              </button>
              <button
                className="ghost"
                type="button"
                onClick={cancelRecording}
                disabled={!isRecording || isLoading}
              >
                Cancel
              </button>
            </div>
          </>
        ) : (
          <div className="controls">
            <button
              className="primary"
              type="button"
              onClick={() => startRecording(eventId)}
              disabled={isRecording || isLoading || audioDevices.length === 0}
            >
              Start Recording
            </button>
          </div>
        )}
        {eventRecordingPending[eventId] && (
          <div
            className="pendingRecordingInline"
            style={{ marginTop: "0.5rem" }}
          >
            <audio
              controls
              preload="metadata"
              src={eventRecordingPending[eventId].audioUrl}
              style={{ flex: 1 }}
            />
            <span className="meta">
              {eventRecordingPending[eventId].status === "processing" &&
                "Processing..."}
              {eventRecordingPending[eventId].status === "saved" && "Saved ✓"}
              {eventRecordingPending[eventId].status === "failed" &&
                (eventRecordingPending[eventId].error ?? "Failed")}
            </span>
          </div>
        )}
      </div>
      <div className="captureBlock">
        <h4 className="captureBlockTitle">Upload a Document</h4>
        <p className="meta">
          Upload one or many PDFs, images, or text files and link them directly
          to this event as assets.
        </p>
        <input
          className="directoryInput"
          type="text"
          placeholder="Captured date override (e.g. Apr 2, 1988 or 1988-04-02)"
          value={capturedDateOverride}
          onChange={(e) => setCapturedDateOverride(e.target.value)}
          disabled={
            eventDocumentUploadingId === eventId || isRecording || isLoading
          }
          style={{ marginBottom: "0.45rem" }}
        />
        <div className="controls">
          <input
            type="file"
            multiple
            accept=".pdf,.jpg,.jpeg,.png,.gif,.webp,.txt"
            disabled={
              eventDocumentUploadingId === eventId || isRecording || isLoading
            }
            onChange={(e) => {
              const files = Array.from(e.target.files ?? []);
              if (files.length > 0) {
                uploadDocumentsToEvent(
                  files,
                  eventId,
                  capturedDateOverride.trim() || null,
                );
              }
              e.currentTarget.value = "";
            }}
            style={{ flex: 1 }}
          />
        </div>
        <div
          className={`pasteTarget ${isDragOverDocumentTarget ? "dragOver" : ""}`}
          role="button"
          tabIndex={0}
          onDragEnter={onDocumentDragEnter}
          onDragOver={onDocumentDragOver}
          onDragLeave={onDocumentDragLeave}
          onDrop={onDocumentDrop}
          aria-label="Drop files to upload to this event"
        >
          <p className="pasteTargetTitle">Drop Files Here</p>
          <p className="meta">
            Drag and drop multiple photos or documents to upload them all to
            this event.
          </p>
        </div>
        {eventDocumentUploadProgress.length > 0 && (
          <div style={{ marginTop: "0.5rem" }}>
            <p className="meta" style={{ marginBottom: "0.25rem" }}>
              Upload Progress
            </p>
            <ul style={{ margin: 0, paddingLeft: "1rem" }}>
              {eventDocumentUploadProgress.map((item, index) => (
                <li
                  key={`${item.fileName}-${index}`}
                  className="meta"
                  style={{ marginBottom: "0.25rem" }}
                >
                  <span>
                    {item.status === "uploading" && "Uploading… "}
                    {item.status === "saved" && "Saved ✓ "}
                    {item.status === "failed" && "Failed ✗ "}
                    {item.fileName}
                    {item.status === "failed" && item.error
                      ? ` (${item.error})`
                      : ""}
                  </span>
                  {item.stages && (
                    <span
                      style={{
                        marginLeft: "0.5rem",
                        display: "inline-flex",
                        gap: "0.4rem",
                        fontSize: "0.75em",
                        opacity: 0.8,
                      }}
                    >
                      {(["geocoding", "faces", "gemini"] as const).map(
                        (stage) => {
                          const s = item.stages?.[stage];
                          if (!s) return null;
                          const labels: Record<string, string> = {
                            geocoding: "📍",
                            faces: "👤",
                            gemini: "✨",
                          };
                          const detail = item.stageDetails?.[stage];
                          const icon = labels[stage];
                          if (s === "pending")
                            return (
                              <span
                                key={stage}
                                title={stage}
                                style={{ opacity: 0.4 }}
                              >
                                {icon}…
                              </span>
                            );
                          if (s === "running")
                            return (
                              <span key={stage} title={stage}>
                                {icon}…
                              </span>
                            );
                          if (s === "done")
                            return (
                              <span
                                key={stage}
                                title={detail ?? stage}
                                style={{ color: "var(--success, green)" }}
                              >
                                {icon}
                                {detail ? ` ${detail}` : " ✓"}
                              </span>
                            );
                          if (s === "skipped")
                            return (
                              <span
                                key={stage}
                                title={`${stage} (already done)`}
                                style={{ opacity: 0.5 }}
                              >
                                {icon} ✓
                              </span>
                            );
                          return null;
                        },
                      )}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
        {eventDocumentUploadingId === eventId && (
          <p className="status">Uploading...</p>
        )}
        {eventDocumentErrors[eventId] && (
          <p className="status" style={{ color: "var(--error, #c00)" }}>
            {eventDocumentErrors[eventId]}
          </p>
        )}
      </div>
      <div className="captureBlock">
        <h4 className="captureBlockTitle">Upload Asset</h4>
        <p className="meta">
          Upload a photo, audio, or file directly as an asset without AI
          analysis.
        </p>
        <input
          className="directoryInput"
          type="text"
          placeholder="Captured date override (optional)"
          value={capturedDateOverride}
          onChange={(e) => setCapturedDateOverride(e.target.value)}
          disabled={
            isUploadingAsset ||
            isSavingLifeStructure ||
            isRecording ||
            isLoading
          }
          style={{ marginBottom: "0.45rem" }}
        />
        <input
          ref={eventAssetInputRef}
          type="file"
          accept=".pdf,.jpg,.jpeg,.png,.gif,.webp,.txt,.mp3,.wav,.m4a,.ogg,.webm,audio/*"
          disabled={
            isUploadingAsset ||
            isSavingLifeStructure ||
            isRecording ||
            isLoading
          }
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file)
              uploadAssetToActiveEvent(
                file,
                capturedDateOverride.trim() || null,
              );
          }}
        />
      </div>
    </div>
  );
}
