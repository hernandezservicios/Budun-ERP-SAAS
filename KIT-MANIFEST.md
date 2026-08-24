# KIT MANIFEST

Este kit está preparado para **Antigravity como IDE + Claude como agente principal**.

## Componentes
- `CLAUDE.md` — reglas principales de Claude.
- `AGENTS.md` — orientación de workspace.
- `docs/MASTER-PROMPT.md` — especificación maestra.
- `docs/phases/PHASES.md` — 25 fases.
- `docs/phases/PHASE-00...PHASE-24...` — detalle de cada fase.
- `.claude/skills/` — skills del agente.
- `.claude/agents/` — revisores.
- `docs/setup/` — configuración paso a paso de PostgreSQL/pgAdmin 4 e integraciones.
- `docs/adr/` — decisiones arquitectónicas.
- `docs/project-status/` — estado persistente del proyecto.
- `scripts/` — utilidades de Windows para diagnóstico, inicio y tests.

## Política incremental
Claude debe agregar al proyecto real solamente lo necesario para la fase activa. No debe construir por adelantado todo el ERP.
