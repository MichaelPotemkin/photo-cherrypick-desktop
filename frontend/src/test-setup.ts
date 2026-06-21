// Vitest setup for component tests: registers @testing-library/jest-dom matchers (toBeInTheDocument,
// toBeDisabled, …) and auto-cleans the rendered DOM between tests.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(cleanup);
