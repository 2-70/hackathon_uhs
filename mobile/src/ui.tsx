import type { ComponentProps, ReactNode, Ref } from 'react';
import Ionicons from '@expo/vector-icons/Ionicons';
import {
  Pressable, ScrollView, StyleSheet, Text, TextInput, View,
  type ScrollViewInstance, type StyleProp, type TextInputInstance, type TextInputProps, type ViewStyle,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

export const palette = {
  paper: '#FFF7ED',
  surface: '#FFFFFF',
  ink: '#282322',
  muted: '#655B55',
  accent: '#AE3E32',
  inverse: '#FFFFFF',
  line: '#EDE0D4',
  accentWash: '#FBE3DB',
  subtle: '#F8EFE6',
  error: '#9F263C',
  errorWash: '#FDECEF',
  violet: '#B3A6F4',
  lilac: '#DDD4FF',
  aqua: '#A4E2CD',
  blue: '#AED5F8',
  navy: '#292322',
  blush: '#FFD8CF',
  peach: '#FFCF9A',
  coral: '#FF8F7D',
};

export type IconName = ComponentProps<typeof Ionicons>['name'];

type ScreenProps = {
  children: ReactNode;
  title?: string;
  subtitle?: string;
  scrollRef?: Ref<ScrollViewInstance>;
  reserveTabBar?: boolean;
  contentStyle?: StyleProp<ViewStyle>;
};

export function Screen({ children, title, subtitle, scrollRef, reserveTabBar = true, contentStyle }: ScreenProps) {
  const insets = useSafeAreaInsets();
  return (
    <ScrollView
      ref={scrollRef}
      style={styles.screen}
      contentContainerStyle={[styles.content, reserveTabBar && { paddingBottom: 118 + insets.bottom }, contentStyle]}
      keyboardShouldPersistTaps="handled"
      showsVerticalScrollIndicator={false}
    >
      {title && (
        <View style={styles.heading}>
          <Text accessibilityRole="header" style={styles.screenTitle}>{title}</Text>
          {subtitle && <Text style={styles.muted}>{subtitle}</Text>}
        </View>
      )}
      {children}
    </ScrollView>
  );
}

type ScreenHeaderProps = {
  title?: string;
  onBack?: () => void;
  action?: ReactNode;
};

export function ScreenHeader({ title, onBack, action }: ScreenHeaderProps) {
  return (
    <View style={styles.screenHeader}>
      {onBack && (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="뒤로"
          onPress={onBack}
          style={({ pressed }) => [styles.headerBack, pressed && styles.dimmed]}
        >
          <Ionicons name="chevron-back" size={22} color={palette.ink} />
        </Pressable>
      )}
      {title ? <Text accessibilityRole="header" style={[styles.screenTitle, styles.headerTitle]}>{title}</Text> : null}
      {action ? <View style={styles.headerAction}>{action}</View> : null}
    </View>
  );
}

type SearchFieldProps = Pick<TextInputProps, 'autoCapitalize' | 'autoCorrect'> & {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  placeholder: string;
};

export function SearchField({ label, value, onChangeText, placeholder, autoCapitalize, autoCorrect }: SearchFieldProps) {
  return (
    <View style={styles.searchField}>
      <Ionicons name="search-outline" size={19} color={palette.accent} accessible={false} />
      <TextInput
        accessibilityLabel={label}
        placeholder={placeholder}
        placeholderTextColor={palette.muted}
        value={value}
        onChangeText={onChangeText}
        autoCapitalize={autoCapitalize}
        autoCorrect={autoCorrect}
        style={styles.searchInput}
      />
      {value.length > 0 && (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="검색어 지우기"
          onPress={() => onChangeText('')}
          style={({ pressed }) => [styles.searchClear, pressed && styles.dimmed]}
        >
          <Ionicons name="close" size={19} color={palette.muted} />
        </Pressable>
      )}
    </View>
  );
}

type ButtonProps = {
  children: ReactNode;
  onPress: () => void;
  tone?: 'primary' | 'secondary' | 'quiet';
  disabled?: boolean;
  icon?: IconName;
};

export function Button({ children, onPress, tone = 'primary', disabled, icon }: ButtonProps) {
  const color = tone === 'primary' ? palette.inverse : palette.accent;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!disabled }}
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [
        styles.button,
        tone === 'primary' && styles.primary,
        tone === 'quiet' && styles.quiet,
        (pressed || disabled) && styles.dimmed,
      ]}
    >
      {icon && <Ionicons name={icon} size={18} color={color} />}
      <Text style={[styles.buttonText, { color }]}>{children}</Text>
    </Pressable>
  );
}

type FieldProps = Pick<TextInputProps, 'value' | 'onChangeText' | 'placeholder' | 'keyboardType' | 'autoCapitalize' | 'autoCorrect'> & {
  label: string;
  inputRef?: Ref<TextInputInstance>;
  invalid?: boolean;
};

export function Field({ label, inputRef, invalid, ...props }: FieldProps) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        ref={inputRef}
        accessibilityLabel={label}
        style={[styles.input, invalid && styles.inputInvalid]}
        placeholderTextColor={palette.muted}
        selectionColor={palette.accent}
        {...props}
      />
    </View>
  );
}

