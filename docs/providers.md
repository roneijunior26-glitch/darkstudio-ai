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

## Checklist da Fase 0

- [ ] FLUX: neurons reais por imagem 1024×576 e 1920×1080
- [ ] Gemini: limites reais de texto com a chave criada (sem billing)
- [ ] Piper e Kokoro em pt-BR: qualidade e licença da voz
- [ ] FFmpeg em runner do GitHub: tempo para renderizar 10 min em 1080p
- [ ] Corte rápido (`-c copy`) e envio ao Google Drive
- [ ] Disparo do workflow por agendador gratuito ou botão

## Política de custo

FREE habilitado; OPTIONAL só com autorização explícita; PAID bloqueado. Ver `backend/app/providers/cost_guard.py`.
