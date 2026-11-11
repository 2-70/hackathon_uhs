import { Link } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import type { Machine } from './model';
import { palette, styles } from './ui';

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
  link: { color: palette.accent, fontSize: 14, fontWeight: '700', textDecorationLine: 'underline' },
});
