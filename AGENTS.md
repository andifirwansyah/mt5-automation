# AGENTS.md — AI Trading Automation

File ini adalah instruksi wajib untuk semua AI agent yang bekerja di project `ai-trading-automation`.

## Bahasa Kerja

Gunakan Bahasa Indonesia untuk analisis, planning, laporan, dan komunikasi teknis.
Gunakan Bahasa Inggris untuk nama class, function, variable, module, commit message teknis, dan istilah code-level yang lazim.

## Source of Truth

Sebelum bekerja, agent wajib membaca file berikut:

```txt
.ai/project-brief.md
.ai/project-map.md
.ai/docs/01-layer-flow-final.md
.ai/docs/02-feature-boundary.md
.ai/docs/03-architecture-overview.md
.ai/docs/04-data-contracts.md
.ai/docs/05-risk-and-safety-policy.md
.ai/task-list.md
```

## Aturan Keras

1. Jangan langsung coding sebelum membuat atau membaca task file.
2. Jangan membuat file random di root project.
3. Jangan menaruh logic fitur di `src/utils`, `src/helpers`, atau `src/common` jika logic itu hanya dipakai satu module.
4. Semua implementasi fitur wajib masuk ke module folder yang sesuai.
5. Semua perubahan shared/global wajib dijelaskan di implementation report.
6. Tidak boleh membuat live order execution sebelum paper execution, risk engine, dan execution gate stabil.
7. Tidak boleh mengklaim sistem profitable tanpa backtest, forward test, dan evidence.
8. Tidak boleh melakukan optimization yang mengarah ke overfitting tanpa catatan risiko.

## Struktur Code

Backend/engine utama berada di:

```txt
src/ai_trading_automation/
```

Module domain berada di:

```txt
src/ai_trading_automation/modules/{module_name}/
```

Test berada di:

```txt
tests/{module_name}/
```

## Mandatory Workflow

Setiap task wajib mengikuti urutan:

```txt
Requirement check
↓
Feature boundary check
↓
Implementation plan
↓
Coding
↓
Self review
↓
Test
↓
Implementation report
```

## Format Laporan Setelah Implementasi

Setelah implementasi, agent wajib menulis ringkasan:

```md
## Implementation Report

### Task

### File Dibuat

### File Diubah

### Shared/Global Changes

### Test yang Dijalankan

### Risiko / Catatan

### Next Step
```
