import type { Dispatch, SetStateAction } from "react";
import { MemoryCard } from "./MemoryCard";
import { collectEventMemoryIds } from "../lib/homePageHelpers";
import type {
  AssetEntry,
  DirectoryEntry,
  LifeEvent,
  MemoryEntry,
  Question,
} from "../types";

type EventLinkedMemoriesProps = {
  event: LifeEvent;
  activeEventId: number | null;
  activeEventAssets: AssetEntry[];
  timeline: MemoryEntry[];
  highlightedElementId: string | null;
  editingMemoryTitleId: number | null;
  setEditingMemoryTitleId: (id: number | null) => void;
  editingMemoryTitleValue: string;
  setEditingMemoryTitleValue: (value: string) => void;
  memoryTitleSavingId: number | null;
  saveMemoryTitle: (memoryId: number, eventId?: number) => Promise<void>;
  expandedMemoryRowIds: Set<number>;
  setExpandedMemoryRowIds: Dispatch<SetStateAction<Set<number>>>;
  questions: Question[];
  peopleDirectory: DirectoryEntry[];
  formatBytes: (bytes: number) => string;
  resolveApiUrl: (path: string) => string;
  acceptResearchSuggestion: (memoryId: number) => Promise<void>;
  dismissResearchSuggestion: (memoryId: number) => Promise<void>;
  reanalyzeMemory: (memoryId: number) => Promise<void>;
  deleteMemory: (memoryId: number) => Promise<void>;
  assignRecorder: (memoryId: number, personId: number) => Promise<void>;
  isLoading: boolean;
  memoryActionId: number | null;
  isRecording: boolean;
};

export function EventLinkedMemories({
  event,
  activeEventId,
  activeEventAssets,
  timeline,
  highlightedElementId,
  editingMemoryTitleId,
  setEditingMemoryTitleId,
  editingMemoryTitleValue,
  setEditingMemoryTitleValue,
  memoryTitleSavingId,
  saveMemoryTitle,
  expandedMemoryRowIds,
  setExpandedMemoryRowIds,
  questions,
  peopleDirectory,
  formatBytes,
  resolveApiUrl,
  acceptResearchSuggestion,
  dismissResearchSuggestion,
  reanalyzeMemory,
  deleteMemory,
  assignRecorder,
  isLoading,
  memoryActionId,
  isRecording,
}: EventLinkedMemoriesProps) {
  const memoryIds = collectEventMemoryIds(
    event,
    activeEventId === event.id ? activeEventAssets : [],
  );
  const linkedMemories = memoryIds
    .map((memoryId) => timeline.find((memory) => memory.id === memoryId))
    .filter((memory): memory is MemoryEntry => memory !== undefined);

  if (linkedMemories.length === 0) {
    return null;
  }

  return (
    <div className="lifeAssetList">
      <div className="entitySectionLabel">
        <span className="entityPill entityPillMemory">Memory</span>
        Narrative, transcript, and extracted context
      </div>
      {linkedMemories.map((linkedMemory) => (
        <div
          key={`event-memory-${event.id}-${linkedMemory.id}`}
          id={`memory-row-${linkedMemory.id}`}
          className={`lifeAssetRow${highlightedElementId === `memory-card-${linkedMemory.id}` ? " focusPulse" : ""}`}
        >
          <div className="assetRowHeader">
            <span style={{ flex: 1, minWidth: 0 }}>
              <strong>
                {linkedMemory.event_description || `Memory ${linkedMemory.id}`}
              </strong>
              <span className="meta">
                {linkedMemory.estimated_date_text
                  ? ` · ${linkedMemory.estimated_date_text}`
                  : ""}
              </span>
            </span>
            <div
              className="controls"
              style={{ gap: "0.4rem", justifyContent: "flex-end" }}
            >
              {editingMemoryTitleId === linkedMemory.id ? (
                <>
                  <input
                    className="directoryInput"
                    type="text"
                    value={editingMemoryTitleValue}
                    autoFocus
                    onChange={(e) => setEditingMemoryTitleValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        void saveMemoryTitle(linkedMemory.id, event.id);
                      }
                      if (e.key === "Escape") {
                        setEditingMemoryTitleId(null);
                        setEditingMemoryTitleValue("");
                      }
                    }}
                    style={{ minWidth: "14rem", maxWidth: "18rem" }}
                  />
                  <button
                    className="primary"
                    type="button"
                    onClick={() =>
                      void saveMemoryTitle(linkedMemory.id, event.id)
                    }
                    disabled={memoryTitleSavingId === linkedMemory.id}
                  >
                    Save
                  </button>
                  <button
                    className="secondary"
                    type="button"
                    onClick={() => {
                      setEditingMemoryTitleId(null);
                      setEditingMemoryTitleValue("");
                    }}
                  >
                    Cancel
                  </button>
                </>
              ) : (
                <button
                  className="secondary"
                  type="button"
                  style={{
                    padding: "0.1rem 0.55rem",
                    fontSize: "0.8rem",
                    flexShrink: 0,
                  }}
                  onClick={() => {
                    setEditingMemoryTitleId(linkedMemory.id);
                    setEditingMemoryTitleValue(
                      linkedMemory.event_description || "",
                    );
                  }}
                >
                  Edit Title
                </button>
              )}
              <h4
                style={{
                  cursor: "pointer",
                  userSelect: "none",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.4rem",
                  margin: 0,
                  padding: "0.1rem 0.55rem",
                  fontSize: "0.8rem",
                  flexShrink: 0,
                }}
                onClick={() =>
                  setExpandedMemoryRowIds((prev) => {
                    const next = new Set(prev);
                    if (next.has(linkedMemory.id)) next.delete(linkedMemory.id);
                    else next.add(linkedMemory.id);
                    return next;
                  })
                }
              >
                <span>
                  {expandedMemoryRowIds.has(linkedMemory.id) ? "▾" : "▸"}
                </span>
                Details
              </h4>
            </div>
          </div>
          {expandedMemoryRowIds.has(linkedMemory.id) && (
            <MemoryCard
              containerId={`memory-card-${linkedMemory.id}`}
              isHighlighted={
                highlightedElementId === `memory-card-${linkedMemory.id}`
              }
              memory={linkedMemory}
              linkedQuestions={questions.filter(
                (q) => q.source_memory_id === linkedMemory.id,
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
                isLoading || memoryActionId === linkedMemory.id || isRecording
              }
              hideHeader
            />
          )}
        </div>
      ))}
    </div>
  );
}
