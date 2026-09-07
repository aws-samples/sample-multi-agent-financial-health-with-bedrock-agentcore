// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
//
// Inline SVG icon set for the interface chrome.
//
// Emoji were used here originally. They render differently on every platform,
// carry their own colour that ignores the surrounding text, and read as
// informal in a financial product. These are stroke icons that inherit
// currentColor and the surrounding font size, so they sit correctly in buttons
// and labels.
//
// Emoji in chat messages are deliberately untouched: those come from the model
// and they help a reader scan a long answer.

import type { CSSProperties, ReactElement } from 'react';

export type IconName =
  | 'flame'
  | 'user'
  | 'trash'
  | 'chart'
  | 'document'
  | 'search'
  | 'check'
  | 'check-circle'
  | 'x'
  | 'alert'
  | 'layers'
  | 'coins'
  | 'lightbulb';

interface IconProps {
  name: IconName;
  /** Size in px. Defaults to 1em so the icon tracks the surrounding font size. */
  size?: number | string;
  className?: string;
  style?: CSSProperties;
  /** Decorative by default. Pass a label when the icon is the only content. */
  label?: string;
}

// ReactElement rather than JSX.Element: React 19 removed the global JSX namespace.
const PATHS: Record<IconName, ReactElement> = {
  // A single closed silhouette plus one inner curve. Three overlapping strokes
  // were tried first and read as a smudge at 16px.
  flame: (
    <>
      <path d="M12 2.8c3.4 3.3 5.2 5.9 5.2 8.8a5.2 5.2 0 0 1-10.4 0c0-2.9 1.8-5.5 5.2-8.8z" />
      <path d="M12 12.6c1.2 1.1 1.8 2 1.8 2.9a1.8 1.8 0 0 1-3.6 0c0-.9.6-1.8 1.8-2.9z" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5 20c0-3.3 3.1-5.5 7-5.5s7 2.2 7 5.5" />
    </>
  ),
  trash: (
    <>
      <path d="M4 7h16" />
      <path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
      <path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12" />
      <path d="M10 11v6M14 11v6" />
    </>
  ),
  chart: (
    <>
      <path d="M4 20h16" />
      <path d="M7 20v-6M12 20V7M17 20v-9" />
    </>
  ),
  document: (
    <>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6" />
      <path d="M15.5 15.5L20 20" />
    </>
  ),
  check: <path d="M5 12.5l4.5 4.5L19 7" />,
  'check-circle': (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M8.5 12.5l2.5 2.5 4.5-5" />
    </>
  ),
  x: <path d="M6 6l12 12M18 6L6 18" />,
  alert: (
    <>
      <path d="M12 4.5L21 19.5H3z" />
      <path d="M12 10v4" />
      <path d="M12 16.8v.2" />
    </>
  ),
  layers: (
    <>
      <path d="M12 3l8 4.5-8 4.5-8-4.5z" />
      <path d="M4 12.5l8 4.5 8-4.5" />
      <path d="M4 16.5l8 4.5 8-4.5" />
    </>
  ),
  coins: (
    <>
      <ellipse cx="9" cy="7" rx="5" ry="2.5" />
      <path d="M4 7v4c0 1.4 2.2 2.5 5 2.5s5-1.1 5-2.5V7" />
      <path d="M10 15.6c.9.6 2.4 1 4 1 2.8 0 5-1.1 5-2.5v-4" />
      <ellipse cx="15" cy="10" rx="4" ry="2" />
    </>
  ),
  lightbulb: (
    <>
      <path d="M9 17h6" />
      <path d="M10 21h4" />
      <path d="M12 3a6 6 0 0 0-3.5 10.9c.3.2.5.6.5 1v.6h6v-.6c0-.4.2-.8.5-1A6 6 0 0 0 12 3z" />
    </>
  ),
};

export function Icon({ name, size = '1em', className, style, label }: IconProps) {
  const path = PATHS[name];
  if (!path) return null;
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={{ flex: '0 0 auto', verticalAlign: '-0.125em', ...style }}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      {path}
    </svg>
  );
}
