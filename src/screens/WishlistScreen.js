import React, { useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, FlatList, Image,
  TouchableOpacity, SafeAreaView, StatusBar, Alert,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { getWishlist, removeFromWishlist } from '../utils/algorithm';

const COLORS = { bg: '#0a0a0a', purple: '#a78bfa', card: '#131313', text: '#fff', muted: '#666' };

export default function WishlistScreen() {
  const [items, setItems] = useState([]);

  useFocusEffect(
    useCallback(() => {
      loadWishlist();
    }, [])
  );

  const loadWishlist = async () => {
    const list = await getWishlist();
    setItems(list);
  };

  const handleRemove = (id, name) => {
    Alert.alert(
      'Remover item',
      `Remover "${name}" dos salvos?`,
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Remover', style: 'destructive',
          onPress: async () => {
            await removeFromWishlist(id);
            loadWishlist();
          },
        },
      ]
    );
  };

  const renderItem = ({ item }) => (
    <View style={s.card}>
      <Image source={{ uri: item.image }} style={s.image} />
      <View style={s.info}>
        <Text style={s.brand}>{item.brand}</Text>
        <Text style={s.name} numberOfLines={2}>{item.name}</Text>
        <Text style={s.price}>R$ {item.price.toFixed(2)}</Text>
        <View style={s.tagsRow}>
          {item.style_tags.slice(0, 2).map(t => (
            <View key={t} style={s.tag}>
              <Text style={s.tagText}>{t}</Text>
            </View>
          ))}
        </View>
        <TouchableOpacity style={s.buyBtn}>
          <Text style={s.buyBtnText}>Comprar</Text>
        </TouchableOpacity>
      </View>
      <TouchableOpacity style={s.removeBtn} onPress={() => handleRemove(item.id, item.name)}>
        <Text style={{ color: COLORS.muted, fontSize: 16 }}>🗑</Text>
      </TouchableOpacity>
    </View>
  );

  return (
    <View style={s.container}>
      <StatusBar barStyle="light-content" backgroundColor={COLORS.bg} />
      <SafeAreaView>
        <View style={s.header}>
          <Text style={s.title}>Salvos</Text>
          <Text style={s.subtitle}>{items.length} {items.length === 1 ? 'peça' : 'peças'}</Text>
        </View>
      </SafeAreaView>

      {items.length === 0 ? (
        <View style={s.empty}>
          <Text style={{ fontSize: 52 }}>🛍️</Text>
          <Text style={s.emptyTitle}>Nada salvo ainda</Text>
          <Text style={s.emptySubtitle}>
            Curta peças no feed ou toque em 🔖 para salvá-las aqui
          </Text>
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={item => item.id}
          renderItem={renderItem}
          contentContainerStyle={{ padding: 16, gap: 14 }}
        />
      )}
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bg },
  header: { paddingHorizontal: 20, paddingTop: 12, paddingBottom: 8 },
  title: { color: '#fff', fontSize: 26, fontWeight: '700' },
  subtitle: { color: COLORS.muted, fontSize: 13, marginTop: 2 },
  card: { flexDirection: 'row', backgroundColor: COLORS.card, borderRadius: 16, overflow: 'hidden' },
  image: { width: 120, height: 150 },
  info: { flex: 1, padding: 14, justifyContent: 'space-between' },
  brand: { color: COLORS.muted, fontSize: 10, letterSpacing: 1.2, textTransform: 'uppercase' },
  name: { color: '#fff', fontSize: 15, fontWeight: '600', marginTop: 2 },
  price: { color: COLORS.purple, fontSize: 16, fontWeight: '700' },
  tagsRow: { flexDirection: 'row', gap: 6, flexWrap: 'wrap' },
  tag: { backgroundColor: '#1f1f1f', borderRadius: 20, paddingHorizontal: 10, paddingVertical: 3 },
  tagText: { color: COLORS.muted, fontSize: 11 },
  buyBtn: { backgroundColor: COLORS.purple, borderRadius: 10, paddingVertical: 8, alignItems: 'center', marginTop: 4 },
  buyBtnText: { color: '#fff', fontSize: 13, fontWeight: '700' },
  removeBtn: { position: 'absolute', top: 10, right: 10 },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 40 },
  emptyTitle: { color: '#fff', fontSize: 20, fontWeight: '700', marginTop: 16 },
  emptySubtitle: { color: COLORS.muted, fontSize: 14, textAlign: 'center', marginTop: 8, lineHeight: 22 },
});
