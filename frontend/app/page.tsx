"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { CaptureSidebar } from "./components/CaptureSidebar";
import { DirectorySidebar } from "./components/DirectorySidebar";
import { EpicCard } from "./components/EpicCard";
import { EventCard } from "./components/EventCard";
import { LifePeriodCard } from "./components/LifePeriodCard";
import { MemoryCard } from "./components/MemoryCard";
import { PeriodComposer } from "./components/PeriodComposer";
import { UnlinkedAssetsInbox } from "./components/UnlinkedAssetsInbox";
import {
  AssetEntry,
  EventFaceEntry,
  LifeEpic,
  LifeEvent,
  LifeThread,
  MemoryEntry,
  Question,
  LifePeriodAnalysis,
} from "./types";
import {
  type TimelineBundle,
  analyzeLifePeriod,
  applyResearchSuggestionById,
  answerQuestionWithMemory,
  assignRecorderPerson,
  createDirectoryEntry as createDirectoryEntryRequest,
  createEvent,
  createMemoryFromAudioBlob,
  createPeriod,
  deleteAsset as deleteAssetById,
  deleteDirectoryEntry as deleteDirectoryEntryRequest,
  deleteEventById,
  deleteMemoryById,
  deletePeriodById,
  dismissQuestionById,
  dismissResearchSuggestionById,
  assignFacePerson,
  createPersonEntry,
  renameFaceSubject,
  deleteFace,
  fetchEventAssets,
  fetchEventFaces,
  linkAssetToEvent,
  mergeEventInto,
  mergePeopleEntries,
  linkPersonToCompreface,
  mergePeriodInto,
  reanalyzeMemoryById,
  removePersonAlias as removePersonAliasRequest,
  renameDirectoryEntry as renameDirectoryEntryRequest,
  updatePeriodById,
  resolveApiUrl,
  saveMainCharacterName as saveMainCharacterNameRequest,
  splitPersonEntry as splitPersonEntryRequest,
  addPersonAlias as addPersonAliasRequest,
  updateEventById,
  updateEpicById,
  updateMemoryTitle as updateMemoryTitleById,
  updateAssetNotes as updateAssetNotesById,
  updateAssetCapturedDate as updateAssetCapturedDateById,
  updateAssetTitle as updateAssetTitleById,
  processEventPhotoAssets,
  processSinglePhotoAsset,
  uploadAsset,
  createThread,
  createEpic,
  deleteThread,
  deleteEpic,
  renameThread,
  API_BASE,
} from "./lib/memoirApi";
import {
  AUDIO_DEVICE_STORAGE_KEY,
  displayPeriodSummary,
  formatBytes,
} from "./lib/memoirUi";
import { useTimelineData } from "./hooks/useTimelineData";
import { useEventActions } from "./hooks/useEventActions";
import { useDocumentIntake } from "./hooks/useDocumentIntake";
import { useRecordingController } from "./hooks/useRecordingController";
import {
  PeriodSortMode,
  UNASSIGNED_PERIOD_VALUE,
  compareDateStringsDesc,
  parseOptionalDateTimestamp,
} from "./lib/homePageHelpers";

type PendingRecording = {
  id: string;
  audioUrl: string;
  sizeBytes: number;
  status: "recorded" | "processing" | "saved" | "failed";
  error?: string;
};

type AnalysisStage = "geocoding" | "faces" | "gemini";
type StageStatus = "pending" | "running" | "done" | "skipped";

type EventDocumentUploadProgressItem = {
  fileName: string;
  assetId?: number;
  isPhoto?: boolean;
  status: "uploading" | "saved" | "failed";
  error?: string;
  stages?: Partial<Record<AnalysisStage, StageStatus>>;
  stageDetails?: Partial<Record<AnalysisStage, string>>;
};

