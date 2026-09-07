// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
export interface HealthIndicator {
  /** i18n key, resolved here at render time so a language switch takes effect. */
  labelKey?: string;
  /** Literal label, for strings that cannot be translated (model scenario names). */
  label?: string;
  /** Appended in parentheses after the label. Literal. */
  labelSuffix?: string;
  value: string;
  /** i18n key for a unit appended to the value, for example "months". */
  unitKey?: string;
  /** i18n key for the badge. */
  tagKey?: string;
  /** Literal badge, for computed values like "+62%". */
  tag?: string;
  status: 'good' | 'warning' | 'danger';
  simulated?: boolean;
  group?: 'situation' | 'minimums' | 'strategy';
  /** Which strategy won, as named by the tools. Carried on strategy-group items. */
  strategyName?: string;
}

interface KeyHealthIndicatorsProps {
  indicators?: HealthIndicator[];
  onDismissScenario?: () => void;
  t: (key: string) => string;
}

/** Map a tool-supplied strategy name onto a short explanation key. */
function strategyHintKey(name: string): string {
  const n = name.toLowerCase();
  if (/avalanch/.test(n)) return 'strategy_hint_avalanche';
  if (/bola de nieve|snowball/.test(n)) return 'strategy_hint_snowball';
  if (/consolida/.test(n)) return 'strategy_hint_consolidation';
  return 'strategy_hint_generic';
}

export function KeyHealthIndicators({ indicators, onDismissScenario, t }: KeyHealthIndicatorsProps) {
  const data = indicators || [];

  if (data.length === 0) {
    return (
      <div className="key-health-indicators">
        <div className="section-label">{t('kpi_title')}</div>
        <p className="info-text">
          {t('kpi_empty')}
        </p>
      </div>
    );
  }

  const situation = data.filter(d => !d.simulated && d.group === 'situation');
  const minimums = data.filter(d => !d.simulated && d.group === 'minimums');
  const strategy = data.filter(d => !d.simulated && d.group === 'strategy');
  const simulated = data.filter(d => d.simulated);
  const ungrouped = data.filter(d => !d.simulated && !d.group);

  const strategyName = strategy.find(d => d.strategyName)?.strategyName || '';

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'good': return '#1e6b4a';
      case 'warning': return '#b07d2a';
      case 'danger': return '#c0392b';
      default: return '#888884';
    }
  };

  const getStatusBg = (status: string) => {
    switch (status) {
      case 'good': return '#e8f5ef';
      case 'warning': return '#fdf6e3';
      case 'danger': return '#fdf0ef';
      default: return '#f5f4f0';
    }
  };

  const labelOf = (ind: HealthIndicator) => {
    const base = ind.labelKey ? t(ind.labelKey) : (ind.label ?? '');
    return ind.labelSuffix ? `${base} (${ind.labelSuffix})` : base;
  };
  const valueOf = (ind: HealthIndicator) =>
    ind.unitKey ? `${ind.value} ${t(ind.unitKey)}` : ind.value;
  const tagOf = (ind: HealthIndicator) =>
    ind.tagKey ? t(ind.tagKey) : (ind.tag ?? '');

  const renderCard = (ind: HealthIndicator, i: number) => (
    <div key={i} className="indicator-card">
      <div className="indicator-label">{labelOf(ind)}</div>
      <div className="indicator-value" style={{ color: getStatusColor(ind.status) }}>
        {valueOf(ind)}
      </div>
      <div className="indicator-tag" style={{ background: getStatusBg(ind.status), color: getStatusColor(ind.status) }}>
        {tagOf(ind)}
      </div>
    </div>
  );

  const renderCards = (items: HealthIndicator[], cols?: number) => (
    <div className="indicators-grid" style={cols ? { gridTemplateColumns: `repeat(${cols}, 1fr)` } : undefined}>
      {items.map(renderCard)}
    </div>
  );

  const renderGroup = (title: string, items: HealthIndicator[], className?: string, detail?: React.ReactNode) => {
    if (items.length === 0) return null;
    return (
      <div className={`kpi-group ${className || ''}`}>
        <div className="kpi-group-title">
          <span>{title}</span>
          {detail}
        </div>
        {renderCards(items, items.length)}
      </div>
    );
  };

  // Name the winning strategy next to the group title. Without it the cards
  // showed a term and a cost with no indication of what the plan was, which did
  // not tie back to the chat.
  const strategyDetail = strategyName ? (
    <span className="kpi-group-detail">
      <strong>{strategyName}</strong>
      <span className="kpi-group-hint">{t(strategyHintKey(strategyName))}</span>
    </span>
  ) : undefined;

  return (
    <div className="key-health-indicators">
      <div className="section-label">{t('kpi_title')}</div>
      {ungrouped.length > 0 && renderCards(ungrouped)}
      {renderGroup(t('section_situation'), situation)}
      {renderGroup(t('section_minimums'), minimums, 'kpi-group-minimums')}
      {renderGroup(t('section_strategy'), strategy, 'kpi-group-strategy', strategyDetail)}
      {simulated.length > 0 && (
        <div className="scenario-section">
          <div className="scenario-header">
            <span className="scenario-title">{t('section_simulation')}</span>
            {onDismissScenario && (
              <button className="scenario-dismiss" onClick={onDismissScenario} aria-label={t('consent_close')}>&times;</button>
            )}
          </div>
          <div className="indicators-grid scenario-grid" style={{ gridTemplateColumns: `repeat(${simulated.length}, 1fr)` }}>
            {simulated.map(renderCard)}
          </div>
        </div>
      )}
    </div>
  );
}
