// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React from 'react';
import { Icon } from './Icon';

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends React.Component<React.PropsWithChildren, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '2rem', textAlign: 'center' }}>
          <h2><Icon name="alert" /> Algo salió mal / Something went wrong</h2>
          <p>Ocurrió un error inesperado. Por favor recarga la página.</p>
          <button onClick={() => window.location.reload()} style={{ padding: '8px 16px', cursor: 'pointer' }}>
            Recargar
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
