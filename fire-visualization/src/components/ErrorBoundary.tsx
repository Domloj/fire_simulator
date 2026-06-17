import React from 'react';

type Props = { children: React.ReactNode };

type State = { hasError: boolean; error?: Error; info?: React.ErrorInfo };

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Update state so the next render shows the fallback UI.
    this.setState({ hasError: true, error, info });
    // Log the error (console and window) for debugging
    // eslint-disable-next-line no-console
    try {
      // attach to window for easier manual inspection in devtools
      // eslint-disable-next-line @typescript-eslint/ban-ts-comment
      // @ts-ignore
      window.__LAST_REACT_ERROR__ = { error, info };
    } catch (e) {
      // ignore
    }
  }

  render() {
    if (this.state.hasError) {
      // Render a minimal fallback UI that doesn't crash overlay
      return (
        <div style={{ padding: '1rem', background: '#fff5f5', color: '#611', border: '1px solid #faa' }}>
          <h3>Something went wrong in the map component</h3>
          <p>Please check the browser console for details.</p>
        </div>
      );
    }

    return this.props.children;
  }
}
