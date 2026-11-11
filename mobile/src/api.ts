import type { Garment, GarmentDraft, GarmentPhotos, Machine, MachineChoice } from './model';

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
  care_wash_strength?: Garment['washStrength'];
  care_max_spin_rpm?: number | null;
  care_tumble_dry_allowed: boolean | null;
  care_dry_method: string | null;
  care_notes: string | null;
  wash_separately?: boolean | null;
  color_bleed_risk?: boolean | null;
  photo_kinds?: (keyof GarmentPhotos)[];
  updated_at: string;
  source_type: 'user_input' | 'physical_label' | 'official_product_information' | 'photo_inference';
  source_reference: string | null;
};

export const washFromApi = { machine_wash: 'machine', hand_wash: 'hand', do_not_wash: 'none' } as const;
const washToApi = { machine: 'machine_wash', hand: 'hand_wash', none: 'do_not_wash', unknown: null } as const;

function fromWardrobe(row: WardrobeRow): Garment {
  function photoUrl(kind: keyof GarmentPhotos) {
    if (!row.photo_kinds?.includes(kind)) return undefined;
    return `${apiUrl}/api/wardrobe/${encodeURIComponent(row.id)}/photos/${kind}?v=${encodeURIComponent(row.updated_at)}`;
  }
  return {
    id: row.id, name: row.item_name, category: row.category ?? '', color: row.color ?? '',
    material: row.material ?? '', wash: row.care_wash_method ? washFromApi[row.care_wash_method] : 'unknown',
    maxTemp: row.care_temperature_celsius, gentle: row.care_gentle,
    washStrength: row.care_wash_strength, maxSpin: row.care_max_spin_rpm,
    washSeparately: row.wash_separately, colorBleedRisk: row.color_bleed_risk,
    photo: photoUrl('clothing'), labelPhoto: photoUrl('label'),
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

export async function writeGarment(draft: GarmentDraft, id?: string, photos?: GarmentPhotos) {
  const source = draft.source === 'care-label' ? 'physical_label'
    : draft.source === 'official-product' ? 'official_product_information' : 'user_input';
  const payload = {
    item_name: draft.name, category: draft.category || null, color: draft.color || null,
    material: draft.material || null, care_wash_method: washToApi[draft.wash],
    care_temperature_celsius: draft.maxTemp, care_gentle: draft.gentle,
    care_wash_strength: draft.washStrength, care_max_spin_rpm: draft.maxSpin,
    wash_separately: draft.washSeparately, color_bleed_risk: draft.colorBleedRisk, photos,
    care_tumble_dry_allowed: draft.dryer === 'unknown' ? null : draft.dryer === 'yes',
    care_dry_method: draft.drying || null, care_notes: draft.careNotes || null,
    source_type: source, source_reference: source === 'user_input' ? null : draft.sourceReference ?? null,
    verification_status: source === 'user_input' ? 'unconfirmed' : 'confirmed',
  };
  const row = await request<WardrobeRow>(
    id ? `/api/wardrobe/${encodeURIComponent(id)}` : '/api/wardrobe',
    json(id ? 'PATCH' : 'POST', payload), photos ? 45000 : undefined,
  );
  return fromWardrobe(row);
}

export function deleteGarment(id: string) {
  return request(`/api/wardrobe/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

type MachineSummary = { id: string; manufacturer: string; model_name: string; source_url: string | null };
type CatalogModel = {
  id: string;
  model_name: string;
  manufacturer_name: string | null;
  applicant_name: string | null;
  capacity_kg: number | null;
  manual_match_status: string;
  source_url: string;
};
type CatalogPage = { items: CatalogModel[]; total: number; total_pages: number };
type CatalogUsage = {
  model: CatalogModel;
  documents: {
    id: string; title: string | null; source_url: string; exact_model_match: boolean; matching_status: string;
  }[];
  instructions: {
    id: string; document_id: string; title: string; instruction_text: string;
    page_number: number | null; review_status: string;
  }[];
  courses?: MachineCourses['courses'];
};
type MachineCourses = {
  machine: MachineSummary;
  courses: {
    id: string;
    name: string;
    course_key: string;
    description: string | null;
    settings: {
      id: string;
      temperature_celsius: number | null;
      temperature_setting: string | null;
      spin_rpm: number | null;
      spin_level: string | null;
      wash_strength: Garment['washStrength'];
      water_level: string | null;
      dry_level: string | null;
      is_default: boolean;
      source_url: string | null;
      manual_page: number | null;
      verification_status: string;
    }[];
  }[];
};
type UserMachine = {
  machine_type: string; machine_model_id: string | null;
  manual_input: { catalog_model_id?: string } | null;
};

function fromMachineSummary(row: MachineSummary): MachineChoice {
  return { id: row.id, maker: row.manufacturer, model: row.model_name, sourceUrl: row.source_url };
}

// Registration records print legal names such as "Whirlpool Corporation" or "삼성전자(주)".
function makerName(name: string) {
  return name.replace(/\(주\)|주식회사|,?\s*\b(co\.?,?\s*ltd|corporation|corp|inc|ltd)\b\.?/gi, '').trim() || name;
}

function fromCatalogModel(row: CatalogModel): MachineChoice {
  return {
    id: row.id, maker: makerName(row.manufacturer_name || row.applicant_name || '제조사 미확인'),
    model: row.model_name, sourceUrl: row.source_url,
    catalog: { capacityKg: row.capacity_kg, hasManual: row.manual_match_status === 'matched' },
  };
}

export async function readMachine(id: string): Promise<Machine> {
  const { machine, courses } = await request<MachineCourses>(`/api/machines/${encodeURIComponent(id)}/courses`);
  return { ...fromMachineSummary(machine), courses: readCourses(courses) };
}

function readCourses(courses: MachineCourses['courses']): Machine['courses'] {
  return courses.map((course) => {
    const settings = course.settings.filter((option) => option.verification_status === 'confirmed');
    return {
      id: course.id, name: course.name, gentle: course.course_key === 'delicates',
      panelName: course.description?.match(/^Cycle Guide, (.+?) — /)?.[1],
      settings: settings.flatMap((option) => {
        const { temperature_celsius: temp, spin_rpm: spin } = option;
        return temp !== null && spin !== null && !option.dry_level ? [{ temp, spin }] : [];
      }),
      verifiedSettings: settings.map((option) => ({
        id: option.id,
        temperature: option.temperature_celsius !== null
          ? `${option.temperature_celsius}°C` : option.temperature_setting ?? '미확인',
        spin: option.spin_rpm !== null ? `${option.spin_rpm} rpm` : option.spin_level ?? '미확인',
        temperatureCelsius: option.temperature_celsius, spinRpm: option.spin_rpm,
        washStrength: option.wash_strength, waterLevel: option.water_level, dryLevel: option.dry_level,
        isDefault: option.is_default, sourceUrl: option.source_url, manualPage: option.manual_page,
      })),
    };
  });
}

async function readCatalogMachine(id: string): Promise<Machine> {
  const usage = await request<CatalogUsage>(`/api/catalog/models/${encodeURIComponent(id)}/usage`);
  const documents = usage.documents
    .filter((document) => document.exact_model_match && document.matching_status === 'confirmed')
    .map((document) => ({ id: document.id, title: document.title, url: document.source_url }));
  const urls = new Map(documents.map(({ id: documentId, url }) => [documentId, url]));
  const instructions = usage.instructions.flatMap((instruction) => {
    const url = urls.get(instruction.document_id);
    const confirmed = instruction.review_status === 'confirmed';
    if (!url || (!confirmed && !instruction.page_number)) return [];
    return [{
      id: instruction.id, title: instruction.title, text: confirmed ? instruction.instruction_text : null,
      url: instruction.page_number ? `${url.split('#')[0]}#page=${instruction.page_number}` : url,
    }];
  });
  return {
    ...fromCatalogModel(usage.model), courses: readCourses(usage.courses ?? []), documents, instructions,
  };
}

