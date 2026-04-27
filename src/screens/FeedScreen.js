import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  View, Text, StyleSheet, Animated, PanResponder,
  TouchableOpacity, Dimensions, Image, ActivityIndicator,
  SafeAreaView, StatusBar, Alert,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { getNextProducts, recordInteraction, getProfile } from '../utils/algorithm';

const { width, height } = Dimensions.get('window');
const SWIPE_THRESHOLD = 90;
const COLORS = { bg: '#0a0a0a', purple: '#a78bfa', card: '#111', text: '#fff', muted: '#888' };

export default function FeedScreen() {
  const [queue, setQueue] = useState([]);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState('');
  const [detail, setDetail] = useState(null);

  // Animated values
  const position = useRef(new Animated.ValueXY()).current;
  const toastAnim = useRef(new Animated.Value(0)).current;
  const detailAnim = useRef(new Animated.Value(height)).current;

  // Refs so panResponder can access latest state
  const queueRef = useRef([]);
  const isAnimating = useRef(false);
  const interactionCount = useRef(0);
  const handleActionRef = useRef(null);

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    setLoading(true);
    const [prods, prof] = await Promise.all([getNextProducts(30), getProfile()]);
    setQueue(prods);
    queueRef.current = prods;
    setProfile(prof);
    interactionCount.current = prof.interactions;
    setLoading(false);
  };

  const showToast = (msg) => {
    setToast(msg);
    Animated.sequence([
      Animated.timing(toastAnim, { toValue: 1, duration: 300, useNativeDriver: true }),
      Animated.delay(1800),
      Animated.timing(toastAnim, { toValue: 0, duration: 300, useNativeDriver: true }),
    ]).start();
  };

  const openDetail = (product) => {
    setDetail(product);
    Animated.spring(detailAnim, { toValue: 0, useNativeDriver: true }).start();
  };

  const closeDetail = () => {
    Animated.timing(detailAnim, { toValue: height, duration: 280, useNativeDriver: true }).start(() => setDetail(null));
  };

  const advanceQueue = async (currentProduct) => {
    position.setValue({ x: 0, y: 0 });
    const newQueue = queueRef.current.slice(1);

    if (newQueue.length < 5) {
      const more = await getNextProducts(20);
      const combined = [...newQueue, ...more];
      queueRef.current = combined;
      setQueue(combined);
    } else {
      queueRef.current = newQueue;
      setQueue(newQueue);
    }

    interactionCount.current += 1;
    const prof = await getProfile();
    setProfile(prof);

    if (interactionCount.current % 10 === 0 && interactionCount.current > 0) {
      showToast('Seu perfil de estilo está evoluindo ✨');
    }
    isAnimating.current = false;
  };

  const handleAction = useCallback(async (type) => {
    if (isAnimating.current || queueRef.current.length === 0) return;
    isAnimating.current = true;

    const currentProduct = queueRef.current[0];
    await recordInteraction(currentProduct, type);

    const targetX = type === 'like' ? width * 1.5 : type === 'skip' ? -width * 1.5 : 0;

    if (type === 'save') {
      showToast('Salvo nos favoritos 🔖');
      advanceQueue(currentProduct);
      return;
    }

    Animated.timing(position, {
      toValue: { x: targetX, y: 0 },
      duration: 280,
      useNativeDriver: false,
    }).start(() => advanceQueue(currentProduct));
  }, []);

  // Keep ref current
  handleActionRef.current = handleAction;

  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => !isAnimating.current,
      onMoveShouldSetPanResponder: (_, g) => Math.abs(g.dx) > 5 || Math.abs(g.dy) > 5,
      onPanResponderMove: (_, g) => {
        if (isAnimating.current) return;
        position.setValue({ x: g.dx, y: g.dy * 0.15 });
      },
      onPanResponderRelease: (_, g) => {
        if (isAnimating.current) return;
        if (g.dx > SWIPE_THRESHOLD) handleActionRef.current('like');
        else if (g.dx < -SWIPE_THRESHOLD) handleActionRef.current('skip');
        else if (g.dy < -80 && queueRef.current[0]) {
          Animated.spring(position, { toValue: { x: 0, y: 0 }, useNativeDriver: false }).start();
          openDetail(queueRef.current[0]);
        } else {
          Animated.spring(position, { toValue: { x: 0, y: 0 }, friction: 5, useNativeDriver: false }).start();
        }
      },
    })
  ).current;

  const rotate = position.x.interpolate({
    inputRange: [-width / 2, 0, width / 2],
    outputRange: ['-12deg', '0deg', '12deg'],
  });
  const likeOpacity = position.x.interpolate({ inputRange: [0, SWIPE_THRESHOLD], outputRange: [0, 1], extrapolate: 'clamp' });
  const skipOpacity = position.x.interpolate({ inputRange: [-SWIPE_THRESHOLD, 0], outputRange: [1, 0], extrapolate: 'clamp' });

  const progress = Math.min((profile?.interactions || 0) / 50, 1);
  const currentProduct = queue[0];

  if (loading) return (
    <View style={[s.container, { justifyContent: 'center', alignItems: 'center' }]}>
      <ActivityIndicator color={COLORS.purple} size="large" />
      <Text style={{ color: COLORS.muted, marginTop: 12 }}>Carregando peças para você...</Text>
    </View>
  );

  if (!currentProduct) return (
    <View style={[s.container, { justifyContent: 'center', alignItems: 'center' }]}>
      <Text style={{ fontSize: 40 }}>✨</Text>
      <Text style={{ color: COLORS.text, fontSize: 18, marginTop: 12 }}>Você viu tudo!</Text>
      <Text style={{ color: COLORS.muted, marginTop: 8, textAlign: 'center', paddingHorizontal: 40 }}>
        Atualizando recomendações com base no seu gosto...
      </Text>
      <TouchableOpacity onPress={loadData} style={s.reloadBtn}>
        <Text style={{ color: COLORS.purple, fontWeight: '600' }}>Ver mais peças</Text>
      </TouchableOpacity>
    </View>
  );

  return (
    <View style={s.container}>
      <StatusBar barStyle="light-content" backgroundColor={COLORS.bg} />

      {/* ── Header ── */}
      <SafeAreaView>
        <View style={s.header}>
          <View>
            <Text style={s.logo}>FitFeed</Text>
            <View style={s.progressTrack}>
              <View style={[s.progressFill, { width: `${progress * 100}%` }]} />
            </View>
          </View>
          <View style={s.chip}>
            <Text style={s.chipText}>
              {(profile?.interactions || 0) < 20 ? '🌀 explorando...' : '🧠 aprendendo seu gosto'}
            </Text>
          </View>
        </View>
      </SafeAreaView>

      {/* ── Card ── */}
      <View style={s.cardArea}>
        {/* Next card (peek) */}
        {queue[1] && (
          <View style={[s.card, { position: 'absolute', top: 6, transform: [{ scale: 0.97 }] }]}>
            <Image source={{ uri: queue[1].image }} style={s.image} />
          </View>
        )}

        {/* Current card */}
        <Animated.View
          style={[s.card, { transform: [{ translateX: position.x }, { translateY: position.y }, { rotate }] }]}
          {...panResponder.panHandlers}
        >
          <Image source={{ uri: currentProduct.image }} style={s.image} />

          {/* CURTIU overlay */}
          <Animated.View style={[s.stickerBox, s.likeSticker, { opacity: likeOpacity }]}>
            <Text style={s.stickerText}>❤️ CURTIU</Text>
          </Animated.View>

          {/* PASSOU overlay */}
          <Animated.View style={[s.stickerBox, s.skipSticker, { opacity: skipOpacity }]}>
            <Text style={s.stickerText}>✕ PASSOU</Text>
          </Animated.View>

          {/* Bottom info gradient */}
          <LinearGradient
            colors={['transparent', 'rgba(0,0,0,0.5)', 'rgba(0,0,0,0.92)']}
            style={s.gradient}
          >
            <Text style={s.brandLabel}>{currentProduct.brand}  ·  {currentProduct.gender}</Text>
            <Text style={s.productName}>{currentProduct.name}</Text>
            <Text style={s.productPrice}>R$ {currentProduct.price.toFixed(2)}</Text>
            <View style={s.tagsRow}>
              {currentProduct.style_tags.map(tag => (
                <View key={tag} style={s.tag}>
                  <Text style={s.tagText}>{tag}</Text>
                </View>
              ))}
              {currentProduct.colors.map(c => (
                <View key={c} style={[s.tag, { borderColor: '#a78bfa44', backgroundColor: '#a78bfa22' }]}>
                  <Text style={[s.tagText, { color: '#c4b5fd' }]}>{c}</Text>
                </View>
              ))}
            </View>
          </LinearGradient>

          {/* Action buttons */}
          <View style={s.actions}>
            <TouchableOpacity onPress={() => handleAction('like')} style={[s.btn, s.btnLike]}>
              <Text style={{ fontSize: 22 }}>❤️</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => handleAction('skip')} style={[s.btn, s.btnSkip]}>
              <Text style={{ fontSize: 20, color: '#fff', fontWeight: '700' }}>✕</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => handleAction('save')} style={[s.btn, s.btnSave]}>
              <Text style={{ fontSize: 20 }}>🔖</Text>
            </TouchableOpacity>
          </View>

          <TouchableOpacity style={s.detailHint} onPress={() => openDetail(currentProduct)}>
            <Text style={s.detailHintText}>↑  ver detalhes</Text>
          </TouchableOpacity>
        </Animated.View>
      </View>

      {/* ── Toast ── */}
      <Animated.View style={[s.toast, { opacity: toastAnim, transform: [{ translateY: toastAnim.interpolate({ inputRange: [0, 1], outputRange: [20, 0] }) }] }]}>
        <Text style={s.toastText}>{toast}</Text>
      </Animated.View>

      {/* ── Detail bottom sheet ── */}
      {detail && (
        <Animated.View style={[s.sheet, { transform: [{ translateY: detailAnim }] }]}>
          <TouchableOpacity style={s.sheetClose} onPress={closeDetail}>
            <Text style={{ color: COLORS.muted, fontSize: 14 }}>✕ fechar</Text>
          </TouchableOpacity>
          <Image source={{ uri: detail.image }} style={s.sheetImage} />
          <View style={s.sheetBody}>
            <Text style={s.sheetBrand}>{detail.brand}  ·  {detail.gender}</Text>
            <Text style={s.sheetName}>{detail.name}</Text>
            <Text style={s.sheetPrice}>R$ {detail.price.toFixed(2)}</Text>
            <Text style={s.sheetDesc}>{detail.description}</Text>

            <Text style={[s.sheetBrand, { marginTop: 16 }]}>Tamanhos</Text>
            <View style={s.sizesRow}>
              {['PP', 'P', 'M', 'G', 'GG'].map(sz => (
                <TouchableOpacity key={sz} style={s.sizeChip}>
                  <Text style={s.sizeText}>{sz}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <TouchableOpacity style={s.buyBtn} onPress={() => { closeDetail(); showToast('Adicionado ao carrinho 🛍️'); }}>
              <Text style={s.buyBtnText}>Adicionar ao carrinho</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.saveDetailBtn} onPress={() => { closeDetail(); handleAction('save'); }}>
              <Text style={s.saveDetailBtnText}>🔖  Salvar peça</Text>
            </TouchableOpacity>
          </View>
        </Animated.View>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bg },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', paddingHorizontal: 20, paddingTop: 8, paddingBottom: 8 },
  logo: { color: '#fff', fontSize: 22, fontWeight: '700', letterSpacing: -0.5 },
  progressTrack: { height: 3, width: 100, backgroundColor: '#222', borderRadius: 4, marginTop: 4 },
  progressFill: { height: 3, backgroundColor: COLORS.purple, borderRadius: 4 },
  chip: { backgroundColor: '#a78bfa22', borderRadius: 20, paddingHorizontal: 12, paddingVertical: 6 },
  chipText: { color: '#c4b5fd', fontSize: 11, fontWeight: '600' },
  cardArea: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 12, paddingBottom: 16 },
  card: {
    width: width - 24, height: height * 0.70, borderRadius: 20,
    overflow: 'hidden', backgroundColor: '#1a1a1a',
    shadowColor: '#000', shadowOpacity: 0.5, shadowRadius: 20, elevation: 10,
  },
  image: { width: '100%', height: '100%', position: 'absolute' },
  gradient: { position: 'absolute', bottom: 0, left: 0, right: 0, paddingBottom: 90, paddingHorizontal: 18, paddingTop: 60 },
  brandLabel: { color: 'rgba(255,255,255,0.55)', fontSize: 11, letterSpacing: 1.5, textTransform: 'uppercase', marginBottom: 4 },
  productName: { color: '#fff', fontSize: 22, fontWeight: '700', marginBottom: 4 },
  productPrice: { color: COLORS.purple, fontSize: 18, fontWeight: '600', marginBottom: 10 },
  tagsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  tag: { backgroundColor: 'rgba(255,255,255,0.12)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.15)', borderRadius: 20, paddingHorizontal: 10, paddingVertical: 3 },
  tagText: { color: 'rgba(255,255,255,0.8)', fontSize: 11 },
  actions: { position: 'absolute', right: 14, bottom: 24, gap: 14 },
  btn: { width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center' },
  btnLike: { backgroundColor: 'rgba(255,255,255,0.15)' },
  btnSkip: { backgroundColor: 'rgba(255,255,255,0.15)' },
  btnSave: { backgroundColor: 'rgba(167,139,250,0.25)' },
  detailHint: { position: 'absolute', bottom: 8, alignSelf: 'center' },
  detailHintText: { color: 'rgba(255,255,255,0.35)', fontSize: 12 },
  stickerBox: { position: 'absolute', top: 40, paddingHorizontal: 18, paddingVertical: 10, borderRadius: 10, borderWidth: 3 },
  stickerText: { fontSize: 18, fontWeight: '900', letterSpacing: 1 },
  likeSticker: { left: 16, borderColor: '#4ade80', backgroundColor: 'rgba(74,222,128,0.15)' },
  skipSticker: { right: 16, borderColor: '#f87171', backgroundColor: 'rgba(248,113,113,0.15)' },
  toast: { position: 'absolute', bottom: 100, alignSelf: 'center', backgroundColor: '#1f1f2e', paddingHorizontal: 20, paddingVertical: 10, borderRadius: 30, borderWidth: 1, borderColor: '#a78bfa44' },
  toastText: { color: '#c4b5fd', fontSize: 13 },
  reloadBtn: { marginTop: 20, paddingHorizontal: 24, paddingVertical: 12, borderRadius: 30, borderWidth: 1, borderColor: COLORS.purple },
  // Detail sheet
  sheet: { position: 'absolute', bottom: 0, left: 0, right: 0, height: height * 0.82, backgroundColor: '#111', borderTopLeftRadius: 24, borderTopRightRadius: 24, overflow: 'hidden' },
  sheetClose: { position: 'absolute', top: 16, right: 20, zIndex: 10 },
  sheetImage: { width: '100%', height: 260 },
  sheetBody: { padding: 20 },
  sheetBrand: { color: COLORS.muted, fontSize: 11, letterSpacing: 1.5, textTransform: 'uppercase', marginBottom: 4 },
  sheetName: { color: '#fff', fontSize: 22, fontWeight: '700', marginBottom: 4 },
  sheetPrice: { color: COLORS.purple, fontSize: 20, fontWeight: '700', marginBottom: 12 },
  sheetDesc: { color: '#aaa', fontSize: 14, lineHeight: 22 },
  sizesRow: { flexDirection: 'row', gap: 10, marginTop: 10, marginBottom: 20 },
  sizeChip: { width: 46, height: 46, borderRadius: 8, borderWidth: 1, borderColor: '#333', alignItems: 'center', justifyContent: 'center' },
  sizeText: { color: '#fff', fontSize: 13, fontWeight: '600' },
  buyBtn: { backgroundColor: COLORS.purple, borderRadius: 14, paddingVertical: 16, alignItems: 'center', marginBottom: 12 },
  buyBtnText: { color: '#fff', fontSize: 16, fontWeight: '700' },
  saveDetailBtn: { borderWidth: 1, borderColor: '#333', borderRadius: 14, paddingVertical: 14, alignItems: 'center' },
  saveDetailBtnText: { color: '#aaa', fontSize: 15 },
});
