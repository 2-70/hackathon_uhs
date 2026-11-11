import { forwardRef, useEffect, useRef, useState, type ComponentProps, type ComponentRef, type ReactNode, type Ref } from 'react';
import Ionicons from '@expo/vector-icons/Ionicons';
import {
  AccessibilityInfo, Animated, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
  type PressableProps, type PressableStateCallbackType, type ScrollViewInstance, type StyleProp,
  type TextInputInstance, type TextInputProps, type ViewStyle,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

export const palette = {
  paper: '#F0EEFC',
  surface: '#FFFEFF',
  ink: '#211B38',
  muted: '#625A76',
  accent: '#5E48DC',
  inverse: '#FFFFFF',
  line: '#E2DCF6',
  accentWash: '#E7E0FF',
  subtle: '#F6F3FF',
  error: '#9F263C',
  errorWash: '#FDECEF',
  violet: '#A99AF7',
  lilac: '#D9D0FF',
  aqua: '#D8EFE1',
  blue: '#DDE8FB',
  navy: '#302554',
  blush: '#FBE2EA',
  peach: '#FCE9CD',
  coral: '#C76C85',
};

export type IconName = ComponentProps<typeof Ionicons>['name'];

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

export function useReducedMotion(): boolean | null {
  const [reduceMotion, setReduceMotion] = useState<boolean | null>(null);

  useEffect(() => {
    let mounted = true;
    AccessibilityInfo.isReduceMotionEnabled().then((enabled) => {
      if (mounted) setReduceMotion(enabled);
    }).catch(() => {
      if (mounted) setReduceMotion(false);
    });
    const subscription = AccessibilityInfo.addEventListener('reduceMotionChanged', setReduceMotion);
    return () => {
      mounted = false;
      subscription.remove();
    };
  }, []);

  return reduceMotion;
}

/** A Pressable-compatible touch target with a short, springy scale response. */
export const SpringPressable = forwardRef<ComponentRef<typeof Pressable>, PressableProps>(function SpringPressable(
  { onPressIn, onPressOut, style, ...props },
  ref,
) {
  const scale = useRef(new Animated.Value(1)).current;
  const [pressed, setPressed] = useState(false);
  const reduceMotion = useReducedMotion();

  const moveTo = (value: number) => {
    if (reduceMotion !== false) {
      scale.setValue(1);
      return;
    }
    Animated.spring(scale, {
      toValue: value,
      useNativeDriver: Platform.OS !== 'web',
      speed: 24,
      bounciness: 7,
    }).start();
  };
  const state: PressableStateCallbackType = { pressed };
  const resolvedStyle = StyleSheet.flatten(typeof style === 'function' ? style(state) : style);
  const userTransform = typeof resolvedStyle?.transform === 'string' ? [] : (resolvedStyle?.transform ?? []);

  return (
    <AnimatedPressable
      {...props}
      ref={ref}
      onPressIn={(event) => {
        setPressed(true);
        moveTo(0.975);
        onPressIn?.(event);
      }}
      onPressOut={(event) => {
        setPressed(false);
        moveTo(1);
        onPressOut?.(event);
      }}
      style={[resolvedStyle, { transform: [...userTransform, { scale }] }]}
    />
  );
});

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
        <SpringPressable
          accessibilityRole="button"
          accessibilityLabel="뒤로"
          onPress={onBack}
          style={({ pressed }) => [styles.headerBack, pressed && styles.dimmed]}
        >
          <Ionicons name="chevron-back" size={22} color={palette.ink} />
        </SpringPressable>
      )}
      {title ? <Text accessibilityRole="header" style={[styles.screenTitle, styles.headerTitle]}>{title}</Text> : null}
      {action ? <View style={styles.headerAction}>{action}</View> : null}
    </View>
  );
}

type LaundryRouteHeaderProps = {
  active: 'drum' | 'machines';
  onBack: () => void;
  onNavigate: (route: '/drum' | '/machines') => void;
};

export function LaundryRouteHeader({ active, onBack, onNavigate }: LaundryRouteHeaderProps) {
  return (
    <View style={[styles.screenHeader, styles.laundryHeader]}>
      <SpringPressable
        accessibilityRole="button"
        accessibilityLabel="뒤로"
        onPress={onBack}
        style={styles.headerBack}
      >
        <Ionicons name="chevron-back" size={22} color={palette.ink} />
      </SpringPressable>
      <View style={styles.laundrySwitch}>
        {([
          ['drum', '드럼', '/drum'],
          ['machines', '세탁기', '/machines'],
        ] as const).map(([key, label, route]) => {
          const selected = active === key;
          return (
            <SpringPressable
              key={key}
              accessibilityRole="tab"
              accessibilityLabel={label}
              accessibilityState={{ selected }}
              onPress={() => { if (!selected) onNavigate(route); }}
              style={[styles.laundrySegment, selected && styles.laundrySegmentSelected]}
            >
              <Text style={[styles.laundrySegmentLabel, selected && styles.laundrySegmentLabelSelected]}>{label}</Text>
            </SpringPressable>
          );
        })}
      </View>
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
        <SpringPressable
          accessibilityRole="button"
          accessibilityLabel="검색어 지우기"
          onPress={() => onChangeText('')}
          style={({ pressed }) => [styles.searchClear, pressed && styles.dimmed]}
        >
          <Ionicons name="close" size={19} color={palette.muted} />
        </SpringPressable>
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
    <SpringPressable
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
    </SpringPressable>
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
    <SpringPressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={({ pressed }) => [styles.chip, selected && styles.chipSelected, pressed && styles.dimmed]}
    >
      <Text style={[styles.chipLabel, selected && styles.chipLabelSelected]}>{children}</Text>
    </SpringPressable>
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
  laundryHeader: { gap: 8 },
  headerBack: { width: 44, height: 44, alignItems: 'flex-start', justifyContent: 'center', paddingLeft: 1 },
  laundrySwitch: { flex: 1, minWidth: 0, maxWidth: 240, flexDirection: 'row', padding: 3, gap: 3, borderRadius: 14, backgroundColor: palette.subtle },
  laundrySegment: { flex: 1, minWidth: 0, minHeight: 36, paddingHorizontal: 8, borderRadius: 11, alignItems: 'center', justifyContent: 'center' },
  laundrySegmentSelected: { backgroundColor: palette.surface, borderWidth: 1, borderColor: palette.line },
  laundrySegmentLabel: { color: palette.muted, fontSize: 12, lineHeight: 16, fontWeight: '700' },
  laundrySegmentLabelSelected: { color: palette.accent, fontWeight: '800' },
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

