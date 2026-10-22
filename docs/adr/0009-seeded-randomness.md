# ADR-0009: Zero Unseeded Randomness in Cartographic Pipeline

- **Status:** Accepted
- **Context:** Label placement and tie-breaking must be 100% repeatable.
- **Decision:** Any stochastic algorithm requires an explicit integer seed (default `0`) recorded in the render specification; all feature collections use deterministic multi-key sorting.
