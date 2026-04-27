# 👗 FitFeed — TikTok de roupas com algoritmo de gosto

App mobile estilo Reels/TikTok para descoberta de roupas com algoritmo que aprende seu gosto ao longo do tempo.

---

## 🚀 Como rodar — Opção 1: Expo Snack (MAIS FÁCIL, sem instalar nada)

1. Acesse **https://snack.expo.dev**
2. Crie uma conta gratuita (ou entre com Google/GitHub)
3. Clique em **"Add file"** e crie a estrutura abaixo colando cada arquivo
4. Instale as dependências no painel da direita em **"Add package"**:
   - `@react-native-async-storage/async-storage`
   - `@react-navigation/native`
   - `@react-navigation/bottom-tabs`
   - `expo-linear-gradient`
   - `react-native-screens`
   - `react-native-safe-area-context`
   - `react-native-gesture-handler`
5. Escaneie o QR Code com o app **Expo Go** (disponível na App Store e Play Store)

### Estrutura de arquivos no Snack:
```
App.js                          ← arquivo principal
src/
  data/
    products.js                 ← 30 produtos seed
  utils/
    algorithm.js                ← motor de aprendizado de gosto
  screens/
    FeedScreen.js               ← feed de swipe (tela principal)
    SearchScreen.js             ← busca e filtros
    WishlistScreen.js           ← peças salvas
    ProfileScreen.js            ← perfil e DNA de estilo
```

---

## 🖥️ Como rodar — Opção 2: Local com Node.js

### Pré-requisitos
- Node.js 18+ instalado
- App **Expo Go** no celular (iOS ou Android)

### Passo a passo

```bash
# 1. Entre na pasta do projeto
cd fitfeed

# 2. Instale as dependências
npm install

# 3. Inicie o servidor
npx expo start

# 4. Escaneie o QR Code com o app Expo Go no celular
```

---

## ✨ Funcionalidades

### 📱 Feed (tela principal)
- Cards full-screen com foto, nome, marca e preço da peça
- **Swipe direita / botão ❤️** → curtir (sinal positivo para o algoritmo)
- **Swipe esquerda / botão ✕** → passar (sinal negativo)
- **Botão 🔖** → salvar nos favoritos
- **Swipe para cima** → ver detalhes completos da peça
- Overlay animado "CURTIU" e "PASSOU" durante o swipe
- Barra de progresso de aprendizado no topo

### 🧠 Algoritmo de gosto
- **0–20 interações**: feed completamente aleatório (fase de exploração)
- **20+ interações**: cada produto recebe um score baseado nos seus likes/skips
- Score calcula: tags de estilo, cores, categoria, marca e faixa de preço
- 80% por score + 20% aleatório (para continuar descobrindo)
- Toast de feedback a cada 10 interações

### 🔍 Busca
- Busca por texto (nome, marca, tag)
- Filtros por categoria (vestido, calça, saia, blazer...)
- Filtros por estilo (casual, boho, streetwear, elegante...)
- Grid 2 colunas com modal de detalhes

### 🔖 Salvos
- Lista de peças salvas
- Botão de compra e remoção
- Estado vazio ilustrado

### 👤 Perfil / DNA de Estilo
- Contador de interações e peças salvas
- Barra de progresso de calibração (0–50 interações)
- Estilos favoritos com ranking visual
- Gráfico de barras por categoria
- Marcas preferidas
- Botão para resetar o perfil

---

## 🎨 Design
- Tema 100% dark (`#0a0a0a`)
- Cor de destaque: **roxo** `#a78bfa`
- Cards full-screen imersivos
- Animações com spring physics nativas do React Native

---

## 📦 Stack
- **React Native** + **Expo SDK 50**
- **AsyncStorage** — persiste o perfil de gosto localmente
- **React Navigation** — navegação por abas
- **expo-linear-gradient** — gradientes nos cards
