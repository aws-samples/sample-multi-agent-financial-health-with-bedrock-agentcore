// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

interface SimulationProps {
  data: Array<{ escenario: string; meses: number; costo_total: number }>;
}

const tt = { backgroundColor: '#fff', border: '1px solid #d4d2ce', borderRadius: '2px', color: '#111110', fontSize: '0.78rem' };

export function Simulation({ data }: SimulationProps) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} layout="vertical" margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e8e6e2" horizontal={false} />
        <XAxis type="number" tick={{ fill: '#888884', fontSize: 11 }} />
        <YAxis type="category" dataKey="escenario" width={130} tick={{ fill: '#3a3a38', fontSize: 11 }} />
        <Tooltip contentStyle={tt} />
        <Legend wrapperStyle={{ fontSize: '0.72rem', color: '#888884' }} />
        <Bar dataKey="meses" fill="#111110" name="Meses" radius={[0, 2, 2, 0]} />
        <Bar dataKey="costo_total" fill="#888884" name="Costo total (S/)" radius={[0, 2, 2, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
