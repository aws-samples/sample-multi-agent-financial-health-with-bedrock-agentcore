#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Generador de estados de cuenta de DEMO.

Todos los nombres de bancos, comercios y establecimientos son FICTICIOS e
inventados para esta demo. No deben usarse marcas reales en ningún documento.
Los titulares y DNIs son sintéticos. Los montos/fechas se mantienen para que
los cálculos de referencia (demo/VALORES-REFERENCIA-CALCULO.md) sigan siendo
válidos.

Uso:
    python3 demo/generate-statements.py
Genera los PDFs en demo/pdfs/<Persona>/.
"""
import os
import sys

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_ROOT = os.path.join(HERE, "pdfs")

# Marcas reales que NUNCA deben aparecer en un documento de demo.
REAL_BRAND_DENYLIST = [
    "metro", "tottus", "plaza vea", "wong", "rappi", "pedidosya", "uber",
    "primax", "repsol", "shell", "starbucks", "juan valdez", "mifarma",
    "inkafarma", "farmacia universal", "netflix", "spotify", "amazon",
    "hbo max", "smart fit", "golds", "cineplanet", "oxxo", "tambo",
    "mcdonald", "kfc", "sodimac", "falabella", "ripley", "scotiabank",
    "bbva", "bcp", "banco andino", "banco continental", "banco del pac",
    "tiendas aurora", "tiendas del sol", "visa", "mastercard", "jockey",
    "larcomar", "real plaza", "mega plaza", "cmr",
]


# Cada estado de cuenta como dato estructurado. Todos los nombres son ficticios.
STATEMENTS = [
    {
        "out": "Carolina/estado-cuenta-banco-vantia-carolina.pdf",
        "issuer": "BANCO VANTIA",
        "slogan": "Tu progreso, primero",
        "card_type": "Tarjeta de Crédito Clásica",
        "holder_label": "Titular",
        "holder": "CAROLINA MENDOZA GARCÍA",
        "dni": "12345678",
        "card": "4532 **** **** 1234",
        "cut_label": "Fecha de Corte",
        "cut_date": "28/02/2026",
        "address": "Av. Los Cedros 1234, San Isidro",
        "ref": "VNT-2026-02-00847",
        "min_label": "PAGO MÍNIMO",
        "min_amount": "680.00",
        "period_amount": "1,841.40",
        "due": "15/03/2026",
        "summary_label": "SALDO TOTAL",
        "balance": "8,000.00",
        "credit_line": "15,000.00",
        "pending_installments": "3",
        "available": "7,000.00",
        "installments_total": "Total cuotas: S/ 1,240.00",
        "desglose": [
            ("Saldo anterior", "6,884.00"),
            ("(-) Pagos recibidos", "-320.00"),
            ("(+) Nuevas compras y consumos", "1,157.90"),
            ("(+) Intereses", "253.20"),
            ("(+) Comisiones y seguros", "24.90"),
            ("Nuevo saldo", "8,000.00"),
        ],
        "tx": [
            ("03/02/2026", "04/02/2026", "SUPERMERCADO NÓVEA - SAN ISIDRO", "-", "250.00"),
            ("05/02/2026", "05/02/2026", "ENTREGA YA*DELIVERY - LIMA", "-", "45.00"),
            ("06/02/2026", "06/02/2026", "GRIFO VOLTIA AV CENTRAL", "-", "120.00"),
            ("08/02/2026", "09/02/2026", "CAFÉ AROMÉ CENTRO PORTADA", "-", "20.50"),
            ("09/02/2026", "09/02/2026", "BOTICA VITALIS - MIRAFLORES", "-", "67.30"),
            ("10/02/2026", "10/02/2026", "PIDE FÁCIL*DELIVERY - LIMA", "-", "32.00"),
            ("12/02/2026", "12/02/2026", "VIAJA APP*TRIP - LIMA", "-", "15.50"),
            ("13/02/2026", "13/02/2026", "SELECTA ONLINE - DESPACHO", "-", "185.00"),
            ("14/02/2026", "14/02/2026", "ENTREGA YA*DELIVERY - LIMA", "-", "52.00"),
            ("15/02/2026", "15/02/2026", "STREAMFLIX.COM", "-", "44.90"),
            ("16/02/2026", "16/02/2026", "VIAJA APP*TRIP - LIMA", "-", "12.00"),
            ("18/02/2026", "18/02/2026", "PIDE FÁCIL*DELIVERY - LIMA", "-", "38.50"),
            ("19/02/2026", "19/02/2026", "CAFÉ AROMÉ PLAZA CENTRAL", "-", "18.50"),
            ("20/02/2026", "21/02/2026", "MARKET 24 MIRAFLORES", "-", "18.00"),
            ("21/02/2026", "21/02/2026", "MUSICWAVE PREMIUM", "-", "19.90"),
            ("22/02/2026", "22/02/2026", "GIMNASIO FITZONE - SAN BORJA", "1/12", "89.00"),
            ("23/02/2026", "23/02/2026", "ENTREGA YA*DELIVERY - LIMA", "-", "41.00"),
            ("25/02/2026", "25/02/2026", "CINE ESTELAR - SAN MIGUEL", "-", "56.00"),
            ("26/02/2026", "26/02/2026", "GO EXPRÉS ANGAMOS - MIRAFLORES", "-", "14.50"),
            ("27/02/2026", "27/02/2026", "VIAJA APP*TRIP - LIMA", "-", "18.30"),
        ],
        "tasas": ("48.00%", "39.29%", "2.80%", "12.40"),
        "footer": ("Banco Vantia S.A. — RUC 20100000001. Av. Central 3456, San Isidro, Lima. "
                   "Central telefónica: (01) 311-0000. Línea gratuita: 0800-00-123. Regulado por la "
                   "Superintendencia de Banca, Seguros y AFP (SBS). Este documento es informativo. "
                   "Ante cualquier discrepancia, prevalecen los registros del banco."),
    },
    {
        "out": "Carolina/estado-cuenta-tiendas-orvia-carolina.pdf",
        "issuer": "TIENDAS ORVIA",
        "slogan": "Vive a tu manera",
        "card_type": "Tarjeta Orvia",
        "holder_label": "Titular",
        "holder": "CAROLINA MENDOZA GARCÍA",
        "dni": "12345678",
        "card": "5489 **** **** 9012",
        "cut_label": "Fecha de Cierre",
        "cut_date": "20/02/2026",
        "address": "Av. Los Cedros 1234, San Isidro",
        "ref": "ORV-2026-02-00391",
        "min_label": "MONTO MÍNIMO A PAGAR",
        "min_amount": "466.00",
        "period_amount": "1,546.50",
        "due": "08/03/2026",
        "summary_label": "DEUDA TOTAL",
        "balance": "4,500.00",
        "credit_line": "6,500.00",
        "pending_installments": "1",
        "available": "2,000.00",
        "installments_total": "Total cuotas: S/ 245.00",
        "desglose": [
            ("Saldo anterior", "2,793.56"),
            ("(-) Pagos recibidos", "-180.00"),
            ("(+) Nuevas compras y consumos", "1,697.90"),
            ("(+) Intereses", "163.64"),
            ("(+) Comisiones y seguros", "24.90"),
            ("Nuevo saldo", "4,500.00"),
        ],
        "tx": [
            ("02/02/2026", "03/02/2026", "TIENDAS ORVIA - PLAZA CENTRAL", "-", "380.00"),
            ("04/02/2026", "04/02/2026", "BURGER NÓVA MIRAFLORES", "-", "25.00"),
            ("06/02/2026", "06/02/2026", "TIENDAS ORVIA ONLINE", "2/6", "520.00"),
            ("08/02/2026", "08/02/2026", "POLLO KRUNCH*DELIVERY - LIMA", "-", "28.00"),
            ("10/02/2026", "10/02/2026", "VIAJA APP*TRIP - LIMA", "-", "10.00"),
            ("11/02/2026", "11/02/2026", "ENTREGA YA*DELIVERY - LIMA", "-", "47.00"),
            ("13/02/2026", "13/02/2026", "CINE ESTELAR PLAZA CENTRAL", "-", "62.00"),
            ("14/02/2026", "14/02/2026", "CAFÉ AROMÉ SAN BORJA", "-", "19.50"),
            ("16/02/2026", "16/02/2026", "PIDE FÁCIL*DELIVERY - LIMA", "-", "39.00"),
            ("17/02/2026", "17/02/2026", "MARKET 24 ANGAMOS", "-", "15.00"),
            ("19/02/2026", "19/02/2026", "MODA URBANA MIRAFLORES", "-", "180.00"),
            ("20/02/2026", "20/02/2026", "CAFÉ MERIDIA - SAN ISIDRO", "-", "16.00"),
            ("22/02/2026", "22/02/2026", "ENTREGA YA*DELIVERY - LIMA", "-", "36.00"),
            ("23/02/2026", "23/02/2026", "VIAJA APP*TRIP - LIMA", "-", "12.50"),
            ("24/02/2026", "24/02/2026", "GO EXPRÉS LARCO - MIRAFLORES", "-", "18.00"),
            ("25/02/2026", "25/02/2026", "STREAMFLIX.COM", "-", "44.90"),
            ("26/02/2026", "26/02/2026", "TIENDAS ORVIA - CENTRO PORTADA", "-", "245.00"),
        ],
        "tasas": ("98.00%", "84.50%", "5.86%", "10.80"),
        "footer": ("Tiendas Orvia S.A. — RUC 20500000004. Av. Los Álamos 1234, Surquillo, Lima. "
                   "Central telefónica: (01) 611-0000. Línea gratuita: 0800-00-789. Regulado por la "
                   "Superintendencia de Banca, Seguros y AFP (SBS). Este documento es informativo. "
                   "Ante cualquier discrepancia, prevalecen los registros de la empresa."),
    },
    {
        "out": "Carolina/estado-cuenta-tiendas-delsu-carolina.pdf",
        "issuer": "TIENDAS DELSU",
        "slogan": "Tu estilo, sin límites",
        "card_type": "Tarjeta Delsu",
        "holder_label": "Cliente",
        "holder": "CAROLINA MENDOZA GARCÍA",
        "dni": "12345678",
        "card": "5412 **** **** 5678",
        "cut_label": "Fecha de Corte",
        "cut_date": "25/02/2026",
        "address": "Av. Los Cedros 1234, San Isidro",
        "ref": "DLS-2026-02-01532",
        "min_label": "CUOTA MÍNIMA",
        "min_amount": "557.00",
        "period_amount": "2,020.40",
        "due": "10/03/2026",
        "summary_label": "TOTAL ADEUDADO",
        "balance": "5,500.00",
        "credit_line": "8,000.00",
        "pending_installments": "2",
        "available": "2,500.00",
        "installments_total": "Total cuotas: S/ 680.00",
        "desglose": [
            ("Saldo anterior", "2,905.14"),
            ("(-) Pagos recibidos", "-220.00"),
            ("(+) Nuevas compras y consumos", "2,623.70"),
            ("(+) Intereses", "166.26"),
            ("(+) Comisiones y seguros", "24.90"),
            ("Nuevo saldo", "5,500.00"),
        ],
        "tx": [
            ("03/02/2026", "04/02/2026", "TIENDAS DELSU - CENTRO PORTADA", "-", "680.00"),
            ("05/02/2026", "05/02/2026", "ENTREGA YA*DELIVERY - LIMA", "-", "52.00"),
            ("07/02/2026", "07/02/2026", "SUPERMERCADO CAMPO FRESCO - SURCO", "-", "320.00"),
            ("09/02/2026", "09/02/2026", "ENTREGA YA EATS*DELIVERY - LIMA", "-", "41.00"),
            ("10/02/2026", "10/02/2026", "CAFÉ AROMÉ MALL MIRADOR", "-", "22.50"),
            ("12/02/2026", "12/02/2026", "TIENDAS DELSU ONLINE", "3/6", "520.00"),
            ("14/02/2026", "14/02/2026", "CONSTRUHOGAR CENTER - ATE", "-", "450.00"),
            ("15/02/2026", "15/02/2026", "MUSICWAVE PREMIUM", "-", "19.90"),
            ("17/02/2026", "17/02/2026", "GO EXPRÉS BENAVIDES - MIRAFLORES", "-", "22.00"),
            ("18/02/2026", "18/02/2026", "ENTREGA YA*DELIVERY - LIMA", "-", "38.00"),
            ("19/02/2026", "19/02/2026", "PIDE FÁCIL*DELIVERY - LIMA", "-", "35.50"),
            ("20/02/2026", "20/02/2026", "VIAJA APP*TRIP - LIMA", "-", "14.00"),
            ("21/02/2026", "21/02/2026", "MARKET 24 SAN ISIDRO", "-", "16.50"),
            ("22/02/2026", "22/02/2026", "ENTREGA YA*DELIVERY - LIMA", "-", "44.00"),
            ("23/02/2026", "23/02/2026", "BOTICA BIENESTAR - SURCO", "-", "58.30"),
            ("25/02/2026", "25/02/2026", "TIENDAS DELSU - GRAN PLAZA", "-", "290.00"),
        ],
        "tasas": ("95.00%", "82.15%", "5.72%", "11.20"),
        "footer": ("Tiendas Delsu S.A. — RUC 20500000003. Av. Las Palmeras 5678, Miraflores, Lima. "
                   "Central telefónica: (01) 615-0000. Línea gratuita: 0800-00-456. Regulado por la "
                   "Superintendencia de Banca, Seguros y AFP (SBS). Este documento es informativo. "
                   "Ante cualquier discrepancia, prevalecen los registros de la empresa."),
    },
    {
        "out": "Miguel/estado-cuenta-banco-nordika-miguel.pdf",
        "issuer": "BANCO NORDIKA",
        "slogan": "Contigo en cada paso",
        "card_type": "Tarjeta de Crédito Clásica",
        "holder_label": "Titular",
        "holder": "MIGUEL TORRES RAMÍREZ",
        "dni": "87654321",
        "card": "4716 **** **** 3456",
        "cut_label": "Fecha de Corte",
        "cut_date": "15/02/2026",
        "address": "Calle Las Acacias 456, La Molina",
        "ref": "NDK-2026-02-04218",
        "min_label": "PAGO MÍNIMO",
        "min_amount": "605.00",
        "period_amount": "2,340.00",
        "due": "05/03/2026",
        "summary_label": "SALDO TOTAL",
        "balance": "12,000.00",
        "credit_line": "20,000.00",
        "pending_installments": "0",
        "available": "8,000.00",
        "installments_total": "Sin cuotas vigentes",
        "desglose": [
            ("Saldo anterior", "10,050.52"),
            ("(-) Pagos recibidos", "-480.00"),
            ("(+) Nuevas compras y consumos", "2,047.70"),
            ("(+) Intereses", "356.88"),
            ("(+) Comisiones y seguros", "24.90"),
            ("Nuevo saldo", "12,000.00"),
        ],
        "tx": [
            ("02/02/2026", "02/02/2026", "SELECTA - SAN BORJA", "-", "450.00"),
            ("03/02/2026", "03/02/2026", "GRIFO VOLTIA AV CENTRAL", "-", "180.00"),
            ("05/02/2026", "05/02/2026", "CAFÉ AROMÉ PLAZA CENTRAL", "-", "28.50"),
            ("06/02/2026", "06/02/2026", "VIAJA APP*TRIP - LIMA", "-", "35.00"),
            ("07/02/2026", "07/02/2026", "MUSICWAVE PREMIUM", "-", "19.90"),
            ("08/02/2026", "08/02/2026", "CINE ESTELAR CENTRO NORTE", "-", "86.00"),
            ("10/02/2026", "10/02/2026", "PIDE FÁCIL*DELIVERY - LIMA", "-", "62.00"),
            ("11/02/2026", "11/02/2026", "MARKET 24 LA MOLINA", "-", "18.50"),
            ("12/02/2026", "12/02/2026", "BOTICA VITALIS - SAN BORJA", "-", "125.00"),
            ("13/02/2026", "13/02/2026", "PRIMEREEL VIDEO", "-", "24.90"),
            ("14/02/2026", "14/02/2026", "ENTREGA YA*DELIVERY - LIMA", "-", "55.00"),
            ("15/02/2026", "15/02/2026", "SUPERMERCADO NÓVEA - LA MOLINA", "-", "380.00"),
            ("17/02/2026", "17/02/2026", "VIAJA APP*TRIP - LIMA", "-", "22.00"),
            ("18/02/2026", "18/02/2026", "GRIFO ENERLIT MONTERRICO", "-", "160.00"),
            ("19/02/2026", "19/02/2026", "CAFÉ AROMÉ CENTRO PORTADA", "-", "24.00"),
            ("20/02/2026", "20/02/2026", "ENTREGA YA*DELIVERY - LIMA", "-", "48.00"),
            ("22/02/2026", "22/02/2026", "SELECTA EXPRESS - SURCO", "-", "210.00"),
            ("23/02/2026", "23/02/2026", "PIDE FÁCIL*DELIVERY - LIMA", "-", "42.00"),
            ("25/02/2026", "25/02/2026", "GO EXPRÉS CAMINOS DEL INCA", "-", "16.00"),
            ("26/02/2026", "26/02/2026", "VIAJA APP*TRIP - LIMA", "-", "28.00"),
            ("27/02/2026", "27/02/2026", "MAXSTREAM", "-", "32.90"),
        ],
        "tasas": ("52.00%", "42.58%", "3.55%", "14.80"),
        "footer": ("Banco Nordika S.A. — RUC 20100000002. Av. Central 1234, San Isidro, Lima. "
                   "Central telefónica: (01) 595-0000. Línea gratuita: 0800-00-234. Regulado por la "
                   "Superintendencia de Banca, Seguros y AFP (SBS). Este documento es informativo. "
                   "Ante cualquier discrepancia, prevalecen los registros del banco."),
    },
    {
        "out": "Miguel/estado-cuenta-banco-marena-miguel.pdf",
        "issuer": "BANCO MARENA",
        "slogan": "Más cerca de ti",
        "card_type": "Tarjeta de Crédito Gold",
        "holder_label": "Titular",
        "holder": "MIGUEL TORRES RAMÍREZ",
        "dni": "87654321",
        "card": "5231 **** **** 7890",
        "cut_label": "Fecha de Corte",
        "cut_date": "20/02/2026",
        "address": "Calle Las Acacias 456, La Molina",
        "ref": "MRN-2026-02-02765",
        "min_label": "PAGO MÍNIMO",
        "min_amount": "579.00",
        "period_amount": "1,296.00",
        "due": "10/03/2026",
        "summary_label": "SALDO TOTAL",
        "balance": "7,000.00",
        "credit_line": "12,000.00",
        "pending_installments": "1",
        "available": "5,000.00",
        "installments_total": "Total cuotas: S/ 159.00",
        "desglose": [
            ("Saldo anterior", "5,648.24"),
            ("(-) Pagos recibidos", "-280.00"),
            ("(+) Nuevas compras y consumos", "1,387.40"),
            ("(+) Intereses", "219.46"),
            ("(+) Comisiones y seguros", "24.90"),
            ("Nuevo saldo", "7,000.00"),
        ],
        "tx": [
            ("03/02/2026", "03/02/2026", "SUPERMERCADO PLAZA FRESCA - SURCO", "-", "320.00"),
            ("05/02/2026", "05/02/2026", "ENTREGA YA*DELIVERY - LIMA", "-", "58.00"),
            ("06/02/2026", "06/02/2026", "CAFÉ AROMÉ TORRE CENTRAL", "-", "31.50"),
            ("08/02/2026", "08/02/2026", "ENTREGA YA EATS*DELIVERY - LIMA", "-", "45.00"),
            ("10/02/2026", "10/02/2026", "STREAMFLIX.COM", "-", "44.90"),
            ("11/02/2026", "11/02/2026", "GO EXPRÉS ANGAMOS - MIRAFLORES", "-", "22.00"),
            ("13/02/2026", "13/02/2026", "GIMNASIO POTENZA CHACARILLA", "1/12", "159.00"),
            ("15/02/2026", "15/02/2026", "GRIFO ENERLIT BENAVIDES", "-", "150.00"),
            ("16/02/2026", "16/02/2026", "ENTREGA YA*DELIVERY - LIMA", "-", "42.00"),
            ("17/02/2026", "17/02/2026", "PIDE FÁCIL*DELIVERY - LIMA", "-", "38.00"),
            ("19/02/2026", "19/02/2026", "VIAJA APP*TRIP - LIMA", "-", "15.00"),
            ("20/02/2026", "20/02/2026", "SELECTA - MIRAFLORES", "-", "280.00"),
            ("22/02/2026", "22/02/2026", "CAFÉ AROMÉ PLAZA GUTIÉRREZ", "-", "25.00"),
            ("23/02/2026", "23/02/2026", "ENTREGA YA*DELIVERY - LIMA", "-", "35.00"),
            ("24/02/2026", "24/02/2026", "MARKET 24 SURQUILLO", "-", "19.00"),
            ("25/02/2026", "25/02/2026", "BOTICA SALUD+ - SURCO", "-", "85.00"),
            ("26/02/2026", "26/02/2026", "VIAJA APP*TRIP - LIMA", "-", "18.00"),
        ],
        "tasas": ("58.00%", "47.50%", "3.89%", "12.60"),
        "footer": ("Banco Marena S.A. — RUC 20100000005. Av. Las Orquídeas 890, San Isidro, Lima. "
                   "Central telefónica: (01) 612-0000. Línea gratuita: 0800-00-567. Regulado por la "
                   "Superintendencia de Banca, Seguros y AFP (SBS). Este documento es informativo. "
                   "Ante cualquier discrepancia, prevalecen los registros del banco."),
    },
]


NAVY = colors.HexColor("#1a2b4a")
STEEL = colors.HexColor("#2e5e8c")
LIGHT = colors.HexColor("#eef2f7")


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("Issuer", parent=ss["Title"], textColor=colors.white,
                          fontSize=18, spaceAfter=0, leading=20))
    ss.add(ParagraphStyle("Slogan", parent=ss["Normal"], textColor=colors.white,
                          fontSize=8, leading=10))
    ss.add(ParagraphStyle("HdrRight", parent=ss["Normal"], textColor=colors.white,
                          fontSize=9, alignment=2, leading=12))
    ss.add(ParagraphStyle("Section", parent=ss["Heading3"], textColor=NAVY,
                          fontSize=10, spaceBefore=8, spaceAfter=2))
    ss.add(ParagraphStyle("Foot", parent=ss["Normal"], fontSize=6.5,
                          textColor=colors.grey, leading=8))
    return ss


def _check_no_real_brands(stmt):
    """Fail loudly if any real brand name leaked into a statement."""
    haystacks = [stmt["issuer"], stmt["slogan"], stmt["card_type"], stmt["footer"]]
    haystacks += [t[2] for t in stmt["tx"]]
    blob = " || ".join(haystacks).lower()
    hits = [b for b in REAL_BRAND_DENYLIST if b in blob]
    if hits:
        raise ValueError(f"{stmt['out']}: real brand(s) detected: {hits}")


def build(stmt):
    ss = _styles()
    out_path = os.path.join(OUT_ROOT, stmt["out"])
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    doc = SimpleDocTemplate(out_path, pagesize=A4,
                            leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f"Estado de Cuenta - {stmt['issuer']}",
                            author=stmt["issuer"])
    W = doc.width
    story = []

    # ── Header band ──
    header_inner = Table(
        [[Paragraph(stmt["issuer"], ss["Issuer"]),
          Paragraph("Estado de Cuenta<br/>" + stmt["card_type"] +
                    "<br/>Período: Febrero 2026", ss["HdrRight"])],
         [Paragraph(stmt["slogan"], ss["Slogan"]), ""]],
        colWidths=[W * 0.6, W * 0.4])
    header_inner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(header_inner)
    story.append(Spacer(1, 3))
    story.append(Paragraph(
        "<i>⚠ DOCUMENTO FICTICIO — Todos los nombres de entidades, comercios, titulares, "
        "DNIs y montos en este documento fueron intencionalmente fabricados para fines de "
        "demostración. No corresponden a personas ni instituciones reales.</i>",
        ParagraphStyle("Disclaimer", parent=ss["Normal"], fontSize=6.5,
                       textColor=colors.HexColor("#cc4400"), leading=8, spaceAfter=2)))
    story.append(Spacer(1, 4))

    # ── Holder / account meta ──
    meta = Table(
        [[f"{stmt['holder_label']}: {stmt['holder']}", f"N° Tarjeta: {stmt['card']}"],
         [f"DNI: {stmt['dni']}", f"{stmt['cut_label']}: {stmt['cut_date']}"],
         [f"Dirección: {stmt['address']}", f"N° de Referencia: {stmt['ref']}"]],
        colWidths=[W * 0.6, W * 0.4])
    meta.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (-1, -1), NAVY),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(meta)
    story.append(Spacer(1, 6))

    # ── Payment boxes ──
    pay = Table(
        [[stmt["min_label"], "PAGO DEL PERÍODO"],
         [f"S/ {stmt['min_amount']}", f"S/ {stmt['period_amount']}"],
         [f"Vence: {stmt['due']}", f"Vence: {stmt['due']}"]],
        colWidths=[W * 0.5, W * 0.5])
    pay.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("BOX", (0, 0), (0, -1), 0.5, STEEL),
        ("BOX", (1, 0), (1, -1), 0.5, STEEL),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TEXTCOLOR", (0, 0), (-1, 0), STEEL),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, 1), 14),
        ("TEXTCOLOR", (0, 1), (-1, 1), NAVY),
        ("FONTSIZE", (0, 2), (-1, 2), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(pay)

    # ── Summary ──
    story.append(Paragraph("RESUMEN DE CUENTA", ss["Section"]))
    summ = Table(
        [[stmt["summary_label"], "LÍNEA DE CRÉDITO", "CUOTAS PENDIENTES"],
         [f"S/ {stmt['balance']}", f"S/ {stmt['credit_line']}", stmt["pending_installments"]],
         [f"Disponible: S/ {stmt['available']}", stmt["installments_total"], ""]],
        colWidths=[W / 3.0] * 3)
    summ.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("TEXTCOLOR", (0, 0), (-1, 0), STEEL),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, 1), 12),
        ("TEXTCOLOR", (0, 1), (-1, 1), NAVY),
        ("FONTSIZE", (0, 2), (-1, 2), 7),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, LIGHT),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(summ)

    # ── Desglose ──
    story.append(Paragraph("DESGLOSE DEL SALDO", ss["Section"]))
    des_rows = [["Concepto", "Monto (S/)"]] + [[c, m] for c, m in stmt["desglose"]]
    des = Table(des_rows, colWidths=[W * 0.7, W * 0.3])
    des.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), STEEL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 0.5, NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, LIGHT]),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(des)

    # ── Movements ──
    story.append(Paragraph("MOVIMIENTOS DEL PERÍODO", ss["Section"]))
    tx_rows = [["Fecha", "Fecha Proc.", "Descripción", "Cuotas", "Monto (S/)"]]
    tx_rows += [list(t) for t in stmt["tx"]]
    tx = Table(tx_rows, colWidths=[W * 0.14, W * 0.14, W * 0.48, W * 0.10, W * 0.14],
               repeatRows=1)
    tx.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), STEEL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("ALIGN", (4, 0), (4, -1), "RIGHT"),
        ("ALIGN", (3, 0), (3, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(tx)

    # ── Rates ──
    tcea, tea, mensual, seguro = stmt["tasas"]
    story.append(Paragraph("Información de Tasas y Comisiones", ss["Section"]))
    rates = Table(
        [[f"TCEA: {tcea}", f"TEA: {tea}", f"Tasa mensual: {mensual}"],
         [f"Seguro desgravamen: S/ {seguro}", "Membresía anual: S/ 0.00", "T.C. del día: S/ 3.72"]],
        colWidths=[W / 3.0] * 3)
    rates.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (-1, -1), NAVY),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(rates)
    story.append(Spacer(1, 10))
    story.append(Paragraph(stmt["footer"], ss["Foot"]))

    doc.build(story)
    return out_path


def main():
    generated = []
    for stmt in STATEMENTS:
        _check_no_real_brands(stmt)
        generated.append(build(stmt))
    print(f"Generados {len(generated)} estados de cuenta (nombres ficticios):")
    for p in generated:
        print("  -", os.path.relpath(p, HERE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
