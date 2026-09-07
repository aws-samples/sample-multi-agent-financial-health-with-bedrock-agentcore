# PDFs de prueba (datos 100% ficticios)

Estados de cuenta mock para probar el agente extractor y la demo completa.

> Todos los nombres de bancos, tiendas, comercios, titulares y DNIs son
> **inventados**. No aparece ninguna marca ni dato real. Los PDFs se generan
> con el script `demo/generate-statements.py` (fuente única de verdad); si
> necesitas regenerarlos, edita ese script y ejecútalo:
>
> ```bash
> python3 demo/generate-statements.py
> ```

## Caso Carolina (3 tarjetas)

Titular sintético: CAROLINA MENDOZA GARCÍA · DNI 12345678

| Archivo | Entidad (ficticia) | Tipo | Saldo | TCEA | Pago mínimo | Corte |
|---|---|---|---|---|---|---|
| `Carolina/estado-cuenta-banco-vantia-carolina.pdf` | Banco Vantia | Tarjeta bancaria clásica | S/ 8,000.00 | 48.00% | S/ 680.00 | 28/02/2026 |
| `Carolina/estado-cuenta-tiendas-orvia-carolina.pdf` | Tiendas Orvia | Tarjeta retail | S/ 4,500.00 | 98.00% | S/ 466.00 | 20/02/2026 |
| `Carolina/estado-cuenta-tiendas-delsu-carolina.pdf` | Tiendas Delsu | Tarjeta retail | S/ 5,500.00 | 95.00% | S/ 557.00 | 25/02/2026 |

Deuda total: **S/ 18,000** · Tarjeta más cara: Tiendas Orvia (TCEA 98%).

## Caso Miguel (2 tarjetas)

Titular sintético: MIGUEL TORRES RAMÍREZ · DNI 87654321

| Archivo | Entidad (ficticia) | Tipo | Saldo | TCEA | Pago mínimo | Corte |
|---|---|---|---|---|---|---|
| `Miguel/estado-cuenta-banco-nordika-miguel.pdf` | Banco Nordika | Tarjeta bancaria clásica | S/ 12,000.00 | 52.00% | S/ 605.00 | 15/02/2026 |
| `Miguel/estado-cuenta-banco-marena-miguel.pdf` | Banco Marena | Tarjeta bancaria gold | S/ 7,000.00 | 58.00% | S/ 579.00 | 20/02/2026 |

Deuda total: **S/ 19,000** · Tarjeta más cara: Banco Marena (TCEA 58%).

## Comercios en las transacciones

Todos ficticios, por ejemplo: Supermercado Nóvea, Entrega Ya, Pide Fácil,
Viaja App, Grifo Voltia, Café Aromé, Botica Vitalis, StreamFlix, MusicWave,
Cine Estelar, Market 24, Go Exprés, Gimnasio FitZone, entre otros.

## Uso

1. Testing del agente extractor (`test-e2e.sh`).
2. Testing manual y demo del proyecto.
