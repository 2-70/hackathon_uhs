import Ionicons from '@expo/vector-icons/Ionicons';
import { router } from 'expo-router';
import { useState } from 'react';
import { Image, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { Garment } from '../src/model';
import { basketLimit, useLaundry } from '../src/store';
import { Button, Notice, Screen, palette, styles } from '../src/ui';

const careLabels: Record<Garment['wash'], string> = {
  machine: '기계 세탁',
  hand: '손세탁',
  none: '물세탁 금지',
  unknown: '세탁 조건 확인 필요',
};

export default function WardrobeScreen() {
  const insets = useSafeAreaInsets();
  const { garments, basketIds, ready, loadError, addToBasket, removeGarment } = useLaundry();
  const [query, setQuery] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [confirmId, setConfirmId] = useState<string>();
  const [removing, setRemoving] = useState(false);
  const [removeError, setRemoveError] = useState(false);
  const [capacityNotice, setCapacityNotice] = useState('');
  const searchTerm = query.trim().toLowerCase();
  const visible = garments.filter((garment) =>
    [garment.name, garment.category, garment.color, garment.material]
      .some((value) => value.toLowerCase().includes(searchTerm)),
  );
  const selected = garments.filter((garment) => selectedIds.includes(garment.id) && !basketIds.includes(garment.id));
  const remaining = Math.max(0, basketLimit - basketIds.length);

  function toggle(id: string) {
    setCapacityNotice('');
    setSelectedIds((previous) =>
      previous.includes(id) ? previous.filter((value) => value !== id) : [...previous, id],
    );
  }

  function addSelected() {
    const accepted = selected.slice(0, remaining).map(({ id }) => id);
    const omitted = addToBasket(selected.map(({ id }) => id));
    if (omitted > 0) {
      setSelectedIds((previous) => previous.filter((id) => !accepted.includes(id)));
      setCapacityNotice(`드럼이 가득 찼어요. 선택한 의류 중 ${omitted}벌이 남았어요.`);
      return;
    }
    setSelectedIds([]);
    setCapacityNotice('');
    router.navigate('/drum');
  }

  async function remove(id: string) {
    if (removing) return;
    setRemoving(true);
    setRemoveError(false);
    try {
      await removeGarment(id);
      setSelectedIds((previous) => previous.filter((value) => value !== id));
      setConfirmId(undefined);
    } catch {
      setRemoveError(true);
    } finally {
      setRemoving(false);
    }
  }

  return (
    <View style={local.screen}>
      <View style={local.hero}>
        <View style={local.heroInner}>
          <View style={local.heroHeading}>
            <Text accessibilityRole="header" style={local.heroTitle}>내 옷장</Text>
            {ready && !loadError && <Text style={local.heroCount}>의류 {garments.length}벌 · 샘플 모드</Text>}
          </View>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="의류 등록"
            onPress={() => router.push('/garment')}
            style={({ pressed }) => [local.heroAction, pressed && styles.dimmed]}
          >
            <Ionicons name="add" size={20} color={palette.accent} />
            <Text style={local.heroActionText}>등록</Text>
          </Pressable>
        </View>
      </View>
      <Screen>
        <View style={local.search}>
          <Ionicons name="search-outline" size={19} color={palette.accent} />
          <TextInput
            accessibilityLabel="의류 검색"
            placeholder="이름, 종류, 색상, 소재"
            placeholderTextColor={palette.muted}
            value={query}
            onChangeText={setQuery}
            style={local.input}
          />
          {query.length > 0 && (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="검색어 지우기"
              onPress={() => setQuery('')}
              style={local.iconButton}
            >
              <Ionicons name="close" size={19} color={palette.muted} />
            </Pressable>
          )}
        </View>
        {loadError && <Notice tone="error">{loadError}</Notice>}
        {!ready && !loadError && <Notice>옷장을 불러오는 중이에요.</Notice>}
        {ready && !loadError && (
          <View style={local.inventory}>
            <View style={local.listHeader}>
              <Text accessibilityRole="header" style={local.listTitle}>
                {searchTerm ? `검색 결과 ${visible.length}벌` : '등록 의류'}
              </Text>
              {basketIds.length > 0 && (
                <Pressable
                  accessibilityRole="button"
                  onPress={() => router.navigate('/drum')}
                  style={({ pressed }) => [local.textButton, pressed && styles.dimmed]}
                >
                  <Text style={local.linkText}>드럼 {basketIds.length}벌</Text>
                  <Ionicons name="arrow-forward" size={15} color={palette.accent} />
                </Pressable>
              )}
            </View>

            {visible.length === 0 && (
              <View style={local.empty}>
                <Text style={styles.title}>{searchTerm ? '일치하는 의류가 없어요' : '등록한 의류가 없어요'}</Text>
                <Text style={styles.muted}>{searchTerm ? '의류 이름이나 소재를 다시 확인해 보세요.' : '의류를 등록해 옷장에 추가하세요.'}</Text>
                {searchTerm && <Button tone="secondary" onPress={() => setQuery('')}>검색어 지우기</Button>}
              </View>
            )}

            {visible.length > 0 && (
              <View style={local.list}>
                {visible.map((garment, index) => {
                  const inBasket = basketIds.includes(garment.id);
                  const checked = selectedIds.includes(garment.id) && !inBasket;
                  const tags = [garment.category, garment.color, garment.material].filter(Boolean).join(' · ');
                  const wash = garment.maxTemp === null
                    ? careLabels[garment.wash]
                    : `${careLabels[garment.wash]} · ${garment.maxTemp}°C 이하`;
                  return (
                    <View key={garment.id} style={[index < visible.length - 1 && local.itemDivider, checked && local.selectedItem]}>
                      <View style={local.itemRow}>
                        <Pressable
                          accessibilityRole="checkbox"
                          accessibilityLabel={[garment.name, tags, wash, inBasket && '드럼에 담김'].filter(Boolean).join(', ')}
                          accessibilityState={{ checked: checked || inBasket, disabled: inBasket }}
                          disabled={inBasket}
                          onPress={() => toggle(garment.id)}
                          style={({ pressed }) => [local.itemTarget, pressed && styles.dimmed]}
                        >
                          <View style={[local.checkbox, checked && local.checked, inBasket && local.inBasket]}>
                            {(checked || inBasket) && (
                              <Ionicons name="checkmark" size={15} color={checked ? palette.inverse : palette.accent} />
                            )}
                          </View>
                          {garment.photo ? (
                            <Image source={{ uri: garment.photo }} style={local.thumb} />
                          ) : (
                            <View style={[local.thumb, garment.wash === 'machine' ? local.thumbAqua : local.thumbViolet]}>
                              <Ionicons
                                name={garment.category === '바지' ? 'pricetag-outline' : 'shirt-outline'}
                                size={22}
                                color={garment.wash === 'machine' ? palette.blue : palette.accent}
                              />
                            </View>
                          )}
                          <View style={local.details}>
                            <Text style={local.garmentName}>{garment.name}</Text>
                            {tags ? <Text style={local.metadata}>{tags}</Text> : null}
                            <Text style={[local.care, (garment.wash === 'unknown' || garment.wash === 'none') && local.warning]}>
                              {wash}{inBasket ? ' · 드럼에 담김' : ''}
                            </Text>
                          </View>
                        </Pressable>
                        <Pressable
                          accessibilityRole="button"
                          accessibilityLabel={`${garment.name} 수정`}
                          onPress={() => router.push({ pathname: '/garment', params: { id: garment.id } })}
                          style={({ pressed }) => [local.iconButton, pressed && styles.dimmed]}
                        >
                          <Ionicons name="create-outline" size={20} color={palette.ink} />
                        </Pressable>
                        <Pressable
                          accessibilityRole="button"
                          accessibilityLabel={`${garment.name} 삭제`}
                          accessibilityState={{ disabled: removing }}
                          disabled={removing}
                          onPress={() => {
                            setRemoveError(false);
                            setConfirmId(garment.id);
                          }}
                          style={({ pressed }) => [local.iconButton, pressed && styles.dimmed]}
                        >
                          <Ionicons name="trash-outline" size={19} color={palette.muted} />
                        </Pressable>
                      </View>

                      {confirmId === garment.id && (
                        <View style={local.confirm}>
                          <Text style={local.confirmText}>이 의류를 옷장에서 삭제할까요?</Text>
                          {removeError && <Notice tone="error">삭제하지 못했어요. 다시 시도해 주세요.</Notice>}
                          <View style={styles.wrap}>
                            <Button tone="secondary" disabled={removing} onPress={() => void remove(garment.id)}>
                              {removing ? '삭제 중…' : '삭제'}
                            </Button>
                            <Button tone="quiet" disabled={removing} onPress={() => setConfirmId(undefined)}>취소</Button>
                          </View>
                        </View>
                      )}
                    </View>
                  );
                })}
              </View>
            )}
          </View>
        )}
      </Screen>
      {selected.length > 0 && (
        <View style={[local.dock, { marginBottom: 98 + insets.bottom }]}>
          {capacityNotice ? <Notice tone="error">{capacityNotice}</Notice> : null}
          <View style={local.dockRow}>
            <View>
              <Text style={local.dockLabel}>{remaining > 0 ? `드럼 ${basketIds.length}/${basketLimit}벌` : '드럼이 가득 찼어요'}</Text>
              <Pressable
                accessibilityRole="button"
                onPress={() => {
                  setSelectedIds([]);
                  setCapacityNotice('');
                }}
                style={({ pressed }) => [local.textButton, pressed && styles.dimmed]}
              >
                <Text style={local.linkText}>선택 해제</Text>
              </Pressable>
            </View>
            <Button icon="basket-outline" disabled={remaining === 0} onPress={addSelected}>
              {selected.length}벌 드럼에 담기
            </Button>
          </View>
        </View>
      )}
    </View>
  );
}

const local = StyleSheet.create({
  screen: { flex: 1 },
  hero: {
    backgroundColor: palette.surface,
    borderBottomWidth: 1,
    borderBottomColor: palette.line,
  },
  heroInner: {
    position: 'relative', width: '100%', maxWidth: 640, minHeight: 74, alignSelf: 'center',
    flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 8, paddingHorizontal: 68,
    paddingVertical: 10,
  },
  heroHeading: { flex: 1, alignItems: 'center', gap: 2 },
  heroTitle: { color: palette.ink, fontSize: 21, lineHeight: 28, fontWeight: '800', letterSpacing: -0.45 },
  heroCount: { color: palette.muted, fontSize: 12, fontWeight: '600' },
  heroAction: {
    position: 'absolute', right: 18, top: 15,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, minHeight: 44,
    paddingHorizontal: 10, borderRadius: 13, backgroundColor: palette.accentWash,
  },
  heroActionText: { color: palette.accent, fontSize: 14, fontWeight: '700' },
  search: {
    flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 48,
    paddingLeft: 13, borderWidth: 1, borderColor: palette.line, borderRadius: 15, backgroundColor: palette.surface,
  },
  input: { flex: 1, minWidth: 0, color: palette.ink, fontSize: 15, paddingRight: 4 },
  iconButton: { width: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  inventory: { gap: 9 },
  listHeader: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8,
    minHeight: 38,
  },
  listTitle: { flexShrink: 1, color: palette.ink, fontSize: 18, fontWeight: '800' },
  textButton: { flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start', gap: 5, minHeight: 44 },
  linkText: { color: palette.accent, fontSize: 13, fontWeight: '700' },
  empty: { alignItems: 'flex-start', gap: 8, padding: 17, backgroundColor: palette.surface, borderRadius: 16, borderWidth: 1, borderColor: palette.line },
  list: { backgroundColor: palette.surface, borderWidth: 1, borderColor: palette.line, borderRadius: 17, overflow: 'hidden' },
  itemDivider: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: palette.line },
  selectedItem: { backgroundColor: palette.accentWash },
  itemRow: { flexDirection: 'row', alignItems: 'center' },
  itemTarget: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 80, paddingVertical: 10, paddingLeft: 10 },
  checkbox: {
    width: 20, height: 20, alignItems: 'center', justifyContent: 'center',
    borderWidth: 1, borderColor: palette.muted, borderRadius: 6, backgroundColor: palette.surface,
  },
  checked: { borderColor: palette.accent, backgroundColor: palette.accent },
  inBasket: { borderColor: palette.line, backgroundColor: palette.subtle },
  thumb: { width: 42, height: 42, borderRadius: 12, backgroundColor: palette.subtle, alignItems: 'center', justifyContent: 'center' },
  thumbAqua: { backgroundColor: palette.aqua },
  thumbViolet: { backgroundColor: palette.accentWash },
  details: { flex: 1, gap: 3 },
  garmentName: { color: palette.ink, fontSize: 15, fontWeight: '800' },
  metadata: { color: palette.muted, fontSize: 12, lineHeight: 16 },
  care: { color: palette.ink, fontSize: 12, lineHeight: 16, fontWeight: '600' },
  warning: { color: palette.error },
  confirm: { alignItems: 'flex-start', gap: 7, paddingHorizontal: 10, paddingVertical: 8, backgroundColor: palette.errorWash },
  confirmText: { color: palette.error, fontSize: 14, fontWeight: '600' },
  dock: {
    width: '100%', maxWidth: 640, alignSelf: 'center', gap: 7, paddingHorizontal: 18, paddingVertical: 10,
    backgroundColor: palette.surface, borderWidth: 1, borderColor: palette.line, borderRadius: 18,
    shadowColor: palette.ink, shadowOpacity: 0.08, shadowRadius: 12, shadowOffset: { width: 0, height: 4 }, elevation: 4,
  },
  dockRow: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 8 },
  dockLabel: { color: palette.ink, fontSize: 13, fontWeight: '700' },
});
