# Fornecedores e limites gratuitos

Pesquisa de 12/11/2026. Limites mudam; tudo marcado "a validar" precisa de teste real (Fase 0).

| Serviço | Uso | Limite gratuito conhecido | Estado |
|---|---|---|---|
| Cloudflare Pages / Workers | Frontend e gatilhos | Sem cartão; acima da cota a requisição falha, sem cobrança | OK |
| Supabase | Auth, Postgres, Storage leve | 2 projetos, 500 MB de banco, 1 GB de storage, pausa após 7 dias sem uso | OK para metadados |
| Cloudflare Workers AI (FLUX) | Imagens | 10.000 neurons/dia; ~170 imagens 1024×1024/dia (fonte de terceiros) | A validar |
| Gemini API | Divisão em cenas, prompts, SEO | Modelos de texto gratuitos com limites baixos; imagem e vídeo, pagos | A validar com a chave |
| Piper TTS | Narração | Motor GPL-3.0; licença de cada voz varia, algumas só não comercial | Auditar a voz pt-BR |
| GitHub Actions | Worker sob demanda | Repositório público: minutos ilimitados; job até 6 h | A medir (render 10 min) |
| Google Drive (API) | MP4 final | 15 GB na conta do usuário | A validar |
| YouTube Data API | Upload | Projeto não auditado: uploads ficam privados | Fluxo: privado + publicação manual |
| Oracle, Koyeb, Hugging Face (Docker), Render | Hospedagem | Exigem cartão ou plano pago | Descartados |
| Vídeo por IA (Wan, LTX, etc.) | Clipes opcionais | Sem API gratuita confiável | Desligado por padrão |

## Resultados da Fase 0 (12/11/2026)

- **FFmpeg** (runner ubuntu, 4 núcleos, 16 GB): 75 cenas de 8 s em 1080p30 com zoompan renderizam em ~7,4 min (5,9 s/cena); concat 9 s; mux 13 s; corte rápido `-c copy` 0,24 s; corte preciso 7,7 s; `xfade` funciona (12 s por par). Tamanho do arquivo não medido (imagem sintética com ruído).
- **Piper pt-BR**: ~0,13 s de processamento por segundo de áudio. Vozes `faber`, `cadu`, `jeff` (medium) são CC0; `edresson` (low) é CC BY 4.0. Falta escolher a voz ouvindo as amostras.
- **Gemini** (plano grátis): `gemini-3.5-flash-lite` divide roteiro em JSON válido (~3 s); rajada de 12 chamadas sem 429; `gemini-2.5-flash-lite` não aceita usuários novos (nome do modelo deve ser configurável); modelos de imagem retornam 429 (cota zero no grátis); 503 ocasional exige retry.
- **FLUX** (token com permissão Workers AI): 3 imagens JPEG de 290–360 KB, ~2,9 s cada. Capacidade diária real ainda não medida.

## Checklist da Fase 0

- [x] FFmpeg em runner do GitHub: tempo para renderizar 10 min em 1080p
- [x] Corte rápido (`-c copy`) e corte preciso
- [x] Gemini: texto, JSON de cenas e limite de taxa
- [x] Piper pt-BR: velocidade e licença das vozes
- [ ] Piper: escolher a voz ouvindo as amostras
- [ ] FLUX: qualidade visual e capacidade diária real (teste "drain")
- [ ] Envio do MP4 ao Google Drive (precisa do OAuth)
- [ ] Disparo do workflow por agendador gratuito ou botão

## Política de custo

FREE habilitado; OPTIONAL só com autorização explícita; PAID bloqueado. Ver `backend/app/providers/cost_guard.py`.