export function readMachineChoice(choice: MachineChoice) {
  return choice.catalog ? readCatalogMachine(choice.id) : readMachine(choice.id);
}

export async function searchMachines(query: string, page: number) {
  const verifiedParams = new URLSearchParams({ machine_type: 'washer', include_catalog: 'false' });
  const catalogParams = new URLSearchParams({ page: String(page), page_size: '12' });
  if (query.trim()) {
    verifiedParams.set('query', query.trim());
    catalogParams.set('query', query.trim());
  }
  const [verified, catalog] = await Promise.allSettled([
    page === 1 ? request<MachineSummary[]>(`/api/machines?${verifiedParams}`) : Promise.resolve([]),
    request<CatalogPage>(`/api/catalog/models?${catalogParams}`),
  ]);
  if (verified.status === 'rejected' && catalog.status === 'rejected') throw catalog.reason;
  const confirmed = verified.status === 'fulfilled' ? verified.value.map(fromMachineSummary) : [];
  const listed = catalog.status === 'fulfilled' ? catalog.value.items.map(fromCatalogModel) : [];
  return {
    machines: [...confirmed, ...listed], catalogTotal: catalog.status === 'fulfilled' ? catalog.value.total : null,
    totalPages: catalog.status === 'fulfilled' ? catalog.value.total_pages : 0,
    partial: verified.status === 'rejected' || catalog.status === 'rejected',
  };
}

type MachinePhotoMatch = {
  status: 'matched' | 'candidates' | 'not_found';
  catalog_models: CatalogModel[];
  machines: MachineSummary[];
  message: string;
};
export type MachinePhoto = { uri: string; file?: File; fileName?: string | null; mimeType?: string };

export async function identifyMachine(photo: MachinePhoto, isWeb: boolean) {
  const form = new FormData();
  const name = photo.file?.name || photo.fileName || 'washer.jpg';
  if (isWeb) {
    form.append('image', photo.file ?? await (await fetch(photo.uri)).blob(), name);
  } else {
    form.append('image', { uri: photo.uri, name, type: photo.mimeType || 'image/jpeg' } as unknown as Blob);
  }
  const found = await request<MachinePhotoMatch>('/api/machines/identify', { method: 'POST', body: form }, 75000);
  return {
    status: found.status, message: found.message,
    machines: [...found.machines.map(fromMachineSummary), ...found.catalog_models.map(fromCatalogModel)],
  };
}

export async function readRegisteredMachine() {
  const registrations = await request<UserMachine[]>('/api/user-machines');
  const current = registrations.find((item) => item.machine_type === 'washer'
    && (item.machine_model_id || item.manual_input?.catalog_model_id));
  if (current?.machine_model_id) return readMachine(current.machine_model_id);
  const catalogId = current?.manual_input?.catalog_model_id;
  return catalogId ? readCatalogMachine(catalogId) : null;
}

export async function writeRegisteredMachine(machine: Machine) {
  await request('/api/user-machines', json('POST', {
    machine_type: 'washer', display_name: machine.model,
    ...(machine.catalog
      ? { manual_input: { catalog_model_id: machine.id } }
      : { machine_model_id: machine.id }),
  }));
}
