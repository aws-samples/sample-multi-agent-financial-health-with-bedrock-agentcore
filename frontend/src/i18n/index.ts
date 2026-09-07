// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { useCallback } from 'react';
import es from './es.json';
import en from './en.json';

const translations: Record<string, Record<string, string>> = { es, en };

export function useTranslation(language: string = 'es') {
  const lang = translations[language] ? language : 'es';
  const t = useCallback(
    (key: string): string => translations[lang]?.[key] ?? translations['es']?.[key] ?? key,
    [lang],
  );
  return { t, language: lang };
}
