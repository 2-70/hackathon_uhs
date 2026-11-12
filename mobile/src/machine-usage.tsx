import { Link } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import type { Machine } from './model';
import type { MachineGuide } from './together';
import { palette, styles } from './ui';

export function MachineGuideBody({ machine, guide }: { machine: Machine; guide: MachineGuide }) {
  const { setting } = guide;
  const origin = setting.isDefault ? '기본값' : '직접 선택';
  const cells = [
    { label: '코스', value: guide.courseLabel, note: null },
    { label: '물 온도', value: setting.temperature, note: origin },
    { label: '탈수', value: setting.spin, note: origin },
    ...(setting.waterLevel ? [{ label: '물 높이', value: setting.waterLevel, note: null }] : []),
  ];
  return (
    <>
      <Text style={styles.rowTitle}>{machine.maker} {machine.model} 추천 설정</Text>
      <View style={local.cells}>
        {cells.map(({ label, value, note }) => (
          <View key={label} style={local.cell} accessible accessibilityLabel={`${label} ${value}${note ? ` ${note}` : ''}`}>
            <Text style={styles.rowMeta}>{label}</Text>
            <Text style={local.value}>{value}</Text>
            {note && <Text style={styles.rowMeta}>{note}</Text>}
          </View>
        ))}
      </View>
      {guide.checks.length > 0 && (
        <View style={local.checks}>
          <Text style={styles.rowTitle}>돌리기 전에 확인하세요</Text>
          {guide.checks.map((line) => <Text key={line} style={styles.body}>• {line}</Text>)}
        </View>
      )}
      {guide.assumptions.map((line) => <Text key={line} style={styles.muted}>{line}</Text>)}
      <ManualLink url={guide.sourceUrl} label="공식 설명서에서 설정 보기" />
    </>
  );
}

export function ManualLink({ url, label }: { url: string | null | undefined; label: string }) {
  if (!url?.startsWith('https://')) return null;
  return <Link href={url as `https://${string}`} target="_blank" rel="noopener noreferrer" style={local.link}>{label}</Link>;
}

export function MachineManual({ machine }: { machine: Machine }) {
  const documents = machine.documents ?? [];
  const instructions = machine.instructions ?? [];
  const confirmed = instructions.filter(({ text }) => text !== null);
  const pages = [...new Map(instructions.filter(({ text }) => text === null)
    .map((item) => [item.title, item])).values()];

  return (
    <View style={local.guide}>
      {machine.catalog && documents.length === 0 && (
        <Text style={styles.muted}>이 모델의 공식 설명서가 아직 연결되지 않았어요. 기기 패널이나 제조사 설명서에서 설정을 확인해 주세요.</Text>
      )}
      {documents.map((document, index) => (
        <ManualLink key={document.id} url={document.url}
          label={documents.length === 1 ? '공식 설명서 열기' : `공식 설명서 ${index + 1} 열기`} />
      ))}
      {confirmed.map((item) => (
        <View key={item.id} style={local.guide}>
          <Text style={styles.rowTitle}>{item.title}</Text>
          <Text style={styles.body}>{item.text}</Text>
          <ManualLink url={item.url} label="설명서 근거 보기" />
        </View>
      ))}
      {pages.length > 0 && (
        <View style={local.guide}>
          <Text style={styles.muted}>설명서에서 자동으로 찾은 페이지예요. 적용 조건과 설정값은 원문에서 확인해 주세요.</Text>
          <View style={styles.wrap}>
            {pages.map((item) => <ManualLink key={item.id} url={item.url} label={item.title} />)}
          </View>
        </View>
      )}
      <ManualLink url={machine.sourceUrl} label={machine.catalog ? '모델 등록 출처' : '제조사 지원 페이지'} />
    </View>
  );
}

const local = StyleSheet.create({
  guide: { gap: 8 },
  cells: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  cell: { flexGrow: 1, flexBasis: 90, minWidth: 90, gap: 2, padding: 10, borderRadius: 12, borderWidth: 1, borderColor: palette.line, backgroundColor: palette.surface },
  value: { color: palette.ink, fontSize: 15, lineHeight: 21, fontWeight: '800' },
  checks: { gap: 4 },
  link: { color: palette.accent, fontSize: 14, fontWeight: '700', textDecorationLine: 'underline' },
});
