// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

interface AlternativesProps {
  data: Array<{ opcion: string; plazo_meses: number; costo_total: number; ahorro: number }>;
}

const tt = { backgroundColor: '#fff', border: '1px solid #d4d2ce', borderRadius: '2px', color: '#111110', fontSize: '0.78rem' };

export function Alternatives({ data }: AlternativesProps) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 20 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e8e6e2" vertical={false} />
        <XAxis dataKey="opcion" tick={{ fill: '#888884', fontSize: 11 }} />
        <YAxis tick={{ fill: '#888884', fontSize: 11 }} tickFormatter={(v) => `S/${(v/1000).toFixed(0)}k`} />
        <Tooltip formatter={(v) => `S/ ${v}`} contentStyle={tt} />
        <Legend wrapperStyle={{ fontSize: '0.72rem', color: '#888884' }} />
        <Bar dataKey="costo_total" fill="#c0392b" name="Costo total" radius={[2, 2, 0, 0]} />
        <Bar dataKey="ahorro" fill="#1e6b4a" name="Ahorro vs mínimos" radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
