import type { ClipboardEventHandler, DragEventHandler } from "react";
import { useRef, useState } from "react";
import { CLIPBOARD_IMAGE_EXTENSIONS } from "../lib/memoirUi";

function asClipboardImageFile(blob: Blob, fallbackNamePrefix: string): File {
  const mimeType = (blob.type || "").toLowerCase();
  const extension = CLIPBOARD_IMAGE_EXTENSIONS[mimeType] || ".png";
  const timestamp = Date.now();
  const fileName = `${fallbackNamePrefix}-${timestamp}${extension}`;
  return new File([blob], fileName, { type: mimeType || "image/png" });
}

function extractImageFromClipboardData(data: DataTransfer | null): File | null {
  if (!data) {
    return null;
  }

  for (const item of Array.from(data.items)) {
    if (item.kind !== "file" || !item.type.startsWith("image/")) {
      continue;
    }
    const file = item.getAsFile();
    if (file) {
      return asClipboardImageFile(file, "screen-clipping");
    }
  }

  return null;
}

function dataTransferHasFiles(dataTransfer: DataTransfer | null): boolean {
  if (!dataTransfer) {
    return false;
  }
  if (dataTransfer.files && dataTransfer.files.length > 0) {
    return true;
  }
  return Array.from(dataTransfer.items || []).some(
    (item) => item.kind === "file",
  );
}

type UseDocumentIntakeArgs = {
  isUploadingDocument: boolean;
  isRecording: boolean;
  isLoading: boolean;
  uploadDocument: (file: File) => Promise<void>;
};

export function useDocumentIntake({
  isUploadingDocument,
  isRecording,
  isLoading,
  uploadDocument,
}: UseDocumentIntakeArgs) {
  const [isReadingClipboard, setIsReadingClipboard] = useState(false);
  const [isDragOverDocumentTarget, setIsDragOverDocumentTarget] =
    useState(false);
  const [documentUploadError, setDocumentUploadError] = useState<string | null>(
    null,
  );
  const documentDragDepthRef = useRef(0);

  async function pasteImageFromClipboard() {
    if (!navigator.clipboard?.read) {
      setDocumentUploadError(
        "Clipboard image reading is not available in this browser. Click the paste box and press Ctrl+V instead.",
      );
      return;
    }

    setIsReadingClipboard(true);
    setDocumentUploadError(null);

    try {
      const items = await navigator.clipboard.read();
      let matchedBlob: Blob | null = null;

      for (const item of items) {
        const imageType = item.types.find((type) => type.startsWith("image/"));
        if (!imageType) {
          continue;
        }
        matchedBlob = await item.getType(imageType);
        break;
      }

      if (!matchedBlob) {
        setDocumentUploadError(
          "No image found in clipboard. Copy a screen clipping, then try again.",
        );
        return;
      }

      await uploadDocument(
        asClipboardImageFile(matchedBlob, "screen-clipping"),
      );
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Could not read from clipboard.";
      setDocumentUploadError(message);
    } finally {
      setIsReadingClipboard(false);
    }
  }

  const onDocumentPasteZonePaste: ClipboardEventHandler<HTMLDivElement> = (
    event,
  ) => {
    if (isUploadingDocument || isRecording || isLoading) {
      return;
    }

    const imageFile = extractImageFromClipboardData(event.clipboardData);
    if (!imageFile) {
      return;
    }

    event.preventDefault();
    void uploadDocument(imageFile);
  };

  const onDocumentDragEnter: DragEventHandler<HTMLDivElement> = (event) => {
    event.preventDefault();
    if (isUploadingDocument || isReadingClipboard || isRecording || isLoading) {
      return;
    }

    documentDragDepthRef.current += 1;
    if (dataTransferHasFiles(event.dataTransfer)) {
      setIsDragOverDocumentTarget(true);
    }
  };

  const onDocumentDragOver: DragEventHandler<HTMLDivElement> = (event) => {
    event.preventDefault();
    if (isUploadingDocument || isReadingClipboard || isRecording || isLoading) {
      return;
    }

    if (dataTransferHasFiles(event.dataTransfer)) {
      event.dataTransfer.dropEffect = "copy";
      setIsDragOverDocumentTarget(true);
    }
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

    if (isUploadingDocument || isReadingClipboard || isRecording || isLoading) {
      return;
    }

    const droppedFile = event.dataTransfer.files?.[0] || null;
    if (!droppedFile) {
      setDocumentUploadError(
        "No file detected. Drop a PDF, image, or text file.",
      );
      return;
    }

    void uploadDocument(droppedFile);
  };

  return {
    isReadingClipboard,
    setIsReadingClipboard,
    isDragOverDocumentTarget,
    documentUploadError,
    setDocumentUploadError,
    pasteImageFromClipboard,
    onDocumentPasteZonePaste,
    onDocumentDragEnter,
    onDocumentDragOver,
    onDocumentDragLeave,
    onDocumentDrop,
  };
}
