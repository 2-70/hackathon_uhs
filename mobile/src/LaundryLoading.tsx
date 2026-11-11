import { useEffect, useRef } from 'react';
import { Animated, Easing, Platform, StyleSheet, Text, View } from 'react-native';
import { palette, styles as uiStyles, useReducedMotion } from './ui';

type LaundryLoadingProps = { label: string; compact?: boolean };

export function LaundryLoading({ label, compact = false }: LaundryLoadingProps) {
  const reduceMotion = useReducedMotion();
  const cycle = useRef(new Animated.Value(0)).current;
  const useNativeDriver = Platform.OS !== 'web';

  useEffect(() => {
    cycle.stopAnimation();
    cycle.setValue(0);
    if (reduceMotion !== false) return;

    const animation = Animated.loop(Animated.sequence([
      Animated.timing(cycle, {
        toValue: 1,
        duration: 1900,
        easing: Easing.inOut(Easing.sin),
        useNativeDriver,
        isInteraction: false,
      }),
      Animated.timing(cycle, {
        toValue: 0,
        duration: 1900,
        easing: Easing.inOut(Easing.sin),
        useNativeDriver,
        isInteraction: false,
      }),
    ]));
    animation.start();
    return () => {
      animation.stop();
      cycle.stopAnimation();
    };
  }, [cycle, reduceMotion, useNativeDriver]);

  return (
    <View style={compact ? local.compact : [uiStyles.card, local.card]}>
      <WasherGraphic compact={compact} cycle={cycle} />
      <Text
        style={compact ? local.compactLabel : local.cardLabel}
        accessibilityRole="text"
        accessibilityLiveRegion="polite"
      >
        {label}
      </Text>
    </View>
  );
}

function WasherGraphic({ compact, cycle }: { compact: boolean; cycle: Animated.Value }) {
  const size = compact ? 36 : 84;
  const drumSize = compact ? 25 : 58;
  const bob = cycle.interpolate({ inputRange: [0, 0.5, 1], outputRange: [1, -2, 1] });
  const scaleY = cycle.interpolate({ inputRange: [0, 0.5, 1], outputRange: [0.82, 1.12, 0.82] });
  const scaleX = cycle.interpolate({ inputRange: [0, 0.5, 1], outputRange: [0.94, 1.03, 0.94] });
  const turn = cycle.interpolate({ inputRange: [0, 0.5, 1], outputRange: ['-4deg', '4deg', '-4deg'] });
  const linenTurn = cycle.interpolate({ inputRange: [0, 0.5, 1], outputRange: ['-13deg', '-7deg', '-13deg'] });
  const firstBubbleOpacity = cycle.interpolate({
    inputRange: [0, 0.13, 0.3, 0.45],
    outputRange: [0, 0.9, 0.75, 0],
    extrapolate: 'clamp',
  });
  const secondBubbleOpacity = cycle.interpolate({
    inputRange: [0.48, 0.66, 0.82, 1],
    outputRange: [0, 0.85, 0.72, 0],
    extrapolate: 'clamp',
  });
  const firstBubbleY = cycle.interpolate({
    inputRange: [0, 0.13, 0.45],
    outputRange: [4, 1, -7],
    extrapolate: 'clamp',
  });
  const secondBubbleY = cycle.interpolate({
    inputRange: [0.48, 0.66, 1],
    outputRange: [4, 1, -7],
    extrapolate: 'clamp',
  });

  return (
    <View
      style={[local.art, { width: size, height: size * 1.08 }]}
      accessible={false}
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      aria-hidden
    >
      <View style={[local.washer, compact ? local.washerCompact : local.washerLarge]}>
        <View style={[local.controlStrip, compact && local.controlStripCompact]}>
          <View style={[local.controlDot, compact && local.controlDotCompact]} />
          <View style={[local.controlLine, compact && local.controlLineCompact]} />
        </View>
        <View style={[local.drumRim, { width: drumSize, height: drumSize, borderRadius: drumSize / 2 }]}>
          <View style={local.drumWindow}>
            <Animated.View
              style={[
                local.water,
                compact ? local.waterCompact : local.waterLarge,
                { transform: [{ translateY: bob }, { scaleX }, { scaleY }, { rotate: turn }] },
              ]}
            />
            <Animated.View
              style={[
                local.bubble,
                compact ? local.bubbleCompact : local.bubbleLarge,
                { opacity: firstBubbleOpacity, transform: [{ translateY: firstBubbleY }] },
              ]}
            />
            <Animated.View
              style={[
                local.bubble,
                compact ? local.bubbleCompact : local.bubbleLarge,
                local.secondBubble,
                { opacity: secondBubbleOpacity, transform: [{ translateY: secondBubbleY }] },
              ]}
            />
            <Animated.View style={[local.linen, compact && local.linenCompact, { transform: [{ rotate: linenTurn }] }]}>
              <View style={[local.linenFold, compact && local.linenFoldCompact]} />
            </Animated.View>
          </View>
        </View>
      </View>
    </View>
  );
}

