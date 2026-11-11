import AsyncStorage from '@react-native-async-storage/async-storage';
import * as FileSystem from 'expo-file-system/legacy';
import {
  createContext, useContext, useEffect, useRef, useState, type ReactNode,
} from 'react';
import {
  deleteGarment, listWardrobe, readRegisteredMachine, writeGarment, writeRegisteredMachine,
} from './api';
import type { Garment, GarmentDraft, GarmentPhotos, Machine } from './model';

const photoStorageKey = 'washwise.local-photos.v1';
const basketStorageKey = 'washwise.basket.v1';
export const basketLimit = 10;

type SavedData = { garments: Garment[]; machine: Machine | null };
type Laundry = SavedData & {
  ready: boolean;
  loadError: string | null;
  basketIds: string[];
  saveGarment: (draft: GarmentDraft, id?: string, photos?: GarmentPhotos) => Promise<Garment>;
  removeGarment: (id: string) => Promise<void>;
  addToBasket: (ids: string[]) => number;
  removeFromBasket: (id: string) => void;
  registerMachine: (machine: Machine) => Promise<void>;
};

const initialData: SavedData = { garments: [], machine: null };
const LaundryContext = createContext<Laundry | null>(null);
const photoDirectory = FileSystem.documentDirectory && FileSystem.documentDirectory + 'washwise-photos/';

async function discardPhoto(uri?: string) {
  if (uri && photoDirectory && uri.startsWith(photoDirectory)) {
    await FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => {});
  }
}

function parseStorage(value: string | null): unknown {
  try {
    return value ? JSON.parse(value) : null;
  } catch {
    return null;
  }
}

export function LaundryProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState(initialData);
  const current = useRef(initialData);
  const writes = useRef<Promise<unknown>>(Promise.resolve());
  const [ready, setReady] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [basketIds, setBasketIds] = useState<string[]>([]);
  const basket = useRef<string[]>([]);
  const basketWrites = useRef<Promise<unknown>>(Promise.resolve());
  const legacyPhotos = useRef<Record<string, string>>({});

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [garments, machine, rawPhotos, rawBasket] = await Promise.all([
          listWardrobe(), readRegisteredMachine(), AsyncStorage.getItem(photoStorageKey).catch(() => null),
          AsyncStorage.getItem(basketStorageKey).catch(() => null),
        ]);
        if (!active) return;
        const photos = parseStorage(rawPhotos);
        if (photos && typeof photos === 'object' && !Array.isArray(photos)) {
          legacyPhotos.current = Object.fromEntries(Object.entries(photos).filter(([, uri]) => typeof uri === 'string'));
        }
        const loaded = {
          garments: garments.map((item) => ({ ...item, photo: item.photo ?? legacyPhotos.current[item.id] })),
          machine,
        };
        const storedIds = parseStorage(rawBasket);
        const ids = new Set(garments.map(({ id }) => id));
        if (Array.isArray(storedIds)) {
          basket.current = [...new Set(storedIds.filter((id) => ids.has(id)))].slice(0, basketLimit);
          setBasketIds(basket.current);
        }
        current.current = loaded;
        setData(loaded);
      } catch {
        if (active) setLoadError('서버에서 옷장과 세탁기를 불러오지 못했어요. 연결을 확인한 뒤 다시 열어 주세요.');
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

  function commit(next: SavedData) {
    current.current = next;
    setData(next);
  }

  async function removeLegacyPhoto(id: string) {
    const photo = legacyPhotos.current[id];
    if (!photo) return;
    delete legacyPhotos.current[id];
    await AsyncStorage.setItem(photoStorageKey, JSON.stringify(legacyPhotos.current)).catch(() => {});
    await discardPhoto(photo);
  }

  function saveGarment(draft: GarmentDraft, id?: string, photos?: GarmentPhotos) {
    return enqueue(async () => {
      const previous = current.current.garments.find((garment) => garment.id === id);
      if (id && !previous) throw new Error('Garment not found');
      const row = await writeGarment(draft, id, photos);
      const saved = { ...row, photo: row.photo ?? legacyPhotos.current[row.id] };
      const garments = previous
        ? current.current.garments.map((garment) => garment.id === id ? saved : garment)
        : [saved, ...current.current.garments];
      commit({ ...current.current, garments });
      if (row.photo) await removeLegacyPhoto(row.id);
      return saved;
    });
  }

  function updateBasket(next: string[]) {
    basket.current = next;
    setBasketIds(next);
    basketWrites.current = basketWrites.current
      .then(() => AsyncStorage.setItem(basketStorageKey, JSON.stringify(next)))
      .catch(() => {});
  }

  function removeFromBasket(id: string) {
    updateBasket(basket.current.filter((item) => item !== id));
  }

  function removeGarment(id: string) {
    return enqueue(async () => {
      await deleteGarment(id);
      const garments = current.current.garments.filter((garment) => garment.id !== id);
      commit({ ...current.current, garments });
      removeFromBasket(id);
      await removeLegacyPhoto(id);
    });
  }

  function addToBasket(ids: string[]) {
    const validIds = new Set(current.current.garments.map(({ id }) => id));
    const next = [...new Set([...basket.current, ...ids.filter((id) => validIds.has(id))])];
    updateBasket(next.slice(0, basketLimit));
    return Math.max(0, next.length - basketLimit);
  }

  function registerMachine(machine: Machine) {
    return enqueue(async () => {
      if (current.current.machine?.id === machine.id) return;
      await writeRegisteredMachine(machine);
      commit({ ...current.current, machine });
    });
  }

  return (
    <LaundryContext.Provider value={{
      ...data, ready, loadError, basketIds,
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

