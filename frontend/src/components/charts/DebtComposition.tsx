// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';

interface DebtCompositionProps {
  data: Array<Record<string, any>>;
}

const tt = { backgroundColor: '#fff', border: '1px solid #d4d2ce', borderRadius: '2px', color: '#111110', fontSize: '0.78rem' };
const FILLS = ['#2563eb', '#e11d48', '#059669', '#d97706', '#7c3aed'];

function normalizeData(data: Array<Record<string, any>>): Array<{ tarjeta: string; saldo: number; tcea: number }> {
  return data.map(item => ({
    tarjeta: item.tarjeta ?? item.banco ?? item.name ?? item.card ?? 'N/A',
    saldo: item.saldo ?? item.balance ?? item.monto ?? item.amount ?? 0,
    tcea: item.tcea ?? item.rate ?? item.tasa ?? 0,
  }));
}

export function DebtComposition({ data }: DebtCompositionProps) {
  const normalized = normalizeData(data);
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={normalized} margin={{ top: 5, right: 10, left: 0, bottom: 20 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e8e6e2" vertical={false} />
        <XAxis dataKey="tarjeta" tick={{ fill: '#888884', fontSize: 11 }} />
        <YAxis tick={{ fill: '#888884', fontSize: 11 }} tickFormatter={(v) => `S/${(v/1000).toFixed(0)}k`} />
        <Tooltip formatter={(v) => `S/ ${v}`} contentStyle={tt} />
        <Bar dataKey="saldo" name="Saldo" radius={[2, 2, 0, 0]}>
          {normalized.map((_, i) => <Cell key={i} fill={FILLS[i % FILLS.length]} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
