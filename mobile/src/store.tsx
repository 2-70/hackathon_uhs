import AsyncStorage from '@react-native-async-storage/async-storage';
import * as FileSystem from 'expo-file-system/legacy';
import {
  createContext, useContext, useEffect, useRef, useState, type ReactNode,
} from 'react';
import { sampleGarments, sampleMachines } from './mock';
import type { Garment, GarmentDraft, Machine } from './model';

const storageKey = 'washwise.sample.v1';
export const basketLimit = 10;

type SavedData = { garments: Garment[]; machineId: string | null };
type Laundry = SavedData & {
  ready: boolean;
  loadError: string | null;
  machine: Machine | null;
  basketIds: string[];
  analysisStarted: boolean;
  startAnalysis: () => void;
  saveGarment: (draft: GarmentDraft, id?: string) => Promise<Garment>;
  removeGarment: (id: string) => Promise<void>;
  addToBasket: (ids: string[]) => number;
  removeFromBasket: (id: string) => void;
  registerMachine: (machine: Machine) => Promise<void>;
};

const initialData: SavedData = { garments: sampleGarments, machineId: null };
const LaundryContext = createContext<Laundry | null>(null);
const photoDirectory = FileSystem.documentDirectory && FileSystem.documentDirectory + 'washwise-photos/';

async function keepPhoto(uri?: string) {
  if (!uri || !photoDirectory || uri.startsWith(photoDirectory)) return uri;
  await FileSystem.makeDirectoryAsync(photoDirectory, { intermediates: true });
  const suffix = uri.match(/\.(jpe?g|png|webp|heic|heif|gif)(?:[?#]|$)/i)?.[1] ?? 'jpg';
  const destination = photoDirectory + createId() + '.' + suffix;
  await FileSystem.copyAsync({ from: uri, to: destination });
  return destination;
}

async function discardPhoto(uri?: string) {
  if (uri && photoDirectory && uri.startsWith(photoDirectory)) {
    await FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => {});
  }
}

function createId() {
  return Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
}

export function LaundryProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState(initialData);
  const current = useRef(initialData);
  const writes = useRef<Promise<unknown>>(Promise.resolve());
  const [ready, setReady] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [basketIds, setBasketIds] = useState<string[]>([]);
  const basket = useRef<string[]>([]);
  const [analysisStarted, setAnalysisStarted] = useState(false);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const raw = await AsyncStorage.getItem(storageKey);
        if (!active || raw === null) return;
        const stored = JSON.parse(raw) as SavedData;
        if (!Array.isArray(stored.garments)) throw new Error('Invalid saved wardrobe');
        current.current = stored;
        setData(stored);
      } catch {
        if (active) setLoadError('저장한 옷장을 불러오지 못했습니다. 앱을 다시 열어 주세요.');
      } finally {
        if (active) setReady(true);
      }
    }
    void load();
    return () => { active = false; };
  }, []);

  function enqueue<T>(operation: () => Promise<T>): Promise<T> {
    if (!ready || loadError) return Promise.reject(new Error('Wardrobe unavailable'));
    const pending = writes.current.then(operation);
    writes.current = pending.catch(() => {});
    return pending;
  }

  async function commit(next: SavedData) {
    await AsyncStorage.setItem(storageKey, JSON.stringify(next));
    current.current = next;
    setData(next);
  }

  function saveGarment(draft: GarmentDraft, id?: string) {
    return enqueue(async () => {
      const previous = current.current.garments.find((garment) => garment.id === id);
      if (id && !previous) throw new Error('Garment not found');
      const photo = await keepPhoto(draft.photo);
      const saved: Garment = { ...draft, id: previous?.id ?? createId(), photo };
      const garments = previous
        ? current.current.garments.map((garment) => garment.id === id ? saved : garment)
        : [saved, ...current.current.garments];

      try {
        await commit({ ...current.current, garments });
      } catch (error) {
        if (photo !== draft.photo) await discardPhoto(photo);
        throw error;
      }
      if (previous?.photo !== photo) await discardPhoto(previous?.photo);
      return saved;
    });
  }

  function updateBasket(next: string[]) {
    basket.current = next;
    setBasketIds(next);
  }

  function removeFromBasket(id: string) {
    updateBasket(basket.current.filter((item) => item !== id));
  }

  function removeGarment(id: string) {
    return enqueue(async () => {
      const previous = current.current.garments.find((garment) => garment.id === id);
      await commit({
        ...current.current,
        garments: current.current.garments.filter((garment) => garment.id !== id),
      });
      removeFromBasket(id);
      await discardPhoto(previous?.photo);
    });
  }

  function addToBasket(ids: string[]) {
    const validIds = new Set(current.current.garments.map(({ id }) => id));
    const next = [...new Set([...basket.current, ...ids.filter((id) => validIds.has(id))])];
    updateBasket(next.slice(0, basketLimit));
    return Math.max(0, next.length - basketLimit);
  }

  function registerMachine(machine: Machine) {
    return enqueue(() => commit({ ...current.current, machineId: machine.id }));
  }

  return (
    <LaundryContext.Provider value={{
      ...data, ready, loadError, basketIds, analysisStarted,
      machine: sampleMachines.find((machine) => machine.id === data.machineId) ?? null,
      startAnalysis: () => setAnalysisStarted(true),
      addToBasket, removeFromBasket, saveGarment, removeGarment, registerMachine,
    }}>
      {children}
    </LaundryContext.Provider>
  );
}

export function useLaundry() {
  const store = useContext(LaundryContext);
  if (!store) throw new Error('LaundryProvider is missing');
  return store;
}

