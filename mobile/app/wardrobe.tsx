import Ionicons from '@expo/vector-icons/Ionicons';
import { router } from 'expo-router';
import { useState } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { Garment } from '../src/model';
import { basketLimit, useLaundry } from '../src/store';
import { Button, Notice, Screen, ScreenHeader, SearchField, palette, styles } from '../src/ui';

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
      setCapacityNotice(`한 번에 ${basketLimit}벌까지 분석할 수 있어요. ${omitted}벌은 드럼에 담지 못했어요.`);
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
      <ScreenHeader
        title="내 옷장"
        action={(
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="옷 추가"
            onPress={() => router.push('/garment')}
            style={({ pressed }) => [local.headerAction, pressed && styles.dimmed]}
          >
            <Ionicons name="add" size={20} color={palette.accent} />
            <Text style={local.headerActionText}>추가</Text>
          </Pressable>
        )}
      />
      <Screen>
        <SearchField
          label="의류 검색"
          value={query}
          onChangeText={setQuery}
          placeholder="이름, 종류, 색상, 소재"
        />
        {loadError && <Notice tone="error">{loadError}</Notice>}
        {!ready && !loadError && <Notice>옷장을 불러오는 중이에요.</Notice>}
        {ready && !loadError && (
          <View style={local.inventory}>
            <View style={local.listHeader}>
              <View style={local.listHeading}>
                <Text accessibilityRole="header" style={local.listTitle}>
                  {searchTerm ? `검색 결과 ${visible.length}벌` : '등록 의류'}
                </Text>
                <Text style={styles.rowMeta}>의류 {garments.length}벌 · 샘플 모드</Text>
              </View>
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
              <View style={[styles.card, styles.cardContent, local.empty]}>
                <View style={[styles.iconBadge, local.emptyIconBadge]} accessible={false}>
                  <Ionicons name={searchTerm ? 'search-outline' : 'shirt-outline'} size={21} color={palette.accent} />
                </View>
                <Text style={styles.title}>{searchTerm ? '찾는 옷이 없어요' : '옷장이 비어 있어요'}</Text>
                {searchTerm ? (
                  <Button tone="secondary" onPress={() => setQuery('')}>검색어 지우기</Button>
                ) : (
                  <Button icon="add" onPress={() => router.push('/garment')}>옷 추가</Button>
                )}
              </View>
            )}

            {visible.length > 0 && (
              <View style={[styles.card, local.list]}>
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
                          {garment.photo || garment.labelPhoto ? (
                            <Image source={{ uri: garment.photo ?? garment.labelPhoto }} style={local.thumbImage} />
                          ) : (
                            <View style={[styles.iconBadge, local.garmentIconBadge]}>
                              <Ionicons
                                name={garment.category === '바지' ? 'pricetag-outline' : 'shirt-outline'}
                                size={20}
                                color={(garment.wash === 'unknown' || garment.wash === 'none') ? palette.error : palette.accent}
                              />
                            </View>
                          )}
                          <View style={local.details}>
                            <Text style={styles.rowTitle}>{garment.name}</Text>
                            {tags ? <Text style={styles.rowMeta}>{tags}</Text> : null}
                            <View style={local.careLine}>
                              <Ionicons
                                name={garment.wash === 'unknown' ? 'help-circle-outline' : garment.wash === 'none' ? 'alert-circle-outline' : 'water-outline'}
                                size={14}
                                color={(garment.wash === 'unknown' || garment.wash === 'none') ? palette.error : palette.accent}
                                accessible={false}
                              />
                              <Text style={[styles.rowMeta, local.care, (garment.wash === 'unknown' || garment.wash === 'none') && local.warning]}>
                                {wash}{inBasket ? ' · 드럼에 담김' : ''}
                              </Text>
                            </View>
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
        <View style={[styles.actionDock, { marginBottom: 98 + insets.bottom }]}>
          {capacityNotice ? <Notice tone="error">{capacityNotice}</Notice> : null}
          <View style={styles.actionDockRow}>
            <View>
              <Text style={local.dockLabel}>{remaining > 0 ? `드럼 ${basketIds.length}벌 · 분석 한도 ${basketLimit}벌` : `분석 한도 ${basketLimit}벌에 도달했어요`}</Text>
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
  headerAction: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, minHeight: 44,
    paddingHorizontal: 10, borderRadius: 13, backgroundColor: palette.accentWash,
  },
  headerActionText: { color: palette.accent, fontSize: 14, fontWeight: '700' },
  iconButton: { width: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  inventory: { gap: 9 },
  listHeader: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8,
    minHeight: 38,
  },
  listHeading: { flexShrink: 1, gap: 2 },
  listTitle: { color: palette.ink, fontSize: 18, lineHeight: 24, fontWeight: '800' },
  textButton: { flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start', gap: 5, minHeight: 44 },
  linkText: { color: palette.accent, fontSize: 13, fontWeight: '700' },
  empty: { alignItems: 'flex-start' },
  emptyIconBadge: { backgroundColor: palette.lilac },
  garmentIconBadge: { backgroundColor: palette.aqua },
  list: { overflow: 'hidden' },
  itemDivider: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: palette.line },
  selectedItem: { backgroundColor: palette.accentWash },
  itemRow: { flexDirection: 'row', alignItems: 'center' },
  itemTarget: { flex: 1, minWidth: 0, flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 80, paddingVertical: 10, paddingLeft: 10 },
  checkbox: {
    width: 20, height: 20, alignItems: 'center', justifyContent: 'center',
    borderWidth: 1, borderColor: palette.muted, borderRadius: 6, backgroundColor: palette.surface,
  },
  checked: { borderColor: palette.accent, backgroundColor: palette.accent },
  inBasket: { borderColor: palette.line, backgroundColor: palette.subtle },
  thumbImage: { width: 38, height: 38, borderRadius: 12, backgroundColor: palette.subtle },
  details: { flex: 1, minWidth: 0, gap: 3 },
  care: { flexShrink: 1 },
  careLine: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  warning: { color: palette.error },
  confirm: { alignItems: 'flex-start', gap: 7, paddingHorizontal: 10, paddingVertical: 8, backgroundColor: palette.errorWash },
  confirmText: { color: palette.error, fontSize: 14, fontWeight: '600' },
  dockLabel: { color: palette.ink, fontSize: 13, fontWeight: '700' },
});
