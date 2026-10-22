---
title: Testing React Components and Hooks
impact: HIGH
impactDescription: tests React UI through what the user sees and does, with React Testing Library, instead of through component internals
tags: react, react-testing-library, user-event, jest-dom, hooks, jsdom
---

## Testing React Components and Hooks

Read this when the stack has `react` in its dependencies (and so for every Next.js repo). It builds on the rest of `rules/lang/javascript/`.

**Test what the user sees and does, never how the component is built.** Find elements the way a user would (by role, label or text), interact through real events, and assert on what changes on screen or on the callbacks and requests that leave the component. Don't assert on state variables, hook call counts or child component props. Those tests break on every refactor and pass through real bugs, which is the opposite of `test-behaviors-not-methods.md`.

### 1. Tooling — Use What's Installed

| Package | Role | If missing |
|---|---|---|
| `@testing-library/react` (RTL) | `render`, `screen`, `renderHook` | Component tests aren't possible. Skip components with a `skipped_reason`; test pure logic only |
| `@testing-library/user-event` | Realistic interactions | Fall back to `fireEvent` from RTL, and note it |
| `@testing-library/jest-dom` | `toBeInTheDocument`, `toHaveTextContent`, `toBeDisabled`, … | Use plain matchers on DOM properties |
| `jest-environment-jsdom` / `jsdom` / `happy-dom` | A DOM to render into | Component tests aren't possible. Skip with a reason naming the package |

Enzyme and `react-test-renderer` are dead with React 18/19. Never introduce them, and never use shallow rendering.

The test file needs a DOM environment. If the config's default is `node` (common in Next.js and full-stack repos), add a docblock at the top of the component test file rather than changing config:

```ts
/** @jest-environment jsdom */          // Jest
// @vitest-environment jsdom             // Vitest (first line of the file)
```

### 2. Queries — in This Order of Preference

1. `getByRole('button', { name: /place order/i })`: what assistive technology sees. Use it for almost everything.
2. `getByLabelText('Email')`: form fields.
3. `getByPlaceholderText`, `getByText`, `getByDisplayValue`: when there's no role or label.
4. `getByAltText`, `getByTitle`.
5. `getByTestId`: last resort, and only if the component already has `data-testid`. Never add one, because that means editing production code.

Pick the variant by what you expect:

| Variant | Use for |
|---|---|
| `getBy*` | The element is there now (throws if absent) |
| `queryBy*` | Asserting the element is **not** there: `expect(screen.queryByRole('alert')).not.toBeInTheDocument()` |
| `findBy*` | The element appears after something async (returns a promise; await it) |

Always query through `screen`. Never use `container.querySelector('.btn-primary')`, because class names and DOM structure are implementation details.

### 3. Interactions: `user-event`

```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { OrderForm } from '@/components/OrderForm';

it('OrderForm_validSubmission_callsOnSubmitWithEnteredQuantity', async () => {
  // Given
  const user = userEvent.setup();
  const onSubmit = jest.fn();
  render(<OrderForm sku="A-100" onSubmit={onSubmit} />);

  // When
  await user.clear(screen.getByLabelText('Quantity'));
  await user.type(screen.getByLabelText('Quantity'), '3');
  await user.click(screen.getByRole('button', { name: /place order/i }));

  // Then
  expect(onSubmit).toHaveBeenCalledWith({ sku: 'A-100', quantity: 3 });
});
```

- Call `userEvent.setup()` once per test **before** `render`, and **await every interaction**. user-event v14 is fully async, and an un-awaited `click` asserts before the event has happened.
- With fake timers, wire them together, or interactions hang: `userEvent.setup({ advanceTimers: jest.advanceTimersByTime })` (Vitest: `vi.advanceTimersByTime`).
- If `user-event` isn't installed, use `fireEvent.click(...)`. It dispatches a single DOM event without the focus/keyboard sequence, so typing tests are less realistic. Say so in the notes.

### 4. Async UI: `findBy*` and `waitFor`

