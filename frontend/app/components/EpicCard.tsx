import { useState } from "react";
import type { ReactNode } from "react";
import type { LifeEpic, LifePeriod, LifeThread } from "../types";

type EpicCardProps = {
  epic: LifeEpic;
  periods: LifePeriod[];
  threads: LifeThread[];
  isOpen: boolean;
  isRenamingTitle: boolean;
  renamingTitleValue: string;
  setRenamingTitleValue: (value: string) => void;
  onToggleOpen: () => void;
  onStartRenameTitle: () => void;
  onSaveRenameTitle: () => void;
  onCancelRenameTitle: () => void;
  onDelete: () => void;
  onAssignThread: (threadId: number | null) => void;
  onAssignPeriod: (periodId: number) => void;
  onCreateEvent: (title: string) => Promise<void>;
  isBusy: boolean;
  children: ReactNode;
};

export function EpicCard({
  epic,
  periods,
  threads,
  isOpen,
  isRenamingTitle,
  renamingTitleValue,
  setRenamingTitleValue,
  onToggleOpen,
  onStartRenameTitle,
  onSaveRenameTitle,
  onCancelRenameTitle,
  onDelete,
  onAssignThread,
  onAssignPeriod,
  onCreateEvent,
  isBusy,
  children,
}: EpicCardProps) {
  const [showThreadPicker, setShowThreadPicker] = useState(false);
  const [showPeriodPicker, setShowPeriodPicker] = useState(false);
  const [newEventDraft, setNewEventDraft] = useState("");
  const assignedThread = threads.find((t) => t.id === epic.thread_id) ?? null;

  return (
    <div className="epicSection">
      <div className="epicHeader">
        <span className="entityPill entityPillEpic">Epic</span>
        {isRenamingTitle ? (
          <div className="controls" style={{ flex: 1 }}>
            <input
              className="directoryInput"
              type="text"
              value={renamingTitleValue}
              autoFocus
              onChange={(e) => setRenamingTitleValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onSaveRenameTitle();
                if (e.key === "Escape") onCancelRenameTitle();
              }}
              style={{ flex: 1 }}
            />
            <button
              className="primary"
              type="button"
              onClick={onSaveRenameTitle}
              disabled={!renamingTitleValue.trim() || isBusy}
            >
              Save
            </button>
            <button
              className="secondary"
              type="button"
              onClick={onCancelRenameTitle}
            >
              Cancel
            </button>
          </div>
        ) : (
          <>
            <h4 className="epicTitle">{epic.title}</h4>
            {assignedThread && (
              <span
                className="entityPill entityPillThread"
                style={{ fontSize: "0.75rem", marginLeft: "0.4rem" }}
              >
                {assignedThread.title}
              </span>
            )}
            {epic.start_date_text && (
              <span
                className="badge"
                style={{ marginLeft: "0.4rem", fontSize: "0.8rem" }}
              >
                {epic.start_date_text}
                {epic.end_date_text &&
                epic.end_date_text !== epic.start_date_text
                  ? ` – ${epic.end_date_text}`
                  : ""}
              </span>
            )}
            <span
              className="badge"
              style={{ marginLeft: "0.4rem", fontSize: "0.8rem" }}
            >
              {epic.event_count} event{epic.event_count === 1 ? "" : "s"}
            </span>
            <div
              className="controls"
              style={{ marginLeft: "auto", gap: "0.3rem" }}
            >
              <h4
                style={{
                  cursor: "pointer",
                  userSelect: "none",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.4rem",
                  margin: 0,
                  fontSize: "0.8rem",
                }}
                onClick={onToggleOpen}
              >
                <span>{isOpen ? "▾" : "▸"}</span>
                Details
              </h4>
              <button
                className="secondary"
                type="button"
                title="Assign thread"
                style={{ padding: "0.1rem 0.45rem", fontSize: "0.8rem" }}
                onClick={() => setShowThreadPicker((v) => !v)}
                disabled={isBusy}
              >
                🧵
              </button>
              <button
                className="secondary"
                type="button"
                title="Move epic to period"
                style={{ padding: "0.1rem 0.45rem", fontSize: "0.8rem" }}
                onClick={() => setShowPeriodPicker((v) => !v)}
                disabled={isBusy}
              >
                📁
              </button>
              <button
                className="secondary"
                type="button"
                title="Rename epic"
                style={{ padding: "0.1rem 0.45rem", fontSize: "0.8rem" }}
                onClick={onStartRenameTitle}
                disabled={isBusy}
              >
                ✏️
              </button>
              <button
                className="secondary"
                type="button"
                title="Delete epic"
                style={{
                  padding: "0.1rem 0.45rem",
                  fontSize: "0.8rem",
                  color: "var(--danger, #c0392b)",
                }}
                onClick={onDelete}
                disabled={isBusy}
              >
                🗑
              </button>
            </div>
          </>
        )}
      </div>
      {isOpen && showThreadPicker && (
        <div
          className="controls"
          style={{ padding: "0.4rem 0.8rem", gap: "0.4rem", flexWrap: "wrap" }}
        >
          <span
            style={{ fontSize: "0.85rem", color: "var(--text-muted, #888)" }}
          >
            Tag thread:
          </span>
          {threads.map((t) => (
            <button
              key={t.id}
              className={`secondary${epic.thread_id === t.id ? " active" : ""}`}
              type="button"
              style={{ fontSize: "0.8rem", padding: "0.15rem 0.5rem" }}
              onClick={() => {
                onAssignThread(epic.thread_id === t.id ? null : t.id);
                setShowThreadPicker(false);
              }}
              disabled={isBusy}
            >
              {t.title}
            </button>
          ))}
          {epic.thread_id !== null && (
            <button
              className="secondary"
              type="button"
              style={{
                fontSize: "0.8rem",
                padding: "0.15rem 0.5rem",
                color: "var(--danger, #c0392b)",
              }}
              onClick={() => {
                onAssignThread(null);
                setShowThreadPicker(false);
              }}
              disabled={isBusy}
            >
              Clear
            </button>
          )}
        </div>
      )}
      {isOpen && showPeriodPicker && (
        <div
          className="controls"
          style={{ padding: "0.4rem 0.8rem", gap: "0.4rem", flexWrap: "wrap" }}
        >
          <span
            style={{ fontSize: "0.85rem", color: "var(--text-muted, #888)" }}
          >
            Move to period:
          </span>
          {periods.map((period) => (
            <button
              key={period.id}
              className={`secondary${epic.period_id === period.id ? " active" : ""}`}
              type="button"
              style={{ fontSize: "0.8rem", padding: "0.15rem 0.5rem" }}
              onClick={() => {
                if (epic.period_id !== period.id) {
                  onAssignPeriod(period.id);
                }
                setShowPeriodPicker(false);
              }}
              disabled={isBusy}
            >
              {period.title}
            </button>
          ))}
        </div>
      )}
      {isOpen && (
        <>
          <div className="epicEventList">{children}</div>
          <div
            className="controls"
            style={{ padding: "0.4rem 0.8rem", gap: "0.4rem" }}
          >
            <input
              className="directoryInput"
              type="text"
              placeholder="New event title…"
              value={newEventDraft}
              onChange={(e) => setNewEventDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && newEventDraft.trim()) {
                  void onCreateEvent(newEventDraft.trim()).then(() =>
                    setNewEventDraft(""),
                  );
                }
              }}
              disabled={isBusy}
              style={{ flex: 1, fontSize: "0.85rem" }}
            />
            <button
              className="primary"
              type="button"
              onClick={() => {
                if (newEventDraft.trim()) {
                  void onCreateEvent(newEventDraft.trim()).then(() =>
                    setNewEventDraft(""),
                  );
                }
              }}
              disabled={!newEventDraft.trim() || isBusy}
              style={{ fontSize: "0.85rem", whiteSpace: "nowrap" }}
            >
              + Add Event
            </button>
          </div>
        </>
      )}
    </div>
  );
}
