import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { stubFetch } from '../../test/apiMocks';
import { AIInsightPanel } from './AIInsightPanel';

const INSIGHT = {
  id: 1,
  request_id: 1,
  calculation_id: 42,
  comparison_id: null,
  provider: 'anthropic',
  model: 'claude-sonnet-5-20260101',
  generated_text: 'Gross is $150,000.00, and net compensation after tax is $113,791.00.',
  created_at: '2026-08-16T00:00:00Z',
  cached: false,
};

describe('AIInsightPanel', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows a generate button and explanation before anything is requested', () => {
    stubFetch({});
    render(<AIInsightPanel target={{ calculationId: 42 }} />);

    expect(screen.getByRole('button', { name: 'Generate AI insight' })).toBeInTheDocument();
    expect(screen.queryByText(/AI-generated interpretation/)).not.toBeInTheDocument();
  });

  it('shows the generated text clearly labeled as AI-generated on success', async () => {
    stubFetch({ createAIInsight: INSIGHT });
    render(<AIInsightPanel target={{ calculationId: 42 }} />);

    fireEvent.click(screen.getByRole('button', { name: 'Generate AI insight' }));

    expect(await screen.findByText('AI-generated interpretation')).toBeInTheDocument();
    expect(screen.getByText(INSIGHT.generated_text)).toBeInTheDocument();
    expect(screen.getByText(/does not compute, verify, or add any numbers/)).toBeInTheDocument();
  });

  it('shows a loading state immediately after the button is clicked', () => {
    stubFetch({ createAIInsight: INSIGHT });
    render(<AIInsightPanel target={{ calculationId: 42 }} />);

    fireEvent.click(screen.getByRole('button', { name: 'Generate AI insight' }));

    // Asserted synchronously, right after the click and before the
    // mocked fetch promise has a chance to resolve - the loading state
    // can be gone by the time an async findBy* query starts polling.
    expect(screen.getByText('Generating insight…')).toBeInTheDocument();
  });

  it('sends the calculation_id in the request body for a calculation target', async () => {
    const fetchSpy = stubFetch({ createAIInsight: INSIGHT });
    render(<AIInsightPanel target={{ calculationId: 42 }} />);

    fireEvent.click(screen.getByRole('button', { name: 'Generate AI insight' }));
    await screen.findByText(INSIGHT.generated_text);

    const call = fetchSpy.mock.calls.find((c) => String(c[0]).endsWith('/ai-insights'));
    expect(call).toBeDefined();
    const body = JSON.parse(String(call?.[1]?.body)) as Record<string, unknown>;
    expect(body).toEqual({ calculation_id: 42 });
  });

  it('sends the comparison_id in the request body for a comparison target', async () => {
    const fetchSpy = stubFetch({
      createAIInsight: { ...INSIGHT, calculation_id: null, comparison_id: 7 },
    });
    render(<AIInsightPanel target={{ comparisonId: 7 }} />);

    fireEvent.click(screen.getByRole('button', { name: 'Generate AI insight' }));
    await screen.findByText(INSIGHT.generated_text);

    const call = fetchSpy.mock.calls.find((c) => String(c[0]).endsWith('/ai-insights'));
    const body = JSON.parse(String(call?.[1]?.body)) as Record<string, unknown>;
    expect(body).toEqual({ comparison_id: 7 });
  });

  it('shows a friendly error and a retry button when generation fails', async () => {
    stubFetch({
      createAIInsight: {
        status: 422,
        body: {
          error: {
            code: 'ai_insight_unavailable',
            message:
              'AI insight could not be generated for this item right now. Please try again later.',
            details: null,
          },
        },
      },
    });
    render(<AIInsightPanel target={{ calculationId: 42 }} />);

    fireEvent.click(screen.getByRole('button', { name: 'Generate AI insight' }));

    expect(
      await screen.findByText(/AI insight could not be generated for this item right now/),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('retrying after a failure calls the endpoint again and can succeed', async () => {
    let callCount = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn(() => {
        callCount += 1;
        if (callCount === 1) {
          return Promise.resolve({
            ok: false,
            status: 502,
            json: () =>
              Promise.resolve({
                error: {
                  code: 'ai_provider_unavailable',
                  message: 'The AI service is temporarily unavailable. Please try again later.',
                },
              }),
            headers: { get: () => null },
          });
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(INSIGHT),
          headers: { get: () => null },
        });
      }),
    );

    render(<AIInsightPanel target={{ calculationId: 42 }} />);
    fireEvent.click(screen.getByRole('button', { name: 'Generate AI insight' }));
    await screen.findByText(/temporarily unavailable/);

    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));

    await waitFor(() => {
      expect(screen.getByText(INSIGHT.generated_text)).toBeInTheDocument();
    });
    expect(callCount).toBe(2);
  });
});
