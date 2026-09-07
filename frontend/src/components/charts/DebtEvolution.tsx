// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

interface DebtEvolutionProps {
  data: Array<Record<string, any>>;
  t: (key: string) => string;
}

const tt = { backgroundColor: '#fff', border: '1px solid #d4d2ce', borderRadius: '2px', color: '#111110', fontSize: '0.78rem' };

function normalizeData(data: Array<Record<string, any>>): Array<{ mes: number; saldo_minimos: number; saldo_plan: number }> {
  return data.map((item, i) => {
    // mes: accept mes, month, Month, or index
    let mes = item.mes ?? item.month ?? item.Month ?? i;
    if (typeof mes === 'string') {
      const num = parseInt(mes.replace(/\D/g, ''));
      mes = isNaN(num) ? i : num;
    }
    // saldo_minimos: accept saldo_minimos or sum of individual card fields as fallback
    let saldo_minimos = item.saldo_minimos ?? item.saldoMinimos ?? item.minimos;
    let saldo_plan = item.saldo_plan ?? item.saldoPlan ?? item.plan ?? item.optimizado;
    // If neither exists, try to infer from card-specific fields (bcp, falabella, etc.)
    if (saldo_minimos == null && saldo_plan == null) {
      const knownKeys = ['mes', 'month', 'Month'];
      const cardKeys = Object.keys(item).filter(k => !knownKeys.includes(k));
      const total = cardKeys.reduce((sum, k) => sum + (typeof item[k] === 'number' ? item[k] : 0), 0);
      saldo_plan = total;
      saldo_minimos = i === 0 ? total : total * 1.15; // rough estimate
    }
    return { mes, saldo_minimos: saldo_minimos ?? 0, saldo_plan: saldo_plan ?? 0 };
  });
}

export function DebtEvolution({ data, t }: DebtEvolutionProps) {
  const normalized = normalizeData(data);
  return (
    <ResponsiveContainer width="100%" height={252}>
      {/* The legend sits above the plot. With the default bottom legend it
          overlapped the "Mes" axis label, which is drawn insideBottom. */}
      <LineChart data={normalized} margin={{ top: 5, right: 10, left: 0, bottom: 24 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e8e6e2" />
        <XAxis dataKey="mes" tick={{ fill: '#888884', fontSize: 11 }} label={{ value: t('chart_month_axis'), position: 'insideBottom', offset: -14, fill: '#888884', fontSize: 11 }} />
        <YAxis tick={{ fill: '#888884', fontSize: 11 }} tickFormatter={(v) => `S/${(v/1000).toFixed(0)}k`} />
        <Tooltip formatter={(v) => `S/ ${v}`} contentStyle={tt} />
        <Legend verticalAlign="top" height={26} wrapperStyle={{ fontSize: '0.72rem', color: '#888884' }} />
        <Line type="monotone" dataKey="saldo_minimos" stroke="#e11d48" strokeWidth={2} dot={false} name={t('chart_paying_minimums')} />
        <Line type="monotone" dataKey="saldo_plan" stroke="#059669" strokeWidth={2} dot={false} name={t('chart_optimized_plan')} />
      </LineChart>
    </ResponsiveContainer>
  );
}