export function Chip({ children, selected, onPress }: { children: ReactNode; selected: boolean; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={({ pressed }) => [styles.chip, selected && styles.chipSelected, pressed && styles.dimmed]}
    >
      <Text style={[styles.chipLabel, selected && styles.chipLabelSelected]}>{children}</Text>
    </Pressable>
  );
}

export function Notice({ children, tone = 'info' }: { children: ReactNode; tone?: 'info' | 'error' | 'success' }) {
  const color = tone === 'error' ? palette.error : tone === 'success' ? palette.accent : palette.ink;
  const icon = tone === 'success' ? 'checkmark-circle-outline' : tone === 'error' ? 'alert-circle-outline' : 'information-circle-outline';
  return (
    <View style={[styles.notice, { backgroundColor: tone === 'error' ? palette.errorWash : palette.accentWash }]} accessibilityLiveRegion="polite">
      <Ionicons name={icon} size={19} color={color} />
      <Text style={[styles.noticeText, { color }]}>{children}</Text>
    </View>
  );
}

export const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: palette.paper },
  content: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: 26, gap: 17, width: '100%', maxWidth: 640, alignSelf: 'center' },
  heading: { gap: 5, paddingBottom: 2 },
  screenHeader: { minHeight: 56, width: '100%', maxWidth: 640, alignSelf: 'center', flexDirection: 'row', alignItems: 'center', paddingHorizontal: 20, gap: 0 },
  headerBack: { width: 44, height: 44, alignItems: 'flex-start', justifyContent: 'center', paddingLeft: 1 },
  headerTitle: { flex: 1, minWidth: 0 },
  headerAction: { minHeight: 44, alignItems: 'center', justifyContent: 'center', marginLeft: 8 },
  screenTitle: { color: palette.ink, fontSize: 28, lineHeight: 36, fontWeight: '800', letterSpacing: -0.7 },
  title: { color: palette.ink, fontSize: 18, lineHeight: 25, fontWeight: '700', letterSpacing: -0.3 },
  body: { color: palette.ink, fontSize: 15, lineHeight: 22 },
  muted: { color: palette.muted, fontSize: 14, lineHeight: 21 },
  mono: { fontVariant: ['tabular-nums'] },
  section: { gap: 12 },
  wrap: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8 },
  card: { backgroundColor: palette.surface, borderWidth: 1, borderColor: palette.line, borderRadius: 18 },
  cardContent: { padding: 14, gap: 12 },
  iconBadge: { width: 38, height: 38, alignItems: 'center', justifyContent: 'center', borderRadius: 12, backgroundColor: palette.accentWash },
  rowTitle: { color: palette.ink, fontSize: 15, lineHeight: 20, fontWeight: '700' },
  rowMeta: { color: palette.muted, fontSize: 12, lineHeight: 16 },
  actionDock: { width: '100%', maxWidth: 640, alignSelf: 'center', gap: 8, paddingHorizontal: 16, paddingVertical: 10, backgroundColor: palette.surface, borderWidth: 1, borderColor: palette.line, borderRadius: 18 },
  actionDockRow: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 8 },
  searchField: { flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 48, paddingLeft: 13, paddingRight: 2, borderWidth: 1, borderColor: palette.line, borderRadius: 15, backgroundColor: palette.surface },
  searchInput: { flex: 1, minWidth: 0, color: palette.ink, fontSize: 15, paddingVertical: 10, paddingRight: 4 },
  searchClear: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  button: { minHeight: 48, flexDirection: 'row', gap: 8, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 9, borderRadius: 13, borderWidth: 1, borderColor: palette.line, backgroundColor: palette.accentWash },
  primary: { backgroundColor: palette.accent, borderColor: palette.accent },
  quiet: { backgroundColor: 'transparent' },
  dimmed: { opacity: 0.62 },
  buttonText: { flexShrink: 1, textAlign: 'center', fontSize: 14, fontWeight: '700' },
  field: { gap: 7 },
  fieldLabel: { color: palette.ink, fontSize: 13, fontWeight: '700' },
  input: { color: palette.ink, backgroundColor: palette.subtle, paddingHorizontal: 13, paddingVertical: 10, minHeight: 48, borderWidth: 1, borderColor: palette.line, borderRadius: 12, fontSize: 15 },
  inputInvalid: { borderColor: palette.error },
  chip: { minHeight: 42, paddingHorizontal: 12, paddingVertical: 5, backgroundColor: palette.surface, borderRadius: 12, borderWidth: 1, borderColor: palette.line, justifyContent: 'center' },
  chipSelected: { backgroundColor: palette.accentWash, borderColor: palette.accent },
  chipLabel: { color: palette.ink, fontSize: 13, fontWeight: '600' },
  chipLabelSelected: { color: palette.accent, fontWeight: '700' },
  notice: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, padding: 12, borderRadius: 14 },
  noticeText: { flex: 1, fontSize: 13, fontWeight: '600', lineHeight: 20 },
});