export default function HomePage() {
  const [isDirectoryDrawerOpen, setIsDirectoryDrawerOpen] = useState(false);
  const [isCaptureDrawerOpen, setIsCaptureDrawerOpen] = useState(false);
  const [activeDirectoryTab, setActiveDirectoryTab] = useState<
    "people" | "places"
  >("people");
  const [directorySearch, setDirectorySearch] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [status, setStatus] = useState("Ready to record a memory.");
  const {
    timeline,
    lifePeriods,
    lifeThreads,
    setLifeThreads,
    lifeEpics,
    setLifeEpics,
    lifeEvents,
    unlinkedAssets,
    setUnlinkedAssets,
    questions,
    setQuestions,
    peopleDirectory,
    placesDirectory,
    mainCharacterName,
    setMainCharacterName,
    loadTimeline,
  } = useTimelineData({ setStatus });
  const [activeEventId, setActiveEventId] = useState<number | null>(null);
  const [activeEventAssets, setActiveEventAssets] = useState<AssetEntry[]>([]);
  const [activeEventFaces, setActiveEventFaces] = useState<EventFaceEntry[]>(
    [],
  );
  const [assigningFaceId, setAssigningFaceId] = useState<number | null>(null);
  const [isSavingLifeStructure, setIsSavingLifeStructure] = useState(false);
  const [isUploadingAsset, setIsUploadingAsset] = useState(false);
  const [assetLinkTargets, setAssetLinkTargets] = useState<
    Record<number, string>
  >({});
  const [eventMergeTargets, setEventMergeTargets] = useState<
    Record<number, string>
  >({});
  const [eventMoveTargets, setEventMoveTargets] = useState<
    Record<number, string>
  >({});
  const [newPeriodTitle, setNewPeriodTitle] = useState("");
  const [newPeriodStart, setNewPeriodStart] = useState("");
  const [newPeriodEnd, setNewPeriodEnd] = useState("");
  const [newPeriodSummary, setNewPeriodSummary] = useState("");
  const [newEventTitle, setNewEventTitle] = useState("");
  const [newEventDateText, setNewEventDateText] = useState("");
  const [newEventDescription, setNewEventDescription] = useState("");
  const [newEventPeriodId, setNewEventPeriodId] = useState("");
  const [editingAssetTitleId, setEditingAssetTitleId] = useState<number | null>(
    null,
  );
  const [editingAssetTitleValue, setEditingAssetTitleValue] = useState("");
  const [assetTitleSavingId, setAssetTitleSavingId] = useState<number | null>(
    null,
  );
  const [processingEventPhotosId, setProcessingEventPhotosId] = useState<
    number | null
  >(null);
  const [processingPhotoAssetId, setProcessingPhotoAssetId] = useState<
    number | null
  >(null);
  const [editingAssetNotesId, setEditingAssetNotesId] = useState<number | null>(
    null,
  );
  const [editingAssetNotesValue, setEditingAssetNotesValue] = useState("");
  const [assetNotesSavingId, setAssetNotesSavingId] = useState<number | null>(
    null,
  );
  const [editingAssetCapturedDateId, setEditingAssetCapturedDateId] = useState<
    number | null
  >(null);
  const [editingAssetCapturedDateValue, setEditingAssetCapturedDateValue] =
    useState("");
  const [assetCapturedDateSavingId, setAssetCapturedDateSavingId] = useState<
    number | null
  >(null);
  const [pendingRecording, setPendingRecording] =
    useState<PendingRecording | null>(null);
  const [recordingForEventId, setRecordingForEventId] = useState<number | null>(
    null,
  );
  const [recordingForAssetId, setRecordingForAssetId] = useState<number | null>(
    null,
  );
  const [eventRecordingPending, setEventRecordingPending] = useState<
    Record<number, PendingRecording>
  >({});
  const [assetRecordingPending, setAssetRecordingPending] = useState<
    Record<number, PendingRecording>
  >({});
  const [isLoading, setIsLoading] = useState(false);
  const [highlightedElementId, setHighlightedElementId] = useState<
    string | null
  >(null);
  const [memoryActionId, setMemoryActionId] = useState<number | null>(null);
  const [directoryBusyKey, setDirectoryBusyKey] = useState<string | null>(null);
  const [isPeriodComposerOpen, setIsPeriodComposerOpen] = useState(false);
  const [expandedPeriods, setExpandedPeriods] = useState<
    Record<number, boolean>
  >({});
  const [expandedEpics, setExpandedEpics] = useState<Record<number, boolean>>(
    {},
  );
  const [eventDraftsByPeriod, setEventDraftsByPeriod] = useState<
    Record<
      number,
      { title: string; dateText: string; description: string; location: string }
    >
  >({});
  const [periodAnalysisById, setPeriodAnalysisById] = useState<
    Record<number, LifePeriodAnalysis | null>
  >({});
  const [periodAnalysisBusyId, setPeriodAnalysisBusyId] = useState<
    number | null
  >(null);
  const [editingPeriodTitleId, setEditingPeriodTitleId] = useState<
    number | null
  >(null);
  const [editingPeriodTitleValue, setEditingPeriodTitleValue] = useState("");
  const [editingPeriodDatesId, setEditingPeriodDatesId] = useState<
    number | null
  >(null);
  const [editingPeriodStartValue, setEditingPeriodStartValue] = useState("");
  const [editingPeriodEndValue, setEditingPeriodEndValue] = useState("");
  const [editingEventTitleId, setEditingEventTitleId] = useState<number | null>(
    null,
  );
  const [editingEventTitleValue, setEditingEventTitleValue] = useState("");
  const [editingEventDateId, setEditingEventDateId] = useState<number | null>(
    null,
  );
  const [editingEventDateValue, setEditingEventDateValue] = useState("");
  const [editingEventLocationId, setEditingEventLocationId] = useState<
    number | null
  >(null);
  const [editingEventLocationValue, setEditingEventLocationValue] =
    useState("");
  const [editingMemoryTitleId, setEditingMemoryTitleId] = useState<
    number | null
  >(null);
  const [editingMemoryTitleValue, setEditingMemoryTitleValue] = useState("");
  const [memoryTitleSavingId, setMemoryTitleSavingId] = useState<number | null>(
    null,
  );
  const [expandedMemoryRowIds, setExpandedMemoryRowIds] = useState<Set<number>>(
    new Set(),
  );
  const [expandedAssetRowIds, setExpandedAssetRowIds] = useState<Set<number>>(
    new Set(),
  );
  const [eventCapturePanelOpenIds, setEventCapturePanelOpenIds] = useState<
    Set<number>
  >(new Set());
  const [eventDocumentUploadingId, setEventDocumentUploadingId] = useState<
    number | null
  >(null);
  const [eventDocumentErrors, setEventDocumentErrors] = useState<
    Record<number, string | null>
  >({});
  const [
    eventDocumentUploadProgressByEventId,
    setEventDocumentUploadProgressByEventId,
  ] = useState<Record<number, EventDocumentUploadProgressItem[]>>({});
  const [mergingPeriodId, setMergingPeriodId] = useState<number | null>(null);
  const [periodSortMode, setPeriodSortMode] =
    useState<PeriodSortMode>("timeline-asc");

  // Threads state
  const [isThreadComposerOpen, setIsThreadComposerOpen] = useState(false);
  const [newThreadTitle, setNewThreadTitle] = useState("");
  const [isSavingThread, setIsSavingThread] = useState(false);
  const [editingThreadTitleId, setEditingThreadTitleId] = useState<
    number | null
  >(null);
  const [editingThreadTitleValue, setEditingThreadTitleValue] = useState("");

  // Epics state
  const [epicDraftsByPeriod, setEpicDraftsByPeriod] = useState<
    Record<number, string>
  >({});
  const [editingEpicTitleId, setEditingEpicTitleId] = useState<number | null>(
    null,
  );
  const [editingEpicTitleValue, setEditingEpicTitleValue] = useState("");

  const [activeQuestion, setActiveQuestion] = useState<Question | null>(null);

  const [showCharacterInput, setShowCharacterInput] = useState(false);
  const [characterInputValue, setCharacterInputValue] = useState("");
  const [isSavingCharacter, setIsSavingCharacter] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const [isUploadingDocument, setIsUploadingDocument] = useState(false);
  const documentFileInputRef = useRef<HTMLInputElement | null>(null);
  const eventAssetInputRef = useRef<HTMLInputElement | null>(null);
  const focusClearTimerRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const shouldDiscardRecordingRef = useRef(false);
  const currentPreviewAudioUrlRef = useRef<string | null>(null);

  const {
    audioDevices,
    selectedDeviceId,
    setSelectedDeviceId,
    audioLevel,
    refreshAudioDevices,
    startAudioLevelMonitoring,
    stopAudioLevelMonitoring,
  } = useRecordingController(setStatus);

  const eventCountByPeriod = useMemo(() => {
    const counts: Record<number, number> = {};
    for (const event of lifeEvents) {
      if (event.period_id === null) {
        continue;
      }
      counts[event.period_id] = (counts[event.period_id] ?? 0) + 1;
    }
    return counts;
  }, [lifeEvents]);

  const sortedLifePeriods = useMemo(() => {
    const periods = [...lifePeriods];
    periods.sort((left, right) => {
      const leftStartTime =
        parseOptionalDateTimestamp(left.start_sort) ??
        parseOptionalDateTimestamp(left.start_date_text);
      const rightStartTime =
        parseOptionalDateTimestamp(right.start_sort) ??
        parseOptionalDateTimestamp(right.start_date_text);
      const leftEndTime =
        parseOptionalDateTimestamp(left.end_sort) ??
        parseOptionalDateTimestamp(left.end_date_text);
      const rightEndTime =
        parseOptionalDateTimestamp(right.end_sort) ??
        parseOptionalDateTimestamp(right.end_date_text);
      const leftEventCount =
        eventCountByPeriod[left.id] ?? left.event_count ?? 0;
      const rightEventCount =
        eventCountByPeriod[right.id] ?? right.event_count ?? 0;

      if (
        periodSortMode === "timeline-asc" ||
        periodSortMode === "timeline-desc"
      ) {
        if (leftStartTime === null && rightStartTime !== null) {
          return 1;
        }
        if (leftStartTime !== null && rightStartTime === null) {
          return -1;
        }
        if (
          leftStartTime !== null &&
          rightStartTime !== null &&
          leftStartTime !== rightStartTime
        ) {
          return periodSortMode === "timeline-asc"
            ? leftStartTime - rightStartTime
            : rightStartTime - leftStartTime;
        }
        if (leftEndTime === null && rightEndTime !== null) {
          return 1;
        }
        if (leftEndTime !== null && rightEndTime === null) {
          return -1;
        }
        if (
          leftEndTime !== null &&
          rightEndTime !== null &&
          leftEndTime !== rightEndTime
        ) {
          return periodSortMode === "timeline-asc"
            ? leftEndTime - rightEndTime
            : rightEndTime - leftEndTime;
        }
      }

      if (periodSortMode === "events-desc") {
        if (leftEventCount !== rightEventCount) {
          return rightEventCount - leftEventCount;
        }
      }

      if (periodSortMode === "updated-desc") {
        const updatedCompare = compareDateStringsDesc(
          left.updated_at,
          right.updated_at,
        );
        if (updatedCompare !== 0) {
          return updatedCompare;
        }
      }

      if (periodSortMode === "title-asc") {
        const titleCompare = left.title.localeCompare(right.title, undefined, {
          sensitivity: "base",
        });
        if (titleCompare !== 0) {
          return titleCompare;
        }
      }

      const createdCompare = compareDateStringsDesc(
        left.created_at,
        right.created_at,
      );
      if (createdCompare !== 0) {
        return createdCompare;
      }
      return left.title.localeCompare(right.title, undefined, {
        sensitivity: "base",
      });
    });
    return periods;
  }, [eventCountByPeriod, lifePeriods, periodSortMode]);

  function markAndScrollTo(elementId: string, delayMs = 120) {
    window.setTimeout(() => {
      const element = document.getElementById(elementId);
      if (!element) {
        return;
      }

      element.scrollIntoView({ behavior: "smooth", block: "center" });
      setHighlightedElementId(elementId);

      if (focusClearTimerRef.current !== null) {
        window.clearTimeout(focusClearTimerRef.current);
      }
      focusClearTimerRef.current = window.setTimeout(() => {
        setHighlightedElementId((current) =>
          current === elementId ? null : current,
        );
      }, 3200);
    }, delayMs);
  }

  function focusEventInTimeline(eventId: number, periodId: number | null) {
    if (periodId !== null) {
      setExpandedPeriods((current) => ({ ...current, [periodId]: true }));
    }
    setActiveEventId(eventId);
    void loadAssetsForEvent(eventId);
    markAndScrollTo(`event-card-${eventId}`, periodId !== null ? 220 : 120);
  }

  function focusMemoryInTimeline(
    memoryId: number,
    data: TimelineBundle | null,
  ) {
    const linkedEvent =
      data?.events?.find((event) =>
        event.linked_memory_ids.includes(memoryId),
      ) || null;
    if (linkedEvent) {
      focusEventInTimeline(linkedEvent.id, linkedEvent.period_id);
      markAndScrollTo(`memory-card-${memoryId}`, 320);
      return;
    }

    markAndScrollTo(`memory-card-${memoryId}`, 160);
  }

  async function loadAssetsForEvent(eventId: number) {
    try {
      const [assets, faces] = await Promise.all([
        fetchEventAssets(eventId),
        fetchEventFaces(eventId),
      ]);
      setActiveEventAssets(assets);
      setActiveEventFaces(faces);
    } catch {
      setStatus("Could not load assets for the selected event.");
      setActiveEventAssets([]);
      setActiveEventFaces([]);
    }
  }

  async function assignFaceToPerson(
    faceId: number,
    personId: number | null,
    eventId: number,
    options?: { promoteUnknownSubject?: boolean },
  ) {
    setAssigningFaceId(faceId);
    setStatus(
      personId === null
        ? "Clearing face assignment..."
        : options?.promoteUnknownSubject
          ? "Saving face assignment and promoting unknown CompreFace subject..."
          : "Saving face assignment...",
    );
    try {
      await assignFacePerson(faceId, personId);
      if (activeEventId === eventId) {
        await loadAssetsForEvent(eventId);
      }
      setStatus(
        personId === null
          ? "Face assignment cleared."
          : options?.promoteUnknownSubject
            ? "Face assignment saved. Unknown CompreFace subject promoted to the selected person name."
            : "Face assignment saved.",
      );
    } catch {
      setStatus("Failed to update face assignment.");
    } finally {
      setAssigningFaceId(null);
    }
  }

  async function discardFace(faceId: number, eventId: number) {
    setStatus("Discarding face...");
    try {
      await deleteFace(faceId);
      if (activeEventId === eventId) {
        setActiveEventFaces((prev) => prev.filter((f) => f.id !== faceId));
      }
      setStatus("Face discarded.");
    } catch {
      setStatus("Failed to discard face.");
    }
  }

  async function renameFaceComprefaceSubject(
    faceId: number,
    newSubjectName: string,
    eventId: number,
  ) {
    setStatus("Renaming CompreFace subject...");
    try {
      await renameFaceSubject(faceId, newSubjectName);
      if (activeEventId === eventId) {
        await loadAssetsForEvent(eventId);
      }
      setStatus("CompreFace subject renamed.");
    } catch {
      setStatus("Failed to rename CompreFace subject.");
      throw new Error("rename_compreface_subject_failed");
    }
  }

  async function createAndAssignFacePerson(
    faceId: number,
    name: string,
    eventId: number,
  ) {
    const normalized = name.trim();
    if (!normalized) {
      return;
    }

    setAssigningFaceId(faceId);
    setStatus("Adding person and assigning face...");
    try {
      const person = await createPersonEntry(normalized);
      await assignFacePerson(faceId, person.id);
      await loadTimeline();
      if (activeEventId === eventId) {
        await loadAssetsForEvent(eventId);
      }
      setStatus("Person added and face assigned.");
    } catch {
      setStatus("Failed to add person and assign face.");
      throw new Error("create_and_assign_face_person_failed");
    } finally {
      setAssigningFaceId(null);
    }
  }

  const {
    eventActionId,
    summarizeEvent,
    deepResearchEvent,
    acceptEventResearchSuggestion,
    dismissEventResearchSuggestion,
  } = useEventActions({
    activeEventId,
    loadTimeline,
    loadAssetsForEvent,
    setStatus,
  });

  // Keep Period/Epic/Event edits and moves on one async UX path (status, busy state, timeline refresh).
  async function runHierarchyMutation<T>(options: {
    startStatus: string;
    successStatus: string;
    failureStatus: string;
    action: () => Promise<T>;
    refreshTimeline?: boolean;
    useBusyState?: boolean;
    onSuccess?: (result: T) => void;
  }): Promise<T | null> {
    const {
      startStatus,
      successStatus,
      failureStatus,
      action,
      refreshTimeline = true,
      useBusyState = false,
      onSuccess,
    } = options;
    if (useBusyState) {
      setIsSavingLifeStructure(true);
    }
    setStatus(startStatus);
    try {
      const result = await action();
      onSuccess?.(result);
      if (refreshTimeline) {
        await loadTimeline();
      }
      setStatus(successStatus);
      return result;
    } catch {
      setStatus(failureStatus);
      return null;
    } finally {
      if (useBusyState) {
        setIsSavingLifeStructure(false);
      }
    }
  }

  async function createLifePeriod() {
    if (!newPeriodTitle.trim()) {
      return;
    }
    setIsSavingLifeStructure(true);
    setStatus("Creating period...");
    try {
      const created = await createPeriod({
        title: newPeriodTitle.trim(),
        start_date_text: newPeriodStart.trim() || null,
        end_date_text: newPeriodEnd.trim() || null,
        summary: newPeriodSummary.trim() || null,
      });
      setNewPeriodTitle("");
      setNewPeriodStart("");
      setNewPeriodEnd("");
      setNewPeriodSummary("");
      await loadTimeline();
      setExpandedPeriods((current) => ({ ...current, [created.id]: true }));
      markAndScrollTo(`period-card-${created.id}`, 220);
      setStatus("Period created.");
    } catch {
      setStatus("Failed to create period.");
    } finally {
      setIsSavingLifeStructure(false);
    }
  }

  async function createLifeEvent(options?: {
    title?: string;
    eventDateText?: string;
    description?: string;
    location?: string;
    periodId?: number | null;
    resetPeriodDraftId?: number;
  }) {
    const title = options?.title ?? newEventTitle;
    const periodId =
      options?.periodId ?? (newEventPeriodId ? Number(newEventPeriodId) : null);
    const eventDateText = options?.eventDateText ?? newEventDateText;
    const description = options?.description ?? newEventDescription;
    const location = options?.location ?? "";

    if (!title.trim()) {
      return;
    }
    setIsSavingLifeStructure(true);
    setStatus("Creating event...");
    try {
      const created = await createEvent({
        title: title.trim(),
        period_id: periodId,
        epic_id: null,
        weight: 5,
        description: description.trim() || null,
        location: location.trim() || null,
        event_date_text: eventDateText.trim() || null,
      });
      setNewEventTitle("");
      setNewEventDateText("");
      setNewEventDescription("");
      if (options?.resetPeriodDraftId !== undefined) {
        setEventDraftsByPeriod((current) => ({
          ...current,
          [options.resetPeriodDraftId!]: {
            title: "",
            dateText: "",
            description: "",
            location: "",
          },
        }));
      }
      await loadTimeline();
      focusEventInTimeline(created.id, created.period_id);
      setStatus("Event created.");
    } catch {
      setStatus("Failed to create event.");
    } finally {
      setIsSavingLifeStructure(false);
    }
  }

  async function analyzePeriod(
    periodId: number,
    options?: {
      applyDates?: boolean;
      applyTitle?: boolean;
      regenerateSummary?: boolean;
    },
  ) {
    setPeriodAnalysisBusyId(periodId);
    setStatus("Analyzing period...");
    try {
      const analysis: LifePeriodAnalysis = await analyzeLifePeriod(periodId, {
        apply_dates: Boolean(options?.applyDates),
        apply_title: Boolean(options?.applyTitle),
        regenerate_summary: Boolean(options?.regenerateSummary),
      });
      setPeriodAnalysisById((current) => ({
        ...current,
        [periodId]: analysis,
      }));

      if (
        options?.applyDates ||
        options?.applyTitle ||
        options?.regenerateSummary
      ) {
        await loadTimeline();
        setStatus("Period recommendations applied.");
      } else {
        setStatus("Period analysis ready.");
      }
    } catch {
      setStatus("Failed to analyze period.");
    } finally {
      setPeriodAnalysisBusyId(null);
    }
  }

  function togglePeriodExpanded(periodId: number) {
    setExpandedPeriods((current) => ({
      ...current,
      [periodId]: !current[periodId],
    }));
  }

  function toggleEpicExpanded(epicId: number) {
    setExpandedEpics((current) => ({ ...current, [epicId]: !current[epicId] }));
  }

  function updateEventDraftForPeriod(
    periodId: number,
    patch: Partial<{
      title: string;
      dateText: string;
      description: string;
      location: string;
    }>,
  ) {
    setEventDraftsByPeriod((current) => ({
      ...current,
      [periodId]: {
        title: current[periodId]?.title || "",
        dateText: current[periodId]?.dateText || "",
        description: current[periodId]?.description || "",
        location: current[periodId]?.location || "",
        ...patch,
      },
    }));
  }

  async function savePeriodDates(periodId: number) {
    const updated = await runHierarchyMutation({
      startStatus: "Saving period dates...",
      successStatus: "Period dates updated.",
      failureStatus: "Failed to update period dates.",
      action: () =>
        updatePeriodById(periodId, {
          start_date_text: editingPeriodStartValue.trim() || null,
          end_date_text: editingPeriodEndValue.trim() || null,
        }),
    });
    if (updated) {
      setEditingPeriodDatesId(null);
      setEditingPeriodStartValue("");
      setEditingPeriodEndValue("");
    }
  }

  async function renamePeriod(periodId: number, newTitle: string) {
    const trimmed = newTitle.trim();
    if (!trimmed) return;
    const updated = await runHierarchyMutation({
      startStatus: "Saving period title...",
      successStatus: "Period title updated.",
      failureStatus: "Failed to rename period.",
      action: () => updatePeriodById(periodId, { title: trimmed }),
    });
    if (updated) {
      setEditingPeriodTitleId(null);
      setEditingPeriodTitleValue("");
    }
  }

  async function renameEvent(eventId: number, newTitle: string) {
    const trimmed = newTitle.trim();
    if (!trimmed) return;
    const updated = await runHierarchyMutation({
      startStatus: "Saving event title...",
      successStatus: "Event title updated.",
      failureStatus: "Failed to rename event.",
      action: () => updateEventById(eventId, { title: trimmed }),
    });
    if (updated) {
      setEditingEventTitleId(null);
      setEditingEventTitleValue("");
    }
  }

  async function saveEventDate(eventId: number, newDateText: string) {
    const updated = await runHierarchyMutation({
      startStatus: "Saving event date...",
      successStatus: "Event date updated.",
      failureStatus: "Failed to update event date.",
      action: () =>
        updateEventById(eventId, {
          event_date_text: newDateText.trim() || null,
        }),
    });
    if (updated) {
      setEditingEventDateId(null);
      setEditingEventDateValue("");
    }
  }

  async function saveEventLocation(eventId: number, newLocation: string) {
    const updated = await runHierarchyMutation({
      startStatus: "Saving event location...",
      successStatus: "Event location updated.",
      failureStatus: "Failed to update event location.",
      action: () =>
        updateEventById(eventId, { location: newLocation.trim() || null }),
    });
    if (updated) {
      setEditingEventLocationId(null);
      setEditingEventLocationValue("");
    }
  }

  async function deletePeriod(periodId: number, periodTitle: string) {
    if (
      !confirm(
        `Delete "${periodTitle}"? Its events and assets will be unlinked but not deleted.`,
      )
    )
      return;
    setStatus("Deleting period...");
    try {
      await deletePeriodById(periodId);
      setPeriodAnalysisById((current) => {
        const next = { ...current };
        delete next[periodId];
        return next;
      });
      await loadTimeline();
      setStatus("Period deleted.");
    } catch {
      setStatus("Failed to delete period.");
    }
  }

  async function createLifeThread() {
    if (!newThreadTitle.trim()) return;
    setIsSavingThread(true);
    setStatus("Creating thread...");
    try {
      const created = await createThread({
        title: newThreadTitle.trim(),
        summary: null,
      });
      setNewThreadTitle("");
      setIsThreadComposerOpen(false);
      setLifeThreads((prev) => [...prev, created]);
      setStatus("Thread created.");
    } catch {
      setStatus("Failed to create thread.");
    } finally {
      setIsSavingThread(false);
    }
  }

  async function doDeleteThread(threadId: number, threadTitle: string) {
    if (
      !confirm(
        `Delete thread "${threadTitle}"? Events and epics in this thread will be untagged but not deleted.`,
      )
    )
      return;
    setStatus("Deleting thread...");
    try {
      await deleteThread(threadId);
      await loadTimeline();
      setStatus("Thread deleted.");
    } catch {
      setStatus("Failed to delete thread.");
    }
  }

  async function saveThreadTitle(threadId: number, title: string) {
    if (!title.trim()) return;
    setStatus("Renaming thread...");
    try {
      await renameThread(threadId, title.trim());
      setEditingThreadTitleId(null);
      setEditingThreadTitleValue("");
      await loadTimeline();
      setStatus("Thread renamed.");
    } catch {
      setStatus("Failed to rename thread.");
    }
  }

  async function doAssignEpicToThread(epicId: number, threadId: number | null) {
    await runHierarchyMutation({
      startStatus: "Updating epic thread...",
      successStatus: "Epic thread updated.",
      failureStatus: "Failed to update epic thread.",
      refreshTimeline: false,
      action: () => updateEpicById(epicId, { thread_id: threadId }),
      onSuccess: (updated) =>
        setLifeEpics((prev) =>
          prev.map((e) => (e.id === epicId ? updated : e)),
        ),
    });
  }

  async function doAssignEpicToPeriod(epicId: number, periodId: number) {
    await runHierarchyMutation({
      startStatus: "Moving epic to period...",
      successStatus: "Epic moved to new period.",
      failureStatus: "Failed to move epic to period.",
      useBusyState: true,
      action: () => updateEpicById(epicId, { period_id: periodId }),
    });
  }

  async function doAssignEventToThread(
    eventId: number,
    threadId: number | null,
  ) {
    await runHierarchyMutation({
      startStatus: "Updating event thread...",
      successStatus: "Event thread updated.",
      failureStatus: "Failed to update event thread.",
      action: () => updateEventById(eventId, { thread_id: threadId }),
    });
  }

  async function doAssignPeriodToThread(
    _periodId: number,
    _threadId: number | null,
  ) {
    // No-op: threads are no longer assigned to periods
  }

  async function createLifeEpic(periodId: number) {
    const title = epicDraftsByPeriod[periodId]?.trim();
    if (!title) return;
    setIsSavingLifeStructure(true);
    setStatus("Creating epic...");
    try {
      const created = await createEpic({
        period_id: periodId,
        title,
        description: null,
        weight: 5,
        start_date_text: null,
        end_date_text: null,
      });
      setEpicDraftsByPeriod((prev) => ({ ...prev, [periodId]: "" }));
      setLifeEpics((prev) => [...prev, created]);
      setExpandedEpics((current) => ({ ...current, [created.id]: true }));
      setStatus("Epic created.");
    } catch {
      setStatus("Failed to create epic.");
    } finally {
      setIsSavingLifeStructure(false);
    }
  }

  async function createLifeEventInEpic(epicId: number, title: string) {
    if (!title.trim()) return;
    setIsSavingLifeStructure(true);
    setStatus("Creating event...");
    try {
      await createEvent({
        title: title.trim(),
        period_id: null,
        epic_id: epicId,
        weight: 5,
        description: null,
        location: null,
        event_date_text: null,
      });
      await loadTimeline();
      setStatus("Event created.");
    } catch {
      setStatus("Failed to create event.");
    } finally {
      setIsSavingLifeStructure(false);
    }
  }

  async function moveEventToEpic(event: LifeEvent, epicId: number | null) {
    await runHierarchyMutation({
      startStatus: "Assigning event to epic...",
      successStatus: "Event assigned.",
      failureStatus: "Failed to assign event.",
      useBusyState: true,
      action: () => updateEventById(event.id, { epic_id: epicId }),
    });
  }

  async function doDeleteEpic(epicId: number, epicTitle: string) {
    if (
      !confirm(
        `Delete epic "${epicTitle}"? Its events will be moved to the period.`,
      )
    )
      return;
    setStatus("Deleting epic...");
    try {
      await deleteEpic(epicId);
      await loadTimeline();
      setStatus("Epic deleted.");
    } catch {
      setStatus("Failed to delete epic.");
    }
  }

  async function saveEpicTitle(epicId: number, title: string) {
    if (!title.trim()) return;
    const updated = await runHierarchyMutation({
      startStatus: "Renaming epic...",
      successStatus: "Epic renamed.",
      failureStatus: "Failed to rename epic.",
      action: () => updateEpicById(epicId, { title: title.trim() }),
    });
    if (updated) {
      setEditingEpicTitleId(null);
      setEditingEpicTitleValue("");
    }
  }

  // Inline epic creation from asset link modal (returns created epic for auto-selection)
  async function createEpicInPeriod(
    periodId: number,
    title: string,
  ): Promise<LifeEpic | null> {
    if (!title.trim()) return null;
    setIsSavingLifeStructure(true);
    setStatus("Creating epic...");
    try {
      const created = await createEpic({
        period_id: periodId,
        title: title.trim(),
        description: null,
        weight: 5,
        start_date_text: null,
        end_date_text: null,
      });
      await loadTimeline();
      setStatus("Epic created.");
      return created;
    } catch {
      setStatus("Failed to create epic.");
      return null;
    } finally {
      setIsSavingLifeStructure(false);
    }
  }

  // Inline event creation from asset link modal (returns created event for auto-selection)
  async function createEventForLinking(payload: {
    title: string;
    periodId: number | null;
    epicId: number | null;
    eventDateText: string | null;
  }): Promise<LifeEvent | null> {
    const { title, periodId, epicId, eventDateText } = payload;
    if (!title.trim()) return null;
    setIsSavingLifeStructure(true);
    setStatus("Creating event...");
    try {
      const created = await createEvent({
        title: title.trim(),
        period_id: periodId,
        epic_id: epicId,
        weight: 5,
        description: null,
        location: null,
        event_date_text: eventDateText,
      });
      await loadTimeline();
      setStatus("Event created and ready to link.");
      return created;
    } catch {
      setStatus("Failed to create event.");
      return null;
    } finally {
      setIsSavingLifeStructure(false);
    }
  }

  async function mergePeriod(fromPeriodId: number, intoPeriodId: number) {
    setMergingPeriodId(null);
    setStatus("Merging period...");
    try {
      await mergePeriodInto(fromPeriodId, intoPeriodId);
      setPeriodAnalysisById((current) => {
        const next = { ...current };
        delete next[fromPeriodId];
        return next;
      });
      await loadTimeline();
      setStatus("Period merged.");
    } catch {
      setStatus("Failed to merge period.");
    }
  }

  async function uploadAssetToActiveEvent(
    file: File,
    capturedDateText: string | null = null,
  ) {
    if (!activeEventId) {
      return;
    }
    setIsUploadingAsset(true);
    setStatus("Uploading asset to event...");
    try {
      const formData = new FormData();
      const kind = file.type.startsWith("audio/")
        ? "audio"
        : file.type.startsWith("image/")
          ? "photo"
          : "document";
      formData.append("file", file, file.name);
      formData.append("kind", kind);
      formData.append("event_id", `${activeEventId}`);
      if (capturedDateText) {
        formData.append("captured_at_text", capturedDateText);
      }
      const uploaded = await uploadAsset(formData);

      if (eventAssetInputRef.current) {
        eventAssetInputRef.current.value = "";
      }
      await Promise.all([loadTimeline(), loadAssetsForEvent(activeEventId)]);
      markAndScrollTo(`asset-row-${uploaded.id}`, 220);
      setStatus("Asset uploaded and linked to event.");
    } catch {
      setStatus("Failed to upload asset to event.");
    } finally {
      setIsUploadingAsset(false);
    }
  }

  async function linkUnlinkedAssetToEvent(assetId: number, eventId?: number) {
    const target = eventId ? `${eventId}` : assetLinkTargets[assetId];
    if (!target) {
      return;
    }

    setIsSavingLifeStructure(true);
    setStatus("Linking asset to event...");
    try {
      await linkAssetToEvent(assetId, Number(target), "evidence");

      setAssetLinkTargets((current) => {
        const next = { ...current };
        delete next[assetId];
        return next;
      });
      await loadTimeline();
      if (activeEventId) {
        await loadAssetsForEvent(activeEventId);
      }
      // Jump to the event where the asset was linked
      const linkedEvent = lifeEvents.find((e) => e.id === Number(target));
      if (linkedEvent) {
        focusEventInTimeline(linkedEvent.id, linkedEvent.period_id);
      }
      setStatus("Asset linked to event.");
    } catch {
      setStatus("Failed to link asset to event.");
    } finally {
      setIsSavingLifeStructure(false);
    }
  }

  async function deleteLifeEvent(eventId: number) {
    if (
      !window.confirm(
        "Remove this event from the timeline? Linked memories and assets will be kept and moved to inbox/unlinked state.",
      )
    ) {
      return;
    }

    setIsSavingLifeStructure(true);
    setStatus("Removing event...");
    try {
      await deleteEventById(eventId);

      if (activeEventId === eventId) {
        setActiveEventId(null);
        setActiveEventAssets([]);
        setActiveEventFaces([]);
      }
      await loadTimeline();
      setStatus("Event removed. Memories and assets were kept.");
    } catch {
      setStatus("Failed to remove event.");
    } finally {
      setIsSavingLifeStructure(false);
    }
  }

  async function mergeLifeEvent(sourceId: number) {
    const targetId = eventMergeTargets[sourceId];
    if (!targetId) {
      return;
    }

    setIsSavingLifeStructure(true);
    setStatus("Merging event...");
    try {
      const merged: LifeEvent = await mergeEventInto(
        sourceId,
        Number(targetId),
      );
      setEventMergeTargets((current) => {
        const next = { ...current };
        delete next[sourceId];
        return next;
      });
      setActiveEventId(merged.id);
      await Promise.all([loadTimeline(), loadAssetsForEvent(merged.id)]);
      setStatus("Event merged.");
    } catch {
      setStatus("Failed to merge event.");
    } finally {
      setIsSavingLifeStructure(false);
    }
  }

  async function moveEventToPeriod(event: LifeEvent) {
    const selectedTarget =
      eventMoveTargets[event.id] ||
      (event.period_id === null
        ? UNASSIGNED_PERIOD_VALUE
        : `${event.period_id}`);
    const nextPeriodId =
      selectedTarget === UNASSIGNED_PERIOD_VALUE
        ? null
        : Number(selectedTarget);
    if (nextPeriodId === event.period_id) {
      return;
    }

    const moved = await runHierarchyMutation({
      startStatus: "Moving event to selected period...",
      successStatus: "Event moved.",
      failureStatus: "Failed to move event.",
      useBusyState: true,
      action: () => updateEventById(event.id, { period_id: nextPeriodId }),
    });
    if (moved) {
      setEventMoveTargets((current) => {
        const next = { ...current };
        delete next[event.id];
        return next;
      });
      focusEventInTimeline(event.id, nextPeriodId);
    }
  }

  useEffect(() => {
    loadTimeline();
  }, []);

  async function dismissQuestion(questionId: number) {
    try {
      await dismissQuestionById(questionId);
      setQuestions((current) => current.filter((q) => q.id !== questionId));
    } catch {
      // silently ignore dismiss errors
    }
  }

  async function saveMainCharacterName(name: string | null) {
    setIsSavingCharacter(true);
    try {
      await saveMainCharacterNameRequest(name);
      setMainCharacterName(name);
      setShowCharacterInput(false);
      setCharacterInputValue("");
    } catch {
      // ignore errors silently
    } finally {
      setIsSavingCharacter(false);
    }
  }

  async function reanalyzeMemory(memoryId: number) {
    setMemoryActionId(memoryId);
    setStatus("Reanalyzing memory...");
    try {
      await reanalyzeMemoryById(memoryId);
      await loadTimeline();
      setStatus("Memory reanalyzed.");
    } catch {
      setStatus("Failed to reanalyze memory.");
    } finally {
      setMemoryActionId(null);
    }
  }

  async function acceptResearchSuggestion(memoryId: number) {
    setMemoryActionId(memoryId);
    setStatus("Applying suggestion...");
    try {
      await applyResearchSuggestionById(memoryId);
      await loadTimeline();
      setStatus("Date updated from research.");
    } catch {
      setStatus("Failed to apply suggestion.");
    } finally {
      setMemoryActionId(null);
    }
  }

  async function dismissResearchSuggestion(memoryId: number) {
    setMemoryActionId(memoryId);
    try {
      await dismissResearchSuggestionById(memoryId);
      await loadTimeline();
    } catch {
      // ignore
    } finally {
      setMemoryActionId(null);
    }
  }

  async function deleteMemory(memoryId: number) {
    if (!window.confirm("Delete this memory permanently?")) {
      return;
    }

    setMemoryActionId(memoryId);
    setStatus("Deleting memory permanently...");
    try {
      await deleteMemoryById(memoryId);
      await loadTimeline();
      setStatus("Memory permanently deleted.");
    } catch {
      setStatus("Failed to delete memory.");
    } finally {
      setMemoryActionId(null);
    }
  }

  async function deleteAsset(assetId: number, eventId?: number) {
    if (
      !window.confirm("Delete this asset permanently? This cannot be undone.")
    ) {
      return;
    }

    setStatus("Deleting asset...");
    try {
      await deleteAssetById(assetId);
      if (eventId !== undefined) {
        await loadAssetsForEvent(eventId);
      } else {
        setUnlinkedAssets((current) => current.filter((a) => a.id !== assetId));
      }
      setStatus("Asset deleted.");
    } catch {
      setStatus("Failed to delete asset.");
    }
  }

  async function saveAssetTitle(
    assetId: number,
    eventId?: number,
    nextTitle?: string,
  ) {
    setAssetTitleSavingId(assetId);
    setStatus("Saving asset title...");
    try {
      const titleToSave =
        nextTitle !== undefined ? nextTitle : editingAssetTitleValue;
      await updateAssetTitleById(assetId, titleToSave.trim() || null);
      setEditingAssetTitleId(null);
      setEditingAssetTitleValue("");
      if (eventId !== undefined) {
        await loadAssetsForEvent(eventId);
      }
      await loadTimeline();
      setStatus("Asset title updated.");
    } catch {
      setStatus("Failed to update asset title.");
    } finally {
      setAssetTitleSavingId(null);
    }
  }

  async function saveAssetNotes(
    assetId: number,
    eventId?: number,
    nextNotes?: string,
  ) {
    setAssetNotesSavingId(assetId);
    setStatus("Saving asset notes...");
    try {
      const notesToSave =
        nextNotes !== undefined ? nextNotes : editingAssetNotesValue;
      await updateAssetNotesById(assetId, notesToSave.trim() || null);
      setEditingAssetNotesId(null);
      setEditingAssetNotesValue("");
      if (eventId !== undefined) {
        await loadAssetsForEvent(eventId);
      }
      await loadTimeline();
      setStatus("Asset notes updated.");
    } catch {
      setStatus("Failed to update asset notes.");
    } finally {
      setAssetNotesSavingId(null);
    }
  }

  async function saveAssetCapturedDate(
    assetId: number,
    eventId?: number,
    nextCapturedDateText?: string,
  ) {
    setAssetCapturedDateSavingId(assetId);
    setStatus("Saving captured date...");
    try {
      const capturedDateToSave =
        nextCapturedDateText !== undefined
          ? nextCapturedDateText
          : editingAssetCapturedDateValue;
      await updateAssetCapturedDateById(
        assetId,
        capturedDateToSave.trim() || null,
      );
      setEditingAssetCapturedDateId(null);
      setEditingAssetCapturedDateValue("");
      if (eventId !== undefined) {
        await loadAssetsForEvent(eventId);
      }
      await loadTimeline();
      setStatus("Captured date updated.");
    } catch {
      setStatus("Failed to update captured date.");
    } finally {
      setAssetCapturedDateSavingId(null);
    }
  }

  async function processPhotosForEvent(eventId: number) {
    setProcessingEventPhotosId(eventId);
    setEventCapturePanelOpenIds((prev) => {
      if (prev.has(eventId)) return prev;
      const next = new Set(prev);
      next.add(eventId);
      return next;
    });
    setStatus("Reprocessing event photos...");

    // Load assets so we can pre-populate per-photo progress rows
    let photoAssets: typeof activeEventAssets = [];
    try {
      const [assets] = await Promise.all([fetchEventAssets(eventId)]);
      photoAssets = assets.filter((a) => a.kind === "photo");
      setActiveEventAssets(assets);
    } catch {
      // continue anyway — progress list will fill in as SSE fires
    }

    const progressRows: EventDocumentUploadProgressItem[] = photoAssets.map(
      (a) => ({
        fileName: a.original_filename || a.title || `asset-${a.id}`,
        assetId: a.id,
        isPhoto: true,
        status: "saved",
        stages: { geocoding: "pending", faces: "pending", gemini: "pending" },
      }),
    );
    if (progressRows.length > 0) {
      setEventDocumentUploadProgressByEventId((prev) => ({
        ...prev,
        [eventId]: progressRows,
      }));
    }

    const url = `${API_BASE}/api/assets/analyze-stream?event_id=${eventId}&include_processed=true`;
    const es = new EventSource(url);

    es.onmessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data as string) as Record<
          string,
          unknown
        >;

        if (data["type"] === "complete" || data["type"] === "error") {
          es.close();
          setProcessingEventPhotosId(null);
          void loadTimeline();
          void loadAssetsForEvent(eventId);
          const count = photoAssets.length;
          setStatus(
            data["type"] === "error"
              ? `Analysis error: ${String(data["message"] ?? "unknown")}`
              : count === 0
                ? "No unprocessed photos found for this event."
                : `Reprocessed ${count} photo${count === 1 ? "" : "s"} for this event.`,
          );
          return;
        }

        const assetId = data["asset_id"] as number;
        const stage = data["stage"] as AnalysisStage;
        const stageStatus = data["status"] as StageStatus;
        if (!assetId || !stage) return;

        setEventDocumentUploadProgressByEventId((prev) => ({
          ...prev,
          [eventId]: (prev[eventId] ?? []).map((item) => {
            if (item.assetId !== assetId) return item;
            const newDetails = { ...item.stageDetails };
            if (
              stage === "geocoding" &&
              typeof data["place"] === "string" &&
              data["place"]
            ) {
              newDetails.geocoding = data["place"] as string;
            } else if (stage === "faces" && data["face_count"] !== undefined) {
              newDetails.faces = String(data["face_count"]);
            } else if (
              stage === "gemini" &&
              typeof data["title"] === "string" &&
              data["title"]
            ) {
              newDetails.gemini = data["title"] as string;
            }
            return {
              ...item,
              stages: { ...item.stages, [stage]: stageStatus },
              stageDetails: newDetails,
            };
          }),
        }));
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      es.close();
      setProcessingEventPhotosId(null);
      void loadTimeline();
      void loadAssetsForEvent(eventId);
      setStatus("Analysis stream closed.");
    };
  }

  async function processPhotoForEventAsset(assetId: number, eventId: number) {
    setProcessingPhotoAssetId(assetId);
    setStatus("Analyzing photo...");
    try {
      const result = await processSinglePhotoAsset(assetId, true);
      await loadTimeline();
      if (activeEventId === eventId) {
        await loadAssetsForEvent(eventId);
      }
      const exifPlacePart = result.exif_place_name
        ? `EXIF place: ${result.exif_place_name}.`
        : "";
      const reverseGeocodePart = result.reverse_geocode_location_name
        ? `Reverse geocode: ${result.reverse_geocode_location_name}.`
        : result.has_gps
          ? "GPS found (reverse geocode unavailable)."
          : "No GPS EXIF found.";
      const analyzedPlacePart = result.analyzed_place_name
        ? `Gemini assessed place: ${result.analyzed_place_name}.`
        : "";
      const capturePart = result.captured_at_text
        ? `Captured: ${result.captured_at_text}.`
        : "";
      const titlePart = result.suggested_title
        ? `Gemini suggests title: "${result.suggested_title}".`
        : "";
      setStatus(
        `Photo analyzed. Found ${result.face_count} face${result.face_count === 1 ? "" : "s"}. ${exifPlacePart} ${reverseGeocodePart} ${analyzedPlacePart} ${capturePart} ${titlePart}`.trim(),
      );
    } catch {
      setStatus("Failed to analyze photo.");
    } finally {
      setProcessingPhotoAssetId(null);
    }
  }

  async function saveMemoryTitle(memoryId: number, eventId?: number) {
    const nextTitle = editingMemoryTitleValue.trim();
    if (!nextTitle) {
      setStatus("Memory title cannot be empty.");
      return;
    }
    setMemoryTitleSavingId(memoryId);
    setStatus("Saving memory title...");
    try {
      await updateMemoryTitleById(memoryId, nextTitle);
      setEditingMemoryTitleId(null);
      setEditingMemoryTitleValue("");
      const data = await loadTimeline();
      focusMemoryInTimeline(memoryId, data);
      if (eventId !== undefined) {
        await loadAssetsForEvent(eventId);
      }
      setStatus("Memory title updated.");
    } catch {
      setStatus("Failed to update memory title.");
    } finally {
      setMemoryTitleSavingId(null);
    }
  }

  async function assignRecorder(memoryId: number, personId: number) {
    setMemoryActionId(memoryId);
    setStatus("Saving recorder...");
    try {
      await assignRecorderPerson(memoryId, personId);
      await loadTimeline();
      setStatus("Recorder saved.");
    } catch {
      setStatus("Failed to save recorder.");
    } finally {
      setMemoryActionId(null);
    }
  }

  async function mergePersonEntry(sourceId: number, intoId: number) {
    setDirectoryBusyKey(`people:merge:${sourceId}`);
    setStatus("Merging people...");
    try {
      await mergePeopleEntries(sourceId, intoId);
      await loadTimeline();
      setStatus("People merged.");
    } catch {
      setStatus("Failed to merge people.");
    } finally {
      setDirectoryBusyKey(null);
    }
  }

  async function splitPersonEntry(
    sourceId: number,
    newNames: string[],
    keepAlias: boolean,
  ) {
    setDirectoryBusyKey(`people:split:${sourceId}`);
    setStatus("Splitting person...");
    try {
      await splitPersonEntryRequest(sourceId, newNames, keepAlias);
      await loadTimeline();
      setStatus("Person split.");
    } catch {
      setStatus("Failed to split person.");
    } finally {
      setDirectoryBusyKey(null);
    }
  }

  async function addPersonAlias(personId: number, alias: string) {
    setDirectoryBusyKey(`people:alias:${personId}`);
    try {
      await addPersonAliasRequest(personId, alias);
      await loadTimeline();
      setStatus("Alias saved.");
    } catch {
      setStatus("Failed to save alias.");
    } finally {
      setDirectoryBusyKey(null);
    }
  }

  async function removePersonAlias(personId: number, alias: string) {
    setDirectoryBusyKey(`people:alias:${personId}`);
    try {
      await removePersonAliasRequest(personId, alias);
      await loadTimeline();
      setStatus("Alias removed.");
    } catch {
      setStatus("Failed to remove alias.");
    } finally {
      setDirectoryBusyKey(null);
    }
  }

  async function linkPersonCompreface(personId: number, subjectName: string) {
    setDirectoryBusyKey(`people:compreface:${personId}`);
    setStatus("Linking person to CompreFace...");
    try {
      await linkPersonToCompreface(personId, subjectName);
      await loadTimeline();
      setStatus("CompreFace link saved.");
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : "Failed to link person to CompreFace.";
      setStatus(message);
    } finally {
      setDirectoryBusyKey(null);
    }
  }

  async function createDirectoryEntry(kind: "people" | "places", name: string) {
    setDirectoryBusyKey(`${kind}:create`);
    setStatus(`Adding ${kind === "people" ? "person" : "place"}...`);
    try {
      await createDirectoryEntryRequest(kind, name);
      await loadTimeline();
      setStatus(`${kind === "people" ? "Person" : "Place"} saved.`);
    } catch {
      setStatus(`Failed to save ${kind === "people" ? "person" : "place"}.`);
    } finally {
      setDirectoryBusyKey(null);
    }
  }

  async function renameDirectoryEntry(
    kind: "people" | "places",
    itemId: number,
    name: string,
  ) {
    setDirectoryBusyKey(`${kind}:rename:${itemId}`);
    setStatus(`Renaming ${kind === "people" ? "person" : "place"}...`);
    try {
      await renameDirectoryEntryRequest(kind, itemId, name);
      await loadTimeline();
      setStatus(`${kind === "people" ? "Person" : "Place"} renamed.`);
    } catch {
      setStatus(`Failed to rename ${kind === "people" ? "person" : "place"}.`);
    } finally {
      setDirectoryBusyKey(null);
    }
  }

  async function deleteDirectoryEntry(
    kind: "people" | "places",
    itemId: number,
  ) {
    if (
      !window.confirm(
        `Delete this ${kind === "people" ? "person" : "place"} from the directory?`,
      )
    ) {
      return;
    }

    setDirectoryBusyKey(`${kind}:delete:${itemId}`);
    setStatus(`Deleting ${kind === "people" ? "person" : "place"}...`);
    try {
      await deleteDirectoryEntryRequest(kind, itemId);
      await loadTimeline();
      setStatus(`${kind === "people" ? "Person" : "Place"} deleted.`);
    } catch {
      setStatus(`Failed to delete ${kind === "people" ? "person" : "place"}.`);
    } finally {
      setDirectoryBusyKey(null);
    }
  }

  useEffect(() => {
    return () => {
      if (focusClearTimerRef.current !== null) {
        window.clearTimeout(focusClearTimerRef.current);
      }
      if (currentPreviewAudioUrlRef.current) {
        URL.revokeObjectURL(currentPreviewAudioUrlRef.current);
      }
      stopAudioLevelMonitoring();
    };
  }, []);

  async function startRecording(
    forEventId?: number,
    options?: { quickCapture?: boolean; relatedAssetId?: number },
  ) {
    try {
      shouldDiscardRecordingRef.current = false;
      const isQuickCapture =
        options?.quickCapture === true && forEventId === undefined;
      const targetAssetId = options?.relatedAssetId;
      const audioConstraint = selectedDeviceId
        ? { deviceId: { exact: selectedDeviceId } }
        : true;
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: audioConstraint,
      });
      streamRef.current = stream;
      chunksRef.current = [];
      startAudioLevelMonitoring(stream);

      await refreshAudioDevices();

      const targetEventId = forEventId ?? null;
      setRecordingForEventId(targetEventId);
      setRecordingForAssetId(targetAssetId ?? null);

      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        const shouldDiscard = shouldDiscardRecordingRef.current;
        shouldDiscardRecordingRef.current = false;

        if (shouldDiscard) {
          chunksRef.current = [];
          setRecordingForEventId(null);
          setRecordingForAssetId(null);
          setStatus(
            activeQuestion
              ? "Recording canceled. Your question is still waiting for an answer."
              : "Recording canceled.",
          );
          return;
        }

        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        const nextAudioUrl = URL.createObjectURL(blob);
        const nextPendingId = `${Date.now()}`;

        if (targetAssetId !== undefined) {
          setAssetRecordingPending((prev) => ({
            ...prev,
            [targetAssetId]: {
              id: nextPendingId,
              audioUrl: nextAudioUrl,
              sizeBytes: blob.size,
              status: "recorded",
            },
          }));
        } else if (targetEventId !== null) {
          setEventRecordingPending((prev) => ({
            ...prev,
            [targetEventId]: {
              id: nextPendingId,
              audioUrl: nextAudioUrl,
              sizeBytes: blob.size,
              status: "recorded",
            },
          }));
        } else {
          setPendingRecording((current) => {
            if (current?.audioUrl) {
              URL.revokeObjectURL(current.audioUrl);
            }
            currentPreviewAudioUrlRef.current = nextAudioUrl;
            return {
              id: nextPendingId,
              audioUrl: nextAudioUrl,
              sizeBytes: blob.size,
              status: "recorded",
            };
          });
        }

        setStatus("Audio recorded. You can play it now while we process it.");
        await uploadRecording(
          blob,
          nextPendingId,
          targetEventId ?? undefined,
          targetAssetId,
          isQuickCapture,
        );
      };

      recorder.start();
      setIsRecording(true);
      setStatus("Recording in progress...");
    } catch (error) {
      setStatus("Microphone permission denied or unavailable.");
    }
  }

  async function startQuickMemoryCapture() {
    // Quick Memory is designed to start capture from a single home-screen tap.
    setIsCaptureDrawerOpen(true);
    if (isRecording || isLoading) {
      return;
    }
    await startRecording(undefined, { quickCapture: true });
  }

  // A period-scoped quick memory still needs an event wrapper so uploads and summaries stay organized.
  async function startQuickMemoryCaptureForPeriod(period: {
    id: number;
    title: string;
  }) {
    if (isRecording || isLoading || isSavingLifeStructure) {
      return;
    }

    setIsSavingLifeStructure(true);
    setStatus(`Preparing quick memory for ${period.title}...`);
    try {
      const createdEvent = await createEvent({
        title: "Quick memory",
        period_id: period.id,
        epic_id: null,
        weight: 5,
        description: null,
        location: null,
        event_date_text: null,
      });

      await loadTimeline();
      focusEventInTimeline(createdEvent.id, createdEvent.period_id);
      await startRecording(createdEvent.id);
    } catch {
      setStatus("Failed to start quick memory in this period.");
    } finally {
      setIsSavingLifeStructure(false);
    }
  }

  function stopRecording() {
    shouldDiscardRecordingRef.current = false;
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }

    streamRef.current?.getTracks().forEach((track) => track.stop());
    stopAudioLevelMonitoring();
    setIsRecording(false);
    setStatus("Finalizing audio clip...");
  }

  function cancelRecording() {
    shouldDiscardRecordingRef.current = true;
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }

    streamRef.current?.getTracks().forEach((track) => track.stop());
    stopAudioLevelMonitoring();
    setIsRecording(false);
    setRecordingForEventId(null);
    setRecordingForAssetId(null);
    setStatus("Canceling recording...");
  }

  async function startRecordingForAsset(assetId: number, eventId: number) {
    if (isRecording || isLoading) {
      return;
    }
    await startRecording(eventId, { relatedAssetId: assetId });
  }

  async function uploadRecording(
    blob: Blob,
    pendingId: string,
    eventId?: number,
    relatedAssetId?: number,
    quickCapture = false,
  ) {
    setIsLoading(true);

    const updatePending = (
      updater: (prev: PendingRecording) => PendingRecording,
    ) => {
      if (relatedAssetId !== undefined) {
        setAssetRecordingPending((prev) => {
          const current = prev[relatedAssetId];
          if (!current || current.id !== pendingId) return prev;
          return { ...prev, [relatedAssetId]: updater(current) };
        });
      } else if (eventId !== undefined) {
        setEventRecordingPending((prev) => {
          const current = prev[eventId];
          if (!current || current.id !== pendingId) return prev;
          return { ...prev, [eventId]: updater(current) };
        });
      } else {
        setPendingRecording((current) =>
          current && current.id === pendingId ? updater(current) : current,
        );
      }
    };

    updatePending((p) => ({ ...p, status: "processing", error: undefined }));

    try {
      const created: MemoryEntry = await createMemoryFromAudioBlob(
        blob,
        eventId,
        relatedAssetId,
        quickCapture,
      );
      if (activeQuestion) {
        try {
          await answerQuestionWithMemory(activeQuestion.id, created.id);
        } catch {
          // ignore answer errors
        }
        setActiveQuestion(null);
      }
      const data = await loadTimeline();
      focusMemoryInTimeline(created.id, data);
      if (eventId !== undefined) {
        await loadAssetsForEvent(eventId);
      }
      setStatus("Memory saved and analyzed.");
      setRecordingForEventId(null);
      setRecordingForAssetId(null);
      updatePending((p) => ({ ...p, status: "saved", error: undefined }));
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to process recording.";
      setStatus(message);
      setRecordingForAssetId(null);
      updatePending((p) => ({
        ...p,
        status: "failed",
        error: message,
      }));
    } finally {
      setIsLoading(false);
    }
  }

  async function uploadDocument(
    file: File,
    capturedDateText: string | null = null,
  ) {
    setIsUploadingDocument(true);
    setDocumentUploadError(null);
    setStatus("Uploading file...");
    try {
      const formData = new FormData();
      formData.append("file", file, file.name);
      const kind = file.type.startsWith("image/") ? "photo" : "document";
      formData.append("kind", kind);
      if (capturedDateText) {
        formData.append("captured_at_text", capturedDateText);
      }
      const uploaded = await uploadAsset(formData);

      await loadTimeline();
      markAndScrollTo(`asset-row-${uploaded.id}`, 180);
      setStatus("File uploaded to unlinked assets inbox.");
      if (documentFileInputRef.current) {
        documentFileInputRef.current.value = "";
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to process document.";
      setDocumentUploadError(message);
      setStatus("Document upload failed.");
    } finally {
      setIsUploadingDocument(false);
    }
  }

  const {
    isReadingClipboard,
    isDragOverDocumentTarget,
    documentUploadError,
    setDocumentUploadError,
    pasteImageFromClipboard,
    onDocumentPasteZonePaste,
    onDocumentDragEnter,
    onDocumentDragOver,
    onDocumentDragLeave,
    onDocumentDrop,
  } = useDocumentIntake({
    isUploadingDocument,
    isRecording,
    isLoading,
    uploadDocument,
  });

  async function uploadDocumentsToEvent(
    files: File[],
    eventId: number,
    capturedDateText: string | null = null,
  ) {
    if (files.length === 0) {
      return;
    }

    const initialProgress: EventDocumentUploadProgressItem[] = files.map(
      (file) => ({
        fileName: file.name || "unnamed file",
        status: "uploading",
      }),
    );

    setEventDocumentUploadingId(eventId);
    setEventDocumentErrors((prev) => ({ ...prev, [eventId]: null }));
    setEventDocumentUploadProgressByEventId((prev) => ({
      ...prev,
      [eventId]: initialProgress,
    }));
    setStatus(
      files.length === 1
        ? "Uploading file to event..."
        : `Uploading ${files.length} files to event...`,
    );

    const uploadedAssetIds: number[] = [];
    const photoAssetIds: number[] = [];
    const failedFileNames: string[] = [];

    try {
      for (const [index, file] of files.entries()) {
        try {
          const formData = new FormData();
          formData.append("file", file, file.name);
          const kind = file.type.startsWith("image/") ? "photo" : "document";
          formData.append("kind", kind);
          formData.append("event_id", String(eventId));
          if (capturedDateText) {
            formData.append("captured_at_text", capturedDateText);
          }
          const uploaded = await uploadAsset(formData);
          uploadedAssetIds.push(uploaded.id);
          if (kind === "photo") photoAssetIds.push(uploaded.id);
          setEventDocumentUploadProgressByEventId((prev) => ({
            ...prev,
            [eventId]: (prev[eventId] ?? []).map((item, itemIndex) =>
              itemIndex === index
                ? {
                    ...item,
                    assetId: uploaded.id,
                    isPhoto: kind === "photo",
                    status: "saved" as const,
                    stages:
                      kind === "photo"
                        ? {
                            geocoding: "pending",
                            faces: "pending",
                            gemini: "pending",
                          }
                        : undefined,
                  }
                : item,
            ),
          }));
        } catch {
          failedFileNames.push(file.name || "unnamed file");
          setEventDocumentUploadProgressByEventId((prev) => ({
            ...prev,
            [eventId]: (prev[eventId] ?? []).map((item, itemIndex) =>
              itemIndex === index
                ? { ...item, status: "failed" as const, error: "Upload failed" }
                : item,
            ),
          }));
        }
      }

      if (uploadedAssetIds.length === 0) {
        setEventDocumentErrors((prev) => ({
          ...prev,
          [eventId]:
            files.length === 1
              ? "Document upload failed."
              : `All ${files.length} uploads failed.`,
        }));
        setStatus("Document upload failed.");
        setEventDocumentUploadingId(null);
        return;
      }

      // All saves complete — release upload lock so user can queue more while analysis runs
      setEventDocumentUploadingId(null);

      if (photoAssetIds.length > 0) {
        setStatus(
          `Analyzing ${photoAssetIds.length} photo${photoAssetIds.length === 1 ? "" : "s"}...`,
        );

        const es = new EventSource(
          `${API_BASE}/api/assets/analyze-stream?asset_ids=${photoAssetIds.join(",")}`,
        );

        es.onmessage = (event: MessageEvent) => {
          try {
            const data = JSON.parse(event.data as string) as Record<
              string,
              unknown
            >;

            if (data["type"] === "complete" || data["type"] === "error") {
              es.close();
              void loadTimeline();
              void loadAssetsForEvent(eventId);
              const count = uploadedAssetIds.length;
              setStatus(
                failedFileNames.length === 0
                  ? count === 1
                    ? "Photo uploaded and analyzed."
                    : `${count} photos uploaded and analyzed.`
                  : `${count} uploaded and analyzed, ${failedFileNames.length} failed.`,
              );
              return;
            }

            const assetId = data["asset_id"] as number;
            const stage = data["stage"] as AnalysisStage;
            const stageStatus = data["status"] as StageStatus;
            if (!assetId || !stage) return;

            setEventDocumentUploadProgressByEventId((prev) => ({
              ...prev,
              [eventId]: (prev[eventId] ?? []).map((item) => {
                if (item.assetId !== assetId) return item;
                const newDetails = { ...item.stageDetails };
                if (
                  stage === "geocoding" &&
                  typeof data["place"] === "string" &&
                  data["place"]
                ) {
                  newDetails.geocoding = data["place"] as string;
                } else if (
                  stage === "faces" &&
                  data["face_count"] !== undefined
                ) {
                  newDetails.faces = String(data["face_count"]);
                } else if (
                  stage === "gemini" &&
                  typeof data["title"] === "string" &&
                  data["title"]
                ) {
                  newDetails.gemini = data["title"] as string;
                }
                return {
                  ...item,
                  stages: { ...item.stages, [stage]: stageStatus },
                  stageDetails: newDetails,
                };
              }),
            }));
          } catch {
            // ignore parse errors
          }
        };

        es.onerror = () => {
          es.close();
          void loadTimeline();
          void loadAssetsForEvent(eventId);
        };
      } else {
        // No photos — load and done
        await Promise.all([loadTimeline(), loadAssetsForEvent(eventId)]);
        markAndScrollTo(
          `asset-row-${uploadedAssetIds[uploadedAssetIds.length - 1]}`,
          220,
        );
        if (failedFileNames.length === 0) {
          setStatus(
            uploadedAssetIds.length === 1
              ? "File uploaded and linked to event."
              : `${uploadedAssetIds.length} files uploaded and linked to event.`,
          );
        } else {
          setEventDocumentErrors((prev) => ({
            ...prev,
            [eventId]: `${failedFileNames.length} file(s) failed: ${failedFileNames.slice(0, 3).join(", ")}${failedFileNames.length > 3 ? ", ..." : ""}`,
          }));
          setStatus(
            `${uploadedAssetIds.length} uploaded, ${failedFileNames.length} failed.`,
          );
        }
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to process document.";
      setEventDocumentErrors((prev) => ({ ...prev, [eventId]: message }));
      setStatus("Document upload failed.");
      setEventDocumentUploadingId(null);
    }
  }

  const [peopleSortMode, setPeopleSortMode] = useState<
    "weighted" | "alphabetical" | "photos"
  >("weighted");
  const normalizedDirectorySearch = directorySearch.trim().toLowerCase();
  let filteredPeopleDirectory = peopleDirectory.filter((entry) => {
    if (!normalizedDirectorySearch) {
      return true;
    }
    if (entry.name.toLowerCase().includes(normalizedDirectorySearch)) {
      return true;
    }
    return entry.aliases.some((alias) =>
      alias.toLowerCase().includes(normalizedDirectorySearch),
    );
  });
  // Sort people by selected mode
  filteredPeopleDirectory = [...filteredPeopleDirectory].sort((a, b) => {
    if (peopleSortMode === "alphabetical") {
      return a.name.localeCompare(b.name);
    }
    if (peopleSortMode === "photos") {
      return (
        b.photo_count - a.photo_count ||
        b.memory_count - a.memory_count ||
        a.name.localeCompare(b.name)
      );
    }
    // weighted (descending by memory_count)
    return b.memory_count - a.memory_count || a.name.localeCompare(b.name);
  });
  const filteredPlacesDirectory = placesDirectory.filter((entry) => {
    if (!normalizedDirectorySearch) {
      return true;
    }
    return entry.name.toLowerCase().includes(normalizedDirectorySearch);
  });
  const activeDirectoryCount =
    activeDirectoryTab === "people"
      ? filteredPeopleDirectory.length
      : filteredPlacesDirectory.length;
  const activeDirectoryTotal =
    activeDirectoryTab === "people"
      ? peopleDirectory.length
      : placesDirectory.length;
  const lifeEventMemoryIds = new Set(
    lifeEvents.flatMap((event) => event.linked_memory_ids),
  );
  const questionsWithContext = questions.map((question) => {
    const sourceMemory = question.source_memory_id
      ? (timeline.find((memory) => memory.id === question.source_memory_id) ??
        null)
      : null;
    const sourceEvent = sourceMemory
      ? (lifeEvents.find((event) =>
          event.linked_memory_ids.includes(sourceMemory.id),
        ) ?? null)
      : null;
    const sourcePeriod =
      sourceEvent && sourceEvent.period_id !== null
        ? (lifePeriods.find((period) => period.id === sourceEvent.period_id) ??
          null)
        : null;

    return {
      question,
      sourceMemory,
      sourceEvent,
      sourcePeriod,
    };
  });
  const questionsByEventId = new Map<number, typeof questionsWithContext>();
  const questionsByPeriodNoEvent = new Map<
    number,
    typeof questionsWithContext
  >();
  const questionsWithNoContext: typeof questionsWithContext = [];
  for (const item of questionsWithContext) {
    if (item.sourceEvent) {
      const list = questionsByEventId.get(item.sourceEvent.id) ?? [];
      list.push(item);
      questionsByEventId.set(item.sourceEvent.id, list);
    } else if (item.sourcePeriod) {
      const list = questionsByPeriodNoEvent.get(item.sourcePeriod.id) ?? [];
      list.push(item);
      questionsByPeriodNoEvent.set(item.sourcePeriod.id, list);
    } else {
      questionsWithNoContext.push(item);
    }
  }
  const compareEventsByStartDate = (
    left: LifeEvent,
    right: LifeEvent,
  ): number => {
    const leftStart =
      parseOptionalDateTimestamp(left.event_date_sort) ??
      parseOptionalDateTimestamp(left.event_date_text);
    const rightStart =
      parseOptionalDateTimestamp(right.event_date_sort) ??
      parseOptionalDateTimestamp(right.event_date_text);
    if (leftStart === null && rightStart !== null) {
      return 1;
    }
    if (leftStart !== null && rightStart === null) {
      return -1;
    }
    if (leftStart !== null && rightStart !== null && leftStart !== rightStart) {
      return leftStart - rightStart;
    }
    return compareDateStringsDesc(left.created_at, right.created_at);
  };

  const compareEpicsByStartDate = (left: LifeEpic, right: LifeEpic): number => {
    const leftStart =
      parseOptionalDateTimestamp(left.start_sort) ??
      parseOptionalDateTimestamp(left.start_date_text);
    const rightStart =
      parseOptionalDateTimestamp(right.start_sort) ??
      parseOptionalDateTimestamp(right.start_date_text);
    if (leftStart === null && rightStart !== null) {
      return 1;
    }
    if (leftStart !== null && rightStart === null) {
      return -1;
    }
    if (leftStart !== null && rightStart !== null && leftStart !== rightStart) {
      return leftStart - rightStart;
    }
    return compareDateStringsDesc(left.created_at, right.created_at);
  };

  const unassignedEvents = [
    ...lifeEvents.filter((event) => event.period_id === null),
  ].sort(compareEventsByStartDate);
  const timelineStandaloneMemories = timeline.filter(
    (memory) => !lifeEventMemoryIds.has(memory.id),
  );

  function renderEventCard(
    event: LifeEvent,
    mergeCandidates: LifeEvent[],
    epicsInPeriod: LifeEpic[] = [],
  ) {
    return (
      <EventCard
        key={event.id}
        event={event}
        mergeCandidates={mergeCandidates}
        isHighlighted={highlightedElementId === `event-card-${event.id}`}
        isOpen={activeEventId === event.id}
        onToggleOpen={async () => {
          if (activeEventId === event.id) {
            setActiveEventId(null);
            setActiveEventAssets([]);
            setActiveEventFaces([]);
            return;
          }
          setActiveEventId(event.id);
          await loadAssetsForEvent(event.id);
        }}
        isSavingLifeStructure={isSavingLifeStructure}
        isRecording={isRecording}
        isLoading={isLoading}
        deleteLifeEvent={deleteLifeEvent}
        editingEventTitleId={editingEventTitleId}
        setEditingEventTitleId={setEditingEventTitleId}
        editingEventTitleValue={editingEventTitleValue}
        setEditingEventTitleValue={setEditingEventTitleValue}
        renameEvent={renameEvent}
        editingEventDateId={editingEventDateId}
        setEditingEventDateId={setEditingEventDateId}
        editingEventDateValue={editingEventDateValue}
        setEditingEventDateValue={setEditingEventDateValue}
        saveEventDate={saveEventDate}
        editingEventLocationId={editingEventLocationId}
        setEditingEventLocationId={setEditingEventLocationId}
        editingEventLocationValue={editingEventLocationValue}
        setEditingEventLocationValue={setEditingEventLocationValue}
        saveEventLocation={saveEventLocation}
        eventMoveTargets={eventMoveTargets}
        setEventMoveTargets={setEventMoveTargets}
        moveEventToPeriod={moveEventToPeriod}
        sortedLifePeriods={sortedLifePeriods}
        epicsInPeriod={epicsInPeriod}
        moveEventToEpic={moveEventToEpic}
        eventMergeTargets={eventMergeTargets}
        setEventMergeTargets={setEventMergeTargets}
        mergeLifeEvent={mergeLifeEvent}
        eventActionId={eventActionId}
        summarizeEvent={summarizeEvent}
        deepResearchEvent={deepResearchEvent}
        processingEventPhotosId={processingEventPhotosId}
        processEventPhotos={processPhotosForEvent}
        processPhotoAsset={processPhotoForEventAsset}
        processingPhotoAssetId={processingPhotoAssetId}
        acceptEventResearchSuggestion={acceptEventResearchSuggestion}
        dismissEventResearchSuggestion={dismissEventResearchSuggestion}
        questionsForEvent={questionsByEventId.get(event.id) ?? []}
        setActiveQuestion={setActiveQuestion}
        dismissQuestion={dismissQuestion}
        eventCapturePanelOpenIds={eventCapturePanelOpenIds}
        setEventCapturePanelOpenIds={setEventCapturePanelOpenIds}
        recordingForEventId={recordingForEventId}
        recordingForAssetId={recordingForAssetId}
        audioDevices={audioDevices}
        selectedDeviceId={selectedDeviceId}
        setSelectedDeviceId={setSelectedDeviceId}
        audioLevel={audioLevel}
        startRecording={startRecording}
        stopRecording={stopRecording}
        cancelRecording={cancelRecording}
        eventRecordingPending={eventRecordingPending}
        assetRecordingPending={assetRecordingPending}
        startRecordingForAsset={startRecordingForAsset}
        eventDocumentUploadingId={eventDocumentUploadingId}
        eventDocumentErrors={eventDocumentErrors}
        eventDocumentUploadProgressByEventId={
          eventDocumentUploadProgressByEventId
        }
        uploadDocumentsToEvent={uploadDocumentsToEvent}
        eventAssetInputRef={eventAssetInputRef}
        isUploadingAsset={isUploadingAsset}
        uploadAssetToActiveEvent={uploadAssetToActiveEvent}
        activeEventAssets={activeEventAssets}
        eventFaces={activeEventFaces}
        highlightedElementId={highlightedElementId}
        expandedAssetRowIds={expandedAssetRowIds}
        setExpandedAssetRowIds={setExpandedAssetRowIds}
        editingAssetTitleId={editingAssetTitleId}
        setEditingAssetTitleId={setEditingAssetTitleId}
        editingAssetTitleValue={editingAssetTitleValue}
        setEditingAssetTitleValue={setEditingAssetTitleValue}
        assetTitleSavingId={assetTitleSavingId}
        saveAssetTitle={saveAssetTitle}
        editingAssetNotesId={editingAssetNotesId}
        setEditingAssetNotesId={setEditingAssetNotesId}
        editingAssetNotesValue={editingAssetNotesValue}
        setEditingAssetNotesValue={setEditingAssetNotesValue}
        assetNotesSavingId={assetNotesSavingId}
        saveAssetNotes={saveAssetNotes}
        editingAssetCapturedDateId={editingAssetCapturedDateId}
        setEditingAssetCapturedDateId={setEditingAssetCapturedDateId}
        editingAssetCapturedDateValue={editingAssetCapturedDateValue}
        setEditingAssetCapturedDateValue={setEditingAssetCapturedDateValue}
        assetCapturedDateSavingId={assetCapturedDateSavingId}
        saveAssetCapturedDate={saveAssetCapturedDate}
        resolveApiUrl={resolveApiUrl}
        formatBytes={formatBytes}
        deleteAsset={deleteAsset}
        assignFaceToPerson={assignFaceToPerson}
        createAndAssignFacePerson={createAndAssignFacePerson}
        renameFaceSubject={renameFaceComprefaceSubject}
        assigningFaceId={assigningFaceId}
        timeline={timeline}
        discardFace={discardFace}
        editingMemoryTitleId={editingMemoryTitleId}
        setEditingMemoryTitleId={setEditingMemoryTitleId}
        editingMemoryTitleValue={editingMemoryTitleValue}
        setEditingMemoryTitleValue={setEditingMemoryTitleValue}
        memoryTitleSavingId={memoryTitleSavingId}
        saveMemoryTitle={saveMemoryTitle}
        expandedMemoryRowIds={expandedMemoryRowIds}
        setExpandedMemoryRowIds={setExpandedMemoryRowIds}
        questions={questions}
        peopleDirectory={peopleDirectory}
        acceptResearchSuggestion={acceptResearchSuggestion}
        dismissResearchSuggestion={dismissResearchSuggestion}
        reanalyzeMemory={reanalyzeMemory}
        deleteMemory={deleteMemory}
        assignRecorder={assignRecorder}
        memoryActionId={memoryActionId}
        threads={lifeThreads}
        onAssignThread={(threadId) =>
          void doAssignEventToThread(event.id, threadId)
        }
      />
    );
  }

  return (
    <main className="appShell">
      <DirectorySidebar
        isDirectoryDrawerOpen={isDirectoryDrawerOpen}
        setIsDirectoryDrawerOpen={setIsDirectoryDrawerOpen}
        activeDirectoryTab={activeDirectoryTab}
        setActiveDirectoryTab={setActiveDirectoryTab}
        directorySearch={directorySearch}
        setDirectorySearch={setDirectorySearch}
        activeDirectoryCount={activeDirectoryCount}
        activeDirectoryTotal={activeDirectoryTotal}
        normalizedDirectorySearch={normalizedDirectorySearch}
        filteredPeopleDirectory={filteredPeopleDirectory}
        filteredPlacesDirectory={filteredPlacesDirectory}
        isBusy={directoryBusyKey !== null || isLoading || isRecording}
        onCreateDirectoryEntry={createDirectoryEntry}
        onRenameDirectoryEntry={renameDirectoryEntry}
        onDeleteDirectoryEntry={deleteDirectoryEntry}
        onMergePersonEntry={mergePersonEntry}
        onSplitPersonEntry={splitPersonEntry}
        onAddPersonAlias={addPersonAlias}
        onRemovePersonAlias={removePersonAlias}
        onLinkPersonCompreface={linkPersonCompreface}
        resolveApiUrl={resolveApiUrl}
        peopleSortMode={peopleSortMode}
        setPeopleSortMode={setPeopleSortMode}
      />

      <div className="workspaceColumn">
        <section className="hero">
          <div className="heroRow">
            <h1>
              {mainCharacterName
                ? `${mainCharacterName}'s Memoir`
                : "Memoir MVP"}
            </h1>
            <div className="heroActions">
              <button
                type="button"
                className="primary captureToggle"
                onClick={() => void startQuickMemoryCapture()}
                disabled={isRecording || isLoading}
              >
                Quick Memory
              </button>
              <button
                type="button"
                className="secondary captureToggle"
                onClick={() => setIsCaptureDrawerOpen(true)}
              >
                + New Memory
              </button>
            </div>
          </div>
          <p>Explore your timeline.</p>
          <p className="meta">
            Tip: start each recording with your name, where this memory
            happened, and when it happened.
          </p>
        </section>

        <>
          <section className="panel" style={{ marginTop: "1rem" }}>
            <div className="periodsHeader">
              <div>
                <h2>Life Threads</h2>
                <p className="meta">
                  Threads group related periods across time — e.g. "Military
                  Career" or "Family".
                </p>
              </div>
              <h2
                style={{
                  cursor: "pointer",
                  userSelect: "none",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.4rem",
                  margin: 0,
                }}
                onClick={() => setIsThreadComposerOpen((c) => !c)}
              >
                <span>{isThreadComposerOpen ? "▾" : "▸"}</span>
                New thread
              </h2>
            </div>

            {isThreadComposerOpen && (
              <div
                className="controls"
                style={{ marginBottom: "0.75rem", flexWrap: "wrap" }}
              >
                <input
                  className="directoryInput"
                  type="text"
                  placeholder="Thread title (e.g. Military Career)"
                  value={newThreadTitle}
                  onChange={(e) => setNewThreadTitle(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void createLifeThread();
                  }}
                  disabled={isSavingThread}
                  style={{ flex: 1 }}
                />
                <button
                  className="primary"
                  type="button"
                  onClick={() => void createLifeThread()}
                  disabled={!newThreadTitle.trim() || isSavingThread}
                >
                  Create Thread
                </button>
              </div>
            )}

            {lifeThreads.length === 0 ? (
              <p className="meta">No threads yet.</p>
            ) : (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.5rem",
                  marginBottom: "0.75rem",
                }}
              >
                {lifeThreads.map((thread) => (
                  <article
                    key={thread.id}
                    className="memory"
                    style={{ padding: "0.55rem 0.75rem" }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.45rem",
                        flexWrap: "wrap",
                      }}
                    >
                      <span className="entityPill entityPillThread">
                        Thread
                      </span>
                      {editingThreadTitleId === thread.id ? (
                        <div className="controls" style={{ flex: 1 }}>
                          <input
                            className="directoryInput"
                            type="text"
                            value={editingThreadTitleValue}
                            autoFocus
                            onChange={(e) =>
                              setEditingThreadTitleValue(e.target.value)
                            }
                            onKeyDown={(e) => {
                              if (e.key === "Enter")
                                void saveThreadTitle(
                                  thread.id,
                                  editingThreadTitleValue,
                                );
                              if (e.key === "Escape") {
                                setEditingThreadTitleId(null);
                                setEditingThreadTitleValue("");
                              }
                            }}
                            style={{ flex: 1 }}
                          />
                          <button
                            className="primary"
                            type="button"
                            onClick={() =>
                              void saveThreadTitle(
                                thread.id,
                                editingThreadTitleValue,
                              )
                            }
                            disabled={!editingThreadTitleValue.trim()}
                          >
                            Save
                          </button>
                          <button
                            className="secondary"
                            type="button"
                            onClick={() => {
                              setEditingThreadTitleId(null);
                              setEditingThreadTitleValue("");
                            }}
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <>
                          <strong>{thread.title}</strong>
                          <span className="badge">
                            {thread.event_count} event
                            {thread.event_count === 1 ? "" : "s"}
                          </span>
                          <span className="badge">
                            {thread.epic_count} epic
                            {thread.epic_count === 1 ? "" : "s"}
                          </span>
                          <button
                            className="secondary"
                            type="button"
                            title="Rename thread"
                            style={{
                              padding: "0.1rem 0.45rem",
                              fontSize: "0.8rem",
                            }}
                            onClick={() => {
                              setEditingThreadTitleId(thread.id);
                              setEditingThreadTitleValue(thread.title);
                            }}
                          >
                            ✏️
                          </button>
                          <button
                            className="secondary"
                            type="button"
                            title="Delete thread"
                            style={{
                              padding: "0.1rem 0.45rem",
                              fontSize: "0.8rem",
                              color: "var(--danger, #c0392b)",
                            }}
                            onClick={() =>
                              void doDeleteThread(thread.id, thread.title)
                            }
                          >
                            🗑
                          </button>
                        </>
                      )}
                    </div>
                    {thread.summary && (
                      <p className="meta" style={{ marginTop: "0.25rem" }}>
                        {thread.summary}
                      </p>
                    )}
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="panel" style={{ marginTop: "1rem" }}>
            <div className="periodsHeader">
              <div>
                <h2>Life Periods</h2>
                <p className="meta">
                  Start with periods, expand only the one you want, and add
                  events inside that period.
                </p>
              </div>
              <div
                className="controls"
                style={{ justifyContent: "flex-end", marginBottom: 0 }}
              >
                <label
                  className="meta"
                  htmlFor="period-sort-mode"
                  style={{ alignSelf: "center" }}
                >
                  Sort
                </label>
                <select
                  id="period-sort-mode"
                  className="directoryInput"
                  value={periodSortMode}
                  onChange={(e) =>
                    setPeriodSortMode(e.target.value as PeriodSortMode)
                  }
                  disabled={isSavingLifeStructure || isRecording || isLoading}
                  style={{ width: "min(18rem, 44vw)" }}
                >
                  <option value="timeline-asc">Timeline: oldest first</option>
                  <option value="timeline-desc">Timeline: newest first</option>
                  <option value="events-desc">Most active first</option>
                  <option value="updated-desc">Recently updated</option>
                  <option value="title-asc">Title: A to Z</option>
                </select>
                <h3
                  style={{
                    cursor: "pointer",
                    userSelect: "none",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.4rem",
                    margin: 0,
                  }}
                  onClick={() => setIsPeriodComposerOpen((current) => !current)}
                >
                  <span>{isPeriodComposerOpen ? "▾" : "▸"}</span>
                  New period
                </h3>
              </div>
            </div>

            <PeriodComposer
              isOpen={isPeriodComposerOpen}
              newPeriodTitle={newPeriodTitle}
              setNewPeriodTitle={setNewPeriodTitle}
              newPeriodStart={newPeriodStart}
              setNewPeriodStart={setNewPeriodStart}
              newPeriodEnd={newPeriodEnd}
              setNewPeriodEnd={setNewPeriodEnd}
              newPeriodSummary={newPeriodSummary}
              setNewPeriodSummary={setNewPeriodSummary}
              isBusy={isSavingLifeStructure || isRecording || isLoading}
              createLifePeriod={createLifePeriod}
              onCreated={() => setIsPeriodComposerOpen(false)}
            />

            <div className="lifePeriodList">
              {lifePeriods.length === 0 && (
                <p className="meta">No periods created yet.</p>
              )}
              {sortedLifePeriods.map((period) => {
                const eventsForPeriod = [
                  ...lifeEvents.filter(
                    (event) => event.period_id === period.id,
                  ),
                ].sort(compareEventsByStartDate);
                const eventsForPeriodIds = new Set(
                  eventsForPeriod.map((e) => e.id),
                );
                const periodQuestionCount =
                  (questionsByPeriodNoEvent.get(period.id)?.length ?? 0) +
                  questionsWithContext.filter(
                    (item) =>
                      item.sourceEvent !== null &&
                      eventsForPeriodIds.has(item.sourceEvent.id),
                  ).length;
                const isExpanded = Boolean(expandedPeriods[period.id]);
                const draft = eventDraftsByPeriod[period.id] || {
                  title: "",
                  dateText: "",
                  description: "",
                };
                const periodAnalysis = periodAnalysisById[period.id] || null;

                return (
                  <LifePeriodCard
                    key={period.id}
                    period={period}
                    isHighlighted={
                      highlightedElementId === `period-card-${period.id}`
                    }
                  >
                    <div className="periodSummaryRow">
                      <div style={{ flex: 1 }}>
                        {editingPeriodTitleId === period.id ? (
                          <div
                            className="controls"
                            style={{ marginBottom: "0.35rem" }}
                          >
                            <input
                              className="directoryInput"
                              type="text"
                              value={editingPeriodTitleValue}
                              autoFocus
                              onChange={(e) =>
                                setEditingPeriodTitleValue(e.target.value)
                              }
                              onKeyDown={(e) => {
                                if (e.key === "Enter")
                                  renamePeriod(
                                    period.id,
                                    editingPeriodTitleValue,
                                  );
                                if (e.key === "Escape") {
                                  setEditingPeriodTitleId(null);
                                  setEditingPeriodTitleValue("");
                                }
                              }}
                              style={{ flex: 1 }}
                            />
                            <button
                              className="primary"
                              type="button"
                              onClick={() =>
                                renamePeriod(period.id, editingPeriodTitleValue)
                              }
                              disabled={!editingPeriodTitleValue.trim()}
                            >
                              Save
                            </button>
                            <button
                              className="secondary"
                              type="button"
                              onClick={() => {
                                setEditingPeriodTitleId(null);
                                setEditingPeriodTitleValue("");
                              }}
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <div
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: "0.5rem",
                              flexWrap: "wrap",
                            }}
                          >
                            <span className="entityPill entityPillPeriod">
                              Period
                            </span>
                            <h3 style={{ margin: 0 }}>{period.title}</h3>
                            <button
                              className="secondary"
                              type="button"
                              title="Edit title"
                              style={{
                                padding: "0.1rem 0.45rem",
                                fontSize: "0.8rem",
                              }}
                              onClick={() => {
                                setEditingPeriodTitleId(period.id);
                                setEditingPeriodTitleValue(period.title);
                              }}
                            >
                              ✏️
                            </button>
                          </div>
                        )}
                        {editingPeriodDatesId === period.id ? (
                          <div
                            className="controls"
                            style={{
                              marginBottom: "0.35rem",
                              flexWrap: "wrap",
                            }}
                          >
                            <input
                              className="directoryInput"
                              type="text"
                              placeholder="Start (e.g. 1948)"
                              value={editingPeriodStartValue}
                              autoFocus
                              onChange={(e) =>
                                setEditingPeriodStartValue(e.target.value)
                              }
                              onKeyDown={(e) => {
                                if (e.key === "Enter")
                                  savePeriodDates(period.id);
                                if (e.key === "Escape")
                                  setEditingPeriodDatesId(null);
                              }}
                              style={{ width: "9rem" }}
                            />
                            <span
                              className="meta"
                              style={{ alignSelf: "center" }}
                            >
                              to
                            </span>
                            <input
                              className="directoryInput"
                              type="text"
                              placeholder="End (e.g. 1960)"
                              value={editingPeriodEndValue}
                              onChange={(e) =>
                                setEditingPeriodEndValue(e.target.value)
                              }
                              onKeyDown={(e) => {
                                if (e.key === "Enter")
                                  savePeriodDates(period.id);
                                if (e.key === "Escape")
                                  setEditingPeriodDatesId(null);
                              }}
                              style={{ width: "9rem" }}
                            />
                            <button
                              className="primary"
                              type="button"
                              onClick={() => savePeriodDates(period.id)}
                            >
                              Save
                            </button>
                            <button
                              className="secondary"
                              type="button"
                              onClick={() => setEditingPeriodDatesId(null)}
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <p className="meta">
                            Range:{" "}
                            <span className="badge">
                              {period.start_date_text || "unknown"}
                            </span>{" "}
                            to{" "}
                            <span className="badge">
                              {period.end_date_text || "unknown"}
                            </span>
                            <button
                              className="secondary"
                              type="button"
                              title="Edit dates"
                              style={{
                                marginLeft: "0.4rem",
                                padding: "0.1rem 0.45rem",
                                fontSize: "0.8rem",
                              }}
                              onClick={() => {
                                setEditingPeriodDatesId(period.id);
                                setEditingPeriodStartValue(
                                  period.start_date_text ?? "",
                                );
                                setEditingPeriodEndValue(
                                  period.end_date_text ?? "",
                                );
                              }}
                            >
                              ✏️
                            </button>
                          </p>
                        )}
                        <p className="meta">
                          Events:{" "}
                          <span className="badge">
                            {eventsForPeriod.length}
                          </span>{" "}
                          Assets:{" "}
                          <span className="badge">{period.asset_count}</span>
                          {periodQuestionCount > 0 && (
                            <>
                              {" "}
                              Questions:{" "}
                              <span className="badge">
                                {periodQuestionCount}
                              </span>
                            </>
                          )}
                        </p>
                      </div>
                    </div>

                    <h3
                      style={{
                        marginTop: 0,
                        cursor: "pointer",
                        userSelect: "none",
                        display: "flex",
                        alignItems: "center",
                        gap: "0.4rem",
                      }}
                      onClick={() => togglePeriodExpanded(period.id)}
                    >
                      <span>{isExpanded ? "▾" : "▸"}</span>
                      Period Details
                    </h3>

                    {isExpanded && (
                      <>
                        {period.summary && (
                          <p>{displayPeriodSummary(period.summary)}</p>
                        )}

                        <div
                          className="controls"
                          style={{ marginTop: "0.45rem" }}
                        >
                          <button
                            className="primary"
                            type="button"
                            onClick={() =>
                              void startQuickMemoryCaptureForPeriod(period)
                            }
                            disabled={
                              isSavingLifeStructure || isRecording || isLoading
                            }
                          >
                            Quick Memory in This Period
                          </button>
                          <button
                            className="secondary"
                            type="button"
                            onClick={() => analyzePeriod(period.id)}
                            disabled={
                              periodAnalysisBusyId === period.id ||
                              isSavingLifeStructure ||
                              isRecording ||
                              isLoading
                            }
                          >
                            Analyze Period
                          </button>
                          <button
                            className="secondary"
                            type="button"
                            onClick={() =>
                              analyzePeriod(period.id, {
                                regenerateSummary: true,
                              })
                            }
                            disabled={
                              periodAnalysisBusyId === period.id ||
                              isSavingLifeStructure ||
                              isRecording ||
                              isLoading
                            }
                          >
                            Generate Summary
                          </button>
                          <button
                            className="secondary"
                            type="button"
                            onClick={() =>
                              setMergingPeriodId(
                                mergingPeriodId === period.id
                                  ? null
                                  : period.id,
                              )
                            }
                            disabled={
                              lifePeriods.length < 2 ||
                              isSavingLifeStructure ||
                              isRecording ||
                              isLoading
                            }
                          >
                            Merge Into…
                          </button>
                          <button
                            className="secondary"
                            type="button"
                            style={{ color: "var(--danger, #c0392b)" }}
                            onClick={() =>
                              deletePeriod(period.id, period.title)
                            }
                            disabled={
                              isSavingLifeStructure || isRecording || isLoading
                            }
                          >
                            Delete Period
                          </button>
                          {periodAnalysis &&
                            (periodAnalysis.recommended_titles.length > 0 ||
                              !periodAnalysis.coverage_ok) && (
                              <button
                                className="primary"
                                type="button"
                                onClick={() =>
                                  analyzePeriod(period.id, {
                                    applyDates: true,
                                    applyTitle: true,
                                    regenerateSummary: true,
                                  })
                                }
                                disabled={
                                  periodAnalysisBusyId === period.id ||
                                  isSavingLifeStructure ||
                                  isRecording ||
                                  isLoading
                                }
                              >
                                Apply Top Recommendation
                              </button>
                            )}
                        </div>

                        {mergingPeriodId === period.id && (
                          <div
                            className="controls"
                            style={{ marginTop: "0.35rem", flexWrap: "wrap" }}
                          >
                            <span
                              className="meta"
                              style={{ alignSelf: "center" }}
                            >
                              Move all events &amp; assets into:
                            </span>
                            {sortedLifePeriods
                              .filter((p) => p.id !== period.id)
                              .map((p) => (
                                <button
                                  key={p.id}
                                  className="secondary"
                                  type="button"
                                  onClick={() => mergePeriod(period.id, p.id)}
                                >
                                  {p.title}
                                </button>
                              ))}
                            <button
                              className="secondary"
                              type="button"
                              onClick={() => setMergingPeriodId(null)}
                            >
                              Cancel
                            </button>
                          </div>
                        )}

                        {periodAnalysis && (
                          <article
                            className="memory"
                            style={{ marginBottom: "0.65rem" }}
                          >
                            <h3>Period Analysis</h3>
                            <p className="meta">
                              Coverage:{" "}
                              <span className="badge">
                                {periodAnalysis.coverage_ok
                                  ? "Good"
                                  : "Needs update"}
                              </span>
                            </p>
                            <p className="meta">
                              {periodAnalysis.coverage_reasoning}
                            </p>
                            {periodAnalysis.recommended_start_date_text &&
                              periodAnalysis.recommended_end_date_text && (
                                <p className="meta">
                                  Recommended date range:{" "}
                                  <span className="badge">
                                    {periodAnalysis.recommended_start_date_text}
                                  </span>{" "}
                                  to{" "}
                                  <span className="badge">
                                    {periodAnalysis.recommended_end_date_text}
                                  </span>
                                </p>
                              )}
                            {periodAnalysis.recommended_titles.length > 0 && (
                              <div style={{ marginTop: "0.45rem" }}>
                                <p className="meta">
                                  <strong>Suggested titles</strong> — click one
                                  to apply it:
                                </p>
                                <div
                                  className="controls"
                                  style={{ flexWrap: "wrap" }}
                                >
                                  {periodAnalysis.recommended_titles.map(
                                    (title) => (
                                      <button
                                        key={title}
                                        className="secondary"
                                        type="button"
                                        style={{ fontWeight: "normal" }}
                                        onClick={async () => {
                                          await renamePeriod(period.id, title);
                                          setPeriodAnalysisById((current) => ({
                                            ...current,
                                            [period.id]: null,
                                          }));
                                        }}
                                      >
                                        {title}
                                      </button>
                                    ),
                                  )}
                                </div>
                              </div>
                            )}
                            <p className="meta">
                              {periodAnalysis.title_reasoning}
                            </p>
                            {periodAnalysis.generated_summary && (
                              <>
                                <p
                                  className="meta"
                                  style={{ marginTop: "0.55rem" }}
                                >
                                  <strong>Suggested summary</strong>
                                </p>
                                <p>{periodAnalysis.generated_summary}</p>
                                <p className="meta">
                                  {periodAnalysis.summary_reasoning}
                                </p>
                              </>
                            )}
                          </article>
                        )}

                        <article
                          className="memory"
                          style={{ marginBottom: "0.65rem" }}
                        >
                          <h3>Add Event to {period.title}</h3>
                          <div className="lifeFormFields">
                            <input
                              className="directoryInput"
                              type="text"
                              placeholder="Event title"
                              value={draft.title}
                              onChange={(e) =>
                                updateEventDraftForPeriod(period.id, {
                                  title: e.target.value,
                                })
                              }
                              disabled={
                                isSavingLifeStructure ||
                                isRecording ||
                                isLoading
                              }
                            />
                            <input
                              className="directoryInput"
                              type="text"
                              placeholder="Event date text"
                              value={draft.dateText}
                              onChange={(e) =>
                                updateEventDraftForPeriod(period.id, {
                                  dateText: e.target.value,
                                })
                              }
                              disabled={
                                isSavingLifeStructure ||
                                isRecording ||
                                isLoading
                              }
                            />
                            <input
                              className="directoryInput"
                              type="text"
                              placeholder="Location (optional)"
                              value={draft.location || ""}
                              onChange={(e) =>
                                updateEventDraftForPeriod(period.id, {
                                  location: e.target.value,
                                })
                              }
                              disabled={
                                isSavingLifeStructure ||
                                isRecording ||
                                isLoading
                              }
                            />
                            <textarea
                              className="directoryInput"
                              placeholder="Event description"
                              value={draft.description}
                              onChange={(e) =>
                                updateEventDraftForPeriod(period.id, {
                                  description: e.target.value,
                                })
                              }
                              disabled={
                                isSavingLifeStructure ||
                                isRecording ||
                                isLoading
                              }
                              rows={3}
                            />
                          </div>
                          <div className="controls">
                            <button
                              className="primary"
                              type="button"
                              onClick={() =>
                                createLifeEvent({
                                  title: draft.title,
                                  eventDateText: draft.dateText,
                                  description: draft.description,
                                  location: draft.location,
                                  periodId: period.id,
                                  resetPeriodDraftId: period.id,
                                })
                              }
                              disabled={
                                !draft.title.trim() ||
                                isSavingLifeStructure ||
                                isRecording ||
                                isLoading
                              }
                            >
                              Create Event
                            </button>
                          </div>
                        </article>

                        <article
                          className="memory"
                          style={{ marginBottom: "0.65rem" }}
                        >
                          <h3>Add Epic to {period.title}</h3>
                          <p className="meta">
                            Epics group related events within this period — e.g.
                            "Deployment to Bahrain" or "Summer Vacation 2010".
                          </p>
                          <div className="controls">
                            <input
                              className="directoryInput"
                              type="text"
                              placeholder="Epic title"
                              value={epicDraftsByPeriod[period.id] ?? ""}
                              onChange={(e) =>
                                setEpicDraftsByPeriod((prev) => ({
                                  ...prev,
                                  [period.id]: e.target.value,
                                }))
                              }
                              onKeyDown={(e) => {
                                if (e.key === "Enter")
                                  void createLifeEpic(period.id);
                              }}
                              disabled={
                                isSavingLifeStructure ||
                                isRecording ||
                                isLoading
                              }
                              style={{ flex: 1 }}
                            />
                            <button
                              className="primary"
                              type="button"
                              onClick={() => void createLifeEpic(period.id)}
                              disabled={
                                !(epicDraftsByPeriod[period.id] ?? "").trim() ||
                                isSavingLifeStructure ||
                                isRecording ||
                                isLoading
                              }
                            >
                              Create Epic
                            </button>
                          </div>
                        </article>

                        {(questionsByPeriodNoEvent.get(period.id)?.length ??
                          0) > 0 && (
                          <div className="inlineQuestionList">
                            <p className="inlineQuestionListLabel">
                              Open questions for this period
                            </p>
                            {questionsByPeriodNoEvent
                              .get(period.id)!
                              .map(({ question, sourceMemory }) => (
                                <article
                                  key={question.id}
                                  className="questionCard inlineQuestionCard"
                                >
                                  <p className="questionText">
                                    {question.text}
                                  </p>
                                  {sourceMemory && (
                                    <p className="questionSource">
                                      From:{" "}
                                      <em>{sourceMemory.event_description}</em>
                                    </p>
                                  )}
                                  <div className="questionActions">
                                    <button
                                      className="primary"
                                      type="button"
                                      onClick={() => {
                                        setActiveQuestion(question);
                                        window.scrollTo({
                                          top: 0,
                                          behavior: "smooth",
                                        });
                                      }}
                                      disabled={isRecording || isLoading}
                                    >
                                      Answer this
                                    </button>
                                    <button
                                      className="ghost"
                                      type="button"
                                      onClick={() =>
                                        dismissQuestion(question.id)
                                      }
                                      disabled={isRecording || isLoading}
                                    >
                                      Remove
                                    </button>
                                  </div>
                                </article>
                              ))}
                          </div>
                        )}

                        {(() => {
                          const epicsForPeriod = [
                            ...lifeEpics.filter(
                              (e) => e.period_id === period.id,
                            ),
                          ].sort(compareEpicsByStartDate);
                          const ungroupedEvents = eventsForPeriod.filter(
                            (ev) =>
                              ev.epic_id === null ||
                              !epicsForPeriod.some(
                                (ep) => ep.id === ev.epic_id,
                              ),
                          );
                          return (
                            <div className="lifeEventList">
                              {eventsForPeriod.length === 0 && (
                                <p className="meta">
                                  No events in this period yet.
                                </p>
                              )}
                              {ungroupedEvents.length > 0 && (
                                <div className="unepicedEventList">
                                  {ungroupedEvents.map((event) =>
                                    renderEventCard(
                                      event,
                                      eventsForPeriod,
                                      epicsForPeriod,
                                    ),
                                  )}
                                </div>
                              )}
                              {epicsForPeriod.map((epic) => {
                                const epicEvents = eventsForPeriod.filter(
                                  (ev) => ev.epic_id === epic.id,
                                );
                                const isEpicExpanded = Boolean(
                                  expandedEpics[epic.id],
                                );
                                return (
                                  <EpicCard
                                    key={epic.id}
                                    epic={epic}
                                    periods={lifePeriods}
                                    threads={lifeThreads}
                                    isOpen={isEpicExpanded}
                                    isRenamingTitle={
                                      editingEpicTitleId === epic.id
                                    }
                                    renamingTitleValue={editingEpicTitleValue}
                                    setRenamingTitleValue={
                                      setEditingEpicTitleValue
                                    }
                                    onToggleOpen={() =>
                                      toggleEpicExpanded(epic.id)
                                    }
                                    onStartRenameTitle={() => {
                                      setEditingEpicTitleId(epic.id);
                                      setEditingEpicTitleValue(epic.title);
                                    }}
                                    onSaveRenameTitle={() =>
                                      void saveEpicTitle(
                                        epic.id,
                                        editingEpicTitleValue,
                                      )
                                    }
                                    onCancelRenameTitle={() => {
                                      setEditingEpicTitleId(null);
                                      setEditingEpicTitleValue("");
                                    }}
                                    onDelete={() =>
                                      void doDeleteEpic(epic.id, epic.title)
                                    }
                                    onAssignThread={(threadId) =>
                                      void doAssignEpicToThread(
                                        epic.id,
                                        threadId,
                                      )
                                    }
                                    onAssignPeriod={(periodId) =>
                                      void doAssignEpicToPeriod(
                                        epic.id,
                                        periodId,
                                      )
                                    }
                                    onCreateEvent={(title) =>
                                      createLifeEventInEpic(epic.id, title)
                                    }
                                    isBusy={
                                      isSavingLifeStructure ||
                                      isRecording ||
                                      isLoading
                                    }
                                  >
                                    {epicEvents.length === 0 ? (
                                      <p className="meta">
                                        No events assigned to this epic yet.
                                      </p>
                                    ) : (
                                      epicEvents.map((event) =>
                                        renderEventCard(
                                          event,
                                          eventsForPeriod,
                                          epicsForPeriod,
                                        ),
                                      )
                                    )}
                                  </EpicCard>
                                );
                              })}
                            </div>
                          );
                        })()}
                      </>
                    )}
                  </LifePeriodCard>
                );
              })}
            </div>

            <article className="memory" style={{ marginTop: "0.75rem" }}>
              <h3>Unassigned Events</h3>
              <p className="meta">
                Events with no period assignment appear here so they never
                disappear from view.
              </p>
              <div className="lifeEventList">
                {unassignedEvents.length === 0 && (
                  <p className="meta">No unassigned events.</p>
                )}
                {unassignedEvents.map((event) =>
                  renderEventCard(event, lifeEvents),
                )}
              </div>
            </article>

            <UnlinkedAssetsInbox
              unlinkedAssets={unlinkedAssets}
              highlightedElementId={highlightedElementId}
              expandedAssetRowIds={expandedAssetRowIds}
              setExpandedAssetRowIds={setExpandedAssetRowIds}
              editingAssetTitleId={editingAssetTitleId}
              setEditingAssetTitleId={setEditingAssetTitleId}
              editingAssetTitleValue={editingAssetTitleValue}
              setEditingAssetTitleValue={setEditingAssetTitleValue}
              assetTitleSavingId={assetTitleSavingId}
              saveAssetTitle={saveAssetTitle}
              editingAssetNotesId={editingAssetNotesId}
              setEditingAssetNotesId={setEditingAssetNotesId}
              editingAssetNotesValue={editingAssetNotesValue}
              setEditingAssetNotesValue={setEditingAssetNotesValue}
              assetNotesSavingId={assetNotesSavingId}
              saveAssetNotes={saveAssetNotes}
              editingAssetCapturedDateId={editingAssetCapturedDateId}
              setEditingAssetCapturedDateId={setEditingAssetCapturedDateId}
              editingAssetCapturedDateValue={editingAssetCapturedDateValue}
              setEditingAssetCapturedDateValue={
                setEditingAssetCapturedDateValue
              }
              assetCapturedDateSavingId={assetCapturedDateSavingId}
              saveAssetCapturedDate={saveAssetCapturedDate}
              resolveApiUrl={resolveApiUrl}
              formatBytes={formatBytes}
              deleteAsset={deleteAsset}
              lifePeriods={lifePeriods}
              lifeEpics={lifeEpics}
              lifeEvents={lifeEvents}
              createEpicInPeriod={createEpicInPeriod}
              createEventForLinking={createEventForLinking}
              assetLinkTargets={assetLinkTargets}
              setAssetLinkTargets={setAssetLinkTargets}
              linkUnlinkedAssetToEvent={linkUnlinkedAssetToEvent}
              isSavingLifeStructure={isSavingLifeStructure}
            />
          </section>

          <section className="timeline">
            {mainCharacterName === null && (
              <article className="questionCard characterPromptCard">
                <p className="questionText">
                  Before we continue, what should we call you on your memory
                  cards?
                </p>
                {showCharacterInput ? (
                  <div className="characterInputRow">
                    <input
                      className="characterInput"
                      type="text"
                      placeholder="Your name or nickname"
                      value={characterInputValue}
                      onChange={(e) => setCharacterInputValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && characterInputValue.trim()) {
                          saveMainCharacterName(characterInputValue.trim());
                        }
                      }}
                      autoFocus
                      disabled={isSavingCharacter}
                    />
                    <button
                      className="primary"
                      type="button"
                      onClick={() => {
                        if (characterInputValue.trim()) {
                          saveMainCharacterName(characterInputValue.trim());
                        }
                      }}
                      disabled={
                        isSavingCharacter || !characterInputValue.trim()
                      }
                    >
                      Save
                    </button>
                    <button
                      className="ghost"
                      type="button"
                      onClick={() => {
                        setShowCharacterInput(false);
                        setCharacterInputValue("");
                      }}
                      disabled={isSavingCharacter}
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <div className="questionActions">
                    <button
                      className="primary"
                      type="button"
                      onClick={() => setShowCharacterInput(true)}
                    >
                      Answer this
                    </button>
                    <button
                      className="ghost"
                      type="button"
                      onClick={() => saveMainCharacterName("")}
                    >
                      Remove
                    </button>
                  </div>
                )}
              </article>
            )}
            {questionsWithNoContext.length > 0 && (
              <div className="questionsSection">
                <p
                  className="inlineQuestionListLabel"
                  style={{ marginBottom: "0.5rem" }}
                >
                  General open questions
                </p>
                {questionsWithNoContext.map(({ question }) => (
                  <article key={question.id} className="questionCard">
                    <p className="questionText">{question.text}</p>
                    <div className="questionActions">
                      <button
                        className="primary"
                        type="button"
                        onClick={() => {
                          setActiveQuestion(question);
                          window.scrollTo({ top: 0, behavior: "smooth" });
                        }}
                        disabled={isRecording || isLoading}
                      >
                        Answer this
                      </button>
                      <button
                        className="ghost"
                        type="button"
                        onClick={() => dismissQuestion(question.id)}
                        disabled={isRecording || isLoading}
                      >
                        Remove
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            )}
            {timelineStandaloneMemories.map((memory) => (
              <MemoryCard
                key={memory.id}
                containerId={`memory-card-${memory.id}`}
                isHighlighted={
                  highlightedElementId === `memory-card-${memory.id}`
                }
                memory={memory}
                linkedQuestions={questions.filter(
                  (q) => q.source_memory_id === memory.id,
                )}
                peopleOptions={peopleDirectory}
                formatBytes={formatBytes}
                resolveApiUrl={resolveApiUrl}
                onAcceptSuggestion={acceptResearchSuggestion}
                onDismissSuggestion={dismissResearchSuggestion}
                onReanalyze={reanalyzeMemory}
                onDelete={deleteMemory}
                onAssignRecorder={assignRecorder}
                isBusy={
                  isLoading || memoryActionId === memory.id || isRecording
                }
              />
            ))}
            {timeline.length === 0 && (
              <p className="meta">No memories yet. Record your first one.</p>
            )}
            {timeline.length > 0 && timelineStandaloneMemories.length === 0 && (
              <p className="meta">
                All captured memories are organized in Life Periods above.
              </p>
            )}
          </section>
        </>
      </div>

      <CaptureSidebar
        isCaptureDrawerOpen={isCaptureDrawerOpen}
        setIsCaptureDrawerOpen={setIsCaptureDrawerOpen}
        selectedDeviceId={selectedDeviceId}
        setSelectedDeviceId={setSelectedDeviceId}
        audioDevices={audioDevices}
        audioLevel={audioLevel}
        isRecording={isRecording}
        isLoading={isLoading}
        activeQuestion={activeQuestion}
        setActiveQuestion={setActiveQuestion}
        status={status}
        startRecording={() => startRecording()}
        stopRecording={stopRecording}
        cancelRecording={cancelRecording}
        documentFileInputRef={documentFileInputRef}
        isUploadingDocument={isUploadingDocument}
        isReadingClipboard={isReadingClipboard}
        isDragOverDocumentTarget={isDragOverDocumentTarget}
        documentUploadError={documentUploadError}
        uploadDocument={uploadDocument}
        pasteImageFromClipboard={pasteImageFromClipboard}
        onDocumentPasteZonePaste={onDocumentPasteZonePaste}
        onDocumentDragEnter={onDocumentDragEnter}
        onDocumentDragOver={onDocumentDragOver}
        onDocumentDragLeave={onDocumentDragLeave}
        onDocumentDrop={onDocumentDrop}
        pendingRecording={pendingRecording}
        formatBytes={formatBytes}
        audioDeviceStorageKey={AUDIO_DEVICE_STORAGE_KEY}
      />
    </main>
  );
}
