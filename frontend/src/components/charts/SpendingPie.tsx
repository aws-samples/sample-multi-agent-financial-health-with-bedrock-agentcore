// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts';

interface SpendingPieProps {
  data: Array<Record<string, any>>;
}

const tt = { backgroundColor: '#fff', border: '1px solid #d4d2ce', borderRadius: '2px', color: '#111110', fontSize: '0.78rem' };
const FILLS = ['#2563eb', '#e11d48', '#059669', '#d97706', '#7c3aed', '#0891b2'];

function normalizeData(data: Array<Record<string, any>>): Array<{ categoria: string; monto: number }> {
  return data.map(item => ({
    categoria: item.categoria ?? item.category ?? item.name ?? item.tipo ?? 'Otro',
    monto: item.monto ?? item.amount ?? item.value ?? item.total ?? 0,
  }));
}

export function SpendingPie({ data }: SpendingPieProps) {
  const normalized = normalizeData(data);
  return (
    <ResponsiveContainer width="100%" height={240}>
      <PieChart>
        <Pie data={normalized} dataKey="monto" nameKey="categoria" cx="50%" cy="45%" outerRadius={85} innerRadius={35} paddingAngle={2}>
          {normalized.map((_, i) => <Cell key={i} fill={FILLS[i % FILLS.length]} />)}
        </Pie>
        <Tooltip formatter={(v) => `S/ ${v}`} contentStyle={tt} />
        <Legend wrapperStyle={{ fontSize: '0.72rem', color: '#888884' }} />
      </PieChart>
    </ResponsiveContainer>
  );
}
