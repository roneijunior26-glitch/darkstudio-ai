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
| Migration inicial com RLS (`backend/migrations/0001_init.sql`) | Aplicada no Supabase; políticas de RLS testadas com 2 usuários (rls_check.sql) |
| Contrato de fornecedores e guarda de custo | Implementado e testado |
| `input_hash` e propagação de reconstrução | Implementado e testado |
| Estados, backoff e SQL de reserva da fila | Implementado; SQL conferido com a migration por teste, **ainda não executado** (o loop do worker virá com testes em Postgres) |
| Varredura de segredos + CI | Implementado (script testado); workflow ainda não rodou no GitHub |
| Frontend (login, dashboard, projetos) | Planejado (próximo passo da Fase 1) |
| Worker (loop de execução, adaptadores reais) | Planejado |
| Workflow do worker no Actions | Planejado |
| Skills do Claude Code (`.claude/skills/`) | Planejado |

## Limitações dos serviços gratuitos

Ver `docs/providers.md`.
