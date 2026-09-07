// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
export interface ChartBlock {
  type: 'debtEvolution' | 'interestArea' | 'debtComposition' | 'spendingPie' | 'simulation' | 'alternatives';
  data: any;
  title?: string;
}

export interface ParsedResponse {
  text: string;
  charts: ChartBlock[];
}

const CHART_REGEX = /:::chart\s*(\{[\s\S]*?\})\s*:::/g;

export function parseResponse(content: string): ParsedResponse {
  const charts: ChartBlock[] = [];
  let text = content;

  for (const match of content.matchAll(CHART_REGEX)) {
    try {
      const chartData = JSON.parse(match[1]);
      charts.push(chartData);
      text = text.replace(match[0], '');
    } catch (err) {
      console.error('Error parseando chart:', err);
    }
  }

  return {
    text: text.trim(),
    charts,
  };
}
