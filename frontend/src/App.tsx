// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { useState, useRef, useCallback, useEffect } from 'react';
import { Authenticator, useAuthenticator } from '@aws-amplify/ui-react';
import { fetchUserAttributes, updateUserAttributes, fetchAuthSession } from 'aws-amplify/auth';
import '@aws-amplify/ui-react/styles.css';
import { Chat } from './components/Chat';
import type { ChatHandle } from './components/Chat';
import { PdfUploader } from './components/PdfUploader';
import { ConsentBanner } from './components/ConsentBanner';
import { KeyHealthIndicators } from './components/KeyHealthIndicators';
import type { HealthIndicator } from './components/KeyHealthIndicators';
import { ChartRenderer } from './components/ChartRenderer';
import { ProfileSettings } from './components/ProfileSettings';
import { FinancialEvolution } from './components/FinancialEvolution';
import { Icon } from './components/Icon';
import type { IconName } from './components/Icon';
import { DEFAULT_COUNTRY, getCountryByCode } from './utils/countries';
import type { CountryConfig } from './utils/countries';
import { useTranslation } from './i18n';
import type { ChartBlock } from './utils/parseResponse';
import './App.css';

export interface UploadedDoc {
  id: string;
  name: string;
  size: number;
  s3Uri: string;
  status: 'uploading' | 'uploaded' | 'analyzing' | 'analyzed' | 'error';
  banco?: string;
  ultimos4?: string;
  fechaCorte?: string;
  dbStatus?: string;
}

interface JobResult {
  job_id: string;
  status: string;
  session_id?: string;
  success?: boolean;
  result?: string;
  usuario_id?: string;
  error?: string;
}

// Labels are i18n keys, resolved at render time. They were hardcoded Spanish,
// so the progress panel stayed Spanish with the interface in English.
const PROGRESS_STEPS: Array<{ labelKey: string; icon: IconName; delay: number }> = [
  { labelKey: 'progress_extracting', icon: 'document', delay: 0 },
  { labelKey: 'progress_consolidating', icon: 'layers', delay: 8000 },
  { labelKey: 'progress_analyzing', icon: 'search', delay: 20000 },
  { labelKey: 'progress_detecting', icon: 'coins', delay: 35000 },
  { labelKey: 'progress_strategy', icon: 'lightbulb', delay: 50000 },
];

