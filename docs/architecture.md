# Arquitetura

Fonte completa do planejamento: documento "DarkStudio AI — Arquitetura, viabilidade e plano de execução" (Claude Docs). Este arquivo resume as decisões em vigor.

## Decisões (12/11/2026)

| Decisão | Valor |
|---|---|
| Orçamento | R$ 0, sem cartão de crédito |
| Frontend | React + TypeScript + Tailwind, Cloudflare Pages |
| Controle (control plane) | Supabase (Auth + Postgres com RLS); o frontend fala direto com ele |
| Processamento (processing plane) | Worker Python executado sob demanda no GitHub Actions |
| Fila | Tabela `tasks` no Postgres (`FOR UPDATE SKIP LOCKED`) |
| Imagem | Cloudflare Workers AI (FLUX), plano Free |
| Texto | Gemini API, plano gratuito, sem billing |
| Voz | Piper TTS (a validar licença das vozes pt-BR; alternativa Kokoro) |
| Mídia | Supabase Storage (leve) + Google Drive do usuário (MP4 final) |
| YouTube | Upload privado e publicação manual no YouTube Studio |
| Repositório | Público: nenhum segredo, `.env` ou mídia é versionado |

## Princípios

- **Tudo é tarefa.** O frontend só insere linhas em `tasks`; o worker as consome.
- **Reconstrução incremental.** Cada artefato tem `input_hash`; só o que mudou é refeito (`backend/app/pipeline/hashing.py`).
- **Guarda de custo antes de cada chamada** (`backend/app/providers/cost_guard.py`). PAID e OPTIONAL só com autorização explícita; cota desconhecida nunca vale como ilimitada.
- **Modo degradado.** Sem worker, a interface continua; a fila só anda quando o workflow é disparado.

## Implementado x planejado

| Item | Estado |
|---|---|
| Migration inicial com RLS (`backend/migrations/0001_init.sql`) | Escrita. **Ainda não aplicada a um Postgres**: validar no Supabase |
| Contrato de fornecedores e guarda de custo | Implementado e testado |
| `input_hash` e propagação de reconstrução | Implementado e testado |
| Estados, backoff e fila (RPC `claim_task` / `reclaim_stuck_tasks`, migration 0004) | Implementado e testado com banco simulado; a reserva real roda no Supabase do usuário |
| Varredura de segredos + CI | Implementado; CI verde no GitHub |
| Frontend sem build (login, canais, nichos, vozes, projetos, progresso, cenas com miniaturas) | Implementado; publicado no GitHub Pages |
| Worker: `split_scenes` (Gemini), `generate_image` (FLUX), `generate_audio` (Gemini TTS / Kokoro), `render_final` (FFmpeg) | Implementado; testado com serviços simulados e FFmpeg real; **ainda não validado de ponta a ponta com um vídeo real** |
| Workflow do worker (agendado a cada 5 min + manual) | Implementado; entrega o MP4 como artifact por 7 dias |
| Entrega no Google Drive | Planejado (precisa do OAuth do usuário) |
| Miniatura, SEO, editor de cortes do MP4, upload no YouTube | Planejado |
| Skills do Claude Code (`.claude/skills/`) | Planejado |

## Limitações dos serviços gratuitos

Ver `docs/providers.md`.
