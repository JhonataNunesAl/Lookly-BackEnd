Documento de Requisitos de Projeto - App de Moda (Estilo Tinder)

Este documento lista todos os requisitos e definições estruturais essenciais que devem ser estabelecidos antes da distribuição das tarefas para a equipe de desenvolvimento e design.

1. Definição do Produto e Negócios (Business Requirements)
Antes de escrever qualquer código, a visão do produto precisa estar clara.

Público-Alvo e Persona: Quem são os usuários ideais? (Ex: Jovens da geração Z e Millennials interessados em moda rápida e eventos).
Modelo de Monetização: Como o app vai gerar dinheiro? (Anúncios, parcerias com marcas/e-commerces, versão Premium sem anúncios, links de afiliados).
Fontes de Conteúdo: De onde virão as fotos dos looks inicialmente? (Curadoria interna, web scraping, parcerias com influenciadores ou conteúdo gerado pelos primeiros usuários).

2. Requisitos Funcionais (O que o app DEVE fazer)
Ações e funcionalidades que o sistema precisa ter para atender ao usuário.

Autenticação e Gestão de Usuários:
Cadastro e Login (Email/Senha, Google, Apple, Facebook).
Criação de perfil (Nome, foto, preferências básicas de estilo).
Feed Principal e Filtro de Categoria (Core Feature):
Exibição de "Cards" em tela cheia.
Filtro Rígido: Se o usuário selecionar uma categoria (ex: "Gótica"), ele verá apenas looks dessa categoria no feed.
Mecânica de Swipe: Deslizar para a direita (Curtir/Salvar) e deslizar para a esquerda (Descartar).
Botões de ação visíveis (Coração, Marcador, Compartilhar).
Estrutura do Look:
Obrigatório pertencer a uma Categoria.
Pode conter de 1 a 6 fotos e até 2 vídeos.
Provador Virtual com Inteligência Artificial (Diferencial):
No card do Look, haverá um botão para testar a roupa.
A IA vai mesclar a foto do Look com a foto de corpo inteiro (full_body_photo_url) e as medidas (body_measurements) salvas no perfil do usuário, gerando uma imagem realista de como a roupa ficaria nele.
Interação Social:
Funcionalidade de enviar um look para um amigo (via link externo pro WhatsApp/Instagram ou via chat interno).
Painel do Usuário (Armário/Salvos):
Galeria onde ficam salvos os looks curtidos.
Possibilidade de criar "Pastas" ou "Coleções" (Ex: "Looks para o Lollapalooza").

3. Requisitos Não Funcionais (Como o app DEVE se comportar)
Atributos de qualidade e performance do sistema.

Performance e Velocidade: O carregamento das imagens no feed deve ser quase instantâneo. É necessário o uso de cache no dispositivo e uma CDN (Content Delivery Network).
Usabilidade (UX): As animações de swipe devem rodar lisas (a 60 frames por segundo) para não frustrar o usuário.
Escalabilidade: O banco de dados deve estar preparado para receber milhares de requisições rápidas (cada swipe para direita ou esquerda é uma requisição ao servidor).
Plataformas: O app será disponibilizado para iOS, Android ou ambos?

4. Requisitos de Design e UX/UI (Entregáveis de Design)
O que a equipe de design precisa entregar antes do desenvolvimento começar.

Identidade Visual (Branding): Logo, paleta de cores, tipografia e tom de voz.
Wireframes: Desenhos estruturais (rascunhos) de todas as telas.
Protótipo de Alta Fidelidade: Telas finais interativas desenhadas no Figma (ou ferramenta similar).
Design System: Padronização de botões, ícones, margens e componentes para que os programadores possam reaproveitar código.
Fluxograma de Navegação (User Flow): Mapeamento do caminho que o usuário faz desde a tela inicial até completar uma ação (ex: achar um look de Carnaval e salvar numa pasta).

5. Arquitetura Técnica e Infraestrutura (Stack Definida)
Com base nas definições do projeto, a pilha de tecnologia (Tech Stack) será:

Front-end (App/Web): React (Sendo React Native para a versão mobile). Focado em criar uma interface reativa, rápida e fluida para a mecânica de swipe e carregamento de cards.
Back-end (API e Lógica): Python (Podendo utilizar frameworks rápidos como FastAPI ou robustos como Django). Será responsável pela lógica de negócios, filtros complexos e integrações.
Banco de Dados, Auth e Storage: Supabase. Servirá como o banco de dados relacional principal (PostgreSQL, excelente para queries complexas como "buscar looks da categoria Gótica que o usuário X ainda não curtiu"), e poderá gerenciar autenticação de usuários e armazenamento das fotos.
Algoritmo de Recomendação (Vantagem do Python): Como o back-end é em Python, o ecossistema é perfeito para, no futuro, criar algoritmos de Machine Learning (com Pandas, Scikit-Learn, etc.) que entendem os estilos favoritos do usuário e calibram o feed automaticamente.

6. Requisitos de Segurança e Legais
Termos de Uso e Política de Privacidade: Como os dados dos usuários serão utilizados.
Adequação à LGPD/GDPR: Permitir que o usuário delete sua conta e todos os seus dados facilmente.
Moderação de Conteúdo: Se os usuários puderem fazer upload de seus próprios looks, é obrigatório ter um sistema de denúncia de conteúdo inapropriado para que o app não seja banido da App Store/Google Play.
