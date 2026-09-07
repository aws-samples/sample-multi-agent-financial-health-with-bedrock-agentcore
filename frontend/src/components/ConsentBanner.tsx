// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { useState } from 'react';

interface ConsentBannerProps {
  t: (key: string) => string;
}

export function ConsentBanner({ t }: ConsentBannerProps) {
  const [visible, setVisible] = useState(true);

  if (!visible) return null;

  return (
    <div className="consent-banner">
      <div className="consent-content">
        <div className="consent-text">
          <h3>{t('consent_title')}</h3>
          <p>{t('consent_text')}</p>
          <ul>
            <li>{t('consent_no_share')}</li>
            <li>{t('consent_encrypted')}</li>
            <li>{t('consent_estimates')}</li>
            <li>{t('consent_no_banks')}</li>
          </ul>
        </div>
        <div className="consent-actions">
          <button onClick={() => setVisible(false)} className="accept-button">
            {t('consent_accept')}
          </button>
          <button onClick={() => setVisible(false)} className="decline-button">
            {t('consent_close')}
          </button>
        </div>
      </div>
    </div>
  );
}
