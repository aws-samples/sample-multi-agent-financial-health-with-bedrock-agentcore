// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import type { ChartBlock } from '../utils/parseResponse';
import { DebtEvolution } from './charts/DebtEvolution';
import { InterestArea } from './charts/InterestArea';
import { DebtComposition } from './charts/DebtComposition';
import { SpendingPie } from './charts/SpendingPie';
import { Simulation } from './charts/Simulation';
import { Alternatives } from './charts/Alternatives';

interface ChartRendererProps {
  chart: ChartBlock;
  t: (key: string) => string;
}

export function ChartRenderer({ chart, t }: ChartRendererProps) {
  switch (chart.type) {
    case 'debtEvolution':
      return <DebtEvolution data={chart.data} t={t} />;
    case 'interestArea':
      return <InterestArea data={chart.data} t={t} />;
    case 'debtComposition':
      return <DebtComposition data={chart.data} />;
    case 'spendingPie':
      return <SpendingPie data={chart.data} />;
    case 'simulation':
      return <Simulation data={chart.data} />;
    case 'alternatives':
      return <Alternatives data={chart.data} />;
    default:
      return null;
  }
}
