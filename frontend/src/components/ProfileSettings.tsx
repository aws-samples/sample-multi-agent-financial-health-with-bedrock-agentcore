// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { useState } from 'react';
import { COUNTRIES, getCountryByCode } from '../utils/countries';

interface ProfileSettingsProps {
  currentCountry: string;
  currentLanguage: string;
  currentIncome: string;
  currentPaymentBehavior: string;
  onSave: (country: string, language: string, income: string, paymentBehavior: string) => void;
  onClose: () => void;
  t: (key: string) => string;
}

export function ProfileSettings({ currentCountry, currentLanguage, currentIncome, currentPaymentBehavior, onSave, onClose, t }: ProfileSettingsProps) {
  const [countryCode, setCountryCode] = useState(currentCountry); // nosemgrep: react-props-in-state
  const [lang, setLang] = useState(currentLanguage); // nosemgrep: react-props-in-state
  const [inc, setInc] = useState(currentIncome); // nosemgrep: react-props-in-state
  const [payBehavior, setPayBehavior] = useState(currentPaymentBehavior); // nosemgrep: react-props-in-state

  const selected = getCountryByCode(countryCode);

  return (
    <div className="profile-overlay" onClick={onClose}>
      <div className="profile-modal" onClick={e => e.stopPropagation()}>
        <div className="profile-modal-header">
          <span>{t('profile_title')}</span>
          <button className="profile-close" onClick={onClose}>&times;</button>
        </div>
        <div className="profile-modal-body">
          <label className="profile-field-label">{t('profile_country')}</label>
          <select value={countryCode} onChange={e => setCountryCode(e.target.value)} className="profile-select">
            {COUNTRIES.map(c => <option key={c.code} value={c.code}>{c.name}</option>)}
          </select>

          <label className="profile-field-label">{t('profile_currency')}</label>
          <div className="profile-readonly">{selected.currency} ({selected.symbol})</div>

          <label className="profile-field-label">{t('profile_fin_term')}</label>
          <div className="profile-readonly">{selected.finTerm} — {selected.finTermFull}</div>

          <label className="profile-field-label">{t('profile_income_label')} ({selected.symbol})</label>
          <input type="text" value={inc} onChange={e => setInc(e.target.value)} className="profile-input" placeholder={t('income_placeholder')} />

          <label className="profile-field-label">{t('profile_language')}</label>
          <select value={lang} onChange={e => setLang(e.target.value)} className="profile-select">
            <option value="es">Español</option>{/* nosemgrep: jsx-not-internationalized */}
            <option value="en">English</option>{/* nosemgrep: jsx-not-internationalized */}
          </select>
          {/* Deliberately quiet, and shown here rather than on the analysis page:
              this is the moment the expectation is set. The interface translates
              immediately, but an analysis that already exists keeps the language
              it was generated in, and a user who is not told that reads it as a
              bug. */}
          <p className="profile-field-hint">{t('language_hint')}</p>

          <label className="profile-field-label">{t('profile_payment_behavior')}</label>
          <div className="profile-radio-group">
            <label className={`profile-radio-option${payBehavior === 'minimum' ? ' selected' : ''}`}>
              <input type="radio" name="payBehavior" value="minimum" checked={payBehavior === 'minimum'} onChange={e => setPayBehavior(e.target.value)} />
              <span>{t('payment_minimum')}</span>
            </label>
            <label className={`profile-radio-option${payBehavior === 'period' ? ' selected' : ''}`}>
              <input type="radio" name="payBehavior" value="period" checked={payBehavior === 'period'} onChange={e => setPayBehavior(e.target.value)} />
              <span>{t('payment_period')}</span>
            </label>
          </div>
        </div>
        <div className="profile-modal-footer">
          <button className="profile-cancel" onClick={onClose}>{t('profile_cancel')}</button>
          <button className="profile-save" onClick={() => onSave(countryCode, lang, inc, payBehavior)}>{t('save')}</button>
        </div>
      </div>
    </div>
  );
}
