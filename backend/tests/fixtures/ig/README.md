# Fixtures de posts do Instagram

Sintéticas (nenhum dado real foi coletado). Os testes as transformam em
`instaloader.Post` (4.15.4) e o coletor lê só a API pública de `Post`.

- `*.json` na raiz: node GraphQL anônimo, `Post(context, node)` (`__typename`,
  `shortcode`, `taken_at_timestamp`, `edge_media_to_caption`,
  `edge_sidecar_to_children`, `display_url`, `is_video`). Fixado =
  `pinned_for_users` não vazio (`Post.is_pinned`).
- `iphone/*.json`: dict de mídia da API iPhone, passado a
  `Post.from_iphone_struct` — é o formato que `Profile.get_posts()` produz com
  sessão logada (`code`, `taken_at`, `media_type`, `caption.text`,
  `image_versions2`, `carousel_media`, `video_versions`). Fixado =
  `timeline_pinned_user_ids` não vazio.