function AppContent() {
  const { user, signOut } = useAuthenticator((ctx) => [ctx.user]);
  const userId = user?.userId || 'demo_user';

  // Profile state
  const [country, setCountry] = useState<CountryConfig>(DEFAULT_COUNTRY);
  const [language, setLanguage] = useState('es');
  const [savedIncome, setSavedIncome] = useState('');
  const [paymentBehavior, setPaymentBehavior] = useState('');
  const [showProfile, setShowProfile] = useState(false);
  const [, setProfileLoaded] = useState(false);
  const [userEmail, setUserEmail] = useState('');
  const { t } = useTranslation(language);

  const [activeTab, setActiveTab] = useState<'analysis' | 'documents' | 'evolution'>('documents');
  const [uploadedDocs, setUploadedDocs] = useState<UploadedDoc[]>([]);
  const [knownHashes, setKnownHashes] = useState<Record<string, string>>({});
  const [income, setIncome] = useState('');
  const [charts, setCharts] = useState<ChartBlock[]>([]);
  const chartsRef = useRef<ChartBlock[]>([]);
  const [indicators, setIndicators] = useState<HealthIndicator[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [progressIdx, setProgressIdx] = useState(0);
  const [notification, setNotification] = useState<{ message: string; type: 'info' | 'warning' | 'error' } | null>(null);
  const progressTimers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const chatRef = useRef<ChatHandle>(null);
  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:3001';

  // Helper: fetch con token JWT de Cognito
  const authFetch = useCallback(async (url: string, options: RequestInit = {}) => {
    const session = await fetchAuthSession();
    const token = session.tokens?.idToken?.toString() || '';
    return fetch(url, {
      ...options,
      headers: {
        ...options.headers,
        'Authorization': token,
      },
    });
  }, []);

  // Persistent session per user
  const sessionIdRef = useRef<string>('');
  useEffect(() => {
    const key = `finhealth_session_${userId}`;
    const stored = localStorage.getItem(key);
    if (stored) {
      sessionIdRef.current = stored;
    } else {
      const newId = crypto.randomUUID();
      sessionIdRef.current = newId;
      localStorage.setItem(key, newId);
    }
  }, [userId]);

  // Load user documents from backend (DynamoDB) on mount
  useEffect(() => {
    if (userId === 'demo_user') return;
    (async () => {
      try {
        const res = await authFetch(`${API_URL}/user-documents/${userId}`);
        if (!res.ok) return;
        const data = await res.json();
        // Reconstruct uploadedDocs from estados_cuenta (primary source)
        let docs: UploadedDoc[] = [];
        if (data.documents && data.documents.length > 0) {
          docs = data.documents.map((doc: any) => ({
            id: doc.file_hash || doc.tarjeta_id,
            name: `${doc.banco} ****${doc.ultimos_4_digitos}`,
            size: 0,
            s3Uri: doc.source_s3_key ? `s3://${data.bucket}/${doc.source_s3_key}` : '',
            status: 'analyzed' as const,
            banco: doc.banco,
            ultimos4: doc.ultimos_4_digitos,
            fechaCorte: doc.fecha_corte,
            dbStatus: doc.status,
          }));
        }
        if (docs.length > 0) {
          setUploadedDocs(docs);
        }
        // Load known hashes for duplicate detection
        if (data.hashes) {
          setKnownHashes(data.hashes);
        }
      } catch (err) {
        console.error('Error loading user documents:', err instanceof Error ? err.message : 'unknown');
      }
    })();
  }, [userId, API_URL]);

  // Load profile from Cognito attributes on login
  useEffect(() => {
    async function loadProfile() {
      try {
        const attrs = await fetchUserAttributes();
        const cc = attrs['custom:country'] || DEFAULT_COUNTRY.code;
        setCountry(getCountryByCode(cc));
        setLanguage(attrs['custom:language'] || 'es');
        if (attrs['email']) setUserEmail(attrs['email']);
        const inc = attrs['custom:income'] || '';
        const pb = attrs['custom:payment_behavior'] || '';
        if (inc) {
          setSavedIncome(inc);
          setIncome(inc);
        }
        setPaymentBehavior(pb);
        setProfileLoaded(true);
        // Auto-open profile if incomplete
        if (!inc || !pb) {
          setShowProfile(true);
        }
      } catch {
        // First login, no custom attrs yet — open profile
        setProfileLoaded(true);
        setShowProfile(true);
      }
    }
    if (userId !== 'demo_user') loadProfile();
  }, [userId]);

  const handleProfileSave = useCallback(async (cc: string, lang: string, inc: string, pb: string) => {
    const c = getCountryByCode(cc);
    setCountry(c);
    setLanguage(lang);
    setSavedIncome(inc);
    setIncome(inc);
    setPaymentBehavior(pb);
    setShowProfile(false);
    try {
      await updateUserAttributes({
        userAttributes: {
          'custom:country': cc,
          'custom:currency': c.currency,
          'custom:language': lang,
          'custom:income': inc,
          'custom:payment_behavior': pb,
        },
      });
    } catch (err) {
      console.error('Error saving profile:', err);
    }
  }, []);

  const sym = country.symbol;

  const startProgress = useCallback(() => {
    setIsProcessing(true);
    setProgressIdx(0);
    progressTimers.current.forEach(t => clearTimeout(t));
    progressTimers.current = [];
    PROGRESS_STEPS.forEach((step, i) => {
      if (i === 0) return;
      const timer = setTimeout(() => setProgressIdx(i), step.delay);
      progressTimers.current.push(timer);
    });
  }, []);

  const stopProgress = useCallback(() => {
    progressTimers.current.forEach(t => clearTimeout(t));
    progressTimers.current = [];
    setIsProcessing(false);
    setProgressIdx(0);
  }, []);

  const upsertDoc = useCallback((id: string, updates: Partial<UploadedDoc> & { name: string; size: number }) => {
    setUploadedDocs(prev => {
      const idx = prev.findIndex(d => d.id === id);
      if (idx >= 0) {
        const copy = [...prev];
        copy[idx] = { ...copy[idx], ...updates };
        return copy;
      }
      return [...prev, { id, name: updates.name, size: updates.size, s3Uri: updates.s3Uri || '', status: updates.status || 'uploading' }];
    });
  }, []);

  // Extract KPI indicators — 3-group layout: situation, minimums, strategy (+ simulation when requested)
  const extractIndicators = useCallback((text: string, chartData?: ChartBlock[], simulated?: boolean) => {
    // Indicators hold i18n KEYS, not resolved strings.
    //
    // They are built once when a response is parsed and then kept in state. If
    // t() were applied here, the cards would keep whatever language was active
    // at parse time and never re-translate on a language switch -- which is
    // exactly the bug this shape prevents. Group titles were always fine
    // because KeyHealthIndicators resolves those at render time.
    //
    // The shape lives in KeyHealthIndicators as HealthIndicator; label/tag
    // (literal) exist there for strings that genuinely cannot be translated:
    // model-supplied scenario names and computed values like "+62%".
    type Ind = HealthIndicator;
    const result: Ind[] = [];
    const symEsc = sym.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const moneyRe = `(?:S\\/|\\$|${symEsc})\\s*`;

    // ── Gather raw data from charts ──
    let totalDeuda = 0;
    if (chartData) {
      const debtChart = chartData.find(c => c.type === 'debtComposition');
      if (debtChart?.data && Array.isArray(debtChart.data)) {
        for (const item of debtChart.data) {
          totalDeuda += (item.saldo || 0);
        }
      }
    }
    if (totalDeuda === 0) {
      const m = text.match(new RegExp(`deuda\\s*total[:\\s]*${moneyRe}([\\d,.]+)`, 'i'))
        || text.match(new RegExp(`${moneyRe}([\\d,.]+).*deuda total`, 'i'));
      if (m) totalDeuda = parseFloat(m[1].replace(/,/g, ''));
    }

    // Extract alternatives data
    let minMeses = 0, minCosto = 0, bestMeses = 0, bestCosto = 0;
    // Which strategy won. The tools name it (Avalancha, Consolidación, Bola de
    // nieve); it used to be discarded, which left the "Estrategia Propuesta"
    // cards showing months and cost without saying what the plan actually was.
    let bestOpcion = '';
    if (chartData) {
      const altChart = chartData.find(c => c.type === 'alternatives');
      if (altChart?.data && Array.isArray(altChart.data)) {
        const minRow = altChart.data.find((d: any) => /m[ií]nimo/i.test(d.opcion || ''));
        if (minRow) { minMeses = minRow.plazo_meses || 0; minCosto = minRow.costo_total || 0; }
        const nonMinimos = altChart.data.filter((d: any) => !/m[ií]nimo/i.test(d.opcion || ''));
        if (nonMinimos.length > 0) {
          const best = nonMinimos.reduce((a: any, b: any) => (a.costo_total < b.costo_total ? a : b), nonMinimos[0]);
          if (best) { bestMeses = best.plazo_meses || 0; bestCosto = best.costo_total || 0; bestOpcion = String(best.opcion || ''); }
        }
      }
    }
    // Fallback from text
    if (bestMeses === 0) {
      const plazoPatterns = [
        /(?:te liberas|libre[s]?)\s*en\s*\*?\*?(\d+)\s*meses/i,
        /(\d+)\s*meses?\s*(?:total|menos|en lugar|antes|para liquidar|para pagar)/i,
        /plazo[:\s]*(\d+)\s*meses/i,
        /en\s*(\d+)\s*meses?\s*(?:podr[ií]as|liquidar|terminar|pagar)/i,
      ];
      for (const pat of plazoPatterns) { const m = text.match(pat); if (m) { bestMeses = parseInt(m[1]); break; } }
    }

    // ── GROUP 1: Tu Situación ──
    if (totalDeuda > 0) {
      result.push({
        labelKey: 'total_debt', group: 'situation',
        value: `${sym} ${Math.round(totalDeuda).toLocaleString()}`,
        tagKey: totalDeuda > 20000 ? 'high_risk' : totalDeuda > 10000 ? 'moderate' : 'low_risk',
        status: totalDeuda > 20000 ? 'danger' : totalDeuda > 10000 ? 'warning' : 'good',
      });
    }
    if (savedIncome && totalDeuda > 0) {
      const ing = parseFloat(savedIncome.replace(/,/g, ''));
      if (ing > 0) {
        const ratio = Math.round((totalDeuda / ing) * 100);
        result.push({
          labelKey: 'debt_income_ratio', group: 'situation',
          value: `${ratio}%`,
          tagKey: ratio > 40 ? 'critical' : ratio > 25 ? 'caution' : 'healthy',
          status: ratio > 40 ? 'danger' : ratio > 25 ? 'warning' : 'good',
        });
      }
    }
    // Intereses mensuales: se muestra solo si el backend lo incluye en los charts
    // (no calculamos en frontend — eso es responsabilidad del agente)

    // ── GROUP 2: Pagando Mínimos ──
    if (minMeses > 0) {
      result.push({
        labelKey: 'min_payoff_time', group: 'minimums',
        value: `${minMeses}`, unitKey: 'months',
        tagKey: minMeses > 36 ? 'long' : minMeses > 18 ? 'medium' : 'short',
        status: minMeses > 36 ? 'danger' : minMeses > 18 ? 'warning' : 'good',
      });
    }
    if (minCosto > 0) {
      result.push({
        labelKey: 'min_total_cost', group: 'minimums',
        value: `${sym} ${Math.round(minCosto).toLocaleString()}`,
        ...(totalDeuda > 0
          ? { tag: `+${Math.round(((minCosto - totalDeuda) / totalDeuda) * 100)}%` }
          : { tagKey: 'high' }),
        status: 'danger',
      });
    }

    // ── GROUP 3: Estrategia Propuesta ──
    if (bestMeses > 0) {
      result.push({
        labelKey: 'strategy_payoff_time', group: 'strategy', strategyName: bestOpcion,
        value: `${bestMeses}`, unitKey: 'months',
        tagKey: bestMeses > 24 ? 'long' : bestMeses > 12 ? 'medium' : 'short',
        status: bestMeses > 24 ? 'danger' : bestMeses > 12 ? 'warning' : 'good',
      });
    }
    if (bestCosto > 0) {
      result.push({
        labelKey: 'strategy_total_cost', group: 'strategy', strategyName: bestOpcion,
        value: `${sym} ${Math.round(bestCosto).toLocaleString()}`,
        ...(totalDeuda > 0
          ? { tag: `+${Math.round(((bestCosto - totalDeuda) / totalDeuda) * 100)}%` }
          : { tagKey: 'moderate' }),
        status: bestCosto > totalDeuda * 1.15 ? 'warning' : 'good',
      });
    }
    if (minCosto > 0 && bestCosto > 0 && minCosto > bestCosto) {
      const ahorro = minCosto - bestCosto;
      result.push({
        labelKey: 'savings', group: 'strategy', strategyName: bestOpcion,
        value: `${sym} ${Math.round(ahorro).toLocaleString()}`,
        tagKey: 'optimized',
        status: 'good',
      });
    }

    // ── Simulation (only when explicitly requested) ──
    if (simulated) {
      const simResult: Ind[] = [];
      // Extract from simulation chart data first (most reliable)
      if (chartData) {
        const simChart = chartData.find(c => c.type === 'simulation');
        if (simChart?.data && Array.isArray(simChart.data)) {
          for (const item of simChart.data) {
            const label = item.escenario || item.concepto || item.label || item.opcion || '';
            const costoTotal = item.costo_total || item.valor || item.monto || 0;
            const plazo = item.plazo_meses || item.meses || 0;
            if (plazo > 0) {
              simResult.push({
                // A scenario name comes from the model, so it stays literal.
                ...(label ? { label } : { labelKey: 'strategy_payoff_time' }),
                value: `${plazo}`, unitKey: 'months',
                tagKey: plazo > 24 ? 'long' : plazo > 12 ? 'medium' : 'short',
                status: plazo > 24 ? 'danger' : plazo > 12 ? 'warning' : 'good',
              });
            }
            if (costoTotal > 0) {
              simResult.push({
                labelKey: 'strategy_total_cost',
                ...(label ? { labelSuffix: label } : {}),
                value: `${sym} ${Math.round(costoTotal).toLocaleString()}`,
                tagKey: 'potential', status: 'good',
              });
            }
          }
          // Add savings row if we have both scenarios
          if (simChart.data.length >= 2) {
            const actual = simChart.data[0];
            const simulado = simChart.data[simChart.data.length - 1];
            if (actual.costo_total && simulado.costo_total) {
              const ahorro = actual.costo_total - simulado.costo_total;
              if (ahorro > 0) {
                simResult.push({
                  labelKey: 'estimated_savings',
                  value: `${sym} ${Math.round(ahorro).toLocaleString()}`,
                  tagKey: 'potential', status: 'good',
                });
              }
            }
          }
        }
      }
      // Fallback: extract from text via regex
      if (simResult.length === 0) {
        const ahorroM = text.match(new RegExp(`ahorr\\w*[:\\s]*${moneyRe}([\\d,.]+)`, 'i'));
        if (ahorroM) {
          const a = parseFloat(ahorroM[1].replace(/,/g, ''));
          if (a > 0) simResult.push({ labelKey: 'estimated_savings', value: `${sym} ${Math.round(a).toLocaleString()}`, tagKey: 'potential', status: 'good' });
        }
        const abonoM = text.match(new RegExp(`abono\\s*(?:extraordinario|extra|adicional)?[:\\s]*${moneyRe}([\\d,.]+)`, 'i'));
        if (abonoM) {
          const a = parseFloat(abonoM[1].replace(/,/g, ''));
          if (a > 0) simResult.push({ labelKey: 'extra_payment', value: `${sym} ${Math.round(a).toLocaleString()}`, tagKey: 'applied', status: 'good' });
        }
        // Also try to extract new plazo and new total cost from text
        const nuevoPlM = text.match(/(\d+)\s*meses/i);
        if (nuevoPlM) {
          const m = parseInt(nuevoPlM[1]);
          if (m > 0 && m < 360) simResult.push({ labelKey: 'strategy_payoff_time', value: `${m}`, unitKey: 'months', tagKey: m > 24 ? 'long' : m > 12 ? 'medium' : 'short', status: m > 24 ? 'danger' : m > 12 ? 'warning' : 'good' });
        }
        const nuevoCostoM = text.match(new RegExp(`costo\\s*total[:\\s]*${moneyRe}([\\d,.]+)`, 'i'));
        if (nuevoCostoM) {
          const c = parseFloat(nuevoCostoM[1].replace(/,/g, ''));
          if (c > 0) simResult.push({ labelKey: 'strategy_total_cost', value: `${sym} ${Math.round(c).toLocaleString()}`, tagKey: 'optimized', status: 'good' });
        }
      }
      return simResult.map(r => ({ ...r, simulated: true }));
    }
    return result;
    // No t() here on purpose: indicators carry keys and are translated at render
    // time, so this does not need to re-run when the language changes.
  }, [savedIncome, sym]);

  // ── Session restoration: load last analysis on login ──
  const restoredRef = useRef(false);
  useEffect(() => {
    if (restoredRef.current || userId === 'demo_user') return;
    restoredRef.current = true;
    (async () => {
      try {
        const res = await authFetch(`${API_URL}/last-analysis/${userId}`);
        if (!res.ok) return;
        const data = await res.json();
        if (!data.found || !data.result) return;
        const { parseResponse } = await import('./utils/parseResponse');
        const parsed = parseResponse(data.result);
        const uniqueCharts = Array.from(
          parsed.charts.reduce((map, chart) => map.set(chart.type, chart), new Map<string, ChartBlock>()).values()
        );
        if (uniqueCharts.length > 0) {
          setCharts(uniqueCharts);
          const kpis = extractIndicators(parsed.text, uniqueCharts, false);
          if (kpis.length > 0) setIndicators(kpis);
          setActiveTab('analysis');
          // Restore session_id from last analysis
          if (data.session_id) {
            sessionIdRef.current = data.session_id;
            localStorage.setItem(`finhealth_session_${userId}`, data.session_id);
          }
          // Add the result to chat history (skip KPI update to avoid duplication)
          if (chatRef.current) {
            skipNextKpiUpdate.current = true;
            chatRef.current.addExternalMessage('assistant', data.result);
          }
        }
      } catch (err) {
        console.error('Error restoring session:', err);
      }
    })();
  }, [userId, API_URL, extractIndicators]);

  const pollJob = useCallback(async (jobId: string): Promise<JobResult> => {
    const POLL_INTERVAL = 5000;
    const MAX_POLLS = 120;
    for (let i = 0; i < MAX_POLLS; i++) {
      await new Promise(r => setTimeout(r, POLL_INTERVAL));
      const res = await authFetch(`${API_URL}/job/${jobId}`);
      if (!res.ok) continue;
      const data = await res.json();
      if (data.status === 'COMPLETED' || data.status === 'FAILED') return data;
    }
    throw new Error('Timeout: el procesamiento tardó demasiado');
  }, [API_URL]);

  const handleUploadComplete = useCallback(async (s3Uris: string[]) => {
    const { parseResponse } = await import('./utils/parseResponse');
    const names = s3Uris.map(u => u.split('/').pop() || u).join(', ');
    setUploadedDocs(prev => prev.map(d => s3Uris.includes(d.s3Uri) ? { ...d, status: 'analyzing' as const } : d));
    startProgress();
    try {
      const incomeNote = savedIncome ? ` Mi ingreso mensual es ${sym} ${savedIncome}.` : '';
      const hasHistory = charts.length > 0 || localStorage.getItem(`finhealth_session_${userId}`) !== null;
      const evolutionNote = hasHistory
        ? ' IMPORTANTE: Ya tengo un análisis previo. Compara los nuevos estados de cuenta con los datos anteriores. Muestra la EVOLUCIÓN de mi deuda (si mejoró o empeoró) y actualiza la estrategia considerando mi progreso.'
        : '';
      const prompt = `He subido ${s3Uris.length} estado(s) de cuenta: ${names}.${incomeNote}${evolutionNote} `
        + `Por favor: 1) Extrae los datos de estos PDFs, 2) Analiza mi salud financiera y genera un plan de pagos optimizado, `
        + `3) Detecta gastos hormiga, 4) Dame una estrategia de mejora. usuario_id: ${userId}`;
      const dispatchRes = await authFetch(`${API_URL}/invoke`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt, usuario_id: userId,
          contexto: { pdfs: s3Uris },
          session_id: sessionIdRef.current,
          country: country.code, currency: country.currency, language,
          payment_behavior: paymentBehavior,
        }),
      });
      if (!dispatchRes.ok) throw new Error(`HTTP ${dispatchRes.status}`);
      const dispatch = await dispatchRes.json();
      if (!dispatch.success) throw new Error(dispatch.error || 'Error al iniciar procesamiento');
      const data = await pollJob(dispatch.job_id);
      if (data.status === 'FAILED') throw new Error(data.error || 'Error en el procesamiento');
      setUploadedDocs(prev => prev.map(d => d.status === 'analyzing' ? { ...d, status: 'analyzed' } : d));
      stopProgress();
      // Reload docs from backend to get proper format (banco, tarjeta, fecha)
      try {
        const docsRes = await authFetch(`${API_URL}/user-documents/${userId}`);
        if (docsRes.ok) {
          const docsData = await docsRes.json();
          if (docsData.documents?.length > 0) {
            setUploadedDocs(docsData.documents.map((doc: any) => ({
              id: doc.file_hash || doc.tarjeta_id,
              name: `${doc.banco} ****${doc.ultimos_4_digitos}`,
              size: 0,
              s3Uri: doc.source_s3_key ? `s3://${docsData.bucket}/${doc.source_s3_key}` : '',
              status: 'analyzed' as const,
              banco: doc.banco,
              ultimos4: doc.ultimos_4_digitos,
              fechaCorte: doc.fecha_corte,
              dbStatus: doc.status,
            })));
          }
        }
      } catch (_) { /* ignore reload error */ }
      if (data.result) {
        const parsed = parseResponse(data.result);
        const uniqueCharts = Array.from(parsed.charts.reduce((map, chart) => map.set(chart.type, chart), new Map<string, ChartBlock>()).values());
        if (uniqueCharts.length > 0) {
          setCharts(uniqueCharts);
          // Update KPIs immediately with the new charts
          const kpis = extractIndicators(parsed.text, uniqueCharts, false);
          if (kpis.length > 0) setIndicators(kpis);
        }
        if (chatRef.current) {
          // Skip the next KPI update from handleAssistantResponse to prevent duplication
          skipNextKpiUpdate.current = true;
          chatRef.current.addExternalMessage('user', `Analiza mis ${s3Uris.length} estado(s) de cuenta: ${names}`);
          chatRef.current.addExternalMessage('assistant', data.result);
        }
      }
      setActiveTab('analysis');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (err) {
      console.error('Error en procesamiento:', err);
      stopProgress();
      setUploadedDocs(prev => prev.map(d => d.status === 'analyzing' ? { ...d, status: 'error' } : d));
      if (chatRef.current) {
        const errorMsg = err instanceof Error ? err.message : 'Error desconocido';
        chatRef.current.addExternalMessage('user', `Analiza mis ${s3Uris.length} estado(s) de cuenta: ${names}`);
        chatRef.current.addExternalMessage('assistant', `⚠️ ${errorMsg}`);
      }
      setActiveTab('analysis');
    }
  }, [savedIncome, userId, API_URL, startProgress, stopProgress, extractIndicators, pollJob, sym, country, language]);

  const handleSaveIncome = () => {
    if (!income.trim()) return;
    setSavedIncome(income);
  };

  // Track whether user explicitly requested a simulation
  const userRequestedSimulation = useRef(false);

  // Skip flag: when handleUploadComplete already processed KPIs, skip the next handleAssistantResponse KPI update
  const skipNextKpiUpdate = useRef(false);

  // Keep chartsRef in sync with charts state
  useEffect(() => { chartsRef.current = charts; }, [charts]);

  const handleAssistantResponse = useCallback((text: string, parsedCharts: ChartBlock[], userMessage?: string) => {
    if (parsedCharts.length > 0) {
      setCharts(prev => {
        const merged = [...prev, ...parsedCharts];
        return Array.from(merged.reduce((map, chart) => map.set(chart.type, chart), new Map<string, ChartBlock>()).values());
      });
    }

    // If handleUploadComplete already set KPIs for this response, skip to avoid duplication
    if (skipNextKpiUpdate.current) {
      skipNextKpiUpdate.current = false;
      return;
    }

    // Use ref for latest charts to avoid stale closure
    const currentCharts = chartsRef.current;
    const allCharts = parsedCharts.length > 0
      ? Array.from([...currentCharts, ...parsedCharts].reduce((map, c) => map.set(c.type, c), new Map<string, ChartBlock>()).values())
      : currentCharts;

    // Only treat as simulation if user explicitly asked for one
    if (userMessage && /simul|qu[eé]\s*pasa\s*si|escenario|hipot[eé]tic/i.test(userMessage)) {
      userRequestedSimulation.current = true;
    }

    // Detect simulation: chart-based OR text-based when user requested it
    const hasSimChart = parsedCharts.some(c => c.type === 'simulation');
    const hasSimText = userRequestedSimulation.current && /escenario simulado|simulaci[oó]n|si\s+(abonas?|pagas?|adelantas?|aumentas?)/i.test(text);
    const isSimulation = userRequestedSimulation.current && (hasSimChart || hasSimText);

    const kpis = extractIndicators(text, allCharts, isSimulation);
    if (kpis.length > 0) {
      if (isSimulation) {
        // Replace simulation indicators, keep base ones
        setIndicators(prev => { const originals = prev.filter(p => !p.simulated); return [...originals, ...kpis]; });
        userRequestedSimulation.current = false;
      } else if (parsedCharts.length > 0) {
        // Replace base indicators, keep simulation ones
        setIndicators(prev => { const simulated = prev.filter(p => p.simulated); return [...kpis, ...simulated]; });
      }
    }
  }, [extractIndicators]);

  const handleDeleteDocument = useCallback(async (fileHash: string) => {
    if (!confirm(t('confirm_delete') || '¿Eliminar este documento y sus datos asociados?')) return;
    try {
      const res = await authFetch(`${API_URL}/documents/${userId}/${fileHash}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setUploadedDocs(prev => prev.filter(d => d.id !== fileHash));
      if (data.remaining_documents === 0) {
        setCharts([]);
        setIndicators([]);
      } else if (data.invalidated_analyses > 0) {
        setCharts([]);
        setIndicators([]);
      }
    } catch (err) {
      console.error('Error deleting document:', err);
    }
  }, [userId, API_URL, t]);

  const handleAnalyzeExisting = useCallback(async () => {
    try {
      const docsRes = await authFetch(`${API_URL}/user-documents/${userId}`);
      if (!docsRes.ok) return;
      const docsData = await docsRes.json();
      const bucket = docsData.bucket || '';
      const s3Uris = (docsData.documents || [])
        .map((d: any) => d.source_s3_key ? `s3://${bucket}/${d.source_s3_key}` : '')
        .filter(Boolean);
      if (s3Uris.length > 0) {
        handleUploadComplete(s3Uris);
      }
    } catch (err) {
      console.error('Error triggering analysis:', err);
    }
  }, [userId, API_URL, handleUploadComplete]);

  const progressPct = isProcessing ? Math.min(((progressIdx + 1) / PROGRESS_STEPS.length) * 100, 95) : 0;

  return (
    <div className="app">
      <ConsentBanner t={t} />
      {showProfile && (
        <ProfileSettings
          currentCountry={country.code}
          currentLanguage={language}
          currentIncome={savedIncome}
          currentPaymentBehavior={paymentBehavior}
          onSave={handleProfileSave}
          onClose={() => setShowProfile(false)}
          t={t}
        />
      )}

      <header>
        <div className="header-inner">
          <div className="header-wordmark"><Icon name="flame" className="wordmark-icon" /> {t('app_name')} <span className="header-tagline">{t('tagline')}</span></div>
          <div className="header-right">
            <nav className="header-nav">
              <button className={`nav-tab ${activeTab === 'analysis' ? 'active' : ''}`} onClick={() => setActiveTab('analysis')}>
                {t('analysis')}
              </button>
              <button className={`nav-tab ${activeTab === 'evolution' ? 'active' : ''}`} onClick={() => setActiveTab('evolution')}>
                {t('evolution')}
              </button>
              <button className={`nav-tab ${activeTab === 'documents' ? 'active' : ''}`} onClick={() => setActiveTab('documents')}>
                {t('documents')}
              </button>
            </nav>
            {userEmail && <span className="user-email">{userEmail.split('@')[0].charAt(0).toUpperCase() + userEmail.split('@')[0].slice(1)}</span>}
            <button className="profile-btn" onClick={() => setShowProfile(true)} title={t('profile')}><Icon name="user" label={t('profile')} /></button>
            <button className="logout-btn" onClick={signOut}>{t('logout')}</button>
            <div className="header-status">{t('online')}</div>
          </div>
        </div>
      </header>

      <main>
        {/* Analysis view */}
        <div style={{ display: activeTab === 'analysis' ? undefined : 'none' }}>
          <div className="analysis-view">
            <div className="analysis-left">
              <KeyHealthIndicators
                indicators={indicators}
                onDismissScenario={() => setIndicators(prev => prev.filter(p => !p.simulated))}
                t={t}
              />
              <div className="graphics-section">
                <div className="section-header"><h2>{t('detailed_analysis')}</h2></div>
                {charts.length > 0 ? (
                  <div className="charts-grid">
                    {charts.map((chart, i) => (
                      <div key={i} className="chart-section">
                        {chart.title && <h3>{chart.title}</h3>}
                        <ChartRenderer chart={chart} t={t} />
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="info-text">{t('charts_placeholder')}</p>
                )}
              </div>
            </div>
            <div className="analysis-right">
              <Chat
                ref={chatRef}
                userId={userId}
                sessionId={sessionIdRef.current}
                sessionIdRef={sessionIdRef as React.MutableRefObject<string | null>}
                s3Uris={uploadedDocs.filter(d => d.status === 'analyzed').map(d => d.s3Uri)}
                onAssistantResponse={handleAssistantResponse}
                savedIncome={savedIncome}
                country={country.code}
                currency={country.currency}
                language={language}
                currencySymbol={sym}
                paymentBehavior={paymentBehavior}
                userName={userEmail ? userEmail.split('@')[0].charAt(0).toUpperCase() + userEmail.split('@')[0].slice(1) : ''}
                t={t}
              />
            </div>
          </div>
        </div>

        {/* Evolution view */}
        {activeTab === 'evolution' && (
          <FinancialEvolution userId={userId} apiUrl={API_URL} currencySymbol={sym} language={language} />
        )}

        {/* Documents view */}
        {activeTab === 'documents' && (
          <div className="documents-view">
            <div className="documents-left">
              <div className="profile-section">
                <div className="section-label">{t('financial_profile')}</div>
                <label className="income-label">{t('monthly_income')} ({sym})</label>
                <div className="income-row">
                  <input type="text" className="income-input" value={income} onChange={(e) => setIncome(e.target.value)} placeholder={t('income_placeholder')} />
                  <button className="save-btn" onClick={handleSaveIncome}>{t('save')}</button>
                </div>
                {savedIncome && <div className="income-saved"><Icon name="check" /> {t('income_saved')}: {sym} {savedIncome}</div>}
              </div>
              <div className="upload-section">
                <PdfUploader userId={userId} knownHashes={knownHashes} onUploadComplete={handleUploadComplete} onDocUpdate={upsertDoc} onNotify={(msg, type) => { setNotification({ message: msg, type }); setTimeout(() => setNotification(null), 8000); }} t={t} />
              </div>
            </div>
            <div className="documents-right">
              <div className="section-label">{t('uploaded_documents')}</div>
              {notification && (
                <div className={`notification-banner notification-${notification.type}`}>
                  <span>{notification.message}</span>
                  <button onClick={() => setNotification(null)}>×</button>
                </div>
              )}
              {isProcessing && (
                <div className="processing-indicator">
                  <div className="progress-bar-track"><div className="progress-bar-fill" style={{ width: `${progressPct}%` }} /></div>
                  <div className="progress-step">
                    <span className="progress-icon"><Icon name={PROGRESS_STEPS[progressIdx].icon} /></span>
                    <span className="progress-label">{t(PROGRESS_STEPS[progressIdx].labelKey)}</span>
                  </div>
                </div>
              )}
              {uploadedDocs.length === 0 && !isProcessing ? (
                <p className="info-text">{t('docs_placeholder')}</p>
              ) : (
                <div className="docs-list">
                  {uploadedDocs.map((doc) => (
                    <div key={doc.id} className={`doc-item doc-${doc.status}`}>
                      <div className="doc-col doc-col-date">{doc.fechaCorte ? doc.fechaCorte.replace(/^\d+\//, '') : ''}</div>
                      <div className="doc-col doc-col-banco">{doc.banco || doc.name}</div>
                      <div className="doc-col doc-col-tarjeta">{doc.ultimos4 ? `****${doc.ultimos4}` : ''}</div>
                      <div className="doc-col doc-col-status">
                        {doc.status === 'uploading' && <><Icon name="document" /> {t('uploading')}</>}
                        {doc.status === 'uploaded' && <><Icon name="check" /> {t('uploaded')}</>}
                        {doc.status === 'analyzing' && <><Icon name="search" /> {t('analyzing')}</>}
                        {doc.status === 'analyzed' && <><Icon name="check-circle" /> {t('analyzed')}</>}
                        {doc.status === 'error' && <><Icon name="x" /> {t('error')}</>}
                      </div>
                      {doc.status === 'analyzed' && (
                        <button className="doc-delete-btn" onClick={() => handleDeleteDocument(doc.id)}><Icon name="trash" label={t('consent_close')} /></button>
                      )}
                    </div>
                  ))}
                  {uploadedDocs.some(d => d.status === 'analyzed') && !isProcessing && (
                    <button className="analyze-btn" onClick={handleAnalyzeExisting}>
                      <Icon name="chart" /> {t('analyze')}
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function App() {
  return (
    <Authenticator loginMechanisms={['email']} hideSignUp={true}>
      <AppContent />
    </Authenticator>
  );
}

export default App;
