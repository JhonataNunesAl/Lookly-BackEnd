import React, { useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  SafeAreaView, StatusBar, Alert,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { getProfile, resetProfile, getTopStyles, getTopCategories } from '../utils/algorithm';

const COLORS = { bg: '#0a0a0a', purple: '#a78bfa', card: '#111', text: '#fff', muted: '#666' };

const STYLE_EMOJI = {
  casual: '👟', boho: '🌸', minimalista: '◻️', streetwear: '🧢',
  elegante: '✨', romântico: '🌹', vintage: '📷', preppy: '📚',
  gótico: '🖤', esportivo: '🏃',
};

const CAT_LABEL = {
  vestido: 'Vestidos', calça: 'Calças', saia: 'Saias',
  top: 'Tops', blazer: 'Blazers', casaco: 'Casacos',
  conjunto: 'Conjuntos', bermuda: 'Bermudas', short: 'Shorts',
};

export default function ProfileScreen() {
  const [profile, setProfile] = useState(null);
  const [topStyles, setTopStyles] = useState([]);
  const [topCategories, setTopCategories] = useState([]);

  useFocusEffect(
    useCallback(() => {
      loadProfile();
    }, [])
  );

  const loadProfile = async () => {
    const prof = await getProfile();
    setProfile(prof);
    setTopStyles(getTopStyles(prof, 5));
    setTopCategories(getTopCategories(prof));
  };

  const handleReset = () => {
    Alert.alert(
      'Resetar perfil',
      'Isso vai apagar todo o seu histórico de gosto e recomeçar do zero. Tem certeza?',
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Resetar', style: 'destructive',
          onPress: async () => {
            await resetProfile();
            loadProfile();
          },
        },
      ]
    );
  };

  const interactions = profile?.interactions || 0;
  const progress = Math.min(interactions / 50, 1);
  const wishlistCount = profile?.wishlist?.length || 0;

  const learningStage =
    interactions === 0 ? 'Começando' :
    interactions < 10 ? 'Explorando' :
    interactions < 20 ? 'Aprendendo' :
    interactions < 50 ? 'Refinando' :
    'Expert em moda';

  return (
    <View style={s.container}>
      <StatusBar barStyle="light-content" backgroundColor={COLORS.bg} />
      <SafeAreaView />
      <ScrollView contentContainerStyle={{ paddingBottom: 40 }}>
        {/* Header card */}
        <View style={s.heroCard}>
          <View style={s.avatar}>
            <Text style={{ fontSize: 32 }}>👗</Text>
          </View>
          <Text style={s.heroTitle}>Seu Estilo DNA</Text>
          <View style={s.stageChip}>
            <Text style={s.stageText}>{learningStage}</Text>
          </View>
        </View>

        {/* Stats row */}
        <View style={s.statsRow}>
          <View style={s.stat}>
            <Text style={s.statNum}>{interactions}</Text>
            <Text style={s.statLabel}>interações</Text>
          </View>
          <View style={s.statDivider} />
          <View style={s.stat}>
            <Text style={s.statNum}>{wishlistCount}</Text>
            <Text style={s.statLabel}>salvos</Text>
          </View>
          <View style={s.statDivider} />
          <View style={s.stat}>
            <Text style={s.statNum}>{topStyles.length}</Text>
            <Text style={s.statLabel}>estilos</Text>
          </View>
        </View>

        {/* Learning progress */}
        <View style={s.section}>
          <Text style={s.sectionTitle}>Progresso de aprendizado</Text>
          <View style={s.progressTrack}>
            <View style={[s.progressFill, { width: `${progress * 100}%` }]} />
          </View>
          <Text style={s.progressLabel}>
            {interactions}/50 interações · {Math.round(progress * 100)}% calibrado
          </Text>
        </View>

        {/* Top styles */}
        {topStyles.length > 0 && (
          <View style={s.section}>
            <Text style={s.sectionTitle}>Seus estilos favoritos</Text>
            <View style={s.stylesGrid}>
              {topStyles.map((style, i) => (
                <View key={style} style={[s.styleCard, i === 0 && s.styleCardTop]}>
                  <Text style={{ fontSize: i === 0 ? 28 : 22 }}>
                    {STYLE_EMOJI[style] || '👔'}
                  </Text>
                  <Text style={[s.styleLabel, i === 0 && { color: '#fff', fontWeight: '700' }]}>
                    {style}
                  </Text>
                  {i === 0 && <Text style={s.styleRank}>#1</Text>}
                </View>
              ))}
            </View>
          </View>
        )}

        {/* Category bars */}
        {topCategories.length > 0 && (
          <View style={s.section}>
            <Text style={s.sectionTitle}>Categorias preferidas</Text>
            {topCategories.slice(0, 6).map(({ cat, pct }) => (
              <View key={cat} style={s.barRow}>
                <Text style={s.barLabel}>{CAT_LABEL[cat] || cat}</Text>
                <View style={s.barTrack}>
                  <View style={[s.barFill, { width: `${pct}%` }]} />
                </View>
                <Text style={s.barPct}>{pct}%</Text>
              </View>
            ))}
          </View>
        )}

        {/* Top brands */}
        {profile && Object.keys(profile.scores.brands).length > 0 && (
          <View style={s.section}>
            <Text style={s.sectionTitle}>Marcas que você curte</Text>
            <View style={s.brandsWrap}>
              {Object.entries(profile.scores.brands)
                .filter(([, v]) => v > 0)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 8)
                .map(([brand]) => (
                  <View key={brand} style={s.brandChip}>
                    <Text style={s.brandChipText}>{brand}</Text>
                  </View>
                ))}
            </View>
          </View>
        )}

        {/* Empty state */}
        {interactions === 0 && (
          <View style={s.emptyState}>
            <Text style={{ fontSize: 48 }}>🧠</Text>
            <Text style={s.emptyTitle}>Nenhum dado ainda</Text>
            <Text style={s.emptySubtitle}>
              Interaja com o feed e o algoritmo vai aprender seu gosto!
            </Text>
          </View>
        )}

        {/* Reset button */}
        {interactions > 0 && (
          <TouchableOpacity style={s.resetBtn} onPress={handleReset}>
            <Text style={s.resetText}>🔄  Resetar perfil de gosto</Text>
          </TouchableOpacity>
        )}
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bg },
  heroCard: { margin: 16, backgroundColor: COLORS.card, borderRadius: 20, padding: 24, alignItems: 'center' },
  avatar: { width: 72, height: 72, borderRadius: 36, backgroundColor: '#a78bfa22', alignItems: 'center', justifyContent: 'center', borderWidth: 2, borderColor: '#a78bfa44', marginBottom: 12 },
  heroTitle: { color: '#fff', fontSize: 20, fontWeight: '700' },
  stageChip: { marginTop: 8, backgroundColor: '#a78bfa22', borderRadius: 20, paddingHorizontal: 16, paddingVertical: 6, borderWidth: 1, borderColor: '#a78bfa44' },
  stageText: { color: COLORS.purple, fontSize: 13, fontWeight: '600' },
  statsRow: { flexDirection: 'row', marginHorizontal: 16, backgroundColor: COLORS.card, borderRadius: 16, padding: 16, marginBottom: 4 },
  stat: { flex: 1, alignItems: 'center' },
  statNum: { color: COLORS.purple, fontSize: 24, fontWeight: '800' },
  statLabel: { color: COLORS.muted, fontSize: 11, marginTop: 2 },
  statDivider: { width: 1, backgroundColor: '#222' },
  section: { margin: 16, marginBottom: 0 },
  sectionTitle: { color: '#fff', fontSize: 16, fontWeight: '700', marginBottom: 14 },
  progressTrack: { height: 8, backgroundColor: '#1f1f1f', borderRadius: 4 },
  progressFill: { height: 8, backgroundColor: COLORS.purple, borderRadius: 4 },
  progressLabel: { color: COLORS.muted, fontSize: 12, marginTop: 8 },
  stylesGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  styleCard: { backgroundColor: '#1a1a1a', borderRadius: 14, padding: 14, alignItems: 'center', minWidth: 80, borderWidth: 1, borderColor: '#222' },
  styleCardTop: { backgroundColor: '#a78bfa22', borderColor: COLORS.purple, padding: 18 },
  styleLabel: { color: COLORS.muted, fontSize: 12, marginTop: 6, textTransform: 'capitalize' },
  styleRank: { color: COLORS.purple, fontSize: 11, fontWeight: '700', marginTop: 4 },
  barRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 12 },
  barLabel: { color: COLORS.muted, fontSize: 13, width: 80 },
  barTrack: { flex: 1, height: 6, backgroundColor: '#1f1f1f', borderRadius: 3, marginHorizontal: 10 },
  barFill: { height: 6, backgroundColor: COLORS.purple, borderRadius: 3 },
  barPct: { color: COLORS.purple, fontSize: 12, fontWeight: '600', width: 36, textAlign: 'right' },
  brandsWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  brandChip: { backgroundColor: '#1a1a1a', borderRadius: 20, paddingHorizontal: 14, paddingVertical: 7, borderWidth: 1, borderColor: '#2a2a2a' },
  brandChipText: { color: '#ccc', fontSize: 13 },
  emptyState: { alignItems: 'center', paddingVertical: 32, paddingHorizontal: 40 },
  emptyTitle: { color: '#fff', fontSize: 18, fontWeight: '700', marginTop: 12 },
  emptySubtitle: { color: COLORS.muted, fontSize: 14, textAlign: 'center', marginTop: 8, lineHeight: 22 },
  resetBtn: { margin: 24, borderWidth: 1, borderColor: '#333', borderRadius: 14, paddingVertical: 14, alignItems: 'center' },
  resetText: { color: '#666', fontSize: 14 },
});
