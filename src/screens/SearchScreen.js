import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, FlatList, Image, TouchableOpacity,
  TextInput, ScrollView, SafeAreaView, StatusBar, Modal,
} from 'react-native';
import { PRODUCTS } from '../data/products';
import { recordInteraction } from '../utils/algorithm';

const COLORS = { bg: '#0a0a0a', purple: '#a78bfa', card: '#131313', text: '#fff', muted: '#666' };
const CATEGORIES = ['todos', 'vestido', 'calça', 'saia', 'top', 'blazer', 'casaco', 'conjunto', 'bermuda', 'short'];
const STYLES_F = ['casual', 'boho', 'minimalista', 'streetwear', 'elegante', 'romântico', 'vintage', 'preppy', 'gótico', 'esportivo'];

export default function SearchScreen() {
  const [query, setQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState('todos');
  const [activeStyle, setActiveStyle] = useState('');
  const [filtered, setFiltered] = useState(PRODUCTS);
  const [selectedProduct, setSelectedProduct] = useState(null);

  useEffect(() => {
    let result = PRODUCTS;

    if (query.trim()) {
      const q = query.toLowerCase();
      result = result.filter(p =>
        p.name.toLowerCase().includes(q) ||
        p.brand.toLowerCase().includes(q) ||
        p.style_tags.some(t => t.includes(q))
      );
    }
    if (activeCategory !== 'todos') {
      result = result.filter(p => p.category === activeCategory);
    }
    if (activeStyle) {
      result = result.filter(p => p.style_tags.includes(activeStyle));
    }
    setFiltered(result);
  }, [query, activeCategory, activeStyle]);

  const renderProduct = ({ item }) => (
    <TouchableOpacity style={s.gridCard} onPress={() => setSelectedProduct(item)}>
      <Image source={{ uri: item.image }} style={s.gridImage} />
      <LinearFallback />
      <View style={s.cardInfo}>
        <Text style={s.cardBrand}>{item.brand}</Text>
        <Text style={s.cardName} numberOfLines={1}>{item.name}</Text>
        <Text style={s.cardPrice}>R$ {item.price.toFixed(2)}</Text>
      </View>
    </TouchableOpacity>
  );

  return (
    <View style={s.container}>
      <StatusBar barStyle="light-content" backgroundColor={COLORS.bg} />
      <SafeAreaView>
        <View style={s.searchBar}>
          <Text style={{ color: COLORS.muted, fontSize: 16, marginRight: 8 }}>🔍</Text>
          <TextInput
            style={s.input}
            placeholder="Buscar peças, marcas ou estilos..."
            placeholderTextColor={COLORS.muted}
            value={query}
            onChangeText={setQuery}
          />
          {query.length > 0 && (
            <TouchableOpacity onPress={() => setQuery('')}>
              <Text style={{ color: COLORS.muted, fontSize: 14 }}>✕</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Category filter */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.filterRow} contentContainerStyle={{ paddingHorizontal: 16, gap: 8 }}>
          {CATEGORIES.map(cat => (
            <TouchableOpacity
              key={cat}
              onPress={() => setActiveCategory(cat)}
              style={[s.filterChip, activeCategory === cat && s.filterChipActive]}
            >
              <Text style={[s.filterChipText, activeCategory === cat && s.filterChipTextActive]}>
                {cat}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {/* Style filter */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.filterRow2} contentContainerStyle={{ paddingHorizontal: 16, gap: 8 }}>
          <TouchableOpacity
            onPress={() => setActiveStyle('')}
            style={[s.styleChip, !activeStyle && s.styleChipActive]}
          >
            <Text style={[s.styleText, !activeStyle && { color: '#fff' }]}>✦ todos estilos</Text>
          </TouchableOpacity>
          {STYLES_F.map(st => (
            <TouchableOpacity
              key={st}
              onPress={() => setActiveStyle(st === activeStyle ? '' : st)}
              style={[s.styleChip, activeStyle === st && s.styleChipActive]}
            >
              <Text style={[s.styleText, activeStyle === st && { color: '#fff' }]}>{st}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      </SafeAreaView>

      <Text style={s.resultCount}>{filtered.length} peças encontradas</Text>

      <FlatList
        data={filtered}
        keyExtractor={item => item.id}
        numColumns={2}
        renderItem={renderProduct}
        contentContainerStyle={{ padding: 12, gap: 12 }}
        columnWrapperStyle={{ gap: 12 }}
        ListEmptyComponent={
          <View style={{ alignItems: 'center', paddingTop: 60 }}>
            <Text style={{ fontSize: 36 }}>🧺</Text>
            <Text style={{ color: COLORS.muted, marginTop: 12 }}>Nenhuma peça encontrada</Text>
          </View>
        }
      />

      {/* Product modal */}
      {selectedProduct && (
        <Modal transparent animationType="slide" visible={true} onRequestClose={() => setSelectedProduct(null)}>
          <View style={s.modalOverlay}>
            <View style={s.modalCard}>
              <TouchableOpacity style={s.modalClose} onPress={() => setSelectedProduct(null)}>
                <Text style={{ color: COLORS.muted }}>✕ fechar</Text>
              </TouchableOpacity>
              <Image source={{ uri: selectedProduct.image }} style={s.modalImage} />
              <ScrollView style={{ padding: 20 }}>
                <Text style={s.modalBrand}>{selectedProduct.brand}  ·  {selectedProduct.gender}</Text>
                <Text style={s.modalName}>{selectedProduct.name}</Text>
                <Text style={s.modalPrice}>R$ {selectedProduct.price.toFixed(2)}</Text>
                <Text style={s.modalDesc}>{selectedProduct.description}</Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 12 }}>
                  {selectedProduct.style_tags.map(t => (
                    <View key={t} style={s.modalTag}>
                      <Text style={s.modalTagText}>{t}</Text>
                    </View>
                  ))}
                </View>
                <TouchableOpacity
                  style={[s.buyBtn, { marginTop: 24 }]}
                  onPress={async () => {
                    await recordInteraction(selectedProduct, 'like');
                    setSelectedProduct(null);
                  }}
                >
                  <Text style={s.buyBtnText}>❤️  Curtir esta peça</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.saveBtn, { marginTop: 12, marginBottom: 24 }]}
                  onPress={async () => {
                    await recordInteraction(selectedProduct, 'save');
                    setSelectedProduct(null);
                  }}
                >
                  <Text style={s.saveBtnText}>🔖  Salvar nos favoritos</Text>
                </TouchableOpacity>
              </ScrollView>
            </View>
          </View>
        </Modal>
      )}
    </View>
  );
}

// Simple color fallback for grid cards
const LinearFallback = () => null;

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bg },
  searchBar: { flexDirection: 'row', alignItems: 'center', marginHorizontal: 16, marginTop: 12, backgroundColor: '#1a1a1a', borderRadius: 12, paddingHorizontal: 14, paddingVertical: 10, borderWidth: 1, borderColor: '#222' },
  input: { flex: 1, color: '#fff', fontSize: 15 },
  filterRow: { marginTop: 12 },
  filterRow2: { marginTop: 8, marginBottom: 4 },
  filterChip: { paddingHorizontal: 14, paddingVertical: 7, borderRadius: 20, backgroundColor: '#1a1a1a', borderWidth: 1, borderColor: '#2a2a2a' },
  filterChipActive: { backgroundColor: COLORS.purple, borderColor: COLORS.purple },
  filterChipText: { color: COLORS.muted, fontSize: 13, textTransform: 'capitalize' },
  filterChipTextActive: { color: '#fff', fontWeight: '600' },
  styleChip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20, backgroundColor: 'transparent', borderWidth: 1, borderColor: '#a78bfa44' },
  styleChipActive: { backgroundColor: '#a78bfa33', borderColor: COLORS.purple },
  styleText: { color: '#a78bfa', fontSize: 12 },
  resultCount: { color: COLORS.muted, fontSize: 12, marginHorizontal: 16, marginVertical: 8 },
  gridCard: { flex: 1, backgroundColor: COLORS.card, borderRadius: 14, overflow: 'hidden' },
  gridImage: { width: '100%', height: 200 },
  cardInfo: { padding: 10 },
  cardBrand: { color: COLORS.muted, fontSize: 10, letterSpacing: 1, textTransform: 'uppercase' },
  cardName: { color: '#fff', fontSize: 13, fontWeight: '600', marginTop: 2 },
  cardPrice: { color: COLORS.purple, fontSize: 13, fontWeight: '600', marginTop: 4 },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'flex-end' },
  modalCard: { backgroundColor: '#111', borderTopLeftRadius: 24, borderTopRightRadius: 24, maxHeight: '88%' },
  modalClose: { padding: 16, alignItems: 'flex-end' },
  modalImage: { width: '100%', height: 280 },
  modalBrand: { color: COLORS.muted, fontSize: 11, letterSpacing: 1.5, textTransform: 'uppercase', marginBottom: 4 },
  modalName: { color: '#fff', fontSize: 22, fontWeight: '700', marginBottom: 4 },
  modalPrice: { color: COLORS.purple, fontSize: 20, fontWeight: '700', marginBottom: 12 },
  modalDesc: { color: '#aaa', fontSize: 14, lineHeight: 22 },
  modalTag: { backgroundColor: '#1a1a1a', borderRadius: 20, paddingHorizontal: 12, paddingVertical: 4 },
  modalTagText: { color: '#888', fontSize: 12 },
  buyBtn: { backgroundColor: COLORS.purple, borderRadius: 14, paddingVertical: 16, alignItems: 'center' },
  buyBtnText: { color: '#fff', fontSize: 16, fontWeight: '700' },
  saveBtn: { borderWidth: 1, borderColor: '#333', borderRadius: 14, paddingVertical: 14, alignItems: 'center' },
  saveBtnText: { color: '#aaa', fontSize: 15 },
});
