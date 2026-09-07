# Valores de Referencia — Algoritmo de Proyección

Generado: 2026-03-07

Algoritmo: `pago_min_dinamico = max(pago_minimo_original, saldo_actual * ratio)`
donde `ratio = pago_minimo / saldo` del documento original.

---

## Gastón — Noviembre 2025 (3 tarjetas)

| Tarjeta | Saldo | TCEA | Pago Mín | Ratio | Interés/mes | Cubre? |
|---------|-------|------|----------|-------|-------------|--------|
| Tiendas Orvia *4471 | S/ 7,200 | 92% | S/ 720 | 10.0% | S/ 402 | SI |
| Tiendas Delsu *8832 | S/ 6,800 | 85% | S/ 680 | 10.0% | S/ 358 | SI |
| Banco Marena *3156 | S/ 5,500 | 45% | S/ 455 | 8.3% | S/ 173 | SI |

- Deuda total: S/ 19,500
- **Pagando mínimos: 16 meses, S/ 27,771 (+42%)**
- Pagando período: 7 meses, S/ 22,555, ahorro S/ 5,216

## Gastón — Diciembre 2025

| Tarjeta | Saldo | TCEA | Pago Mín | Ratio |
|---------|-------|------|----------|-------|
| Tiendas Orvia | S/ 5,400 | 92% | S/ 540 | 10.0% |
| Tiendas Delsu | S/ 6,600 | 85% | S/ 660 | 10.0% |
| Banco Marena | S/ 5,350 | 45% | S/ 535 | 10.0% |

- Deuda total: S/ 17,350
- **Pagando mínimos: 16 meses, S/ 24,267 (+40%)**

## Gastón — Enero 2026

| Tarjeta | Saldo | TCEA | Pago Mín | Ratio |
|---------|-------|------|----------|-------|
| Tiendas Orvia | S/ 3,500 | 92% | S/ 350 | 10.0% |
| Tiendas Delsu | S/ 6,400 | 85% | S/ 640 | 10.0% |
| Banco Marena | S/ 5,200 | 45% | S/ 520 | 10.0% |

- Deuda total: S/ 15,100
- **Pagando mínimos: 16 meses, S/ 20,933 (+39%)**

## Gastón — Febrero 2026

| Tarjeta | Saldo | TCEA | Pago Mín | Ratio |
|---------|-------|------|----------|-------|
| Tiendas Orvia | S/ 1,800 | 92% | S/ 180 | 10.0% |
| Tiendas Delsu | S/ 6,100 | 85% | S/ 610 | 10.0% |
| Banco Marena | S/ 5,000 | 45% | S/ 500 | 10.0% |

- Deuda total: S/ 12,900
- **Pagando mínimos: 16 meses, S/ 17,694 (+37%)**

---

## Carolina (3 tarjetas)

| Tarjeta | Saldo | TCEA | Pago Mín | Ratio | Interés/mes | Cubre? |
|---------|-------|------|----------|-------|-------------|--------|
| Tiendas Orvia | S/ 4,500 | 98% | S/ 466 | 10.4% | S/ 264 | SI |
| Tiendas Delsu | S/ 5,500 | 95% | S/ 557 | 10.1% | S/ 315 | SI |
| Banco Vantia | S/ 8,000 | 48% | S/ 680 | 8.5% | S/ 266 | SI |

- Deuda total: S/ 18,000
- **Pagando mínimos: 16 meses, S/ 25,478 (+42%)**
- Pagando período: 5 meses, S/ 20,024, ahorro S/ 5,454

---

## Miguel (2 tarjetas)

| Tarjeta | Saldo | TCEA | Pago Mín | Ratio | Interés/mes | Cubre? |
|---------|-------|------|----------|-------|-------------|--------|
| Banco Nordika | S/ 12,000 | 52% | S/ 605 | 5.0% | S/ 426 | SI |
| Banco Marena | S/ 7,000 | 58% | S/ 579 | 8.3% | S/ 272 | SI |

- Deuda total: S/ 19,000
- **Pagando mínimos: 35 meses, S/ 30,765 (+62%)**
- Pagando período: 7 meses, S/ 21,500, ahorro S/ 9,266

Nota: Banco Nordika de Miguel tiene el ratio más bajo (5.0%) pero aún cubre el interés mensual (3.5%).

---

## Resumen comparativo

| Usuario | Deuda | Mínimos (meses) | Costo total | Sobrecosto | Edge case |
|---------|-------|-----------------|-------------|------------|-----------|
| Gastón Nov | S/ 19,500 | 16 | S/ 27,771 | +42% | No |
| Gastón Dic | S/ 17,350 | 16 | S/ 24,267 | +40% | No |
| Gastón Ene | S/ 15,100 | 16 | S/ 20,933 | +39% | No |
| Gastón Feb | S/ 12,900 | 16 | S/ 17,694 | +37% | No |
| Carolina | S/ 18,000 | 16 | S/ 25,478 | +42% | No |
| Miguel | S/ 19,000 | 35 | S/ 30,765 | +62% | Banco Nordika ratio 5% (límite) |