const local = StyleSheet.create({
  card: {
    minHeight: 166,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
    paddingHorizontal: 18,
    paddingVertical: 18,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: palette.line,
    backgroundColor: palette.surface,
  },
  compact: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 13,
    backgroundColor: palette.accentWash,
  },
  cardLabel: {
    color: palette.ink,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '600',
    textAlign: 'center',
  },
  compactLabel: {
    flex: 1,
    minWidth: 0,
    color: palette.ink,
    fontSize: 13,
    lineHeight: 19,
    fontWeight: '600',
  },
  art: { alignItems: 'center', justifyContent: 'center' },
  washer: {
    alignItems: 'center',
    justifyContent: 'flex-start',
    borderWidth: 2,
    borderColor: 'rgba(255,255,255,0.9)',
    backgroundColor: palette.violet,
  },
  washerLarge: { width: 72, height: 80, borderRadius: 17, paddingTop: 6, gap: 4 },
  washerCompact: { width: 32, height: 36, borderRadius: 8, borderWidth: 1.5, paddingTop: 2, gap: 1 },
  controlStrip: { width: '66%', height: 7, flexDirection: 'row', alignItems: 'center', gap: 4 },
  controlStripCompact: { height: 3 },
  controlDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: palette.surface },
  controlDotCompact: { width: 3, height: 3, borderRadius: 1.5 },
  controlLine: { width: 18, height: 3, borderRadius: 2, backgroundColor: palette.lilac },
  controlLineCompact: { width: 8, height: 2 },
  drumRim: {
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: palette.surface,
    backgroundColor: palette.accent,
  },
  drumWindow: {
    width: '100%',
    height: '100%',
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 999,
    backgroundColor: palette.blue,
  },
  water: {
    position: 'absolute',
    left: '8%',
    bottom: '8%',
    width: '84%',
    borderRadius: 999,
    backgroundColor: palette.lilac,
  },
  waterLarge: { height: '57%' },
  waterCompact: { height: '55%' },
  bubble: {
    position: 'absolute',
    bottom: '34%',
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: palette.surface,
  },
  bubbleLarge: { left: '25%', width: 5, height: 5, borderRadius: 3 },
  bubbleCompact: { left: '24%', width: 2, height: 2, borderRadius: 1 },
  secondBubble: { left: '67%', bottom: '24%' },
  linen: {
    position: 'absolute',
    top: '33%',
    width: '55%',
    height: '25%',
    alignItems: 'flex-end',
    justifyContent: 'center',
    borderRadius: 7,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.9)',
    backgroundColor: palette.blush,
    transform: [{ rotate: '-12deg' }],
  },
  linenCompact: { borderRadius: 3, borderWidth: 0.6 },
  linenFold: { width: '45%', height: 1.5, marginRight: 3, borderRadius: 1, backgroundColor: palette.coral },
  linenFoldCompact: { height: 0.8, marginRight: 1.5 },
});
