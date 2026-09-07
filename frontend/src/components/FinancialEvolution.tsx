// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { useState, useEffect, useCallback } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { Icon } from './Icon';

interface FinancialEvolutionProps {
  userId: string;
  apiUrl: string;
  currencySymbol: string;
  language: string;
}

type Period = 'semester' | 'year' | '5years';

interface Snapshot {
  timestamp: string;
  fecha_corte?: string;
  deuda_total?: number;
  intereses_mensuales?: number;
  ratio_deuda_ingreso?: number;
}

const tt = { backgroundColor: '#fff', border: '1px solid #d4d2ce', borderRadius: '2px', color: '#111110', fontSize: '0.78rem' };

export function FinancialEvolution({ userId, apiUrl, currencySymbol, language }: FinancialEvolutionProps) {
  const [period, setPeriod] = useState<Period>('semester');
  const [data, setData] = useState<Snapshot[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const labels = language === 'en'
    ? { title: 'Financial Evolution', semester: 'Semester', year: 'Year', fiveYears: '5 Years', noData: 'No historical data yet. Data will appear after your first analysis.', debt: 'Total Debt', interest: 'Monthly Interest' }
    : { title: 'Evolución Financiera', semester: 'Semestre', year: 'Año', fiveYears: '5 Años', noData: 'Aún no hay datos históricos. Aparecerán después de tu primer análisis.', debt: 'Deuda Total', interest: 'Intereses Mensuales' };

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const { fetchAuthSession } = await import('aws-amplify/auth');
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString() || '';
      const res = await fetch(`${apiUrl}/history/${userId}?period=${period}`, {
        headers: { 'Authorization': token },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json.history || json.snapshots || json.data || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error');
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [apiUrl, userId, period]);

  useEffect(() => { fetchHistory(); }, [fetchHistory]);

  const chartData = data.map(s => {
    // Usar fecha_corte (DD/MM/YYYY) del documento si existe, sino timestamp
    let dateLabel: string;
    if (s.fecha_corte) {
      const parts = s.fecha_corte.split('/');
      if (parts.length === 3) {
        const dt = new Date(parseInt(parts[2]), parseInt(parts[1]) - 1, parseInt(parts[0]));
        dateLabel = dt.toLocaleDateString(language === 'en' ? 'en-US' : 'es-PE', { month: 'short', year: '2-digit' });
      } else {
        dateLabel = s.fecha_corte;
      }
    } else {
      dateLabel = new Date(s.timestamp).toLocaleDateString(language === 'en' ? 'en-US' : 'es-PE', { month: 'short', year: '2-digit' });
    }
    return {
      date: dateLabel,
      deuda: s.deuda_total || 0,
      intereses: s.intereses_mensuales || 0,
    };
  });

  return (
    <div className="evolution-view">
      <div className="section-label">{labels.title}</div>
      <div className="evolution-period-selector">
        {(['semester', 'year', '5years'] as Period[]).map(p => (
          <button key={p} className={`period-btn ${period === p ? 'active' : ''}`} onClick={() => setPeriod(p)}>
            {p === 'semester' ? labels.semester : p === 'year' ? labels.year : labels.fiveYears}
          </button>
        ))}
      </div>
      {loading && <p className="info-text">{language === 'en' ? 'Loading...' : 'Cargando...'}</p>}
      {error && <p className="info-text"><Icon name="alert" /> {error}</p>}
      {!loading && !error && chartData.length === 0 && <p className="info-text">{labels.noData}</p>}
      {chartData.length > 0 && (
        <div className="evolution-chart-container">
          <ResponsiveContainer width="100%" height={360}>
            <LineChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e8e6e2" />
              <XAxis dataKey="date" tick={{ fill: '#888884', fontSize: 11 }} />
              <YAxis tick={{ fill: '#888884', fontSize: 11 }} tickFormatter={(v) => `${currencySymbol}${(v/1000).toFixed(0)}k`} />
              <Tooltip formatter={(v) => `${currencySymbol} ${v}`} contentStyle={tt} />
              <Legend wrapperStyle={{ fontSize: '0.72rem', color: '#888884' }} />
              <Line type="monotone" dataKey="deuda" stroke="#e11d48" strokeWidth={2} dot={{ r: 3 }} name={labels.debt} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
