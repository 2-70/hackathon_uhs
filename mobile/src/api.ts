import type { Garment, GarmentDraft, Machine } from './model';

const configuredUrl = process.env.EXPO_PUBLIC_API_URL?.trim();
const browserUrl = typeof location === 'undefined' ? undefined : `${location.protocol}//${location.hostname}:8001`;
const apiUrl = (configuredUrl || browserUrl || 'http://10.0.2.2:8001').replace(/\/+$/, '');

export async function request<T>(path: string, init?: RequestInit, timeout = 12000): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(apiUrl + path, { ...init, signal: controller.signal });
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(body?.error?.message ?? body?.detail?.message ?? '서버에서 요청을 처리하지 못했어요.');
    }
    return body as T;
  } catch (error) {
    if (controller.signal.aborted) throw new Error('서버 응답이 늦어요. 잠시 뒤 다시 시도해 주세요.');
    if (error instanceof TypeError) throw new Error('WashWise 서버에 연결하지 못했어요.');
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}

type WardrobeRow = {
  id: string;
  item_name: string;
  category: string | null;
  color: string | null;
  material: string | null;
  care_wash_method: 'machine_wash' | 'hand_wash' | 'do_not_wash' | null;
  care_temperature_celsius: number | null;
  care_gentle: boolean | null;
  care_tumble_dry_allowed: boolean | null;
  care_dry_method: string | null;
  care_notes: string | null;
  source_type: 'user_input' | 'physical_label' | 'official_product_information' | 'photo_inference';
  source_reference: string | null;
};

export const washFromApi = { machine_wash: 'machine', hand_wash: 'hand', do_not_wash: 'none' } as const;
const washToApi = { machine: 'machine_wash', hand: 'hand_wash', none: 'do_not_wash', unknown: null } as const;

function fromWardrobe(row: WardrobeRow): Garment {
  return {
    id: row.id, name: row.item_name, category: row.category ?? '', color: row.color ?? '',
    material: row.material ?? '', wash: row.care_wash_method ? washFromApi[row.care_wash_method] : 'unknown',
    maxTemp: row.care_temperature_celsius, gentle: row.care_gentle,
    dryer: row.care_tumble_dry_allowed === null ? 'unknown' : row.care_tumble_dry_allowed ? 'yes' : 'no',
    drying: row.care_dry_method ?? '', careNotes: row.care_notes ?? undefined,
    source: row.source_type === 'physical_label' ? 'care-label'
      : row.source_type === 'official_product_information' ? 'official-product' : 'manual',
    sourceReference: row.source_reference ?? undefined,
  };
}

export async function listWardrobe() {
  return (await request<WardrobeRow[]>('/api/wardrobe')).map(fromWardrobe);
}

export async function writeGarment(draft: GarmentDraft, id?: string) {
  const source = draft.source === 'care-label' ? 'physical_label'
    : draft.source === 'official-product' ? 'official_product_information' : 'user_input';
  const payload = {
    item_name: draft.name, category: draft.category || null, color: draft.color || null,
    material: draft.material || null, care_wash_method: washToApi[draft.wash],
    care_temperature_celsius: draft.maxTemp, care_gentle: draft.gentle,
    care_tumble_dry_allowed: draft.dryer === 'unknown' ? null : draft.dryer === 'yes',
    care_dry_method: draft.drying || null, care_notes: draft.careNotes || null,
    source_type: source, source_reference: source === 'user_input' ? null : draft.sourceReference ?? null,
    verification_status: source === 'user_input' ? 'unconfirmed' : 'confirmed',
  };
  const row = await request<WardrobeRow>(
    id ? `/api/wardrobe/${encodeURIComponent(id)}` : '/api/wardrobe',
    json(id ? 'PATCH' : 'POST', payload),
  );
  return fromWardrobe(row);
}

export function deleteGarment(id: string) {
  return request(`/api/wardrobe/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

type MachineSummary = { id: string; manufacturer: string; model_name: string };
type MachineCourses = {
  machine: MachineSummary;
  courses: {
    id: string;
    name: string;
    course_key: string;
    settings: {
      id: string;
      temperature_celsius: number | null;
      temperature_setting: string | null;
      spin_rpm: number | null;
      spin_level: string | null;
      verification_status: string;
    }[];
  }[];
};
type UserMachine = { machine_type: string; machine_model_id: string | null };

export async function readMachine(id: string): Promise<Machine> {
  const { machine, courses } = await request<MachineCourses>(`/api/machines/${encodeURIComponent(id)}/courses`);
  return {
    id: machine.id, maker: machine.manufacturer, model: machine.model_name,
    courses: courses.map((course) => {
      const settings = course.settings.filter((option) => option.verification_status === 'confirmed');
      return {
        id: course.id, name: course.name, gentle: course.course_key === 'delicates',
        settings: settings.flatMap((option) => {
          const { temperature_celsius: temp, spin_rpm: spin } = option;
          return temp !== null && spin !== null ? [{ temp, spin }] : [];
        }),
        verifiedSettings: settings.map((option) => ({
          id: option.id,
          temperature: option.temperature_celsius !== null
            ? `${option.temperature_celsius}°C` : option.temperature_setting ?? '미확인',
          spin: option.spin_rpm !== null ? `${option.spin_rpm} rpm` : option.spin_level ?? '미확인',
        })),
      };
    }),
  };
}

export async function searchMachines(query: string) {
  const params = new URLSearchParams({ machine_type: 'washer' });
  if (query.trim()) params.set('query', query.trim());
  const matches = await request<MachineSummary[]>(`/api/machines?${params}`);
  return Promise.all(matches.map((machine) => readMachine(machine.id)));
}

export async function readRegisteredMachine() {
  const registrations = await request<UserMachine[]>('/api/user-machines');
  const current = registrations.find((item) => item.machine_type === 'washer' && item.machine_model_id);
  return current?.machine_model_id ? readMachine(current.machine_model_id) : null;
}

export async function writeRegisteredMachine(machine: Machine) {
  await request('/api/user-machines', json('POST', {
    machine_type: 'washer', display_name: machine.model, machine_model_id: machine.id,
  }));
}
