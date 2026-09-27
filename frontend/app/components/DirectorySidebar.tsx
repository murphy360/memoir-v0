import { DirectoryEntry } from "../types";
import { DirectoryManager } from "./DirectoryManager";

type DirectorySidebarProps = {
  isDirectoryDrawerOpen: boolean;
  setIsDirectoryDrawerOpen: (value: boolean) => void;
  activeDirectoryTab: "people" | "places";
  setActiveDirectoryTab: (value: "people" | "places") => void;
  directorySearch: string;
  setDirectorySearch: (value: string) => void;
  activeDirectoryCount: number;
  activeDirectoryTotal: number;
  normalizedDirectorySearch: string;
  filteredPeopleDirectory: DirectoryEntry[];
  filteredPlacesDirectory: DirectoryEntry[];
  isBusy: boolean;
  onCreateDirectoryEntry: (
    kind: "people" | "places",
    name: string,
  ) => Promise<void>;
  onRenameDirectoryEntry: (
    kind: "people" | "places",
    itemId: number,
    name: string,
  ) => Promise<void>;
  onDeleteDirectoryEntry: (
    kind: "people" | "places",
    itemId: number,
  ) => Promise<void>;
  onMergePersonEntry: (sourceId: number, intoId: number) => Promise<void>;
  onSplitPersonEntry: (
    sourceId: number,
    newNames: string[],
    keepAlias: boolean,
  ) => Promise<void>;
  onAddPersonAlias: (personId: number, alias: string) => Promise<void>;
  onRemovePersonAlias: (personId: number, alias: string) => Promise<void>;
  onLinkPersonCompreface: (
    personId: number,
    subjectName: string,
  ) => Promise<void>;
  resolveApiUrl: (path: string) => string;
  peopleSortMode: "weighted" | "alphabetical" | "photos";
  setPeopleSortMode: (mode: "weighted" | "alphabetical" | "photos") => void;
};

export function DirectorySidebar(props: DirectorySidebarProps) {
  const {
    isDirectoryDrawerOpen,
    setIsDirectoryDrawerOpen,
    activeDirectoryTab,
    setActiveDirectoryTab,
    directorySearch,
    setDirectorySearch,
    activeDirectoryCount,
    activeDirectoryTotal,
    normalizedDirectorySearch,
    filteredPeopleDirectory,
    filteredPlacesDirectory,
    isBusy,
    onCreateDirectoryEntry,
    onRenameDirectoryEntry,
    onDeleteDirectoryEntry,
    onMergePersonEntry,
    onSplitPersonEntry,
    onAddPersonAlias,
    onRemovePersonAlias,
    onLinkPersonCompreface,
    resolveApiUrl,
    peopleSortMode,
    setPeopleSortMode,
  } = props;
  return (
    <>
      <button
        type="button"
        className="secondary directoryToggle"
        onClick={() => setIsDirectoryDrawerOpen(true)}
      >
        People & Places
      </button>

      {isDirectoryDrawerOpen && (
        <button
          type="button"
          className="directoryBackdrop"
          aria-label="Close directory panel"
          onClick={() => setIsDirectoryDrawerOpen(false)}
        />
      )}

      <aside
        className={`directorySidebar ${isDirectoryDrawerOpen ? "isOpen" : ""}`}
      >
        <div className="directorySidebarHeader">
          <div>
            <h2>Directories</h2>
            <p className="meta directoryMeta">
              {activeDirectoryCount} shown of {activeDirectoryTotal}
            </p>
          </div>
          <button
            type="button"
            className="ghost directoryClose"
            onClick={() => setIsDirectoryDrawerOpen(false)}
          >
            Close
          </button>
        </div>

        <div
          className="directoryTabRow"
          role="tablist"
          aria-label="Directory tabs"
        >
          <button
            type="button"
            role="tab"
            aria-selected={activeDirectoryTab === "people"}
            className={
              activeDirectoryTab === "people" ? "primary" : "secondary"
            }
            onClick={() => setActiveDirectoryTab("people")}
          >
            People
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeDirectoryTab === "places"}
            className={
              activeDirectoryTab === "places" ? "primary" : "secondary"
            }
            onClick={() => setActiveDirectoryTab("places")}
          >
            Places
          </button>
        </div>

        <div className="directoryFilterHeaderRow">
          <label
            className="directoryFilterLabel"
            htmlFor="directory-filter-input"
          >
            Search {activeDirectoryTab === "people" ? "people" : "places"}
          </label>
          <button
            type="button"
            className="ghost directoryFilterClear"
            onClick={() => setDirectorySearch("")}
            disabled={!directorySearch}
          >
            Clear
          </button>
        </div>
        <input
          id="directory-filter-input"
          type="search"
          className="directoryInput"
          placeholder={
            activeDirectoryTab === "people"
              ? "Type a name or alias"
              : "Type a place name"
          }
          value={directorySearch}
          onChange={(event) => setDirectorySearch(event.target.value)}
          autoComplete="off"
        />

        {activeDirectoryTab === "people" ? (
          <>
            <div
              style={{ display: "flex", alignItems: "center", marginBottom: 8 }}
            >
              <label
                htmlFor="people-sort-mode"
                style={{ marginRight: 8, fontSize: 14 }}
              >
                Sort by:
              </label>
              <select
                id="people-sort-mode"
                value={peopleSortMode}
                onChange={(e) =>
                  setPeopleSortMode(
                    e.target.value as "weighted" | "alphabetical" | "photos",
                  )
                }
                style={{ fontSize: 14 }}
              >
                <option value="weighted">Most memories</option>
                <option value="photos">Most photos</option>
                <option value="alphabetical">A-Z</option>
              </select>
            </div>
            <DirectoryManager
              title="People Directory"
              addLabel="Add a person"
              emptyLabel={
                normalizedDirectorySearch
                  ? "No matching people for this search."
                  : "No people have been added yet."
              }
              items={filteredPeopleDirectory}
              showAvatars
              resolveApiUrl={resolveApiUrl}
              isBusy={isBusy}
              onCreate={(name) => onCreateDirectoryEntry("people", name)}
              onRename={(itemId, name) =>
                onRenameDirectoryEntry("people", itemId, name)
              }
              onDelete={(itemId) => onDeleteDirectoryEntry("people", itemId)}
              onMerge={onMergePersonEntry}
              onSplit={onSplitPersonEntry}
              onAddAlias={onAddPersonAlias}
              onRemoveAlias={onRemovePersonAlias}
              onLinkCompreface={onLinkPersonCompreface}
              detailsHrefBuilder={(itemId) => `/people/${itemId}`}
              showDetailActions={false}
            />
          </>
        ) : (
          <DirectoryManager
            title="Places Directory"
            addLabel="Add a place"
            emptyLabel={
              normalizedDirectorySearch
                ? "No matching places for this search."
                : "No places have been added yet."
            }
            items={filteredPlacesDirectory}
            isBusy={isBusy}
            onCreate={(name) => onCreateDirectoryEntry("places", name)}
            onRename={(itemId, name) =>
              onRenameDirectoryEntry("places", itemId, name)
            }
            onDelete={(itemId) => onDeleteDirectoryEntry("places", itemId)}
          />
        )}
      </aside>
    </>
  );
}
