import AsyncStorage from '@react-native-async-storage/async-storage';
import { PRODUCTS } from '../data/products';

const PROFILE_KEY = 'fitfeed_profile';

const defaultProfile = () => ({
  interactions: 0,
  scores: { tags: {}, colors: {}, categories: {}, brands: {}, price_ranges: {} },
  wishlist: [],
  seen: [],
});

export const getProfile = async () => {
  try {
    const data = await AsyncStorage.getItem(PROFILE_KEY);
    return data ? JSON.parse(data) : defaultProfile();
  } catch {
    return defaultProfile();
  }
};

const saveProfile = async (profile) => {
  try {
    await AsyncStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
  } catch (e) {
    console.warn('Erro ao salvar perfil', e);
  }
};

export const recordInteraction = async (product, type) => {
  const profile = await getProfile();
  // like=+2, save=+4, skip=-1
  const delta = type === 'save' ? 4 : type === 'like' ? 2 : -1;

  product.style_tags.forEach(tag => {
    profile.scores.tags[tag] = (profile.scores.tags[tag] || 0) + delta;
  });
  product.colors.forEach(color => {
    profile.scores.colors[color] = (profile.scores.colors[color] || 0) + delta;
  });
  profile.scores.categories[product.category] =
    (profile.scores.categories[product.category] || 0) + delta;
  profile.scores.brands[product.brand] =
    (profile.scores.brands[product.brand] || 0) + delta;
  profile.scores.price_ranges[product.price_range] =
    (profile.scores.price_ranges[product.price_range] || 0) + delta;

  if (!profile.seen.includes(product.id)) profile.seen.push(product.id);
  if (type === 'save' && !profile.wishlist.includes(product.id)) {
    profile.wishlist.push(product.id);
  }
  profile.interactions += 1;
  await saveProfile(profile);
  return profile;
};

const scoreProduct = (product, scores) => {
  let score = 0;
  product.style_tags.forEach(t => { score += scores.tags[t] || 0; });
  product.colors.forEach(c => { score += scores.colors[c] || 0; });
  score += scores.categories[product.category] || 0;
  score += scores.brands[product.brand] || 0;
  score += scores.price_ranges[product.price_range] || 0;
  return score;
};

export const getNextProducts = async (count = 20) => {
  const profile = await getProfile();
  const unseen = PRODUCTS.filter(p => !profile.seen.includes(p.id));
  const pool = unseen.length >= count ? unseen : PRODUCTS; // reset pool if exhausted

  if (profile.interactions < 20) {
    // Cold start: pure random
    return [...pool].sort(() => Math.random() - 0.5).slice(0, count);
  }

  // Weighted random: score + 20% noise to allow discovery
  const scored = pool.map(p => ({
    ...p,
    _score: scoreProduct(p, profile.scores) + Math.random() * 3,
  }));
  return scored.sort((a, b) => b._score - a._score).slice(0, count);
};

export const getWishlist = async () => {
  const profile = await getProfile();
  return PRODUCTS.filter(p => profile.wishlist.includes(p.id));
};

export const removeFromWishlist = async (productId) => {
  const profile = await getProfile();
  profile.wishlist = profile.wishlist.filter(id => id !== productId);
  await saveProfile(profile);
};

export const resetProfile = async () => {
  await AsyncStorage.removeItem(PROFILE_KEY);
};

export const getTopStyles = (profile, topN = 3) => {
  const tags = profile.scores.tags;
  return Object.entries(tags)
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, topN)
    .map(([tag]) => tag);
};

export const getTopCategories = (profile) => {
  const cats = profile.scores.categories;
  const total = Object.values(cats).reduce((s, v) => s + Math.max(v, 0), 0) || 1;
  return Object.entries(cats)
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([cat, val]) => ({ cat, pct: Math.round((val / total) * 100) }));
};