```tsx
it('OrderStatus_loaded_showsConfirmedBadge', async () => {
  mockedFetchOrder.mockResolvedValue(buildOrder({ status: 'CONFIRMED' }));

  render(<OrderStatus orderId="ord-1" />);

  expect(await screen.findByText('Confirmed')).toBeInTheDocument();
});
```

- `findBy*` is `waitFor` + `getBy*`. Prefer it for "something appears".
- `waitFor` is for an assertion that becomes true, such as a mock being called. Keep exactly one assertion inside it, and no side effects (no clicks). It re-runs the callback many times.
- An "update was not wrapped in act(...)" warning means the test finished while the component was still updating. Await the UI change that causes it (`findBy*`). Don't wrap things in `act` by hand. RTL already does that for `render` and user-event.

### 5. Hooks: `renderHook`

Test a custom hook through a component that uses it when one exists. For a reusable hook, use `renderHook` from `@testing-library/react` (the old `@testing-library/react-hooks` package is obsolete since React 18):

```ts
import { renderHook, act } from '@testing-library/react';

it('useCart_addItem_increasesTotal', () => {
  const { result } = renderHook(() => useCart());

  act(() => {
    result.current.addItem({ sku: 'A', unitPriceCents: 500, quantity: 2 });
  });

  expect(result.current.totalCents).toBe(1000);
});
```

Here, calling a hook's function directly is the one place explicit `act` is correct. Read `result.current` **after** the act, never a destructured value captured before it.

### 6. Providers: Context, Router, Data Fetching, State

Components that read context crash without their providers. Render inside the **real** providers, configured for the test, and put them in one custom `render` helper (or reuse the repo's existing `test-utils` render):

```tsx
// test-utils/render.tsx
import type { ReactElement } from 'react';
import { render, type RenderOptions } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

export function renderWithProviders(
  ui: ReactElement,
  { route = '/', ...options }: { route?: string } & RenderOptions = {},
) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
    options,
  );
}
```

- **React Query / SWR:** a new client per test with `retry: false`. A shared client leaks cached data between tests, and retries turn an error-path test into a timeout. For SWR, wrap in `<SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>`.
- **React Router:** `MemoryRouter` with `initialEntries`. Assert on navigation by what renders at the new route, or by `useNavigate` being called if it's mocked.
- **Redux:** a real store from the app's own `configureStore` and reducers, with `preloadedState`. Never mock `useSelector`/`useDispatch`.
- **Theme, i18n and auth providers:** use the real provider with test values. Mock an auth SDK only at its network/client boundary.

### 7. What to Mock in Components

- **Do mock:** the data layer at its module boundary (the API client, or `fetch`/MSW, per `mocking-js-ts.md`), and the browser APIs jsdom lacks (`window.matchMedia`, `IntersectionObserver`, `ResizeObserver`), which belong in the existing setup file or a helper.
- **Don't mock:** child components (render the real tree; mock a child only when it's heavy *and* irrelevant to this behaviour, such as a chart or map widget), React itself, or the component's own hooks.
- **Callbacks passed as props** are plain `jest.fn()`/`vi.fn()`, and asserting on them is a legitimate behavioural check.

### 8. Accessibility Comes Free

`getByRole` with `{ name }` fails when a button has no accessible name or an input has no label. When a query only works by text or test-id because the element has no accessible name, write the test with the query that works and note the gap. Don't edit the component.

### Checklist

- [ ] RTL with a DOM environment (docblock if the default is `node`); no Enzyme, no shallow rendering
- [ ] Queries by role/label/text through `screen`; `queryBy*` for absence, `findBy*` for async
- [ ] `userEvent.setup()` before render; every interaction awaited; fake timers wired in if used
- [ ] No assertions on state, props of children, or hook internals
- [ ] Providers are real and per-test (new QueryClient, `retry: false`; MemoryRouter; real Redux store)
- [ ] Data layer mocked at its module/network boundary; child components rendered for real
- [ ] No `data-testid` or other change added to production components
