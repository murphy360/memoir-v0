import { useState } from "react";
import type {
  AssetEntry,
  DirectoryEntry,
  LifeEpic,
  LifeEvent,
  LifePeriod,
  LifeThread,
  MemoryEntry,
  Question,
} from "../types";
import { type TimelineBundle, fetchTimelineBundle } from "../lib/memoirApi";
import { dedupeQuestions } from "../lib/memoirUi";

type UseTimelineDataArgs = {
  setStatus: (value: string) => void;
};

export function useTimelineData({ setStatus }: UseTimelineDataArgs) {
  const [timeline, setTimeline] = useState<MemoryEntry[]>([]);
  const [lifePeriods, setLifePeriods] = useState<LifePeriod[]>([]);
  const [lifeThreads, setLifeThreads] = useState<LifeThread[]>([]);
  const [lifeEpics, setLifeEpics] = useState<LifeEpic[]>([]);
  const [lifeEvents, setLifeEvents] = useState<LifeEvent[]>([]);
  const [unlinkedAssets, setUnlinkedAssets] = useState<AssetEntry[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [peopleDirectory, setPeopleDirectory] = useState<DirectoryEntry[]>([]);
  const [placesDirectory, setPlacesDirectory] = useState<DirectoryEntry[]>([]);
  const [mainCharacterName, setMainCharacterName] = useState<
    string | null | undefined
  >(undefined);

  async function loadTimeline(): Promise<TimelineBundle | null> {
    try {
      const data = await fetchTimelineBundle();
      setTimeline(data.memories);
      if (data.questions) {
        setQuestions(dedupeQuestions(data.questions));
      }
      if (data.people) {
        setPeopleDirectory(data.people);
      }
      if (data.places) {
        setPlacesDirectory(data.places);
      }
      if (data.settings) {
        setMainCharacterName(data.settings.main_character_name);
      }
      if (data.threads) {
        setLifeThreads(data.threads);
      }
      if (data.periods) {
        setLifePeriods(data.periods);
      }
      if (data.epics) {
        setLifeEpics(data.epics);
      }
      if (data.events) {
        setLifeEvents(data.events);
      }
      if (data.unlinkedAssets) {
        setUnlinkedAssets(data.unlinkedAssets);
      }
      return data;
    } catch {
      setStatus("Could not load timeline from API.");
      return null;
    }
  }

  return {
    timeline,
    setTimeline,
    lifePeriods,
    setLifePeriods,
    lifeThreads,
    setLifeThreads,
    lifeEpics,
    setLifeEpics,
    lifeEvents,
    setLifeEvents,
    unlinkedAssets,
    setUnlinkedAssets,
    questions,
    setQuestions,
    peopleDirectory,
    setPeopleDirectory,
    placesDirectory,
    setPlacesDirectory,
    mainCharacterName,
    setMainCharacterName,
    loadTimeline,
  };
}
