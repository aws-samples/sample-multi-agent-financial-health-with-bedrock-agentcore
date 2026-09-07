// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
export interface CountryConfig {
  code: string;
  name: string;
  currency: string;
  symbol: string;
  finTerm: string;
  finTermFull: string;
}

export const COUNTRIES: CountryConfig[] = [
  { code: 'PE', name: 'Perú', currency: 'PEN', symbol: 'S/', finTerm: 'TCEA', finTermFull: 'Tasa de Costo Efectivo Anual' },
  { code: 'MX', name: 'México', currency: 'MXN', symbol: 'MX$', finTerm: 'CAT', finTermFull: 'Costo Anual Total' },
  { code: 'CL', name: 'Chile', currency: 'CLP', symbol: 'CL$', finTerm: 'CAE', finTermFull: 'Carga Anual Equivalente' },
  { code: 'CO', name: 'Colombia', currency: 'COP', symbol: 'CO$', finTerm: 'EA', finTermFull: 'Efectiva Anual' },
  { code: 'AR', name: 'Argentina', currency: 'ARS', symbol: 'AR$', finTerm: 'CFT', finTermFull: 'Costo Financiero Total' },
  { code: 'BR', name: 'Brasil', currency: 'BRL', symbol: 'R$', finTerm: 'CET', finTermFull: 'Custo Efetivo Total' },
  { code: 'US', name: 'Estados Unidos', currency: 'USD', symbol: 'US$', finTerm: 'APR', finTermFull: 'Annual Percentage Rate' },
  { code: 'BO', name: 'Bolivia', currency: 'BOB', symbol: 'Bs', finTerm: 'TEA', finTermFull: 'Tasa Efectiva Anual' },
  { code: 'PY', name: 'Paraguay', currency: 'PYG', symbol: '₲', finTerm: 'TEA', finTermFull: 'Tasa Efectiva Anual' },
  { code: 'UY', name: 'Uruguay', currency: 'UYU', symbol: '$U', finTerm: 'TEA', finTermFull: 'Tasa Efectiva Anual' },
  { code: 'VE', name: 'Venezuela', currency: 'VES', symbol: 'Bs.D', finTerm: 'TEA', finTermFull: 'Tasa Efectiva Anual' },
  { code: 'GT', name: 'Guatemala', currency: 'GTQ', symbol: 'Q', finTerm: 'TEA', finTermFull: 'Tasa Efectiva Anual' },
  { code: 'HN', name: 'Honduras', currency: 'HNL', symbol: 'L', finTerm: 'TEA', finTermFull: 'Tasa Efectiva Anual' },
  { code: 'NI', name: 'Nicaragua', currency: 'NIO', symbol: 'C$', finTerm: 'TEA', finTermFull: 'Tasa Efectiva Anual' },
  { code: 'CR', name: 'Costa Rica', currency: 'CRC', symbol: '₡', finTerm: 'TEA', finTermFull: 'Tasa Efectiva Anual' },
  { code: 'PA', name: 'Panamá', currency: 'PAB', symbol: 'B/.', finTerm: 'TEA', finTermFull: 'Tasa Efectiva Anual' },
  { code: 'DO', name: 'Rep. Dominicana', currency: 'DOP', symbol: 'RD$', finTerm: 'TEA', finTermFull: 'Tasa Efectiva Anual' },
  { code: 'EC', name: 'Ecuador', currency: 'USD', symbol: 'US$', finTerm: 'TEA', finTermFull: 'Tasa Efectiva Anual' },
];

export const DEFAULT_COUNTRY = COUNTRIES[0]; // Perú

export function getCountryByCode(code: string): CountryConfig {
  return COUNTRIES.find(c => c.code === code) || DEFAULT_COUNTRY;
}
