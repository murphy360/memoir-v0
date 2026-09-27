import { ReactNode, useEffect, useMemo, useState } from "react";
import type { EventFaceEntry } from "../types";

type ModalAction = {
  label: string;
  onClick: () => void;
  variant?: "primary" | "secondary" | "ghost";
  disabled?: boolean;
};

type PhotoDetailsModalProps = {
  isOpen: boolean;
  imageUrl: string;
  title: string;
  onClose: () => void;
  faces?: EventFaceEntry[];
  focusFaceId?: number | null;
  filename?: string | null;
  capturedText?: string | null;
  positionText?: string | null;
  dimensionsText?: string | null;
  notes?: string | null;
  topActions?: ModalAction[];
  footerActions?: ModalAction[];
  extraMeta?: ReactNode;
};

type FaceImageSize = {
  width: number;
  height: number;
};

function getFaceBox(
  face: EventFaceEntry,
  imageSize: FaceImageSize,
): { x: number; y: number; w: number; h: number } | null {
  const looksNormalized =
    face.bbox_x >= 0 &&
    face.bbox_y >= 0 &&
    face.bbox_w > 0 &&
    face.bbox_h > 0 &&
    face.bbox_x <= 1 &&
    face.bbox_y <= 1 &&
    face.bbox_w <= 1 &&
    face.bbox_h <= 1;

  const x = looksNormalized ? face.bbox_x * imageSize.width : face.bbox_x;
  const y = looksNormalized ? face.bbox_y * imageSize.height : face.bbox_y;
  const w = looksNormalized ? face.bbox_w * imageSize.width : face.bbox_w;
  const h = looksNormalized ? face.bbox_h * imageSize.height : face.bbox_h;

  if (w <= 0 || h <= 0) {
    return null;
  }

  const maxX = Math.max(0, imageSize.width - 1);
  const maxY = Math.max(0, imageSize.height - 1);
  const clampedX = Math.min(Math.max(0, x), maxX);
  const clampedY = Math.min(Math.max(0, y), maxY);
  const clampedW = Math.min(w, imageSize.width - clampedX);
  const clampedH = Math.min(h, imageSize.height - clampedY);

  if (clampedW <= 0 || clampedH <= 0) {
    return null;
  }

  return {
    x: clampedX,
    y: clampedY,
    w: clampedW,
    h: clampedH,
  };
}

export function PhotoDetailsModal({
  isOpen,
  imageUrl,
  title,
  onClose,
  faces = [],
  focusFaceId = null,
  filename = null,
  capturedText = null,
  positionText = null,
  dimensionsText = null,
  notes = null,
  topActions = [],
  footerActions = [],
  extraMeta = null,
}: PhotoDetailsModalProps) {
  const [showFaceBoxes, setShowFaceBoxes] = useState(true);
  const [imageSize, setImageSize] = useState<FaceImageSize | null>(null);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  const faceBoxes = useMemo(() => {
    if (!imageSize) {
      return [] as Array<{
        face: EventFaceEntry;
        box: { x: number; y: number; w: number; h: number };
      }>;
    }
    return faces
      .map((face) => {
        const box = getFaceBox(face, imageSize);
        return box ? { face, box } : null;
      })
      .filter(
        (
          entry,
        ): entry is {
          face: EventFaceEntry;
          box: { x: number; y: number; w: number; h: number };
        } => Boolean(entry),
      );
  }, [faces, imageSize]);

  if (!isOpen) {
    return null;
  }

  return (
    <div
      className="assetPreviewOverlay"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="assetPreviewModal"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="assetPreviewHeader">
          <h3>{title}</h3>
          <button className="secondary" type="button" onClick={onClose}>
            Close
          </button>
        </div>

        {(faces.length > 0 || topActions.length > 0) && (
          <div className="assetPreviewImageControls">
            {faces.length > 0 && (
              <button
                className="secondary"
                type="button"
                onClick={() => setShowFaceBoxes((current) => !current)}
              >
                {showFaceBoxes ? "Hide" : "Show"} Face Boxes ({faces.length})
              </button>
            )}
            {topActions.map((action) => (
              <button
                key={action.label}
                className={action.variant || "secondary"}
                type="button"
                onClick={action.onClick}
                disabled={action.disabled}
              >
                {action.label}
              </button>
            ))}
          </div>
        )}

        <div className="assetPreviewImageWrap">
          <img
            src={imageUrl}
            alt={title}
            className="assetPreviewImage"
            onLoad={(event) => {
              const width = event.currentTarget.naturalWidth;
              const height = event.currentTarget.naturalHeight;
              if (width > 0 && height > 0) {
                setImageSize({ width, height });
              }
            }}
          />
          {showFaceBoxes && imageSize && (
            <svg
              className="personFaceOverlay"
              viewBox={`0 0 ${imageSize.width} ${imageSize.height}`}
              aria-hidden="true"
            >
              {faceBoxes.map(({ face, box }) => (
                <rect
                  key={face.id}
                  x={box.x}
                  y={box.y}
                  width={box.w}
                  height={box.h}
                  className={
                    face.id === focusFaceId
                      ? "personFaceOverlayBox personFaceOverlayBoxFocus"
                      : "personFaceOverlayBox personFaceOverlayBoxStrong"
                  }
                />
              ))}
            </svg>
          )}
        </div>

        <div className="assetPreviewMeta">
          {filename && (
            <p className="meta">
              <strong>Filename:</strong> {filename}
            </p>
          )}
          <p className="meta">
            <strong>Captured:</strong> {capturedText || "unknown"}
          </p>
          <p className="meta">
            <strong>Position:</strong> {positionText || "Unavailable"}
          </p>
          {dimensionsText && (
            <p className="meta">
              <strong>Dimensions:</strong> {dimensionsText}
            </p>
          )}
          <p className="meta">
            <strong>Notes:</strong> {notes || "none"}
          </p>
          {extraMeta}
        </div>

        {footerActions.length > 0 && (
          <div className="assetPreviewActions">
            {footerActions.map((action) => (
              <button
                key={`footer-${action.label}`}
                className={action.variant || "secondary"}
                type="button"
                onClick={action.onClick}
                disabled={action.disabled}
              >
                {action.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
