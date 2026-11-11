import type { ComponentProps, ReactNode, Ref } from 'react';
import Ionicons from '@expo/vector-icons/Ionicons';
import {
  Pressable, ScrollView, StyleSheet, Text, TextInput, View,
  type ScrollViewInstance, type TextInputInstance, type TextInputProps,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

export const palette = {
  paper: '#F8F6F7',
  surface: '#FFFFFF',
  ink: '#171923',
  muted: '#5F6270',
  accent: '#5A4BA3',
  inverse: '#FFFFFF',
  line: '#E7E7EF',
  accentWash: '#E8E4F8',
  subtle: '#F3F2F6',
  error: '#9F263C',
  errorWash: '#FDECEF',
  violet: '#BCBEF1',
  lilac: '#D6D8FF',
  aqua: '#BFEBEA',
  blue: '#DDE7F5',
  navy: '#242539',
  blush: '#E9BFC0',
  peach: '#FBE0CD',
  coral: '#FF9DA0',
};

export type IconName = ComponentProps<typeof Ionicons>['name'];

type ScreenProps = {
  children: ReactNode;
  title?: string;
  subtitle?: string;
  scrollRef?: Ref<ScrollViewInstance>;
  reserveTabBar?: boolean;
};

export function Screen({ children, title, subtitle, scrollRef, reserveTabBar = true }: ScreenProps) {
  const insets = useSafeAreaInsets();
  return (
    <ScrollView
      ref={scrollRef}
      style={styles.screen}
      contentContainerStyle={[styles.content, reserveTabBar && { paddingBottom: 118 + insets.bottom }]}
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

type RingProps = {
  value: number;
  max: number;
  size?: number;
  thickness?: number;
  track?: string;
  color?: string;
  children?: ReactNode;
};

export function ProgressRing({
  value, max, size = 144, thickness = 10, track = palette.accentWash, color = palette.violet, children,
}: RingProps) {
  const ratio = max > 0 ? Math.max(0, Math.min(value / max, 1)) : 0;
  const angle = 360 * ratio;
  const half = size / 2;
  const radius = (size - thickness) / 2;
  const radians = angle * Math.PI / 180;
  const circle = { width: size, height: size, borderRadius: half, borderWidth: thickness };
  const halfMask = { width: half, height: size };

  return (
    <View style={[ring.center, { width: size, height: size }]}>
      <View pointerEvents="none" style={[ring.topLeft, circle, { borderColor: track }]} />
      {angle > 0 && (
        <>
          {/* Each window reveals the part of the rotating half-circle inside its half of the ring. */}
          <View pointerEvents="none" style={[ring.top, ring.clip, halfMask, { left: half }]}>
            <View style={[ring.top, { left: -half, width: size, height: size, transform: [{ rotate: Math.min(angle, 180) + 'deg' }] }]}>
              <View style={[ring.topLeft, ring.clip, halfMask]}>
                <View style={[ring.topLeft, circle, { borderColor: color }]} />
              </View>
            </View>
          </View>
          {angle > 180 && (
            <View pointerEvents="none" style={[ring.topLeft, ring.clip, halfMask]}>
              <View style={[ring.topLeft, { width: size, height: size, transform: [{ rotate: (angle - 180) + 'deg' }] }]}>
                <View style={[ring.top, ring.clip, halfMask, { left: half }]}>
                  <View style={[ring.top, circle, { left: -half, borderColor: color }]} />
                </View>
              </View>
            </View>
          )}
          {ratio < 1 && (
            <>
              <View pointerEvents="none" style={[ring.top, { left: radius, width: thickness, height: thickness, borderRadius: thickness / 2, backgroundColor: color }]} />
              <View pointerEvents="none" style={{ position: 'absolute', width: thickness, height: thickness, borderRadius: thickness / 2, backgroundColor: color, left: radius + radius * Math.sin(radians), top: radius - radius * Math.cos(radians) }} />
            </>
          )}
        </>
      )}
      {children}
    </View>
  );
}

const ring = StyleSheet.create({
  center: { alignItems: 'center', justifyContent: 'center' },
  top: { position: 'absolute', top: 0 },
  topLeft: { position: 'absolute', top: 0, left: 0 },
  clip: { overflow: 'hidden' },
});

export const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: palette.paper },
  content: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: 26, gap: 17, width: '100%', maxWidth: 640, alignSelf: 'center' },
  heading: { gap: 5, paddingBottom: 2 },
  screenTitle: { color: palette.ink, fontSize: 29, lineHeight: 38, fontWeight: '800', letterSpacing: -0.9 },
  title: { color: palette.ink, fontSize: 18, lineHeight: 25, fontWeight: '700', letterSpacing: -0.3 },
  body: { color: palette.ink, fontSize: 15, lineHeight: 22 },
  muted: { color: palette.muted, fontSize: 14, lineHeight: 21 },
  mono: { fontVariant: ['tabular-nums'] },
  section: { gap: 12 },
  wrap: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8 },
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

