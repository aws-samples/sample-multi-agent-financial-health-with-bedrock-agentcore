// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

interface InterestAreaProps {
  data: Array<{ mes: number; interes_minimos: number; interes_plan: number }>;
  t: (key: string) => string;
}

const tt = { backgroundColor: '#fff', border: '1px solid #d4d2ce', borderRadius: '2px', color: '#111110', fontSize: '0.78rem' };

export function InterestArea({ data, t }: InterestAreaProps) {
  return (
    <ResponsiveContainer width="100%" height={252}>
      {/* Legend above the plot: the default bottom placement overlapped the
          "Mes" axis label. */}
      <AreaChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 24 }}>
        <defs>
          <linearGradient id="gRed" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#c0392b" stopOpacity={0.15} />
            <stop offset="95%" stopColor="#c0392b" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="gGreen" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#1e6b4a" stopOpacity={0.15} />
            <stop offset="95%" stopColor="#1e6b4a" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#e8e6e2" />
        <XAxis dataKey="mes" tick={{ fill: '#888884', fontSize: 11 }} label={{ value: t('chart_month_axis'), position: 'insideBottom', offset: -14, fill: '#888884', fontSize: 11 }} />
        <YAxis tick={{ fill: '#888884', fontSize: 11 }} />
        <Tooltip formatter={(v) => `S/ ${v}`} contentStyle={tt} />
        <Legend verticalAlign="top" height={26} wrapperStyle={{ fontSize: '0.72rem', color: '#888884' }} />
        <Area type="monotone" dataKey="interes_minimos" stroke="#c0392b" fill="url(#gRed)" strokeWidth={1.5} name={t('chart_interest_minimums')} />
        <Area type="monotone" dataKey="interes_plan" stroke="#1e6b4a" fill="url(#gGreen)" strokeWidth={1.5} name={t('chart_interest_plan')} />
      </AreaChart>
    </ResponsiveContainer>
  );
}
